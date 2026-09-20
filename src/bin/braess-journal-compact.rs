//! Offline journal compaction. Retains original audit bytes under ARCHIVE_PATH.
//! Holding the configured budget lock excludes gateway startup across inode swap.
use braess_router::{
    Rubric, durable_budget::DurableBudget, durable_requests::DurableRequests, gateway::Config,
};
use std::{fs::File, path::Path};

fn parent(path: &Path) -> std::io::Result<std::path::PathBuf> {
    path.parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."))
        .canonicalize()
}
fn compact(
    config: &Config,
    rubric: &Rubric,
    archive: &Path,
    checkpoint: &Path,
    mut stage: impl FnMut(&str) -> std::io::Result<()>,
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let scope = config.request_journal_scope(rubric)?;
    let source = config
        .request_journal_path
        .as_ref()
        .ok_or("request_journal_path required")?;
    let budget_path = config.budget_path.as_ref().ok_or("budget_path required")?;
    let directory = parent(source)?;
    if parent(archive)? != directory || parent(checkpoint)? != directory {
        return Err("archive and checkpoint must share the journal directory".into());
    }
    // Symlink replacement would otherwise replace the link rather than its target.
    if !std::fs::symlink_metadata(source)?.file_type().is_file() {
        return Err("journal must be a regular file, not a symlink".into());
    }
    let _budget_owner = DurableBudget::open(budget_path, config.max_jev_calls)?;
    let journal = DurableRequests::open(source, &scope, config.admission_limit)?;
    let before = journal.snapshot();
    let old_bytes = std::fs::metadata(source)?.len();
    journal.checkpoint_to(checkpoint, &scope)?;
    stage("checkpoint_synced")?;
    // Explicit new archive link; never overwrite an existing archive.
    std::fs::hard_link(source, archive)?;
    File::open(&directory)?.sync_all()?;
    stage("archive_synced")?;
    let checkpoint_owner = DurableRequests::open(checkpoint, &scope, config.admission_limit)?;
    if checkpoint_owner.snapshot() != before {
        return Err("checkpoint replay differs from source".into());
    }
    let new_bytes = std::fs::metadata(checkpoint)?.len();
    std::fs::rename(checkpoint, source)?;
    stage("replaced")?;
    File::open(&directory)?.sync_all().map_err(|error| format!("journal replaced; directory sync failed; inspect journal and archive before retry: {error}"))?;
    stage("directory_synced")?;
    Ok(
        serde_json::json!({"compacted":true,"old_bytes":old_bytes,"new_bytes":new_bytes,
        "state":before,"archive":archive,"journal":source}),
    )
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 4 {
        return Err("usage: braess-journal-compact CONFIG ARCHIVE_PATH CHECKPOINT_PATH".into());
    }
    let config: Config = serde_json::from_slice(&std::fs::read(&args[1])?)?;
    let rubric: Rubric = serde_json::from_slice(&std::fs::read(&config.rubric_path)?)?;
    println!(
        "{}",
        compact(
            &config,
            &rubric,
            Path::new(&args[2]),
            Path::new(&args[3]),
            |_| Ok(())
        )?
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};
    use std::{
        io,
        path::PathBuf,
        sync::atomic::{AtomicU64, Ordering},
    };

    static SEQUENCE: AtomicU64 = AtomicU64::new(0);

    struct Fixture {
        directory: PathBuf,
        config: Config,
        rubric: Rubric,
        scope: String,
        before: Value,
        source_bytes: Vec<u8>,
        budget_bytes: Vec<u8>,
    }
    impl Fixture {
        fn new() -> Self {
            let directory = std::env::temp_dir().join(format!(
                "jev-compact-{}-{}",
                std::process::id(),
                SEQUENCE.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&directory).unwrap();
            let config: Config = serde_json::from_value(json!({
                "bind":"127.0.0.1:0", "mode":"mock", "jev_url":"http://127.0.0.1:18000/jev",
                "rubric_path":"eval/rubric.json", "deadline_ms":1000,
                "max_request_bytes":4096, "max_response_bytes":4096,
                "admission_limit":4, "tracking_limit":8, "uncertainty_ttl_ms":1000,
                "max_jev_calls":100, "budget_path":directory.join("budget"),
                "request_journal_path":directory.join("journal"),
                "handlers":{"general":["http://127.0.0.1:18001/general"],
                    "coding":["http://127.0.0.1:18002/coding"],
                    "reasoning":["http://127.0.0.1:18003/reasoning"]}
            }))
            .unwrap();
            let rubric: Rubric =
                serde_json::from_str(include_str!("../../eval/rubric.json")).unwrap();
            let scope = config.request_journal_scope(&rubric).unwrap();
            let budget_path = config.budget_path.as_ref().unwrap();
            DurableBudget::initialize(budget_path, config.max_jev_calls).unwrap();
            let budget = DurableBudget::open(budget_path, config.max_jev_calls).unwrap();
            assert!(budget.reserve().unwrap());
            assert!(budget.reserve().unwrap());
            drop(budget);
            let source = config.request_journal_path.as_ref().unwrap();
            DurableRequests::initialize(source, &scope).unwrap();
            let journal = DurableRequests::open(source, &scope, config.admission_limit).unwrap();
            let first_pending = journal.begin("jev").unwrap();
            for _ in 0..50 {
                let id = journal.begin("jev").unwrap();
                journal.complete(id).unwrap();
            }
            let last_pending = journal
                .begin("handler:http://127.0.0.1:18002/coding")
                .unwrap();
            assert_eq!((first_pending, last_pending), (1, 52));
            let before = journal.snapshot();
            drop(journal);
            let source_bytes = std::fs::read(source).unwrap();
            let budget_bytes = std::fs::read(budget_path).unwrap();
            Self {
                directory,
                config,
                rubric,
                scope,
                before,
                source_bytes,
                budget_bytes,
            }
        }
        fn source(&self) -> &Path {
            self.config.request_journal_path.as_ref().unwrap()
        }
        fn archive(&self) -> PathBuf {
            self.directory.join("archive")
        }
        fn checkpoint(&self) -> PathBuf {
            self.directory.join("checkpoint")
        }
        fn assert_preserved(&self) {
            let journal =
                DurableRequests::open(self.source(), &self.scope, self.config.admission_limit)
                    .unwrap();
            assert_eq!(journal.snapshot(), self.before);
            assert_eq!(
                std::fs::read(self.config.budget_path.as_ref().unwrap()).unwrap(),
                self.budget_bytes
            );
            let budget = DurableBudget::open(
                self.config.budget_path.as_ref().unwrap(),
                self.config.max_jev_calls,
            )
            .unwrap();
            assert_eq!(budget.used(), 2);
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.directory);
        }
    }

    // These are injected boundary failures, not process crashes or power-loss tests.
    #[test]
    fn injected_boundary_failures_preserve_state_and_hold_ownership() {
        let stages = [
            "checkpoint_synced",
            "archive_synced",
            "replaced",
            "directory_synced",
        ];
        for (failure_index, failure_stage) in stages.iter().enumerate() {
            let fixture = Fixture::new();
            let mut observed = Vec::new();
            let result = compact(
                &fixture.config,
                &fixture.rubric,
                &fixture.archive(),
                &fixture.checkpoint(),
                |stage| {
                    observed.push(stage.to_owned());
                    assert!(
                        DurableBudget::open(
                            fixture.config.budget_path.as_ref().unwrap(),
                            fixture.config.max_jev_calls
                        )
                        .is_err(),
                        "budget unlocked at {stage}"
                    );
                    assert!(
                        DurableRequests::open(
                            fixture.source(),
                            &fixture.scope,
                            fixture.config.admission_limit
                        )
                        .is_err(),
                        "source unlocked at {stage}"
                    );
                    if stage != "checkpoint_synced" {
                        assert_eq!(
                            std::fs::read(fixture.archive()).unwrap(),
                            fixture.source_bytes
                        );
                        assert!(
                            DurableRequests::open(
                                &fixture.archive(),
                                &fixture.scope,
                                fixture.config.admission_limit
                            )
                            .is_err(),
                            "archived source unlocked at {stage}"
                        );
                    }
                    if stage == *failure_stage {
                        Err(io::Error::other("injected compaction boundary failure"))
                    } else {
                        Ok(())
                    }
                },
            );
            assert!(result.is_err());
            assert_eq!(observed, stages[..=failure_index]);
            fixture.assert_preserved();
            if failure_index == 0 {
                assert!(!fixture.archive().exists());
            } else {
                assert_eq!(
                    std::fs::read(fixture.archive()).unwrap(),
                    fixture.source_bytes
                );
            }
            if failure_index < 2 {
                assert_eq!(
                    std::fs::read(fixture.source()).unwrap(),
                    fixture.source_bytes
                );
                assert!(fixture.checkpoint().exists());
            } else {
                assert!(!fixture.checkpoint().exists());
            }
        }
    }

    #[test]
    fn successful_compaction_shrinks_history_and_preserves_unfinished_ids() {
        let fixture = Fixture::new();
        let result = compact(
            &fixture.config,
            &fixture.rubric,
            &fixture.archive(),
            &fixture.checkpoint(),
            |_| Ok(()),
        )
        .unwrap();
        assert_eq!(result["compacted"], true);
        assert!(result["new_bytes"].as_u64().unwrap() < result["old_bytes"].as_u64().unwrap());
        fixture.assert_preserved();
        assert_eq!(
            std::fs::read(fixture.archive()).unwrap(),
            fixture.source_bytes
        );
        assert!(!fixture.checkpoint().exists());
        let journal = DurableRequests::open(
            fixture.source(),
            &fixture.scope,
            fixture.config.admission_limit,
        )
        .unwrap();
        journal.complete(1).unwrap();
        journal.complete(52).unwrap();
        assert_eq!(journal.begin("jev").unwrap(), 53);
        assert_eq!(journal.snapshot()["completed"], 52);
        assert_eq!(journal.pending("jev"), 1);
    }

    #[test]
    fn existing_archive_or_checkpoint_is_never_overwritten() {
        for occupy_archive in [true, false] {
            let fixture = Fixture::new();
            let occupied = if occupy_archive {
                fixture.archive()
            } else {
                fixture.checkpoint()
            };
            std::fs::write(&occupied, b"existing evidence").unwrap();
            let result = compact(
                &fixture.config,
                &fixture.rubric,
                &fixture.archive(),
                &fixture.checkpoint(),
                |_| Ok(()),
            );
            assert!(result.is_err());
            assert_eq!(std::fs::read(occupied).unwrap(), b"existing evidence");
            assert_eq!(
                std::fs::read(fixture.source()).unwrap(),
                fixture.source_bytes
            );
            fixture.assert_preserved();
        }
    }

    #[cfg(unix)]
    #[test]
    fn symlink_source_is_rejected_without_replacing_target() {
        let fixture = Fixture::new();
        let alias = fixture.directory.join("alias");
        std::os::unix::fs::symlink(fixture.source(), &alias).unwrap();
        let mut config = fixture.config.clone();
        config.request_journal_path = Some(alias.clone());
        assert!(
            compact(
                &config,
                &fixture.rubric,
                &fixture.archive(),
                &fixture.checkpoint(),
                |_| Ok(())
            )
            .is_err()
        );
        assert!(
            std::fs::symlink_metadata(alias)
                .unwrap()
                .file_type()
                .is_symlink()
        );
        assert_eq!(
            std::fs::read(fixture.source()).unwrap(),
            fixture.source_bytes
        );
        assert!(!fixture.archive().exists());
        assert!(!fixture.checkpoint().exists());
        fixture.assert_preserved();
    }

    #[test]
    fn active_budget_owner_blocks_compaction_before_creating_artifacts() {
        let fixture = Fixture::new();
        let owner = DurableBudget::open(
            fixture.config.budget_path.as_ref().unwrap(),
            fixture.config.max_jev_calls,
        )
        .unwrap();
        let mut stages = 0;
        let result = compact(
            &fixture.config,
            &fixture.rubric,
            &fixture.archive(),
            &fixture.checkpoint(),
            |_| {
                stages += 1;
                Ok(())
            },
        );
        assert!(result.is_err());
        assert_eq!(stages, 0);
        assert!(!fixture.archive().exists());
        assert!(!fixture.checkpoint().exists());
        assert_eq!(
            std::fs::read(fixture.source()).unwrap(),
            fixture.source_bytes
        );
        drop(owner);
        fixture.assert_preserved();
    }
}
