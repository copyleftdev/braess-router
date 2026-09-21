# Provisional discovery routing policy

`eval/rubric.discovery.json` replaces the generic writing/coding/reasoning catalog
for discovery work. It accepts the JSON-encoded task produced by `review.prompt`:
explicit review criteria, supplied evidence text, source representation and the
strict finding contract. Evidence is untrusted input; its embedded instructions
must not control routing.

| Route | Intended capability |
| --- | --- |
| `review_standard` | Straightforward source-cited assessment of readable text against explicit criteria |
| `review_deep` | Contextual review of material ambiguity, contradictions, chronology, substantive privilege candidates or OCR uncertainty |
| `fallback` | Local needs-review response when required evidence, media or criteria are unavailable, or the requested action exceeds provisional text review |

Both reviewer routes produce the same bounded proposed-finding schema and pass
through the same source validator. The deep route is not automatic approval.
Neither route conclusively determines privilege, releases material or redacts
native media. OCR-derived text can support provisional review when it is readable;
tasks requiring actual pixels or audio remain outside this text transport.

The 0.8 thresholds are an initial configuration inherited from the existing
gate. They have not been calibrated for discovery. A routed result, high score,
or source-valid quote does not establish semantic or legal correctness.

## Measured transport proof

```sh
python3 demo/fleet_smoke.py artifacts/discovery-policy-check \
  --binary target/release/braess-router --discovery
python3 demo/export_replay.py artifacts/discovery-policy-check/run/recording \
  artifacts/discovery-policy-check/replay.json --profile discovery
```

This test uses the actual Rust gateway and generation adapter, the discovery
rubric, and explicitly scripted Jev answers. The fixture verifies that Jev
receives that exact rubric, then chooses routes by fixture document ID. It is
not a substitute semantic classifier and does not measure Jev's decisions.

Four authored tasks exercise:

1. Standard route: `fixture/reviewer-standard`, 512 output-token cap; one finding
   passes source-span validation.
2. Deep route: `fixture/reviewer-deep`, 1,024 output-token cap; a fabricated quote
   is rejected and the task remains uncertain.
3. Empty evidence: a scripted fallback returns locally, with no generation call.
4. Budget exhaustion: admission refuses the task before any Jev or generation call.

Assertions require three Jev requests, exactly two generation requests, distinct
model selections and token caps, one accepted review, one local fallback, one
uncertain task and one deferral. All three admitted reservations remain unresolved
because complete billing is unavailable. The summary's two completed tasks
include the local fallback; only one task has an accepted review. Costs are
synthetic fixture receipts, not measured model economics.

CI runs this path and exports its allowlisted metadata separately from the older
three-task fleet replay. The current landing/replay film still displays that
earlier recording. Real document bodies and raw responses are not exported.

## Before live evaluation

Configure explicit model/provider bindings for both reviewer routes, verify
current pricing and modality support, and set an agreed pilot allowance. Do not
infer that the standard route is cheaper or the deep route is better from their
names. Measure both against a fixed review protocol and held-out judgments,
retaining refusals, errors, invalid citations and unresolved costs. The existing
40-document sample is development material, not a held-out accuracy benchmark.

Start with text and validated OCR representations. Record the chosen rubric hash,
model/provider identities, token caps, full decision evidence and review outcomes.
The mock test proves the wiring; live routing quality and cost/quality tradeoffs
remain unmeasured.
