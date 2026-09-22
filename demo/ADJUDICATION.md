# Private human assessment records

Source-span validation establishes that a quote exists. It does not establish
responsiveness, privilege, completeness or legal correctness. The adjudication
companion keeps supplied human assessments separate from sealed execution logs.

```sh
python3 demo/adjudication.py prepare CORPUS PREPARED/tasks.json RUN NEW_QUEUE.json
```

The queue verifies the recording and reproduces each accepted review through
`review_link.py`. It includes every recorded task, including uncertain, deferred,
fallback and incomplete work. A task without a validated review has no review
attached. Every entry starts `awaiting_human`, with no decision. The private file
contains source quotes where available; it is not a public export.

A reviewer supplies a separate JSON file. Its `queue_sha256` is the hash of the
exact saved queue bytes, and each `review_sha256` comes from that queue entry:

```json
{
  "queue_sha256": "<exact queue SHA-256>",
  "reviewer_id": "<opaque reviewer identifier>",
  "decisions": [
    {
      "task_id": "<task identifier>",
      "review_sha256": "<review SHA-256, or null when absent>",
      "outcome": "needs_more_context",
      "note": "<reviewer's explanation>"
    }
  ]
}
```

Record those supplied decisions with:

```sh
python3 demo/adjudication.py resolve CORPUS PREPARED/tasks.json RUN \
  QUEUE.json SUPPLIED_DECISIONS.json NEW_ASSESSMENT.json
```

The resolver reconstructs the queue from its current source artifacts before
accepting anything. Outcomes are `confirm_review`, `reject_review`, or
`needs_more_context`. An absent or unvalidated review only permits the last
outcome. Duplicate/unknown tasks, mismatched review or queue hashes, modified
source reviews and oversized notes fail. Decisions may cover a subset: omitted
tasks and requests for more context remain unresolved. The report records UTC,
source hashes, supplied-decision hash, and assessed/unresolved counts. Outputs
are private, create-only and bounded to 16 MiB; source recordings stay unchanged.

This is an assessment record, not a reviewer authentication system. The opaque
identifier is supplied, not authenticated. It neither adjudicates automatically
nor converts agreement into benchmark truth. Confirmation does not approve a
redacted derivative or publication. Finding-level edits, authenticated review,
independent gold labels and UI integration remain separate work.

Local evidence: a pending queue was built for the actual OCR review recording,
and another retained all four states of the discovery-policy fixture. No real
human decision was supplied or invented. Tests use explicitly labeled synthetic
assessments to exercise resolution, tampering rejection and unresolved work.
