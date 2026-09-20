//! Single-host unfinished-attempt journal. Successful begin is durable before
//! dispatch; only validated response completion may append a terminal record.
//! Filesystem sync is requested, but these tests do not prove power-loss safety.
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs::{File, OpenOptions},
    io::{self, BufRead, BufReader, Read, Write},
    path::Path,
    sync::{
        Mutex,
        atomic::{AtomicBool, Ordering},
    },
};

const MAX_FILE: u64 = 64 * 1024 * 1024;
// Covers the complete-event JSON encoding with a maximum-width u64 identity.
const TERMINAL_RESERVE: u64 = 64;
const MAX_SCOPE: usize = 65_536;
const MAX_ENDPOINT: usize = 4096;
const MAX_PENDING: usize = 65_536;
const SNAPSHOT_RECORDS: usize = 128;
// JSON can escape each byte into six characters. Header is the largest line.
const MAX_LINE: usize = MAX_SCOPE * 6 + 1024;

#[derive(Serialize, Deserialize)]
#[serde(tag = "event", rename_all = "snake_case", deny_unknown_fields)]
enum Event {
    Header { version: u32, scope: String },
    Begin { id: u64, endpoint: String },
    Complete { id: u64 },
    Checkpoint { begun: u64, completed: u64 },
    Restore { id: u64, endpoint: String },
    CheckpointEnd,
}
#[derive(Default)]
struct Cache {
    unresolved: BTreeMap<u64, String>,
    by_endpoint: BTreeMap<String, usize>,
    begun: u64,
    completed: u64,
}
impl Cache {
    fn begin(&mut self, id: u64, endpoint: String) {
        *self.by_endpoint.entry(endpoint.clone()).or_default() += 1;
        self.unresolved.insert(id, endpoint);
        self.begun = id;
    }
    fn complete(&mut self, id: u64) -> io::Result<()> {
        let endpoint = self
            .unresolved
            .remove(&id)
            .ok_or_else(|| invalid("unknown or completed attempt"))?;
        let count = self
            .by_endpoint
            .get_mut(&endpoint)
            .expect("journal cache count");
        *count -= 1;
        if *count == 0 {
            self.by_endpoint.remove(&endpoint);
        }
        self.completed += 1;
        Ok(())
    }
}
struct Writer {
    // Kept even after I/O failure: failure must not release exclusive ownership.
    file: File,
    length: u64,
    last_id: u64,
}
pub struct DurableRequests {
    scope: String,
    writer: Mutex<Writer>,
    cache: Mutex<Cache>,
    healthy: AtomicBool,
    per_endpoint_limit: usize,
}
fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}
fn valid_scope(scope: &str) -> bool {
    !scope.is_empty() && scope.len() <= MAX_SCOPE
}
fn valid_endpoint(endpoint: &str) -> bool {
    !endpoint.is_empty() && endpoint.len() <= MAX_ENDPOINT
}
fn line(event: &Event) -> io::Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec(event).map_err(io::Error::other)?;
    bytes.push(b'\n');
    Ok(bytes)
}
impl DurableRequests {
    /// Creates new state only. Existing files, including damaged state, are never replaced.
    pub fn initialize(path: &Path, scope: &str) -> io::Result<()> {
        if !valid_scope(scope) {
            return Err(invalid("invalid request journal scope"));
        }
        let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
        file.try_lock()
            .map_err(|_| io::Error::other("request journal locked"))?;
        file.write_all(&line(&Event::Header {
            version: 1,
            scope: scope.into(),
        })?)?;
        file.sync_all()?;
        let parent = path
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        File::open(parent)?.sync_all()
    }
    /// Fails closed for torn, inconsistent, missing, mismatched, or owned state.
    pub fn open(path: &Path, scope: &str, per_endpoint_limit: usize) -> io::Result<Self> {
        if !valid_scope(scope) || !(1..=MAX_PENDING).contains(&per_endpoint_limit) {
            return Err(invalid("invalid request journal limits"));
        }
        let mut file = OpenOptions::new().read(true).append(true).open(path)?;
        file.try_lock()
            .map_err(|_| io::Error::other("request journal locked"))?;
        let metadata = file.metadata()?;
        if !metadata.is_file() || metadata.len() == 0 || metadata.len() > MAX_FILE {
            return Err(invalid("invalid request journal length"));
        }
        let mut cache = Cache::default();
        let mut total = 0u64;
        let mut checkpoint_allowed = true;
        let mut checkpoint_active = false;
        {
            let mut reader = BufReader::new(&mut file);
            loop {
                let mut bytes = Vec::new();
                let n = (&mut reader)
                    .take(MAX_LINE as u64 + 1)
                    .read_until(b'\n', &mut bytes)?;
                if n == 0 {
                    break;
                }
                total += n as u64;
                if n > MAX_LINE || total > MAX_FILE || bytes.last() != Some(&b'\n') {
                    return Err(invalid("oversized or torn request journal line"));
                }
                let event: Event = serde_json::from_slice(&bytes)
                    .map_err(|_| invalid("malformed request journal event"))?;
                if total == n as u64 {
                    match event {
                        Event::Header {
                            version: 1,
                            scope: stored,
                        } if stored == scope => {}
                        _ => return Err(invalid("request journal header mismatch")),
                    }
                    continue;
                }
                match event {
                    Event::Checkpoint { begun, completed } if checkpoint_allowed => {
                        if completed > begun {
                            return Err(invalid("invalid checkpoint totals"));
                        }
                        cache.begun = begun;
                        cache.completed = completed;
                        checkpoint_allowed = false;
                        checkpoint_active = true;
                    }
                    Event::Restore { id, endpoint } if checkpoint_active => {
                        if id == 0
                            || id > cache.begun
                            || cache.unresolved.contains_key(&id)
                            || !valid_endpoint(&endpoint)
                            || cache.unresolved.len() >= MAX_PENDING
                            || cache.by_endpoint.get(&endpoint).copied().unwrap_or(0)
                                >= per_endpoint_limit
                        {
                            return Err(invalid("invalid checkpoint restore"));
                        }
                        *cache.by_endpoint.entry(endpoint.clone()).or_default() += 1;
                        cache.unresolved.insert(id, endpoint);
                    }
                    Event::CheckpointEnd if checkpoint_active => {
                        if cache.completed.checked_add(cache.unresolved.len() as u64)
                            != Some(cache.begun)
                        {
                            return Err(invalid("checkpoint totals do not conserve requests"));
                        }
                        checkpoint_active = false;
                    }
                    Event::Begin { id, endpoint } if !checkpoint_active => {
                        checkpoint_allowed = false;
                        if !valid_endpoint(&endpoint)
                            || cache.begun.checked_add(1) != Some(id)
                            || cache.unresolved.len() >= MAX_PENDING
                            || cache.by_endpoint.get(&endpoint).copied().unwrap_or(0)
                                >= per_endpoint_limit
                        {
                            return Err(invalid("invalid request journal begin"));
                        }
                        cache.begin(id, endpoint);
                    }
                    Event::Complete { id } if !checkpoint_active => {
                        checkpoint_allowed = false;
                        cache.complete(id)?;
                    }
                    _ => return Err(invalid("invalid request journal event order")),
                }
            }
        }
        if checkpoint_active {
            return Err(invalid("incomplete request journal checkpoint"));
        }
        if total != metadata.len() {
            return Err(invalid("request journal changed during replay"));
        }
        if total + cache.unresolved.len() as u64 * TERMINAL_RESERVE > MAX_FILE {
            return Err(invalid("request journal lacks terminal headroom"));
        }
        Ok(Self {
            scope: scope.into(),
            writer: Mutex::new(Writer {
                file,
                length: total,
                last_id: cache.begun,
            }),
            cache: Mutex::new(cache),
            healthy: AtomicBool::new(true),
            per_endpoint_limit,
        })
    }
    /// Writes a new bounded checkpoint without replacing or mutating source state.
    /// Caller owns offline replacement policy; any failed export leaves its target
    /// for inspection and must not be published. Cache locks never span disk I/O.
    pub fn checkpoint_to(&self, destination: &Path, scope: &str) -> io::Result<()> {
        let _writer = self
            .writer
            .lock()
            .map_err(|_| io::Error::other("request journal writer poisoned"))?;
        self.check_healthy()?;
        if scope != self.scope {
            return Err(invalid("request journal checkpoint scope mismatch"));
        }
        let (begun, completed, pending) = {
            let cache = self
                .cache
                .lock()
                .map_err(|_| io::Error::other("request journal cache poisoned"))?;
            (cache.begun, cache.completed, cache.unresolved.len())
        };
        if completed.checked_add(pending as u64) != Some(begun) {
            return Err(invalid("checkpoint source totals do not conserve requests"));
        }
        let mut target = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(destination)?;
        target
            .try_lock()
            .map_err(|_| io::Error::other("checkpoint target locked"))?;
        let mut length = 0u64;
        let mut emit = |event: Event| -> io::Result<()> {
            let bytes = line(&event)?;
            let next = length
                .checked_add(bytes.len() as u64)
                .ok_or_else(|| invalid("checkpoint length overflow"))?;
            if next + pending as u64 * TERMINAL_RESERVE > MAX_FILE {
                return Err(invalid("checkpoint exceeds terminal headroom"));
            }
            target.write_all(&bytes)?;
            length = next;
            Ok(())
        };
        emit(Event::Header {
            version: 1,
            scope: scope.into(),
        })?;
        emit(Event::Checkpoint { begun, completed })?;
        let mut last = 0u64;
        loop {
            let next = {
                let cache = self
                    .cache
                    .lock()
                    .map_err(|_| io::Error::other("request journal cache poisoned"))?;
                cache
                    .unresolved
                    .range((std::ops::Bound::Excluded(last), std::ops::Bound::Unbounded))
                    .next()
                    .map(|(&id, endpoint)| (id, endpoint.clone()))
            };
            let Some((id, endpoint)) = next else { break };
            emit(Event::Restore { id, endpoint })?;
            last = id;
        }
        emit(Event::CheckpointEnd)?;
        target.sync_all()?;
        let parent = destination
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        File::open(parent)?.sync_all()
    }
    fn check_healthy(&self) -> io::Result<()> {
        if !self.healthy.load(Ordering::Acquire) {
            return Err(io::Error::other("request journal poisoned"));
        }
        Ok(())
    }
    fn append(&self, writer: &mut Writer, event: &Event) -> io::Result<()> {
        self.append_with(writer, event, |file, bytes| {
            file.write_all(bytes)?;
            file.sync_all()
        })
    }
    fn append_with(
        &self,
        writer: &mut Writer,
        event: &Event,
        persist: impl FnOnce(&mut File, &[u8]) -> io::Result<()>,
    ) -> io::Result<()> {
        let bytes = line(event)?;
        let next_length = writer
            .length
            .checked_add(bytes.len() as u64)
            .filter(|n| *n <= MAX_FILE)
            .ok_or_else(|| io::Error::other("request journal file limit reached"))?;
        if let Err(error) = persist(&mut writer.file, &bytes) {
            self.healthy.store(false, Ordering::Release);
            return Err(error);
        }
        writer.length = next_length;
        Ok(())
    }
    /// Call on a bounded storage worker. Only dispatch after this returns Ok.
    pub fn begin(&self, endpoint: &str) -> io::Result<u64> {
        if !valid_endpoint(endpoint) {
            return Err(invalid("invalid journal endpoint"));
        }
        let mut writer = self
            .writer
            .lock()
            .map_err(|_| io::Error::other("request journal writer poisoned"))?;
        self.check_healthy()?;
        let pending = {
            let cache = self
                .cache
                .lock()
                .map_err(|_| io::Error::other("request journal cache poisoned"))?;
            if cache.unresolved.len() >= MAX_PENDING
                || cache.by_endpoint.get(endpoint).copied().unwrap_or(0) >= self.per_endpoint_limit
            {
                return Err(io::Error::other("request journal pending limit reached"));
            }
            cache.unresolved.len()
        };
        let id = writer
            .last_id
            .checked_add(1)
            .ok_or_else(|| io::Error::other("request journal identity exhausted"))?;
        let event = Event::Begin {
            id,
            endpoint: endpoint.into(),
        };
        // Existing completions must remain writable even when new admission is
        // refused at the file limit. Reserve a terminal for this begin as well.
        let required =
            writer.length + line(&event)?.len() as u64 + (pending as u64 + 1) * TERMINAL_RESERVE;
        if required > MAX_FILE {
            return Err(io::Error::other(
                "request journal terminal headroom exhausted",
            ));
        }
        self.append(&mut writer, &event)?;
        writer.last_id = id;
        self.cache
            .lock()
            .map_err(|_| io::Error::other("request journal cache poisoned"))?
            .begin(id, endpoint.into());
        Ok(id)
    }
    /// Only after the full response is validated. No TTL or cancellation completion.
    pub fn complete(&self, id: u64) -> io::Result<()> {
        let mut writer = self
            .writer
            .lock()
            .map_err(|_| io::Error::other("request journal writer poisoned"))?;
        self.check_healthy()?;
        if !self
            .cache
            .lock()
            .map_err(|_| io::Error::other("request journal cache poisoned"))?
            .unresolved
            .contains_key(&id)
        {
            return Err(invalid("unknown or completed attempt"));
        }
        self.append(&mut writer, &Event::Complete { id })?;
        self.cache
            .lock()
            .map_err(|_| io::Error::other("request journal cache poisoned"))?
            .complete(id)
    }
    /// Cache-only; never waits for disk I/O. usize::MAX fails closed on cache poison.
    pub fn pending(&self, endpoint: &str) -> usize {
        self.cache
            .lock()
            .map(|c| c.by_endpoint.get(endpoint).copied().unwrap_or(0))
            .unwrap_or(usize::MAX)
    }
    /// Cache-only bounded summary. Snapshot may lag a concurrently syncing append.
    pub fn snapshot(&self) -> Value {
        let Ok(cache) = self.cache.lock() else {
            return json!({"healthy":false,"error":"cache_poisoned"});
        };
        let unresolved: Vec<_> = cache
            .unresolved
            .iter()
            .take(SNAPSHOT_RECORDS)
            .map(|(id, endpoint)| json!({"id":id,"endpoint":endpoint}))
            .collect();
        let endpoints: BTreeMap<_, _> = cache.by_endpoint.iter().take(SNAPSHOT_RECORDS).collect();
        json!({"healthy":self.healthy.load(Ordering::Acquire) && !self.writer.is_poisoned(),"begun":cache.begun,"completed":cache.completed,"pending":cache.unresolved.len(),"per_endpoint_limit":self.per_endpoint_limit,"endpoints":endpoints,"endpoints_truncated":cache.by_endpoint.len()>SNAPSHOT_RECORDS,"unresolved":unresolved,"unresolved_truncated":cache.unresolved.len()>SNAPSHOT_RECORDS})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        path::PathBuf,
        sync::{
            Arc,
            atomic::{AtomicU64, Ordering},
        },
    };
    static SEQUENCE: AtomicU64 = AtomicU64::new(0);
    struct Temp(PathBuf);
    impl Temp {
        fn new() -> Self {
            Self(std::env::temp_dir().join(format!(
                "jev-requests-{}-{}",
                std::process::id(),
                SEQUENCE.fetch_add(1, Ordering::Relaxed)
            )))
        }
    }
    impl Drop for Temp {
        fn drop(&mut self) {
            let _ = std::fs::remove_file(&self.0);
        }
    }
    #[test]
    fn reopen_preserves_unfinished_and_monotonic_identity() {
        let path = Temp::new();
        DurableRequests::initialize(&path.0, "scope").unwrap();
        assert!(DurableRequests::initialize(&path.0, "scope").is_err());
        let journal = DurableRequests::open(&path.0, "scope", 2).unwrap();
        let a = journal.begin("a").unwrap();
        let b = journal.begin("a").unwrap();
        journal.complete(a).unwrap();
        assert!(journal.complete(a).is_err());
        assert!(journal.complete(999).is_err());
        drop(journal);
        let journal = DurableRequests::open(&path.0, "scope", 2).unwrap();
        assert_eq!(journal.pending("a"), 1);
        let c = journal.begin("a").unwrap();
        assert_eq!((a, b, c), (1, 2, 3));
        assert!(journal.begin("a").is_err());
        assert_eq!(
            journal.snapshot()["unresolved"],
            json!([{"id":2,"endpoint":"a"},{"id":3,"endpoint":"a"}])
        );
        journal.complete(b).unwrap();
        journal.complete(c).unwrap();
        drop(journal);
        let journal = DurableRequests::open(&path.0, "scope", 2).unwrap();
        assert_eq!(journal.pending("a"), 0);
        assert_eq!(journal.begin("b").unwrap(), 4);
    }
    #[test]
    fn exclusive_owner_and_scope_are_enforced() {
        let path = Temp::new();
        assert!(DurableRequests::open(&path.0, "scope", 1).is_err());
        DurableRequests::initialize(&path.0, "scope").unwrap();
        let journal = DurableRequests::open(&path.0, "scope", 1).unwrap();
        assert!(DurableRequests::open(&path.0, "scope", 1).is_err());
        drop(journal);
        assert!(DurableRequests::open(&path.0, "other", 1).is_err());
        assert!(DurableRequests::open(&path.0, "scope", 0).is_err());
    }
    #[test]
    fn malformed_torn_and_inconsistent_events_refuse_replay() {
        for suffix in [
            "{",
            "\n",
            "{}\n",
            "{\"event\":\"complete\",\"id\":1}\n",
            "{\"event\":\"begin\",\"id\":2,\"endpoint\":\"a\"}\n",
            "{\"event\":\"begin\",\"id\":1,\"endpoint\":\"a\",\"extra\":true}\n",
        ] {
            let path = Temp::new();
            DurableRequests::initialize(&path.0, "scope").unwrap();
            OpenOptions::new()
                .append(true)
                .open(&path.0)
                .unwrap()
                .write_all(suffix.as_bytes())
                .unwrap();
            assert!(
                DurableRequests::open(&path.0, "scope", 2).is_err(),
                "{suffix}"
            );
        }
    }
    #[test]
    fn concurrent_begins_obey_cap_and_cache_reads_do_not_wait_on_writer() {
        let path = Temp::new();
        DurableRequests::initialize(&path.0, "scope").unwrap();
        let journal = Arc::new(DurableRequests::open(&path.0, "scope", 4).unwrap());
        let workers: Vec<_> = (0..16)
            .map(|_| {
                let j = journal.clone();
                std::thread::spawn(move || j.begin("a").is_ok())
            })
            .collect();
        assert_eq!(
            workers
                .into_iter()
                .filter_map(|w| w.join().ok())
                .filter(|b| *b)
                .count(),
            4
        );
        let _writer = journal.writer.lock().unwrap();
        assert_eq!(journal.pending("a"), 4);
        assert_eq!(journal.snapshot()["healthy"], true);
    }
    #[test]
    fn snapshots_bound_detail_without_losing_pending_totals() {
        let path = Temp::new();
        DurableRequests::initialize(&path.0, "scope").unwrap();
        let journal = DurableRequests::open(&path.0, "scope", 2).unwrap();
        // Exercise snapshot limits independently from storage speed.
        for id in 1..=130 {
            journal
                .cache
                .lock()
                .unwrap()
                .begin(id, format!("endpoint-{id}"));
        }
        let snapshot = journal.snapshot();
        assert_eq!(snapshot["pending"], 130);
        assert_eq!(snapshot["unresolved"].as_array().unwrap().len(), 128);
        assert_eq!(snapshot["endpoints"].as_object().unwrap().len(), 128);
        assert_eq!(snapshot["unresolved_truncated"], true);
        assert_eq!(snapshot["endpoints_truncated"], true);
        assert_eq!(journal.pending("endpoint-130"), 1);
    }
    #[test]
    fn checkpoint_preserves_sparse_pending_totals_and_next_identity() {
        let source = Temp::new();
        let target = Temp::new();
        DurableRequests::initialize(&source.0, "scope").unwrap();
        let journal = DurableRequests::open(&source.0, "scope", 8).unwrap();
        let ids: Vec<_> = (0..6)
            .map(|n| journal.begin(if n % 2 == 0 { "a" } else { "b" }).unwrap())
            .collect();
        for id in [ids[0], ids[2], ids[3], ids[5]] {
            journal.complete(id).unwrap();
        }
        let source_bytes = std::fs::read(&source.0).unwrap();
        let source_snapshot = journal.snapshot();
        journal.checkpoint_to(&target.0, "scope").unwrap();
        assert_eq!(std::fs::read(&source.0).unwrap(), source_bytes);
        assert_eq!(journal.snapshot(), source_snapshot);
        let replay = DurableRequests::open(&target.0, "scope", 8).unwrap();
        assert_eq!(replay.snapshot(), source_snapshot);
        assert_eq!(
            replay.snapshot()["unresolved"],
            json!([{"id":2,"endpoint":"b"},{"id":5,"endpoint":"a"}])
        );
        assert_eq!(replay.begin("c").unwrap(), 7);
        replay.complete(2).unwrap();
        drop(replay);
        let replay = DurableRequests::open(&target.0, "scope", 8).unwrap();
        assert_eq!(replay.snapshot()["begun"], 7);
        assert_eq!(replay.snapshot()["completed"], 5);
        assert_eq!(replay.pending("a"), 1);
        assert_eq!(replay.pending("b"), 0);
        assert_eq!(replay.pending("c"), 1);
    }
    #[test]
    fn checkpoint_exports_every_pending_record_beyond_status_detail_limit() {
        let source = Temp::new();
        let target = Temp::new();
        DurableRequests::initialize(&source.0, "scope").unwrap();
        let journal = DurableRequests::open(&source.0, "scope", 512).unwrap();
        for _ in 0..130 {
            let completed = journal.begin("a").unwrap();
            journal.complete(completed).unwrap();
            journal.begin("a").unwrap();
        }
        assert_eq!(journal.snapshot()["unresolved_truncated"], true);
        journal.checkpoint_to(&target.0, "scope").unwrap();
        let replay = DurableRequests::open(&target.0, "scope", 512).unwrap();
        assert_eq!(replay.pending("a"), 130);
        assert_eq!(replay.snapshot()["completed"], 130);
        assert_eq!(replay.begin("a").unwrap(), 261);
        // Last pending ID was omitted by the public status detail limit.
        replay.complete(260).unwrap();
        assert_eq!(replay.pending("a"), 130);
    }
    #[test]
    fn checkpoint_existing_target_and_wrong_scope_leave_source_unchanged() {
        let source = Temp::new();
        let target = Temp::new();
        let wrong = Temp::new();
        DurableRequests::initialize(&source.0, "scope").unwrap();
        let journal = DurableRequests::open(&source.0, "scope", 2).unwrap();
        journal.begin("a").unwrap();
        let before = std::fs::read(&source.0).unwrap();
        std::fs::write(&target.0, b"existing target").unwrap();
        assert!(journal.checkpoint_to(&target.0, "scope").is_err());
        assert!(journal.checkpoint_to(&wrong.0, "wrong").is_err());
        assert!(!wrong.0.exists());
        assert_eq!(std::fs::read(&source.0).unwrap(), before);
        assert_eq!(std::fs::read(&target.0).unwrap(), b"existing target");
        assert_eq!(journal.snapshot()["healthy"], true);
    }
    #[test]
    fn incomplete_and_invalid_checkpoint_sections_are_rejected() {
        let checkpoint = || Event::Checkpoint {
            begun: 2,
            completed: 1,
        };
        let restore = |id| Event::Restore {
            id,
            endpoint: "a".into(),
        };
        for events in [
            vec![checkpoint()],
            vec![checkpoint(), restore(1)],
            vec![checkpoint(), Event::CheckpointEnd],
            vec![checkpoint(), restore(0), Event::CheckpointEnd],
            vec![checkpoint(), restore(3), Event::CheckpointEnd],
            vec![checkpoint(), restore(1), restore(1), Event::CheckpointEnd],
            vec![restore(1)],
            vec![Event::CheckpointEnd],
            vec![
                Event::Begin {
                    id: 1,
                    endpoint: "a".into(),
                },
                checkpoint(),
            ],
            vec![
                checkpoint(),
                Event::Begin {
                    id: 3,
                    endpoint: "a".into(),
                },
            ],
            vec![
                checkpoint(),
                restore(1),
                Event::Complete { id: 1 },
                Event::CheckpointEnd,
            ],
            vec![checkpoint(), restore(1), Event::CheckpointEnd, checkpoint()],
            vec![checkpoint(), restore(1), Event::CheckpointEnd, restore(2)],
            vec![
                Event::Checkpoint {
                    begun: 1,
                    completed: 2,
                },
                Event::CheckpointEnd,
            ],
            vec![
                Event::Checkpoint {
                    begun: u64::MAX,
                    completed: u64::MAX,
                },
                restore(1),
                Event::CheckpointEnd,
            ],
            vec![
                Event::Checkpoint {
                    begun: 2,
                    completed: 0,
                },
                restore(1),
                restore(2),
                Event::CheckpointEnd,
            ],
        ] {
            let path = Temp::new();
            DurableRequests::initialize(&path.0, "scope").unwrap();
            let mut file = OpenOptions::new().append(true).open(&path.0).unwrap();
            for event in events {
                file.write_all(&line(&event).unwrap()).unwrap();
            }
            drop(file);
            assert!(DurableRequests::open(&path.0, "scope", 1).is_err());
        }
    }
    #[test]
    fn terminal_space_is_reserved_before_admitting_another_attempt() {
        assert!(line(&Event::Complete { id: u64::MAX }).unwrap().len() as u64 <= TERMINAL_RESERVE);
        let path = Temp::new();
        DurableRequests::initialize(&path.0, "scope").unwrap();
        let journal = DurableRequests::open(&path.0, "scope", 4).unwrap();
        let first = journal.begin("a").unwrap();
        let begin_size = line(&Event::Begin {
            id: first + 1,
            endpoint: "a".into(),
        })
        .unwrap()
        .len() as u64;
        // Model a nearly full journal without allocating a 64 MiB fixture.
        journal.writer.lock().unwrap().length = MAX_FILE - begin_size - 2 * TERMINAL_RESERVE;
        let second = journal.begin("a").unwrap();
        assert_eq!(
            journal.writer.lock().unwrap().length,
            MAX_FILE - 2 * TERMINAL_RESERVE
        );
        assert!(journal.begin("a").is_err());
        assert_eq!(journal.pending("a"), 2);
        journal.complete(first).unwrap();
        journal.complete(second).unwrap();
        assert_eq!(journal.pending("a"), 0);
        assert!(journal.writer.lock().unwrap().length <= MAX_FILE);
        assert_eq!(journal.snapshot()["healthy"], true);
    }
    #[test]
    fn failed_persistence_poison_preserves_lock_and_refuses_further_work() {
        let path = Temp::new();
        DurableRequests::initialize(&path.0, "scope").unwrap();
        let journal = DurableRequests::open(&path.0, "scope", 2).unwrap();
        let first = journal.begin("a").unwrap();
        let result = journal.append_with(
            &mut journal.writer.lock().unwrap(),
            &Event::Complete { id: first },
            |file, bytes| {
                // Inject a short, uncertain append followed by an I/O error.
                file.write_all(&bytes[..1])?;
                Err(io::Error::other("injected persistence error"))
            },
        );
        assert!(result.is_err());
        assert_eq!(journal.snapshot()["healthy"], false);
        assert_eq!(journal.pending("a"), 1);
        assert!(journal.begin("b").is_err());
        assert!(journal.complete(first).is_err());
        let blocked = DurableRequests::open(&path.0, "scope", 2).err().unwrap();
        assert_eq!(blocked.to_string(), "request journal locked");
        drop(journal);
        let damaged = DurableRequests::open(&path.0, "scope", 2).err().unwrap();
        assert_eq!(
            damaged.to_string(),
            "oversized or torn request journal line"
        );
    }
    #[test]
    fn size_and_input_limits_refuse_growth() {
        let path = Temp::new();
        DurableRequests::initialize(&path.0, "scope").unwrap();
        let journal = DurableRequests::open(&path.0, "scope", 2).unwrap();
        assert!(journal.begin("").is_err());
        assert!(journal.begin(&"x".repeat(MAX_ENDPOINT + 1)).is_err());
        journal.writer.lock().unwrap().length = MAX_FILE;
        assert!(journal.begin("a").is_err());
        assert_eq!(journal.pending("a"), 0);
        drop(journal);
        let file = OpenOptions::new().write(true).open(&path.0).unwrap();
        file.set_len(MAX_FILE + 1).unwrap();
        assert!(DurableRequests::open(&path.0, "scope", 2).is_err());
    }
}
