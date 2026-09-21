# Recorded review to source association

`review_link.py` verifies one completed finding set against the prepared task,
source corpus, sealed observer recording and saved gateway response. It writes
a private association artifact for later replay integration; it does not run a
reviewer, serve documents, publish evidence or modify a recording.

```sh
python3 demo/review_link.py CORPUS PREPARED/tasks.json RUN TASK_ID NEW_LINK.json
# For an OCR task, also verify the exact inspector assets:
python3 demo/review_link.py CORPUS PREPARED/tasks.json RUN TASK_ID NEW_LINK.json \
  --inspector INSPECTOR_BUNDLE
```

Verification requires:

- Prepared task and corpus hashes matching the fleet input manifest and recorded
  corpus provenance; task identity derived from document, source and protocol.
- One queued → started → received → validated → completed event sequence for the
  selected task, with matching source/family/modality and exact request-body hash.
- A successful nonfallback response whose bytes match the recorded response hash.
- A saved report matching the recorded review hash and reproducible by running
  source-span validation against the answer inside that response.
- For an inspector association, matching native/text/mapping identities plus
  page images, text and word assets reproducible from the original OCR corpus.
  The existing bounded renderer runs in a disposable child. Its optional Pillow
  dependency is required. Decoder changes that alter serialized PNG bytes require
  rebuilding the inspector bundle; they are not silently treated as equivalent.

The artifact carries run/task/document IDs, source/protocol/input hashes,
response metadata, the validated report and its source locations, event hashes,
and the validation event's elapsed time. A consuming replay must check its own
run ID and task ID and reveal findings only at or after that recorded time.
The current UI does not consume this artifact yet.

The run's `synthetic` or `live` scope is preserved. A locally generated link has
zero new provider calls even when it refers to a previous live run. Integrity
checks do not authenticate a provider, establish legal accuracy, or approve
publication. Rejected, deferred, incomplete and fallback tasks cannot acquire a
completed-review association through this command; their recorded outcomes remain
available in the ordinary replay.

Validation includes both text and OCR fixtures, mixed-document/request rejection,
changed response bytes, altered report content, and replacement image pixels
with internally consistent but wrong manifest hashes. A link was also verified
against the actual saved local `discovery-policy-v2` execution: synthetic provider
scope, document `3.0.A`, one validated finding. This is not a live Enron review.
