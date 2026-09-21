# Two-document live pilot preparation

`pilot_plan.py` binds exactly two prepared text/OCR tasks to the dated pricing
scenario and the discovery rubric. It creates private, reviewable configurations;
it does not authorize spending, read credentials, initialize state or start a
service.

```sh
python3 demo/pilot_plan.py create CORPUS PREPARED/tasks.json PRICING_SOURCES \
  eval/rubric.discovery.json NEW_PLAN_DIRECTORY
python3 demo/pilot_plan.py verify NEW_PLAN_DIRECTORY
```

The plan fixes one worker, two lifetime Jev calls, two lifetime generation calls,
no automatic retries, explicit provider/model/output-limit bindings, loopback
ports 8178/8179 and private durable-state paths. The adapter pins the provider
through its existing `only`/`order`, disabled-fallback and required-parameter
contract. Reviewer output limits are 1,024 and 2,048 tokens; input request bodies
must fit the actual gateway JSON envelope's 16 KiB bound. The observer's 15-second
timeout exceeds the 10-second gateway and 8-second adapter deadlines.

Jev uses the existing direct TypeSafe transport. OpenRouter Decisions transport
is still separate future work. Each attempted task reserves the more expensive
reviewer scenario before the semantic decision is known. A fallback can consume
a Jev call without dispatching a reviewer. Unknown outcomes retain their monetary
reservation; partial generation receipts do not settle combined charges.

Verification rereads the pricing sources (24-hour maximum age), source objects,
prepared tasks, policy and configuration hashes. It also reconstructs the expected
runtime configurations: editing a provider or call limit and updating its file
hash does not make it match the priced plan. The plan uses absolute paths and
must be recreated when moved. Hashes establish consistency, not authenticity.

## Prepared local experiment

Ignored `artifacts/two-document-pilot-v1` contains a private combined corpus with
one text-rendered Enron email and the existing two-page TIFF's OCR text, from
separate families. Selection is deterministic: the first document of each prior
bounded development corpus. Source-manifest hashes and selection are recorded.
This is a plumbing pilot, not a representative sample or held-out accuracy test.
The protocol is explicitly hypothetical, asking about energy operations and
personal contact details. Reviewers receive text, including OCR uncertainty;
no native image pixels are sent to a provider.

The saved pricing evidence yields a total admission reservation of $1.909436034.
No spending allowance has been selected. The plan remains
`prepared_not_authorized`, and its actual journals and budgets are uninitialized.
A separate `config-check` copy passed the actual Rust adapter, Jev-budget and
request-journal create-only initializers with no credentials, service startup or
inference. `config-verification.json` records those binary hashes and exit codes.
Those local checks validate configuration/state setup, not provider access or
response contracts.

## Remaining before execution

Select the pilot's spending allowance; refresh expired price evidence; reverify
this plan immediately before startup; initialize fresh durable call limits and a
shared monetary ledger bound to `pricing.json`; and run the two tasks once with
private captures. The execution coordinator still needs to enforce this preflight
and record binary/config hashes for the live run. Do not invoke the raw fleet
command with an arbitrary estimate and call it a bound pilot.

Keep both API keys only in the child processes that need them. Preserve returned
raw responses privately, validate findings, retain unresolved reservations and
review the two outcomes before considering a larger run. A small provider probe
is the experiment that establishes the current contract; local fixtures cannot
promise complete provider equivalence. Complete billing reconciliation, native
vision/audio review and a reviewed public film remain separate deliverables.

Tests cover the fixed route/call bounds, changed source bytes, changed provider
bindings even after manifest rehashing, stale evidence, and rejection of a batch
that is not exactly two fully prepared tasks.
