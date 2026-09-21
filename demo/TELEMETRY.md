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
local fixtures, not paid inference. The committed web replay predates these
traces; stage visualization and durable server-side telemetry are still pending.
