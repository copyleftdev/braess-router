# Discovery review fleet: dogfood experiment plan

Status: proposed, 2026-09-21. This document plans a real, paid workload against
Braess Router; it does not claim that the review application exists yet.
Working interpretation: litigation-defense discovery. Pilot dollar cap awaits
user selection. Planning and offline development can proceed without paid calls.

## The experiment

Can a Jev-directed review fleet reduce generation cost while preserving measured
responsiveness recall, evidence accuracy and redaction quality compared with a
fixed-model review pipeline? The output is a reproducible review bundle and an
honest, event-driven film of the run, including failures and disagreements.

Start with one defined matter, a written request for production, and a versioned
review protocol. Defense relevance includes evidence adverse to the defense;
there is no routing rule that discards an inconvenient document. Privilege flags
and proposed redactions remain recommendations for human review.

## Corpus decision

Prefer an **Enron subset aligned to a specific TREC Legal Track release and its
judgments**. The task is email discovery, so matching the workload and evaluation
labels matters more than choosing the newest dataset.

| Candidate | Purpose | Decision |
| --- | --- | --- |
| EDRM Enron v2 / TREC Legal | Emails, attachments, production requests and relevance judgments | Primary candidate; verify access, document IDs, family mapping and terms before acquisition |
| CMU Enron, May 2015 | Email/thread ingestion and workflow smoke tests | Accessible fallback, but excludes attachments; do not apply TREC labels without a verified mapping |
| CUAD, 2021 | Expert-labeled clause extraction from commercial contracts | Optional second track for exact highlights; not a substitute for email discovery |
| ACORD, ACL 2025 | Expert-rated query-to-clause retrieval | Modern retrieval extension after the discovery pilot |
| Controlled synthetic supplement | Known redaction spans, modern message formats, adversarial instructions | Separate stress suite; never blend into claims about real-corpus accuracy |

The [TREC Legal site](https://trec-legal.umiacs.umd.edu/) describes the discovery
tasks and links their judgments. Its [Enron v2 identification helpers](https://trec-legal.umiacs.umd.edu/corpora/trec/legal10/)
provide a starting point for matching records. [CMU's corpus description](https://www.cs.cmu.edu/~enron/)
explicitly notes removed attachments and earlier redactions. These collections
are not interchangeable. Download availability and source-content reuse rights
remain to be checked; an index page is not proof of either.

[CUAD](https://www.atticusprojectai.org/cuad/) provides 510 contracts annotated
for 41 clause types. [ACORD](https://www.atticusprojectai.org/acord/) provides
expert-rated legal clause retrieval data. Atticus lists its datasets under
[CC BY 4.0](https://www.atticusprojectai.org/datasets/). Neither supplies a complete
email responsiveness, privilege and redaction gold standard.

Acquisition must produce a manifest of source URLs, release, terms, download and
extraction hashes, stable source IDs, parent/attachment relationships, duplicate
clusters, document lengths and extraction failures. Preserve originals. Use
content-addressed derived text with a reversible source-location map. Sandbox
attachment extraction; enforce archive expansion, file-size and runtime limits.
No corpus downloads or raw document content belong in the crate or Git history.

Proposed pilot: 20 documents for plumbing, then up to 400 review units split by
whole thread/family/near-duplicate cluster into 200 development and 200 held-out
units. Actual counts depend on available judgments and the selected budget.
Keep a representative sample separate from a labeled challenge set. Unjudged is
not nonresponsive. Publish judged coverage, prevalence and exclusions. Existing
benchmark exposure to model training limits claims about generalization.

## Fleet and routing

The fleet consists of specialized, bounded workers operating a durable task graph.
Start with four concurrent tasks, queue capacity 32, and no recursive spawning.
Every generated review travels through Braess; workers have no direct provider
credentials. Endpoint replication must not multiply a shared spend allowance.

| Worker | Output | Execution policy |
| --- | --- | --- |
| Intake | Normalized text, hashes, thread/family links, exact duplicate map | Local deterministic processing |
| Triage | Proposed review route and uncertainty | Jev using a discovery-specific rubric |
| Responsiveness reviewer | Responsive/nonresponsive/uncertain, issue tags, exact supporting spans | Lower-cost text model initially |
| Context reviewer | Thread contradictions, chronology, missing-context flags | Stronger model when context or uncertainty warrants |
| Sensitive-content reviewer | PII/redaction candidates and privilege indicators with spans | Required policy coverage; Jev may prioritize or escalate, not waive it |
| Independent verifier | Unsupported findings, missed evidence, disagreements | Blind review of a fixed sample plus escalations |
| Adjudication queue | Human resolutions, accepted highlights and redactions | Bounded terminal state, not an endless model debate |

A document may require multiple tasks. Braess currently chooses one handler per
request; the workflow scheduler owns fan-out and dependencies. Its trusted stage
field and immutable review protocol constrain which routes are eligible. Document
text is untrusted evidence, never executable instructions or authority to alter
routes, budgets or publication rules.

Proposed routes: `review_basic`, `review_context`, `review_sensitive`,
`review_verify`, and local `fallback` mapped by the scheduler to human review.
Use separate stage-specific gateway configurations where necessary to prevent a
mandatory sensitive-content task being routed into an ordinary summary. In the
pilot each task gets at most one initial generation and one planned escalation;
verification is a separately budgeted task. No silent retries or fallback loops.

Jev selects effort and can assess whether a proposed finding is supported, but
its confidence is not a calibrated legal error probability. Calibrate thresholds
on the development split and audit some high-confidence exclusions. Always
report human-review coverage and cost rather than hiding abstentions.

## Multimodal routing and the router showcase

The dogfood workload should demonstrate capability selection as well as reviewer
selection. Inventory actual file signatures, formats, page counts, image counts,
audio/video duration, extraction quality and unsupported/encrypted objects before
claiming corpus coverage. Attachments do not establish that usable audio or video
exists. If a modality is absent, add an explicitly separate, rights-cleared test
collection; never present supplemental media as original Enron evidence.

Use two routing layers:

1. Deterministic intake establishes which capabilities are eligible: native text,
   scanned document/image, audio, video, mixed attachment or unsupported input.
   File extensions alone are insufficient. Cheap local extraction and quality
   checks precede model dispatch where appropriate.
2. Jev chooses the next eligible semantic task and review effort from the trusted
   task envelope and available extracted evidence. Braess selects the handler;
   the handler executes an explicitly supported model. Jev is not assumed to
   perceive raw images or audio. Missing or poor extraction triggers a dedicated
   perception worker or human review, not invented content.

| Input | Candidate processing path | Evidence locator |
| --- | --- | --- |
| Native email/document | Text extraction → semantic review | Source ID and exact text span |
| Scanned PDF/image | OCR/layout → quality check → vision review when needed | Page/image ID and bounding box |
| Audio, if present | Transcription → quality check → transcript review; audio-capable review when necessary | Source ID and timestamp interval |
| Video, if present | Bounded frame/audio extraction → coordinated review | Frame timestamp and audio interval |
| Mixed email family | Fan-out attachment processing → family-level review | Parent/attachment links and child locators |
| Unsupported/encrypted/corrupt | Explicit blocked state → human queue | Original hash and failure reason |

Transcripts, OCR and captions are derived evidence with tool/model versions and
quality flags. A summary cannot replace the source. Findings retain coordinates
or timestamps so reviewers can reopen the exact image region or sound segment.
Do not infer speaker identity from a voice. Sparse video frames cannot establish
coverage of unseen intervals; record sampling and missed/unsupported coverage.

Implement typed asset references into a controlled local content store rather
than stuffing base64 media into the existing text request or letting models fetch
arbitrary URLs. Resolve references inside the worker with size, duration, pixel,
page, decompression and timeout bounds. Treat document instructions as untrusted
across every modality. New vision/audio/video handlers need independently tested
provider contracts, response schemas and pricing before live admission. Current
Braess/OpenRouter generation support is text-only; this section describes planned
extensions, not existing functionality.

Budget reservations must include image/page units, audio duration, frame sampling,
transcription and downstream review, using verified provider billing rules.
Expand evaluation by modality: extraction errors, relevant visual evidence missed,
transcription errors, source-location validity, and redaction leakage. Image/PDF
redactions remove source pixels and hidden text; audio redactions remove the
specified sound interval and corresponding transcript text in the derivative.
All remain proposed edits until approved, with originals preserved.

For the film, keep Braess visually central. Show an email family splitting into
text, vision and audio lanes only when those events occurred, then rejoining for
context review. Each routing event exposes eligible capabilities, the selected
route, recorded Jev scores when available, the policy rule applied, selected
handler/model, latency and cost. Distinguish deterministic format decisions from
semantic Jev choices; never fabricate a model's explanation. Demonstrate a real
escalation caused by poor extraction or conflicting evidence, if observed.

Delivery order: text plus image/scanned-page vertical slice first; audio next if
the inventory supports it or a supplemental collection is selected; video later.
The first film should make a small number of real routing decisions legible before
showing aggregate fleet activity.

## OpenRouter integration work

OpenRouter documents Jev at `POST /api/alpha/decisions`, using
`typesafe/jev-1.13`. Its typed answers and usage envelope differ from chat
completions. See the [official Decisions reference](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request).
The [official cascade example](https://openrouter.ai/docs/cookbook/evaluate-and-optimize/jev-verified-cascade)
is relevant to selective escalation, but supplies no evidence of legal accuracy.

Current Braess pins the direct TypeSafe URL and model and permits exactly the
`route` and `supported` questions. The existing OpenRouter adapter only performs
text generation. Required work:

1. Add an explicit decision-provider abstraction with distinct direct-TypeSafe
   and OpenRouter transports; pin model IDs and normalize validated responses.
2. Capture a small, finite Decisions contract sample after budget selection;
   retain sanitized raw request/response bodies, status, timing and model IDs.
   Never record authorization headers. Add offline replay and negative fixtures.
3. Preserve durable decision-call accounting and add trace correlation before
   claiming the entire fleet is observed. Keep decision and generation costs separate.
4. Add reviewer prompt templates, bounded structured finding validation and
   task-envelope correlation. The current text adapter's answer string alone
   does not establish valid legal-review output.

Keep typed decision evaluation reusable so verification questions do not require
relaxing the router's two-question contract. Pin catalog and rubric versions per
run; compare transports empirically rather than assuming response parity.

## Budget and evaluation

No paid pilot begins until its dollar cap is chosen. Model selection follows a
small measured comparison, not a reputation ranking. Snapshot provider prices
and supported parameters before the run. Restrict models/providers and reject
unpriced requests. The existing adapter's lifetime call cap is not a spend cap.

Add a durable shared run-level ledger before parallel live work. Atomically
reserve a conservative input-plus-maximum-output estimate before each dispatch;
include Jev, verification, escalations, overhead and a margin. Account for
in-flight reservations when admitting work. Keep reservations for unknown
outcomes. Reconcile reported receipts after completion; provider/key spending
controls, if verified available, add another boundary. An estimate is not a
provider-guaranteed invoice ceiling.

For model m, estimate each call as:
`input_token_bound * input_price_m + output_token_cap * output_price_m + fees`.
Use the actual tokenizer or a demonstrated conservative bound including all
prompts and wrappers. Allocate the pilot envelope provisionally: 10% contract
probes/calibration, 60% matched experiment arms, 20% verification/escalation,
10% unresolved-charge margin. Abort admission before exhausting reservations.

Compare three arms over identical held-out families and review tasks:

- Fixed economical model.
- Fixed stronger model.
- Jev-directed selective escalation.

Baseline routes still use Braess transport and accounting through an explicit
benchmark-only fixed policy; they do not masquerade as semantic routing. Include
all Jev and verifier costs in the routed arm. Freeze task protocol, splits,
prompts, models, thresholds, token bounds and escalation rules before evaluation.
Reserve capacity for complete matched groups; partial groups are reported separately.

Report responsiveness precision/recall and false negatives, evidence-span validity,
redaction span precision/recall and leakage, abstentions, disagreements, human
review minutes, per-document cost, cost per correctly reviewed document, p50/p95
latency, queue depth, unresolved attempts and all failures. Report uncertainty
using family-level resampling where sample size permits. No fleet-wide recall
claim from an enriched or incompletely judged sample. Human-adjudicated labels
are necessary where the source lacks gold labels; model agreement is not truth.

Proposed scaling gates: all accepted highlights map to actual source spans; no
known sensitive test span survives in an approved redacted derivative; no lost or
duplicate committed tasks in crash tests; no admission beyond the configured
reservation envelope. Quality gate: predeclare a maximum two-percentage-point
recall loss versus the stronger baseline and assess its uncertainty. If the pilot
cannot resolve that margin, report it as inconclusive and enlarge the evaluation
rather than announcing equivalence. Exact quality thresholds remain provisional.

## Review artifacts and film

Record events as work occurs, not by reconstructing an attractive story afterward.
Each event carries `run_id`, monotonic sequence, UTC and elapsed timestamps,
`document_id`, `family_id`, `task_id`, parent task, attempt, route, worker, requested
and reported model, rubric/prompt/config hashes, decision probabilities when
available, queue/service time, reservation/receipt IDs, tokens, cost status and
result/error reference. Use an append-only log, content hashes and a sealed run
manifest. Capture decisions and concise evidence-backed findings, not hidden
model chain-of-thought or credentials.

Keep original documents, provider captures and full findings in a restricted run
bundle. A separately validated public export contains approved excerpts,
pseudonymous IDs, findings and event traces. Replay and film use that export only.
A highlight is a byte/character span plus normalization version and source mapping;
a redaction is a new derivative that removes the underlying text, not a black
rectangle. Verify extraction, search, copy/paste and metadata on exported files.
PDF rendering requires its own page-coordinate and hidden-content tests.

Film outline, approximately 90–120 seconds:

1. A real corpus and a specific production request enter the system.
2. Document particles reach Braess; Jev decisions light the selected reviewer lanes.
3. Follow one document into exact highlights and a proposed redaction.
4. Show a genuine disagreement, escalation and human resolution if observed.
5. Pull back to the fleet and reveal measured quality, cost and unresolved work.

The existing monochrome landing-page visual language can carry this. Every
particle corresponds to a recorded task; lane crossings are observed dispatches,
branching means real fan-out, and stalled particles mean unresolved work. Mark
replay speed and sampling explicitly. Deterministic replay must reproduce counts
and totals without new API calls; live model reruns need not reproduce answers.
If controlled failures are used for the film, label their separate test run.
Publish selection rules and the full aggregate report alongside the curated story.

## Implementation order and deliverables

1. **Corpus + contract:** inventory media and verify corpus/label alignment and terms; create loader,
   manifest, frozen splits and up to three paid Decisions probes within the chosen cap.
2. **Run kernel:** bounded durable task graph, shared monetary reservations, trace
   IDs, event schema and restart/crash tests. Offline fixtures first.
3. **Review vertical slice:** one document → Jev → Braess → reviewer → validated
   source spans → verification → human queue → persisted receipt and replay event.
4. **Matched pilot:** run the three arms under one envelope, export metrics,
   adjudicate sampled outputs and decide whether the quality evidence supports scale.
5. **Replay and film:** event-driven fleet view, document detail, redaction preview,
   visible cost/quality measures, reproducible recording and approved public bundle.

Suggested separation: the reviewer workflow, corpus tooling and film belong in a
companion application; only reusable provider/accounting/trace primitives belong
in the Braess crate. Keep raw corpora, credentials and recordings out of its package.
Next implementation target is stages 1–2, followed by the vertical slice. A larger
fleet or a polished film is downstream of passing the measured pilot.
