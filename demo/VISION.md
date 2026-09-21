# Direct image review: measured transport boundary

The OpenRouter adapter now supports explicit image-reference routes as well as
text routes. Displaying scans and validating OCR coordinates alone does not
establish direct image inference; the transport has separate local fixture tests.

OpenRouter documents multipart chat content with text and `image_url` parts;
private local images can use base64 data URLs. PNG is supported, but model and
provider limits must be checked separately. Source, checked 2026-09-21:
[official image-input documentation](https://openrouter.ai/docs/guides/overview/multimodal/image-understanding).

## Offline wire-shape experiment

```sh
python3 demo/vision_envelope.py INSPECTOR_BUNDLE NEW_DIRECTORY \
  --prompt 'Describe page structure without inferring missing words.' \
  --model fixture/vision-reviewer --provider fixture --pages 1 2
```

This verifies inspector asset hashes, prepares a small source-reference envelope
and a private multipart provider-request specimen, checks base64 round trips, and
records sizes and hashes. It performs no HTTP request. Fixture model/provider
labels deliberately make no claim about a real provider's capability or price.
The reference is accepted by a configured `vision_reference` route with the exact
bundle provisioned in its registry. Output directories are create-only. Input is bounded to eight pages,
8 MiB of selected PNGs and an 8 KiB prompt. Provider limits may be smaller.

For the actual two-page source fixture, an experiment with a 107-byte prompt
measured 285,299 image bytes, 380,876 provider-request bytes and a 744-byte wrapped
gateway reference. Its exact prompt, image hashes and request hash remain in the
private experiment files. The provider request exceeds the adapter's current
65,536-byte maximum inbound limit; the reference fits the pilot's 16,384-byte
gateway limit. These are transport measurements, not token or cost estimates.

## Handler integration

Keep routing text and asset references separate from image payloads. Jev receives
the bounded task description and available-capability metadata. A selected vision
handler resolves only explicitly provisioned source hashes, verifies the selected
pages, and assembles multipart content after routing. Image bytes do not pass
through the text classifier. Arbitrary prompt text must not become a file path,
remote URL fetch, model selection or provider-policy override.

The handler implements an explicit reference-input mode, immutable bounded asset
registry, separate outbound byte bound and existing durable generation admission
and receipt behavior. Text routes retain their contract. Unknown assets and
mismatched references fail before generation reservation or provider send. Live
image model/provider capability, pricing and a bounded contract probe remain
required before paid dispatch. Configuration and bounds are documented in
[the adapter guide](../docs/OPENROUTER.md#provisioned-image-references).

Record source modality separately from reviewer input modality, page hashes and
selection order, asset resolution and request-assembly timing, request byte count,
actual generation model/provider, token and cost receipts, and unresolved work.
Do not map image-only findings to OCR word offsets without supporting evidence;
page-region observations require a separate validated coordinate contract.

The preparation experiment itself does not dispatch, calibrate route quality, approve
publication, establish OCR accuracy or perform native redaction. Audio needs a
real or explicitly labeled supplemental sample and its own capability contract.

## Real scan transport replay, with synthetic providers

The integration experiment accepts an explicit private inspector bundle. It
verifies the bundle assets, copies its page PNGs into a private experiment
registry, and sends all pages (one to eight, at most 8 MiB total) through the
actual local gateway and adapter. Jev and reviewer responses remain scripted.

```sh
python3 scripts/openrouter_e2e.py artifacts/NEW_SCAN_TRANSPORT \
  --binary /absolute/path/to/braess-openrouter \
  --inspector artifacts/ocr-review-replay-v1/inspector
```

The gateway binary must be beside the adapter binary. The command makes no live
provider calls. It checks exact ordered PNG round trips, invalid-reference
rejection before generation admission, immutable startup bytes, restart refusal
on source alteration, durable receipts, and receipt retention in the sealed
observer recording and route analysis. Alteration tests affect only the copied
experiment registry; the original inspector stays unchanged.

The two-page Enron scan passed this path locally: 285,299 source PNG bytes became
an actual 380,822-byte provider request. The fixture records the received request's
byte count and SHA-256 before JSON parsing. `result.json` records ordered page
hashes, dimensions, byte lengths, manifest hash and request hash. The private
`events.json` includes the full synthetic-provider request, including source
image data; it is not a public telemetry export. `vision-recording` and
`vision-metrics.json` retain the request-bound image receipt without that payload.
These measurements differ from the earlier preparation specimen because the
prompt and model configuration differ.

This is transport evidence on real source pixels, not a semantic evaluation.
The local Jev fixture chooses a scripted route; no model has interpreted these
scans in this experiment. Live capability, quality, pricing and content approval
remain separate gates.

## Inspect submitted pages

A private execution replay can now connect its image receipt to the exact scan
pages sent to the handler:

```sh
python3 demo/serve.py --port 4183 \
  --recording artifacts/vision-corpus-transport-v3/vision-recording \
  --image-reference artifacts/vision-corpus-transport-v3/vision-reference.json \
  --image-task vision-fixture \
  --evidence-bundle artifacts/ocr-review-replay-v1/inspector
```

`vision_link.py` verifies the sealed recording, exact submitted reference bytes,
queued document identity, inspector manifest, ordered page hashes, dimensions and
byte lengths. The receipt must bind that exact reference and page order. Changed
reference whitespace, wrong documents, altered pixels, duplicate selections,
incorrect geometry and absent legacy receipts cannot acquire a source link.
The private association contains no prompt or generated answer. It can also be
saved independently, without starting the viewer:

```sh
python3 demo/vision_link.py RECORDING EXACT_REFERENCE INSPECTOR TASK_ID NEW_LINK.json
```

The viewer offers **Inspect submitted page** only after the recorded response.
Selecting it opens the source scan without finding boxes or a highlighted quote;
the accompanying OCR text is extraction evidence, not evidence of what the image
reviewer read. Rewinding or changing tasks clears the association; manually
choosing an OCR word or page returns to ordinary source inspection. Source pages
remain available for manual inspection independently of replay time. The same
existing black-and-white inspector supports both input provenance and separately
validated OCR findings, with explicit labels for their different meanings.

This association proves equality with provisioned input assets, not original
native-file authenticity, model understanding, review accuracy or an approved
redaction. Browser checks cover both actual scan pages, replay gating, manual
selection clearing and rejected mismatched associations at desktop and mobile
sizes. The original OCR-finding navigation regression also passes. Existing
public-export and frozen-package commands do not yet include this new association;
use the private loopback preview for this slice.
