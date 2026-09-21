# OpenRouter execution adapter

`braess-openrouter` is a loopback handler service and the Rust library module
`braess_router::openrouter`. Jev selects a capability, Poise selects a handler
endpoint, and this adapter executes the configured generation model. It supports
one user message, either text or explicitly provisioned image references, and a
non-streaming text response. Chat histories, tools, streaming, model fallback
and automatic retries are outside this version.

## Start the service

Build with `cargo build --locked --release --bins`. Copy
[`config/openrouter.live.example.json`](../config/openrouter.live.example.json)
and set an absolute journal path in a private, durable directory. The example's
`/tmp` path is for experiments only. Select explicit model IDs and provider slugs
available to your OpenRouter account; the example model is not a quality claim.
Set `OPENROUTER_API_KEY` through your process supervisor or secret manager.
Never put it in the configuration or repository.

```sh
braess-openrouter --config config/openrouter.live.example.json --init
braess-openrouter --config config/openrouter.live.example.json
```

Initialization is create-only. Startup requires the existing, valid journal.
For a stopped service, use `--inspect` to inspect accounting without a key or
network access. A second owner is refused. While running, use `/status`.
`/health` reports liveness; `/ready` reports local admission and accounting
capacity, with upstream health explicitly unchecked.

Configure Braess's handler map as follows, keeping the Jev rubric's route labels
aligned. Each route needs its own URL:

```json
{
  "general": ["http://127.0.0.1:8083/generate/general"],
  "coding": ["http://127.0.0.1:8083/generate/coding"],
  "reasoning": ["http://127.0.0.1:8083/generate/reasoning"]
}
```

Give Braess a longer deadline than the adapter to allow time for Jev and response
handling. Size Braess's response bound to include the adapter response envelope.
The generic `POST /generate` accepts `{"request":"Reply with OK.","route":"general"}`.
Route-specific URLs accept the same body and reject mismatched labels. Callers
cannot override the model, provider or output-token limit. Responses contain
`answer` and an `execution` receipt with the requested and reported model,
generation ID, finish reason and provider-reported usage. Braess nests this under
`handler_response`; its top-level Jev usage remains separate.

## Accounting and failure behavior

### Provisioned image references

An image route sets `"input_mode":"vision_reference"`. The adapter's optional
`vision_bundles` object maps the SHA-256 of each inspector `manifest.json` to an
absolute bundle directory. Generate bundles with the repository's verified
`demo/evidence_bundle.py` workflow. Select and verify an image-capable model and
provider before enabling a live route; input mode is operator configuration,
not an online capability check. Existing routes default to `text`; omitted image
fields keep their prior serialized journal scope.

The normal `request` string then holds a JSON `vision_reference_v1` envelope:
schema version 1, document ID, native-source hash, inspector-manifest hash,
bounded prompt, and an ordered `pages` array. Each selected page names its page
number, PNG hash, byte count, width and height. See [the measured preparation
workflow](../demo/VISION.md) for an offline request builder. Callers cannot pass
file paths, URLs, model overrides or undeclared fields in this envelope.

Startup verifies manifest and page hashes, PNG signatures and header dimensions,
and retains immutable base64 content. It does not decode PNG pixels, rerun OCR or
authenticate the manifest producer; provision source-verified bundles. A registry
has at most eight bundles and 8 MiB total PNG bytes. Each bundle has at most 32
pages of at most 16 million pixels; each request selects at most eight distinct
pages and an 8 KiB prompt. Image-enabled configurations allow at most four pending
generation slots. Outbound serialized JSON is bounded at 12 MiB independently
of the smaller inbound reference bound. Actual provider limits may be lower.

Resolution happens before generation reservation. Missing or mismatched source,
manifest, page or geometry fails without a generation attempt. Successful
`execution.input_evidence` contains the exact reference-string SHA-256 and the
ordered image hashes, persisted with the completion receipt. Prompts and image
bytes are absent from the journal. Failed dispatched requests retain their usual
unknown reservation; no successful source receipt is invented for them.

The offline integration suite proves gateway routing to multipart PNG content,
byte-for-byte image preservation, invalid-reference rejection before reservation,
frozen startup bytes, restart refusal after source modification, and durable
source receipts. This is synthetic transport evidence, not live image-model
quality, billing validation or a coordinate-aware vision review.

### Durable reservations

Before dispatch, the adapter synchronously persists a reservation. Before returning
success, it persists a validated completion receipt. Receipts contain metadata and
usage, not prompts or generated answers. Requested and reported model identifiers
can differ because a provider may report a specific model snapshot.

- `admission_limit` bounds pending reservations, including unresolved attempts.
- `max_calls` is a lifetime attempt cap across restarts, **not a dollar budget**.
  Every reserved attempt consumes one call permanently, even after completion.
- `max_tokens` limits requested output tokens. Input tokens and incomplete requests
  can also incur cost. Optional reported cost is per completion, not a billing ledger.
- HTTP errors, malformed responses, deadlines, cancellation and process death
  retain unresolved reservations. A timeout does not prove upstream work stopped.
- There are no automatic retries, redirects, proxy-environment forwarding, model
  fallback arrays, or alternate-provider fallbacks. Requests explicitly set
  `provider.only`, `provider.order`, `allow_fallbacks: false` and
  `require_parameters: true`.

The append-only journal is bounded at 16 MiB. Full, malformed, truncated, locked,
or unwritable state fails closed. Configuration is bound to the journal: changing
any configuration field requires a separately managed deployment, not an in-place
restart. There is no reconciliation, compaction, migration or force-release command
for this adapter yet. Do not delete or replace journals to bypass uncertain work or
reset budgets. Exhaustion needs operator review; this remains a single-server alpha.
The Rust API shares the same accounting, but embedders must bound task creation and
provide their own ingress and lifecycle controls.

## Evidence

```sh
python3 scripts/openrouter_e2e.py artifacts/openrouter-check --binary target/release/braess-openrouter
```

This offline suite tests the actual Braess → adapter → mock OpenRouter path,
provider controls, usage separation, rejection before dispatch, durable receipts,
lifetime budgets, exclusive ownership, overload, redirects, malformed responses,
response bounds, timeouts and forced termination. It records finite artifacts and
hashes. It also runs in the full validation pipeline and CI without credentials.
Synthetic fixtures cover these cases; they do not promise complete parity with
all providers or establish generation quality.

Protocol references: [OpenRouter API overview](https://openrouter.ai/docs/api/reference/overview)
and [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).
