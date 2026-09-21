# Discovery fleet demo — in development

This companion will collect real execution evidence for an interactive replay and
film. A bounded text-review runner is implemented; native media workers and complete
live pricing/reconciliation are not implemented yet. A local replay interface now reads the recorded protocol smoke. The design and experiment scope
are in [the dogfood plan](../docs/DOGFOOD.md).

The recording component is a durable observer at Braess's HTTP boundary. It
records real timings and routing responses without copying prompts, generated
answers or authorization headers into its event log. Gateway response traces now
retain Jev probabilities and local send/validation boundaries. Poise candidate
scores, durable internal dispatch events and worker intervals remain unobserved.
Missing observations remain missing; response traces can be lost on disconnect.

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

## Native media and OCR

A bounded prefix of the official native archive now has a signature inventory.
Thirteen image candidates decoded, including three multipage TIFFs; one two-page
TIFF has local OCR with source-linked word coordinates. Validated OCR findings
now carry the original image hash, page and pixel boxes. [Measured coverage,
reproduction and limits](MEDIA.md). This is local extraction, not semantic review. The [image transport experiment](VISION.md)
now also sends both scan pages through the local gateway and image handler with
scripted providers, recording exact request and page hashes.

## Execute validated reviewer tasks

The [bounded fleet runner](FLEET.md) now connects prepared tasks to actual Braess
and OpenRouter-adapter execution, private response capture, source-span validation
and replay events. Its offline full-path test distinguishes validated findings,
fabricated quotes and budget deferrals. Real-corpus paid execution is still pending.

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
no provider calls. It now displays the three-task fleet smoke: one source-validated
review, one rejected quote retained as uncertain, and one budget deferral. The
Jev and reviewer responses are synthetic; actual Braess execution, validation and
admission gating were measured. The cost total stays unknown because the source
has no complete billing record. Per-response costs are synthetic fixture receipts.

`demo/export_replay.py RECORDING demo/web/replay.json` verifies a sealed smoke
recording before exporting it. Its default profile accepts the original six
gateway fixture IDs. The explicit fleet profile accepts only pinned fleet task
IDs and allowlisted metadata labels, with no source text or raw responses:

```sh
python3 demo/export_replay.py artifacts/fleet-check/run/recording demo/web/replay.json --profile fleet
```

Live recordings require a future content-review/export gate. Browser parsing
checks basic shape; the Python verifier is the integrity authority. Hashes alone
are not an authenticity proof.

The committed replay was exported from `artifacts/discovery-fleet-routing-trace-v2`:
three tasks, eleven events, 36.80 ms observed elapsed time. The task inspector
shows source-validation counts, route/model/provider, tokens, admission estimate,
receipt cost, event times and provenance hashes. It only reveals events at or
before the replay clock. A deferred square stays at intake; an uncertain diamond
remains separate from accepted completion even after a successful HTTP response.

The decision panel shows the recorded route distribution, model confidence and
supported score against configured minimums. Gateway send-to-validation intervals
use a separate local clock; they are revealed only after the observer receives
the response. Missing endpoints stay unknown. These synthetic provider scores
are not legal-accuracy estimates.

## Capture a local film draft

For a reproducible film input, [freeze a private replay package](PACKAGE.md).
It gathers the verified replay, source associations, optional scans, viewer and
route analysis under a file-hash manifest. It can be served without the original
corpus directories. The [source-navigation capture](SOURCE_FILM.md) demonstrates
the private scan workflow; the generic fixture capture below covers fleet states.

With the loopback preview running, Playwright available and FFmpeg/ffprobe on PATH:

```sh
node demo/record_film.cjs artifacts/NEW_FILM_DIRECTORY
```

Set `PLAYWRIGHT_MODULE` to an installed module path if it is not resolvable by
Node. Capture refuses existing output directories. It records the same renderer
and replay controls, then visits accepted, uncertain and deferred tasks. The
output includes WebM, H.264 MP4 and a manifest with recording/renderer hashes,
capture steps and measured video properties. Capture wall time is separate from
the two recorded clocks. No provider calls occur and live scope is refused.

The first local draft is 26.28 seconds at 1440×1100. It demonstrates synthetic
fleet execution, not the final live-corpus film. Capture verifies source stability,
outcome assertions and basic encoding; a complete manifest does not substitute
for visually inspecting the film or approving publication. Artifacts stay ignored.

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

- The [routing trace panels](TELEMETRY.md) now show decision distributions and
  partial timings. Durable server-side events remain separate work; response
  traces cannot survive every client disconnect.
- Conservative pricing estimates and full receipt reconciliation; shared durable
  reservations and observer dispatch gating are implemented and tested.
- Join sampled native media to text IDs and implement vision review. A bounded
  native inventory, local OCR and source-linked OCR findings are implemented.
- Run the prepared real corpus under the [provisional discovery rubric](DISCOVERY_POLICY.md) and
  verified provider pricing; [text findings and draft redaction contracts](REVIEW.md)
  are now connected to the bounded runner.
  Native image redaction and audio coordinates still need separate implementation.
- Public live-export validation and the final corpus film. A local synthetic
  film draft is captured; the replay and its
  desktop/mobile browser verification are complete for the current smoke slice;
  see the [surface brief](../.impeccable/surface-briefs/discovery-replay.md).

The recorded smoke is development evidence, not completion of the dogfood goal.
