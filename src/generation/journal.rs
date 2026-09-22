//! Bounded, exclusive, append-only generation journal. Prompts and answers are
//! deliberately excluded. A failed sync poisons the writer until offline repair.
use super::{Config, Failure, Receipt, fail};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
#[cfg(unix)]
use std::os::unix::fs::OpenOptionsExt;
use std::{
    collections::BTreeMap,
    fs::{File, OpenOptions},
    io::{self, Read, Write},
};
const MAX_FILE: u64 = 16 * 1024 * 1024;
const MAX_LINE: usize = 65_536;
const RECEIPT_RESERVE: u64 = 4096;
#[derive(Serialize, Deserialize)]
#[serde(tag = "event", rename_all = "snake_case", deny_unknown_fields)]
enum Event {
    Header {
        version: u32,
        scope: String,
    },
    Begin {
        id: u64,
        route: String,
        model: String,
    },
    Complete {
        receipt: Box<Receipt>,
    },
}
#[derive(Default)]
struct Accounting {
    begun: u64,
    completed: u64,
    prompt_tokens: u64,
    completion_tokens: u64,
    pending: BTreeMap<u64, (String, String)>,
    last_receipt: Option<Receipt>,
}
fn invalid() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "invalid generation journal")
}
fn encode(event: &Event) -> io::Result<Vec<u8>> {
    let mut line = serde_json::to_vec(event).map_err(|_| invalid())?;
    line.push(b'\n');
    if line.len() > MAX_LINE {
        return Err(invalid());
    }
    Ok(line)
}
impl Accounting {
    fn receipt_totals(&self, r: &Receipt) -> io::Result<(u64, u64)> {
        if !r.valid()
            || self.pending.get(&r.attempt_id)
                != Some(&(r.route.clone(), r.requested_model.clone()))
        {
            return Err(invalid());
        }
        Ok((
            self.prompt_tokens
                .checked_add(r.usage.prompt_tokens)
                .ok_or_else(invalid)?,
            self.completion_tokens
                .checked_add(r.usage.completion_tokens)
                .ok_or_else(invalid)?,
        ))
    }
    fn complete(&mut self, r: Receipt) -> io::Result<()> {
        let (prompt, completion) = self.receipt_totals(&r)?;
        self.pending.remove(&r.attempt_id);
        self.completed += 1;
        self.prompt_tokens = prompt;
        self.completion_tokens = completion;
        self.last_receipt = Some(r);
        Ok(())
    }
}
pub(super) struct Journal {
    file: File,
    config: Config,
    bytes: u64,
    healthy: bool,
    accounting: Accounting,
}
impl Journal {
    pub fn initialize(config: &Config) -> io::Result<()> {
        let scope = config.scope().map_err(|_| invalid())?;
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        options.mode(0o600);
        let mut file = options.open(&config.journal_path)?;
        file.try_lock().map_err(|_| invalid())?;
        file.write_all(&encode(&Event::Header { version: 1, scope })?)?;
        file.sync_all()?;
        File::open(config.journal_path.parent().ok_or_else(invalid)?)?.sync_all()
    }
    pub fn open(config: &Config) -> io::Result<Self> {
        let scope = config.scope().map_err(|_| invalid())?;
        if config
            .journal_path
            .symlink_metadata()?
            .file_type()
            .is_symlink()
        {
            return Err(invalid());
        }
        let mut file = OpenOptions::new()
            .read(true)
            .append(true)
            .open(&config.journal_path)?;
        file.try_lock().map_err(|_| invalid())?;
        let metadata = file.metadata()?;
        if !metadata.is_file() || metadata.len() > MAX_FILE || metadata.len() == 0 {
            return Err(invalid());
        }
        let mut data = String::new();
        (&mut file).take(MAX_FILE + 1).read_to_string(&mut data)?;
        if data.len() as u64 > MAX_FILE || !data.ends_with('\n') {
            return Err(invalid());
        }
        let mut accounting = Accounting::default();
        for (n, line) in data.lines().enumerate() {
            if line.len() > MAX_LINE {
                return Err(invalid());
            }
            let event: Event = serde_json::from_str(line).map_err(|_| invalid())?;
            match event {
                Event::Header {
                    version: 1,
                    scope: stored,
                } if n == 0 && stored == scope => {}
                Event::Begin { id, route, model } if n > 0 => {
                    if id != accounting.begun + 1
                        || id > config.max_calls
                        || accounting.pending.len() >= config.admission_limit
                        || !config.routes.get(&route).is_some_and(|r| r.model == model)
                    {
                        return Err(invalid());
                    }
                    accounting.begun = id;
                    accounting.pending.insert(id, (route, model));
                }
                Event::Complete { receipt } if n > 0 && receipt.backend == config.backend => {
                    accounting.complete(*receipt)?
                }
                _ => return Err(invalid()),
            }
        }
        Ok(Self {
            file,
            config: config.clone(),
            bytes: data.len() as u64,
            healthy: true,
            accounting,
        })
    }
    fn append(&mut self, event: &Event) -> Result<(), Failure> {
        if !self.healthy {
            return Err(fail(503, "journal_unavailable"));
        }
        let bytes = encode(event).map_err(|_| fail(503, "journal_unavailable"))?;
        if self.bytes + bytes.len() as u64 > MAX_FILE {
            return Err(fail(503, "journal_full"));
        }
        if self
            .file
            .write_all(&bytes)
            .and_then(|_| self.file.sync_all())
            .is_err()
        {
            self.healthy = false;
            return Err(fail(503, "journal_unavailable"));
        }
        self.bytes += bytes.len() as u64;
        Ok(())
    }
    pub fn begin(&mut self, route: String, model: String) -> Result<u64, Failure> {
        if !self.healthy {
            return Err(fail(503, "journal_unavailable"));
        }
        if self.accounting.pending.len() >= self.config.admission_limit {
            return Err(fail(503, "generation_admission_full"));
        }
        if self.accounting.begun >= self.config.max_calls {
            return Err(fail(503, "generation_call_budget_exhausted"));
        }
        // Reserve space for a receipt for every outstanding reservation.
        if self.bytes
            + MAX_LINE as u64
            + (self.accounting.pending.len() as u64 + 1) * RECEIPT_RESERVE
            > MAX_FILE
        {
            return Err(fail(503, "journal_full"));
        }
        let id = self.accounting.begun + 1;
        self.append(&Event::Begin {
            id,
            route: route.clone(),
            model: model.clone(),
        })?;
        self.accounting.begun = id;
        self.accounting.pending.insert(id, (route, model));
        Ok(id)
    }
    pub fn complete(&mut self, receipt: Receipt) -> Result<(), Failure> {
        if receipt.backend != self.config.backend {
            return Err(fail(503, "journal_backend_mismatch"));
        }
        self.accounting
            .receipt_totals(&receipt)
            .map_err(|_| fail(503, "journal_unavailable"))?;
        let event = Event::Complete {
            receipt: Box::new(receipt.clone()),
        };
        if encode(&event)
            .map_err(|_| fail(503, "journal_unavailable"))?
            .len() as u64
            > RECEIPT_RESERVE
        {
            return Err(fail(503, "journal_unavailable"));
        }
        self.append(&event)?;
        self.accounting
            .complete(receipt)
            .map_err(|_| fail(503, "journal_unavailable"))
    }
    pub fn status(&self) -> Value {
        let room = self.bytes
            + MAX_LINE as u64
            + (self.accounting.pending.len() as u64 + 1) * RECEIPT_RESERVE
            <= MAX_FILE;
        json!({"ready":self.healthy && room && self.accounting.begun<self.config.max_calls && self.accounting.pending.len()<self.config.admission_limit,
            "upstream_health":"unchecked","healthy":self.healthy,"calls_reserved":self.accounting.begun,"completed":self.accounting.completed,
            "pending":self.accounting.pending.len(),"pending_attempts":self.accounting.pending.iter().map(|(id,(route,model))|json!({"attempt_id":id,"route":route,"requested_model":model})).collect::<Vec<_>>(),
            "prompt_tokens_observed":self.accounting.prompt_tokens,"completion_tokens_observed":self.accounting.completion_tokens,
            "last_receipt":self.accounting.last_receipt,"cost_scope":"reported per receipt; unresolved calls may still incur cost"})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn write_failure_poisoning_retains_pending_work() {
        let path =
            std::env::temp_dir().join(format!("braess-or-io-failure-{}.jsonl", std::process::id()));
        let config = Config {
            backend: crate::generation::Backend::Openrouter,
            bind: "127.0.0.1:9876".parse().unwrap(),
            mode: super::super::Mode::Mock,
            url: "http://127.0.0.1:9877/x".into(),
            journal_path: path.clone(),
            deadline_ms: 1000,
            max_request_bytes: 1024,
            max_response_bytes: 4096,
            admission_limit: 1,
            max_calls: 2,
            vision_bundles: BTreeMap::new(),
            routes: BTreeMap::from([(
                "general".into(),
                super::super::Route {
                    model: "fixture/general".into(),
                    provider: "fixture".into(),
                    reasoning: None,
                    output_format: None,
                    max_tokens: 8,
                    input_mode: super::super::InputMode::Text,
                },
            )]),
        };
        Journal::initialize(&config).unwrap();
        let mut journal = Journal::open(&config).unwrap();
        journal
            .begin("general".into(), "fixture/general".into())
            .unwrap();
        journal.file = File::open(&path).unwrap(); // Inject a write failure with a read-only descriptor.
        let receipt = Receipt {
            backend: crate::generation::Backend::Openrouter,
            reported_cost_jpy: None,
            reasoning_tokens: None,
            attempt_id: 1,
            route: "general".into(),
            requested_model: "fixture/general".into(),
            model: "fixture/general".into(),
            provider: None,
            generation_id: "gen-fixture".into(),
            finish_reason: "stop".into(),
            input_evidence: None,
            usage: super::super::Usage {
                prompt_tokens: 1,
                completion_tokens: 1,
                total_tokens: 2,
                cost: None,
            },
        };
        assert!(journal.complete(receipt).is_err());
        assert_eq!(journal.status()["healthy"], false);
        assert_eq!(journal.status()["pending"], 1);
        drop(journal);
        let recovered = Journal::open(&config).unwrap();
        assert_eq!(recovered.status()["pending"], 1);
        drop(recovered);
        std::fs::remove_file(path).unwrap();
    }
}
