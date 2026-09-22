# Review findings and draft text redactions

`review.py` builds a bounded review request and validates a strict JSON response.
Every response must identify its source document and source hash. Each finding
includes an exact quote, character offsets, a short explanation and one of three
kinds: `issue_highlight`, `privacy_candidate`, or `privilege_candidate`.
Responsiveness can be `responsive`, `nonresponsive` or `uncertain`. Responsive
reports require at least one issue highlight. None of these labels is accepted
as evidence of legal correctness merely because it has valid source coordinates.

The validator rejects unexpected/duplicate fields, duplicate finding IDs, changed
source objects, fabricated quotes, invalid ranges and unbounded output. It returns
verified byte/character locations and a hash of the original reviewer response.
The source is not silently repaired, whitespace-normalized or truncated to make a
model's answer fit. Imported OCR bundles additionally resolve quotes to original
image pages and pixel boxes, with native-image and mapping hashes. OCR confidence
does not establish transcription accuracy. Native PDF and audio locations are
not yet supported.

`redact(..., approved_ids=[...])` requires specific candidate IDs. It unions
approved overlapping ranges and writes a separate UTF-8 derivative with the
selected text actually removed, plus a receipt linking the original, reviewer
response and derivative hashes. Originals are untouched. Repeated exact quotes
remaining elsewhere are reported; approval for one span does not authorize a
silent document-wide replacement. The derivative is marked not approved for
publication. This does not establish complete sensitive-data coverage, redact
native attachments or constitute a legal privilege determination. For OCR input,
it removes text only from the derived transcript; the original image pixels
remain unchanged and must not be treated as a redacted image.

## Prepare review tasks without spending

Create a private JSON protocol with exactly these fields:

```json
{
  "id": "your-matter",
  "version": "1",
  "scope": "reviewed_production_request",
  "production_request": "Your explicit request for production and review criteria."
}
```

A synthetic exercise must use `scope: "synthetic_protocol"`. That scope is an
explicit caller assertion, not a certification that a lawyer reviewed it. Do not
substitute a fabricated request when evaluating TREC topic labels: use a verified
protocol matching the chosen topic and disclose how its instructions were derived.

```sh
python3 demo/prepare_review.py CORPUS_DIRECTORY PRIVATE_PROTOCOL.json NEW_OUTPUT_DIRECTORY
```

The output contains stable task IDs, family/source/protocol hashes and bounded
prompts. Corpus judgments stay outside the prompts. Documents exceeding the
initial gateway body bound are listed as requiring chunking, not dropped or
silently shortened. Prepared tasks contain source content and remain private.
They are not served by the replay server. Preparation makes no provider calls and
does not claim that a reviewer ran.

Next: bind prepared tasks to the discovery-specific Jev rubric and actual reviewer
handlers; persist bounded raw reviewer responses; validate before creating any
accepted finding; record finding and approval events for replay. Add chunking and
source-coordinate reconciliation before treating long documents as reviewed.
