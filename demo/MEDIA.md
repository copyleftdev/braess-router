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

## Integration still needed

The native prefix begins in a different part of the archive from the existing
40-document text sample. Join by verified native/text IDs before showing family
context; do not imply these are the same reviewed documents. The OCR mapping is
not yet wired into `review.locate`, which currently handles text-rendering offsets.
A future accepted OCR finding must resolve to image-page boxes through this
mapping and retain uncertainty about extraction errors.

Next stages are native/text joins, OCR/vision task routing, a tested image-capable
provider handler, source-linked evidence inspection and approved public excerpts.
The current web replay contains no native images or real Enron text. Audio and
video workers remain planned, contingent on actual corpus media or a separately
identified supplemental dataset.
