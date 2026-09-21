# Discovery fleet demo — in development

This companion will collect real execution evidence for an interactive replay and
film. The review fleet, native media workers and complete live pricing/reconciliation
are not implemented yet. A local replay interface now reads the recorded protocol smoke. The design and experiment scope
are in [the dogfood plan](../docs/DOGFOOD.md).

The recording component is a durable observer at Braess's HTTP boundary. It
records real timings and routing responses without copying prompts, generated
answers or authorization headers into its event log. It does not yet observe
Jev probabilities, internal dispatch timestamps, Poise candidate scores or worker
execution intervals. Missing observations must remain missing in a visualization.

## Verify and run locally

```sh
python3 -m unittest discover -s demo -p 'test_*.py'
cargo build --locked --release --bin braess-router
python3 demo/smoke.py artifacts/discovery-recording --binary target/release/braess-router
```

Use a fresh output directory. The smoke runs the actual Rust gateway against
local synthetic Jev and handler services with two client workers. It makes no
paid calls. The six fixtures cover ordinary routes, low confidence, malformed
upstream output and a handler error. They are protocol exercises, not legal
reviews. Its replay JSON is explicitly labeled `synthetic`.

`recording/run.json` identifies the run, scope, provenance hashes and observation
boundary. `events.jsonl` contains ordered, timestamped, hash-chained observations.
Each successful append is flushed to durable storage before returning.
`seal.json` commits to the event count and terminal hash. The verifier rejects
reordering, altered payloads, truncated lines, invalid transitions and a missing
seal unless explicit incomplete-run inspection is requested. A sealed recording
may still contain incomplete tasks. Hashes detect accidental or externally
anchored tampering; they are not signatures and do not authenticate a malicious
producer that rewrites the entire bundle.

Task transitions: queued → started → response → completed or uncertain. A started
request may also become uncertain without a response. `handler_completed` means
the gateway returned a handler result, not that legal accuracy was established.
Unknown costs stay unknown. Reported generation receipts are subtotaled using
decimal arithmetic; they do not constitute the full invoice. An observer failure
never initiates a retry or cancels remote work. This layer is not a spend ledger,
a scheduler or an idempotency mechanism.

Recording directories are created privately, but generic identifier fields can
still contain private information if callers misuse them. Supply opaque IDs.
Treat run bundles as private until an explicit public-export validator and source
content approval exist. No automatic public export or Pages deployment is enabled.

## Real corpus development sample

A bounded importer now matches the official TREC Enron text renderings to their
training-seed IDs, preserving family relationships, source hashes, exact evidence
offsets and conflicting judgments. The first local sample contains 40 documents
across 25 families. [Acquisition, scope and reproduction](CORPUS.md). Real source
content stays in ignored artifacts; the replay still uses synthetic fixtures.

## Shared spending reservations

The observer can now reserve from a durable, concurrent run-level ledger before
dispatch. Live scope requires that ledger. Unknown charges remain reserved, and
estimate overruns freeze further admission. [Behavior, evidence and remaining
pricing work](BUDGET.md). The pilot dollar cap is still awaiting selection.

## Explore the recorded replay

```sh
python3 demo/serve.py
```

Open http://127.0.0.1:4174. The server exposes an explicit asset allowlist, never
the repository root. The preview starts paused, supports keyboard playback and
scrubbing, and shows a task inspector with event timestamps and hashes. It makes
no provider calls. It currently displays six synthetic protocol tasks, not the
planned legal corpus. The cost total stays unknown because the source has no
complete billing record.

`demo/export_replay.py RECORDING demo/web/replay.json` verifies a sealed smoke
recording before exporting it. The exporter only accepts the six synthetic fixture
IDs; live recordings require a future content-review/export gate. Browser parsing
checks basic shape; the Python verifier is the integrity authority. Hashes alone
are not an authenticity proof.

## Visualization notes carried forward

The incumbent [GitHub page](https://copyleftdev.github.io/braess-router/) uses a
precision traffic instrument: near-black `#080808`, porcelain `#f5f5f2`, graphite
rules `#303030`, self-hosted Archivo, and a pale evidence surface. Preserve those
choices. Geometry distinguishes states without color. Avoid floating panels,
glow effects and unrelated decorative motion.

The review replay should use one clock for particles, counts, selection and event
history. Scrubbing must rebuild the same state from recorded events; pause and
reduced-motion modes keep all evidence readable. Stop rendering while hidden.
Use bounded visible particles and label any aggregation. Distinguish measured
wall-clock time from replay speed and purely illustrative path interpolation.
Do not show an internal route-selection timestamp until instrumentation records it.

The router stays central. Selecting a task will reveal its route, evidence
locations, observed usage, uncertainty and eventual reviewer outcome in a light
document pane. Modality lanes appear only for capabilities exercised in that run.
Errors and human-review queues remain visible; no invented resolutions or zeroed
costs. A future film export must use the same event-driven renderer as playback.

## Next implementation boundaries

- Internal decision/dispatch/completion events with task correlation.
- Conservative pricing estimates and full receipt reconciliation; shared durable
  reservations and observer dispatch gating are implemented and tested.
- Native media acquisition and extraction; text-rendering manifests and exact
  source-location validation are implemented for a real TREC development sample.
- Wire prepared review tasks and validated text findings into reviewer execution;
  [text findings and draft redaction contracts](REVIEW.md) are implemented.
  Image/audio coordinates still need separate validation.
- Public-export validation and film capture. The local synthetic replay and its
  desktop/mobile browser verification are complete for the current smoke slice;
  see the [surface brief](../.impeccable/surface-briefs/discovery-replay.md).

The recorded smoke is development evidence, not completion of the dogfood goal.
