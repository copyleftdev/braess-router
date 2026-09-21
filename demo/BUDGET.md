# Run-level spending reservations

`budget.py` provides a shared SQLite ledger for the demo's concurrent workers.
It uses WAL, FULL synchronization and immediate transactions. Creation is explicit
and refuses existing state; opening requires an existing regular database and
matching pricing-manifest hash. Files live inside a privately created directory.

Amounts are decimal strings converted upward to integer nanodollars. Binary
floating-point money, negative values and nonfinite values are rejected.
Reservations consume available allowance atomically, before dispatch permission
is returned. Multiple processes share the same database. Each attempt ID is
unique; an existing ID never grants permission for another dispatch. The lifetime
attempt count never decreases, even when a completion reports zero cost.

Completion settlement requires a receipt hash and reported total charge. Replaying
that exact receipt is idempotent; a conflicting receipt is rejected. A completed
charge releases only the unused estimate. If the reported charge exceeds its
reservation, the ledger records it and permanently freezes further admission.
It does not hide an overrun by rejecting the financial evidence. There is no
force-release or unfreeze command. Unknown outcomes retain their full estimate
across process exit and restart.

## Observer integration

`observe(..., budget=ledger, estimate_usd="...")` reserves against a stable hash
of the run ID and task ID before recording `request_started` or opening a network
connection. That event includes `budget_attempt_id`, `budget_reserved_usd`, and
`pricing_sha256`, making the reservation link available to later visualization.
A recorder failure after reservation conservatively leaves the reservation held.
Live-scope observation refuses to dispatch without a ledger. Other applications
can still call Braess independently: this is the demo observer's boundary, not
a network-wide enforcement mechanism.

The current gateway response lacks a complete combined Jev/generation charge.
The observer therefore does **not** automatically settle from a generation-only
receipt. Even a successful task retains its financial reservation until complete
charge evidence is available. Task completion and financial reconciliation are
separate states. Synthetic smoke estimates are test amounts, not incurred cost.

## Limits before a paid pilot

The pilot cap remains unselected. No new paid requests were made to test this
ledger. A [dated text-pilot pricing snapshot and capacity-based quote](PRICING.md)
now exist, with [a bounded configuration plan](PILOT.md). Execution-time
enforcement of that binding, modality-specific estimation,
provider contract capture and complete receipt reconciliation remain before
using this as a paid fleet controller. A pricing hash binds state to the caller's
selected catalog; the ledger does not establish that the catalog is accurate.
It trusts the caller's estimate and charge evidence.

An admission envelope is not a provider-guaranteed invoice ceiling. Unexpected
pricing or underestimated image/audio/context costs can exceed it; freeze-on-
overrun prevents subsequent admission, not already dispatched work. Account-level
provider caps can provide another boundary after their behavior is verified.

There is no distributed ledger, multi-host coordination, automatic scheduler
resume or billing lookup yet. The database must reside on local storage with
working SQLite locking and fsync semantics. The parent directory must exist.
Protect it from concurrent filesystem replacement; hashes are not authentication
against a writer who can modify local state. Lock contention times out after five
seconds and dispatch stays denied. Inspection currently scans the bounded attempt
history; benchmark a larger workload before selecting a larger fleet size.

## Evidence

`test_budget.py` checks independent-process contention, restart retention, abrupt
process exit after commit, duplicate IDs, idempotent receipts, overrun freeze,
exact upward rounding, policy mismatch and lifetime attempt exhaustion.
`test_observe_budget.py` checks that missing/exhausted budgets cause no network
call and that transport failure retains both the reservation and its trace link.
`smoke.py` exercises the actual Braess binary with six budgeted local fixture calls;
it writes `budget-status.json` alongside the verified recording. None of these
checks constitutes evidence of live pricing accuracy or paid legal-review quality.
