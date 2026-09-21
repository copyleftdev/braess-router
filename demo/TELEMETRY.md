# Routing evidence and local timing

Gateway responses now carry `routing_trace` on operations that entered the
executor, including failures and deadlines. Ingress rejection or malformed HTTP
input can occur before execution and therefore has no trace. Old recordings
without traces remain readable; missing values are unknown, never zero-duration
stages.

All offsets are integer nanoseconds from one gateway-local monotonic start:

| Field | Observation |
| --- | --- |
| `decision_send_started_ns` | Jev transport send was about to be attempted |
| `decision_validated_ns` | Complete Jev response passed the routing contract and gate |
| `handler_send_started_ns` | Selected handler transport send was about to be attempted |
| `handler_validated_ns` | Complete handler response passed gateway JSON/transport validation |
| `finished_ns` | Local execution returned or reached its deadline |

A send boundary is not proof of delivery or provider acknowledgement. Handler
validation does not mean a review finding is valid: the fleet validates the
returned review afterward. Local completion does not resolve uncertain remote
work. A client disconnect may prevent the trace from reaching the observer;
this response metadata is not a durable server event journal.

The interval between each send start and validation includes local transport and
validation overhead. Admission, endpoint selection and journal writes outside
those boundaries remain in the gaps. Do not describe these as pure model inference
latencies, or align the gateway clock directly with the observer clock. The
observer receives the trace with the response; it does not receive live stage
notifications.

`decision` retains the validated model choice, full bounded route distribution,
confidence, supported score, configured thresholds, final route and gate reason.
For example, low confidence can retain the model's `general` choice while the
gate selects `fallback`. Contract-invalid answers are not copied into telemetry.
Scores are provider outputs, not calibrated legal-accuracy probabilities. Labels
come from the operator rubric; no document text, upstream diagnostics, URLs or
credentials are included.

`routing_trace.py` validates field allowlists, finite probabilities, distribution
shape, threshold consistency and monotonic boundary order before recording.
The fleet publication profile further restricts route labels to its known
synthetic catalog. Live publication remains refused.

The integration gate checks accepted routes, fallback, malformed and invalid
decisions, failed handlers, deadlines and refusal before dispatch. The fleet
smoke checks that gateway traces survive capture and validation. These tests use
local fixtures, not paid inference. The committed web replay displays route
probabilities, gate minimums and separate Jev/handler timing bars. Evidence only
appears once the containing response is visible at the observer clock; missing
timing endpoints remain unknown. Durable server-side telemetry remains pending.

## Private route analysis

```sh
python3 demo/run_metrics.py RUN/recording NEW_METRICS.json
```

This creates a private, create-only analysis artifact from a sealed recording.
It verifies the event chain, checks that input bytes remain unchanged during
verification, and records source-file and analyzer hashes. It makes no provider
calls and does not authorize publication. Task identifiers and provider metadata
can still be private even though source document text is absent.

Each task preserves modality, final observed route, model choice and gate scores,
policy, requested/observed models, provider identifiers, terminal state and
reason, token counts, reported generation cost, reservation, finding count, and
the contributing event sequence numbers. The report includes route cohorts and
a separate group for tasks without an observed route. Deferred, uncertain, and
incomplete tasks remain represented.

Timing summaries use nearest-rank p50/p95 with explicit observed and missing
counts. Queue wait uses observer event offsets; request duration uses the
observer's recorded elapsed milliseconds. Jev and handler intervals use their
respective gateway send/validation boundaries. Gateway completion is an offset
from gateway start. These clocks are not aligned or subtracted from one another.
No measurement is invented for a missing boundary or absent response.

Generation receipt subtotals retain decimal arithmetic. With no receipts, the
subtotal is null. Reservations are retained separately and never added to
charges. Total cost and savings remain null: the recording does not establish
complete billing or a counterfactual baseline. Synthetic runs keep their scope;
their cost receipts are fixture values, not actual provider charges.

Route cohorts are descriptive observations, not randomized comparisons. A tiny
sample's p95 is not a production latency estimate. Finding-span validation is
not a measure of legal accuracy. These artifacts support later visualization;
the browser derives the timing subset directly from visible replay events.

The **Across the routes** section groups returned routes, preserving uncertain
tasks in their observed route cohort. It shows completed/uncertain/pending
counts and nearest-rank client, Jev and handler medians with sample coverage.
Tasks without a returned route are counted separately. Rewinding removes future
responses and outcomes. This view does not load the final analysis artifact,
which would expose results ahead of the clock. Its final values are checked
against `run_metrics.py` output by `test_route_comparison.cjs`, using the saved
four-task discovery fixture. The browser test requires that fixture and its
`route-metrics-v2.json` artifact; it intercepts replay data on the local preview
at port 4180 and never invokes a provider.
