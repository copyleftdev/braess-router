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
private captures. The execution coordinator described below enforces this preflight and records
binary/config hashes for the run. Do not invoke the raw fleet
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


## Check current readiness without execution

```sh
python3 demo/pilot_run.py PLAN_DIRECTORY BUILT_BINARY_DIRECTORY \
  --preflight-output NEW_PRIVATE_READINESS.json
```

This mode needs no credentials or allowance. It verifies the source, pricing,
configuration and unattempted plan, then hashes all four current executables and
coordinator sources. Its private, create-only report records the reservation,
pricing expiry and call limits. Place the report outside the one-shot plan;
readiness does not create execution claims, initialize journals, bind ports,
start processes or make provider calls. It does not establish provider access,
model quality or spending authorization. The execution path still performs its
own checks immediately before dispatch; a saved readiness report cannot bypass
those checks.

The current local binaries passed this offline check with the two-document plan.
The real plan remains unattempted, with no selected allowance. Tests verify that
readiness leaves plan bytes unchanged, refuses an attempted plan, protects its
output from overwrite and never invokes process startup or endpoint checks.

## Execute once after allowance selection

```sh
# Supply TYPESAFE_API_KEY and OPENROUTER_API_KEY through the environment.
python3 demo/pilot_run.py PLAN_DIRECTORY BUILT_BINARY_DIRECTORY \
  --allowance-usd SELECTED_ALLOWANCE
```

The coordinator refuses stale or changed plans, insufficient allowance, missing
credentials, occupied loopback endpoints and any previously attempted or
initialized plan. A create-only, fsynced `execution.json` claims the attempt before
initialization. It binds the plan/configuration, executable and coordinator-source
hashes to the selected allowance. The claim is never removed on failure.

It initializes fresh monetary, Jev-call, request and generation journals; starts
the real adapter and gateway; waits for local health responses; and rechecks the
plan and executable hashes immediately before fleet admission. Exactly one worker
processes the two tasks, without automatic retry or resume. Gateway and adapter
children receive only their respective named provider credential plus a small
base environment. Initializers receive neither key. Credentials are not written
to the execution claim, commands or configuration files.

After completion or exception, the coordinator stops its children and writes
`execution-summary.json`. Unknown attempts remain reserved and an aborted plan
cannot be rerun. Local logs and the fleet's raw captures remain private. A
`fleet_finished` status means the task loop finished, not that both reviews
succeeded or that all charges were reconciled. Inspect the recorded task outcomes
and budget before considering another explicitly planned experiment.

The coordinator was tested with fault injection for missing credentials,
insufficient allowance, initialization failure, changed preflight after startup,
unknown dispatch results and credential isolation. A separate local startup-only
check used the actual Rust binaries and dummy credentials, replacing fleet dispatch
with a no-request callback. Both services initialized, answered health checks and
stopped; monetary attempts and provider calls were zero. This checks process
orchestration, not the live provider contract. No real pilot has run yet, and the
allowance question remains unanswered.
