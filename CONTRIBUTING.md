# Contributing

Use Rust 1.97.1, rustfmt, Clippy and Python 3.11+ and systemd-analyze on Linux.

```sh
cargo fetch --locked
python3 scripts/test_version.py
python3 scripts/test_evidence.py
python3 scripts/validate_local.py artifacts/local
python3 scripts/verify_evidence.py artifacts/local --report artifacts/evidence.json
cargo package --locked
```

Use a new artifact directory each time. Validation records source and binary hashes,
commands and outcomes; generated artifacts are ignored by Git. Tests make no live
provider calls. Never add credentials, captured production requests or runtime state.

Submit changes through a pull request. Runtime, installer, dependency, configuration or rubric changes require a
package version bump and a changelog entry. CI enforces this against the base commit.
Keep prereleases as `X.Y.Z-alpha.N`, `-beta.N`, or `-rc.N`; stable versions use X.Y.Z.
A version bump does not publish anything. Releases use the separate workflow.

Report the behavior changed and the checks run. Claims about capacity or accuracy
need representative measurements, not only passing synthetic tests.

V1 release claims must satisfy the [acceptance protocol](docs/ACCEPTANCE.md).
