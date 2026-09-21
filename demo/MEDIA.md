# Native media inventory and local OCR

The official native attachment archive advertises 8,789,660,717 bytes. A successful
HTTP range request acquired bytes 0–33,554,431 into ignored local artifacts. The
prefix is only a sample; its SHA-256, response-header hash, Content-Range and ETag
are recorded. It is never described as a complete native corpus.

The local prefix scan found 1,359 complete members:

| Signature | Members |
| --- | ---: |
| OLE compound storage | 702 |
| UTF-8 text | 519 |
| Unknown binary | 110 |
| PDF | 15 |
| GIF | 5 |
| JPEG | 1 |
| BMP | 4 |
| TIFF | 3 |

No recognized audio signature occurred in this prefix. That does not establish
that audio is absent elsewhere, or that unknown containers contain no media.
File signatures suggest candidate capabilities; they are not full validation.
For example, a `.doc` filename can contain plain text or a compound container.
The scanner never executes an attachment, opens a remote link or expands a nested
archive. Native IDs are preserved separately from content hashes.

All 13 image candidates decoded in bounded subprocesses using Pillow 12.1.1.
Six are 1×1 pixels. Three TIFFs contain 2, 8 and 5 pages respectively. Decoding
checks technical readability, not content, relevance or sensitivity. PDFs and
legacy Office containers remain unvalidated by a native document decoder.

## Reproduce the local stages

Optional image dependency: `demo/requirements-media.txt`, pinned to the decoder
used for these observations. OCR requires the system `tesseract` executable and
English language data; the verified environment reports Tesseract 5.5.0.

```sh
python3 demo/media.py PREFIX_FILE RESPONSE_HEADERS NEW_DIRECTORY \
  --source-url https://trec-legal.umiacs.umd.edu/corpora/trec/legal10/edrmv2nativeattach.tar.bz2
python3 demo/probe_images.py NEW_DIRECTORY/inventory.json NEW_DIRECTORY/image-probe.json
python3 demo/ocr.py IMAGE_OBJECT NEW_OCR_DIRECTORY --sha256 SOURCE_HASH --pages PAGE_COUNT
```

Acquisition used a 32 MiB initial byte range. `media.py` requires matching
Content-Range metadata, bounds individual members to 8 MiB and the scan to 128 MiB
of declared expansion or 4,096 entries. Complete objects are stored by hash;
archive paths are never used as output paths. A partial compressed stream can
end during the next member. The inventory explicitly records that termination
without pretending to validate the remaining archive or the truncated member.
Stored objects and manifests remain private and outside Git.

`probe_images.py` hashes each object before decoding. Each worker has a 512 MiB
address-space limit, five CPU seconds, an eight-second wall deadline, a 16-million-
pixel limit and at most 32 frames. It loads every allowed frame. A probe failure
is a recorded unsupported/failed result, never an implied empty image. Resource
limits do not constitute a complete hostile-file sandbox.

`ocr.py` verifies the input hash, limits OCR to one thread, uses a disposable
worker with 768 MiB address space, 30 CPU seconds, a 45-second wall timeout and a
16 MiB output-file bound. It requires the expected page count from a validated
image and checks that every expected page appears in the TSV. Empty pages are
reported explicitly. An unsuccessful run may leave partial files without a valid
mapping receipt; use a fresh output directory for any deliberate new attempt.

The local OCR sample is the two-page TIFF
`3.1027804.K0UPP3NZX0YQSHTER2EJ0QGAGOU2V2QSB.1`. It produced 581 words and no empty
pages. Raw TSV is retained privately. The derived text joins recognized words
with spaces; `mapping.json` records that transformation as
`ocr-tsv-word-join-v1`, plus character ranges, page numbers, pixel boxes and OCR
confidence. Source-image, TSV and derived-text hashes link the artifacts. OCR
confidence is not a calibrated legal-accuracy probability. There has been no
semantic review of these pages and no model/API call in these stages.

## Source-linked findings

`ocr_evidence.import_bundle` imports the native image, derived text and mapping
into a private, create-only corpus directory. Content hashes bind all three.
Validation checks word coverage, page geometry and bounding boxes before writing
a complete manifest. Failed imports can leave partial objects without a manifest.

`corpus.locate` now resolves accepted OCR quotes to both text offsets and source
page pixel boxes. Review validation verifies the native image and mapping even
when the response contains no findings. Prompts identify OCR-derived input and
its extraction uncertainty. The fleet records the original modality as `image`;
the reviewer currently receives OCR text, not pixels. This does not establish
vision-model support or OCR transcription accuracy.

## Integration still needed

The native prefix begins in a different part of the archive from the existing
40-document text sample. Join by verified native/text IDs before showing family
context; do not imply these are the same reviewed documents. Image-region
coordinates are available for evidence inspection; the replay still needs the
corresponding private image viewer.

Next stages are native/text joins, OCR/vision task routing, a tested image-capable
provider handler, source-linked evidence inspection and approved public excerpts.
The current web replay contains no native images or real Enron text. Audio and
video workers remain planned, contingent on actual corpus media or a separately
identified supplemental dataset.

## Private inspector bundle

`evidence_bundle.py` prepares browser-readable page PNGs, OCR text and word boxes
from an imported OCR corpus. It does not serve those files or add them to the
public replay. Run it into a new private directory:

```sh
python3 demo/evidence_bundle.py CORPUS/manifest.json DOCUMENT_ID NEW_DIRECTORY
```

The exporter rechecks native/text/mapping hashes, then decodes the image in a
bounded child process (768 MiB address space, 20 CPU seconds, 30-second wall
limit). Decoded frame count and every page's dimensions must exactly match the
OCR mapping. Pages retain source pixel coordinates: no crop, resize or orientation
transform. PNGs use RGBA pixels without inherited image metadata; visible source
content remains present. Output is limited to 64 MiB per PNG and 128 MiB total.
These resource limits are not a complete hostile-file sandbox.

A final manifest binds page hashes, text, word boxes, source hashes, decoder
version and exporter source hash. A failed export can leave partial files, but
no completed manifest. Existing output directories are refused. The bundle is
private source material, not a reviewed publication or native redaction.
`review_performed` and `publication_approved` remain false. OCR confidence remains
an extraction signal, not evidence of transcription or legal accuracy.

The actual two-page TIFF exported with all 581 OCR word locations. Tests compare
synthetic multipage source pixels against exported PNG pixels and reject mapping
page-count/dimension mismatches. The next UI integration can load these explicit
assets and use the same source-page pixel coordinate system for highlights.
