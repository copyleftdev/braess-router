# Bounded reviewer execution

`fleet.py` now connects prepared tasks, spending reservations, the actual Braess
HTTP gateway, the OpenRouter generation adapter and exact-span validation.
It takes one to four workers and at most 400 prepared tasks. Every task is tried
once in the run. There is no recursive spawning, automatic retry or automatic
resume of uncertain work.

Before dispatch, it verifies the corpus-manifest hash, request hashes, source
identities and unique safe task IDs. The observer reserves shared budget before
opening a connection. Refused admission produces a `task_deferred` event rather
than pretending that an upstream request failed. A network/handler problem stays
uncertain. Complete billing is still unavailable, so monetary estimates remain
reserved even when review output is received successfully.

A successful gateway response is not sufficient to count a completed review.
The runner stores the raw response privately, parses the returned answer as a
review report, verifies each source span, and synchronizes the validated report
before appending `review_validated`. Only then does it record `task_completed`
with outcome `review_validated`. A fabricated quote is retained in its private
response artifact but yields `review_validation_failed` and an uncertain task.
This measures structural/source validity, not legal correctness.

## Offline full-path proof

```sh
cargo build --locked --release --bins
python3 demo/fleet_smoke.py artifacts/fleet-check --binary target/release/braess-router
```

The smoke launches the actual Rust gateway and OpenRouter adapter against local
Jev and generation fixtures. Three authored documents exercise one valid review,
one fabricated quote and one budget deferral. It asserts exactly two generation
requests and writes the results and executable hashes. No paid requests occur.
This test is now included in CI. The fixture uses the existing capability rubric;
it does not validate a discovery-specific semantic policy or real model accuracy.

## Run prepared tasks

Once the gateway, discovery rubric, provider pricing and pilot allowance have
been configured and validated, the command is:

```sh
python3 demo/fleet.py CORPUS PREPARED_TASKS.json NEW_RUN_DIRECTORY \
  --gateway-url http://127.0.0.1:8080/route \
  --budget EXISTING_BUDGET_DIRECTORY \
  --pricing-sha256 PINNED_PRICING_SHA256 \
  --estimate-usd CONSERVATIVE_PER_TASK_ESTIMATE \
  --scope live --workers 2
```

The runner requires a shared ledger even for synthetic scope. Scope is an explicit
caller declaration; the runner cannot establish whether a separately configured
gateway is live from its loopback address alone. It never reads provider keys.

The private run directory contains a hashed input manifest, hash-chained recording,
raw gateway responses, validated review reports and a budget/result summary.
Review events refer to report hashes and counts; they do not copy quotations into
the metadata log. Generation IDs and usage are recorded when supplied by the
adapter. Internal Jev probabilities and dispatch intervals still require gateway
instrumentation; current timings are measured at the observer boundary.

Do not re-run an uncertain task merely because its run directory has been sealed.
Sealing means the local log closed, not that upstream work stopped. A new run has
a new observation ID and is a deliberate new attempt; cross-run deduplication and
a resume/adjudication controller are not implemented. Task and budget outcomes
remain distinct from complete billing reconciliation.

The web replay is still the six-task protocol slice. It does not yet consume these
review events or source documents, and the export gate continues to refuse live
content. The legal corpus has prepared tasks but has not been sent to a provider.
Paid execution remains gated on the selected dollar cap and verified estimates.
