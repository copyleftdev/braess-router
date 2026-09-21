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
