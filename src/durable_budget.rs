//! Single-host, exclusively owned lifetime call budget. Reserve durably before
//! dispatch; never refund a reservation, even after cancellation or a crash.
use std::{
    fs::{File, OpenOptions},
    io::{self, Read, Write},
    path::Path,
    sync::{
        Mutex,
        atomic::{AtomicBool, AtomicU64, Ordering},
    },
};

const MAGIC: &[u8; 8] = b"JEVBUD01";
pub struct DurableBudget {
    file: Mutex<BudgetFile>,
    used: AtomicU64,
    limit: u64,
    healthy: AtomicBool,
}
struct BudgetFile {
    file: File,
    disabled: bool,
}
impl DurableBudget {
    /// Explicit initialization only. Existing state is never overwritten.
    pub fn initialize(path: &Path, limit: u64) -> io::Result<()> {
        if !(1..=1_000_000).contains(&limit) {
            return Err(io::Error::other("invalid budget limit"));
        }
        let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
        file.try_lock()
            .map_err(|_| io::Error::other("budget locked"))?;
        file.write_all(MAGIC)?;
        file.write_all(&limit.to_le_bytes())?;
        file.sync_all()?;
        let parent = path
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        File::open(parent)?.sync_all()
    }
    /// Missing, corrupt, mismatched, or already owned state refuses startup.
    pub fn open(path: &Path, limit: u64) -> io::Result<Self> {
        let mut file = OpenOptions::new().read(true).append(true).open(path)?;
        file.try_lock()
            .map_err(|_| io::Error::other("budget locked"))?;
        let size = file.metadata()?.len();
        if !(16..=1_000_016).contains(&size) {
            return Err(io::Error::other("invalid budget length"));
        }
        let mut bytes = Vec::new();
        (&mut file).take(1_000_017).read_to_end(&mut bytes)?;
        if bytes.len() < 16
            || &bytes[..8] != MAGIC
            || bytes[8..16] != limit.to_le_bytes()
            || !(1..=1_000_000).contains(&limit)
            || bytes[16..].iter().any(|b| *b != 1)
            || bytes.len() as u64 - 16 > limit
        {
            return Err(io::Error::other("invalid budget state"));
        }
        Ok(Self {
            used: AtomicU64::new(bytes.len() as u64 - 16),
            file: Mutex::new(BudgetFile {
                file,
                disabled: false,
            }),
            limit,
            healthy: AtomicBool::new(true),
        })
    }
    pub fn used(&self) -> u64 {
        self.used.load(Ordering::Acquire)
    }
    /// Never acquires the writer lock or waits for filesystem I/O.
    pub fn healthy(&self) -> bool {
        self.healthy.load(Ordering::Acquire) && !self.file.is_poisoned()
    }
    pub fn reserve(&self) -> io::Result<bool> {
        self.reserve_with(|file| file.write_all(&[1]).and_then(|()| file.sync_all()))
    }
    fn reserve_with(&self, persist: impl FnOnce(&mut File) -> io::Result<()>) -> io::Result<bool> {
        let mut guard = self
            .file
            .lock()
            .map_err(|_| io::Error::other("budget poisoned"))?;
        if guard.disabled {
            return Err(io::Error::other("budget unavailable"));
        }
        if self.used() >= self.limit {
            return Ok(false);
        }
        if let Err(error) = persist(&mut guard.file) {
            // Uncertain write: disable dispatch, but retain exclusive ownership
            // until this instance (including in-progress reservations) drops.
            guard.disabled = true;
            self.healthy.store(false, Ordering::Release);
            return Err(error);
        }
        self.used.fetch_add(1, Ordering::Release);
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    static SEQUENCE: AtomicU64 = AtomicU64::new(0);
    fn path() -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "jev-budget-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ))
    }
    #[test]
    fn reopen_preserves_exhaustion_and_excludes_second_owner() {
        let path = path();
        DurableBudget::initialize(&path, 2).unwrap();
        assert!(DurableBudget::initialize(&path, 2).is_err());
        let budget = DurableBudget::open(&path, 2).unwrap();
        assert!(DurableBudget::open(&path, 2).is_err());
        assert!(budget.reserve().unwrap());
        drop(budget);
        assert!(DurableBudget::open(&path, 3).is_err());
        let budget = DurableBudget::open(&path, 2).unwrap();
        assert_eq!(budget.used(), 1);
        assert!(budget.reserve().unwrap());
        assert!(!budget.reserve().unwrap());
        drop(budget);
        assert!(!DurableBudget::open(&path, 2).unwrap().reserve().unwrap());
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn missing_and_torn_state_fail_closed() {
        let path = path();
        assert!(DurableBudget::open(&path, 2).is_err());
        std::fs::write(&path, b"JEVB").unwrap();
        assert!(DurableBudget::open(&path, 2).is_err());
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn concurrent_reservations_never_exceed_limit() {
        let path = path();
        DurableBudget::initialize(&path, 7).unwrap();
        let budget = std::sync::Arc::new(DurableBudget::open(&path, 7).unwrap());
        let workers: Vec<_> = (0..32)
            .map(|_| {
                let b = budget.clone();
                std::thread::spawn(move || b.reserve().unwrap())
            })
            .collect();
        assert_eq!(
            workers
                .into_iter()
                .map(|w| u64::from(w.join().unwrap()))
                .sum::<u64>(),
            7
        );
        drop(budget);
        assert_eq!(DurableBudget::open(&path, 7).unwrap().used(), 7);
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn uncertain_write_disables_reservations_without_releasing_exclusive_lock() {
        for append_before_error in [false, true] {
            let path = path();
            DurableBudget::initialize(&path, 2).unwrap();
            let budget = DurableBudget::open(&path, 2).unwrap();
            let failed = budget.reserve_with(|file| {
                if append_before_error {
                    file.write_all(&[1])?;
                }
                Err(io::Error::other("injected persistence failure"))
            });
            assert!(failed.is_err());
            assert!(!budget.healthy());
            assert!(budget.reserve().is_err());
            assert!(DurableBudget::open(&path, 2).is_err());
            drop(budget);
            let reopened = DurableBudget::open(&path, 2).unwrap();
            assert_eq!(reopened.used(), u64::from(append_before_error));
            drop(reopened);
            std::fs::remove_file(path).unwrap();
        }
    }
}
