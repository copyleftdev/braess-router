# V1 acceptance protocol — revision 1

This protocol is the checklist for the accepted single-server v1 milestone. It
preserves the broader scaling goal as later work. An alpha publication, successful
build, green CI check or matching hash bundle is not by itself v1 acceptance.
Record the candidate commit and package version before running acceptance. Changes
to runtime code, configuration or fixtures require a new candidate run. Changes to
this protocol require an explicit revision and review, not silent relaxation.

## Evidence required

| Requirement | Evidence and pass condition |
| --- | --- |
| Reproducible source and build | Clean candidate checkout, locked dependency resolution, formatting, Rust tests, Clippy and release build pass. Source copies/hashes match the candidate. |
| Bounded routing | Gateway, catalog and readiness checks pass, including rejection without dispatch, deadline handling and conservative uncertainty accounting. |
| Provider contract | All seven observed cases replay exact status/body/content type; captured success routes correctly; error injection remains sanitized and retains charges. This is finite contract coverage, not general provider equivalence. |
| Operator deployment | Installed foreground and actual user-systemd lifecycles pass: private state, initialization refusal, SIGTERM drain, SIGKILL/restart retention, environment-file loading and cleanup. |
| Offline maintenance | Inspection does not mutate state; quiescent migration preserves budget, counters and identities; unresolved work blocks migration; injected replacement failures retain a replayable scope and original archive. |
| Unresolved-work recovery | A provider/handler-specific way to establish and correlate completion is implemented and tested before releasing uncertain admission. Timeouts, TTLs, EOF and process death cannot substitute for that evidence. **Open.** |
| Distribution | Cargo package verification and publication dry-run pass on the candidate. Public source excludes credentials and historical artifacts. Secret scanning passes for tracked history. |
| Release controls | Version-policy negative tests pass; protected branch requires CI; release tag matches the package and main history before approval; publishing token remains isolated to the release environment. Actual publication permission is unverified until a publication succeeds. |
| Workload acceptance | Representative labeled inputs, expected fallback behavior, offered load and latency/error targets are recorded before evaluation. Results meet those targets on the deployment topology. **Open: workload and targets not supplied.** |

Every pass must name its artifact or hosted run and source revision. Record failures,
missing evidence and scope limitations; do not replace them with a passing summary.
Existing historical runs remain evidence for their recorded revisions, not automatic
proof for the latest commit. Do not rerun live provider experiments without a new,
finite question and request budget.

## Local evidence verification

```sh
cargo fetch --locked
python3 scripts/test_version.py
python3 scripts/test_evidence.py
python3 scripts/validate_local.py artifacts/candidate
python3 scripts/verify_evidence.py artifacts/candidate --report artifacts/evidence.json
cargo package --locked
cargo publish --locked --dry-run
```

Use new output paths. The evidence verifier checks the complete file manifest,
ordered twelve-stage results, and saved/current source hashes. It rejects incomplete,
stale, altered or path-escaping bundles. Its report always separates local evidence
validity from v1 acceptance; it does not sign provenance, independently rerun the
commands, certify external CI identity, or establish upstream completion.

Run the real-systemd check separately using the deployment guide. Keep generated
artifacts outside Git; CI uploads its validation bundle and verification report.
Do not remove successful checks merely to accommodate a failing candidate.

## Current disposition

The project remains alpha. Local correctness, observed contracts, deployment and
quiescent maintenance have evidence. Provider-specific uncertain-work reconciliation,
representative workload acceptance and a complete candidate audit remain open.
Publishing an alpha does not close those requirements or the broader scale objective.
