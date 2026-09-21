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
The private viewer consumes these associations through the server-verified
`review-links.json` asset.

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


## Private replay with findings

```sh
python3 demo/serve.py --port 4176 \
  --review-corpus CORPUS \
  --review-tasks PREPARED/tasks.json \
  --review-run RUN
```

All three review arguments are required together. Before binding the loopback
port, the server verifies the sealed run and rechecks every completed validated
review against the supplied inputs. It freezes the resulting replay and finding
associations in memory. There is a 200-task viewer limit and 16 MiB association
limit. No saved link file is accepted on trust, and no publication export is made.

The pale task inspector shows quotes, reviewer notes, character ranges and page
numbers when present. Findings appear at their validation event, disappear when
scrubbing earlier, and follow task selection. Rejected, fallback and deferred
tasks have no accepted finding association. A mismatch in run, task, review hash
or validation timestamp hides findings and shows a recovery message.

Live scope is supported in this private view with explicit live-provider labels
and partial-cost wording. Verification to date used the saved synthetic discovery
run; the live-label browser test intercepts fixtures and is not a paid live run.
The default viewer and public fixture exporter remain separate. An independently
loaded OCR inspector still has no automatic finding-to-page navigation; that
integration and actual live corpus review remain pending.

`demo/test_linked_replay.cjs` checks the four-task discovery fixture on port 4176,
including task/clock isolation and mismatched association responses. The generic
three-task browser suite accepts `BRAESS_REPLAY_URL` to test a separate default
viewer instance.
