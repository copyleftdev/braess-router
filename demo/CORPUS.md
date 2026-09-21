# Corpus acquisition and evidence locations

The first development corpus is now locally acquired from the
[official TREC Legal Enron v2 index](https://trec-legal.umiacs.umd.edu/corpora/trec/legal10/):
`edrmv2txt-v2.tar.bz2` and `seed.csv`. The archive contains text renderings of emails
and attachments. It is not the native-attachment archive, and no image, audio or
video capability can be claimed from these text files. Public-film reuse and
excerpt approval remain separate work before publishing corpus content.

The initial bounded sample in ignored local artifacts contains:

| Observation | Count |
| --- | ---: |
| Source documents | 40 |
| Unique content hashes | 34 |
| Containing-email families | 25 |
| Attachment text renderings | 17 |
| Documents with conflicting topic judgments | 2 |
| Verified character-to-byte span roundtrips | 40 |

These are the first matching training-seed IDs encountered in archive order.
They are for implementation, not a representative sample or a held-out benchmark.
Some documents have multiple topic judgments. Raw label counts include conflicts;
never use them directly as an accuracy denominator. The complete seed file has
48 document/topic pairs with multiple assessment values. Both assessed/unassessed
pairs and contradictory responsive/nonresponsive pairs occur. The loader preserves
all distinct records and explicitly lists conflicting topics. It does not infer
adjudication order or silently select a preferred label.

TREC's index defines the seed columns as containing-email identity (with an
attachment hash when applicable), topic, assessment and document identity.
Assessments -1 and -2 remain `not_assessed`; they are not negatives. The importer
matches the document identity to the archive filename and derives its family
from the seed's containing-email column. Missing parent records remain missing;
family membership does not imply the complete email family is in this sample.

## Reproduce ingestion

After acquiring the source files locally:

```sh
python3 demo/corpus.py \
  artifacts/corpus-source/edrmv2txt-v2.tar.bz2 \
  artifacts/corpus-source/seed.csv \
  artifacts/enron-development --limit 40
```

Use a fresh output directory. The importer hashes both source files, scans the
archive with member/count/expanded-byte bounds, and never extracts archive paths
to disk. Absolute paths, traversal, links and device members are rejected. Selected
text is stored under its SHA-256 in a private object directory. Document IDs,
source member names, original text hashes, family IDs, judgments, encoding,
normalization and byte/character counts are preserved in `manifest.json`.
The importer does not parse or execute document macros, attachments or scripts.
The archive is an acquired, trusted-source input; the Python parser itself is not
a general-purpose hostile-archive sandbox.

Strict UTF-8 decoding avoids silently replacing evidence. Unsupported text is
listed as excluded. There is no whitespace normalization: the stored text uses
identity normalization. Complete ingestion of the requested sample does not mean
the entire archive has been scanned or the entire corpus has been preserved.
An interrupted or rejected ingest may leave partial objects without a manifest;
never treat that directory as a completed corpus or retry into it.

`locate(root, document, start=..., end=..., quote=...)` verifies the object's hash,
checks exact quote equality, and returns both character and UTF-8 byte offsets.
It refuses mismatched quotes, stale objects and invalid ranges. These coordinates
refer to the text rendering, not native PDF pages or audio timecodes. OCR, image
regions and transcript alignment will require their own coordinate mappings.

The source archive and extracted content remain under ignored `artifacts/` and
are not served by the replay server. The existing web replay still contains only
synthetic protocol metadata; no real Enron documents have been sent to a model
or added to that public-style export.

## Before evaluation and multimodal review

- Select an explicit production request and its review guidelines.
- Establish adjudicated labels where training seeds conflict; exclude unresolved
  conflicts from scored outcomes and report their coverage.
- Group entire families and exact/near-duplicate content before creating splits;
  this sample is not a frozen evaluation split.
- Acquire and inventory native attachments separately. Verify any image/audio
  examples actually exist; supplemental media must be labeled separately.
- Preserve source-specific identifiers and coordinates through extraction.
- Obtain reviewed model findings, validate spans, and only then build the
  source-content export for the film.
