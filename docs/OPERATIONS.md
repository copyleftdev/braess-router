# Operations

Run one process on a trusted Linux host. The listener and handler URLs must use
literal loopback HTTP addresses; Jev live mode uses the fixed HTTPS provider URL.
Do not expose the listener through a public proxy without designing authentication
and access controls separately.

Use the [deployment guide](DEPLOYMENT.md) to prepare a private user service.

## Configuration

Start with `config/gateway.mock.json` or `config/gateway.live.example.json`.
`rubric_path` resolves relative to the working directory. Run from the repository
root or use absolute paths. The rubric must name exactly the configured handlers
plus `fallback`. There may be 1–32 handlers, 1–16 endpoints each and at most 48
endpoints total. Labels begin with a lowercase ASCII letter and contain lowercase
letters, digits, underscores or hyphens, up to 64 bytes. Destinations must be unique.

`admission_limit` bounds active work; `tracking_limit` bounds active and uncertain
records. `deadline_ms` covers the route operation including body parsing.
`max_request_bytes` bounds the JSON envelope and request text;
`max_response_bytes` bounds buffered upstream bodies, not total process memory.
`max_jev_calls` counts reservations, not currency or provider-account usage.

`jev_rate_limit` optionally sets `max_requests` per `window_ms`. It starts with a
full-window cooldown. Limits apply to local dispatch authorization, not all clients
of the API account. Retry-After is returned only when a retry time is known.

## Durable state

Without persistence, restart loses call-budget and uncertainty history. For durable
operation, configure `budget_path` and `request_journal_path` as absolute paths in
a stable directory controlled by the service user. Initialize once:

```sh
braess-budget-init /absolute/state/calls.budget 1000
braess-journal-init /absolute/config/gateway.json
braess-router --config /absolute/config/gateway.json
```

The budget maximum must match configuration. Reservations are synced before dispatch
and never refunded. The journal records begins before dispatch and completions only
after fully validated responses. Exclusive locks prevent concurrent state owners.

Unresolved requests continue consuming admission capacity after restart. TTL expiry,
a timeout, socket EOF, or a process restart is not proof of upstream completion.
There is currently no supported reconciliation command. Scope migration is supported
only for a fully completed journal; see [offline recovery](RECOVERY.md).
Do not delete state to restore capacity. Preserve it and stop admission while
investigating the upstream outcome. This recovery limitation remains alpha work.

Configuration changes affecting journal scope are rejected on replay. Offline
compaction preserves unresolved work and scope; it does not reset the budget:

```sh
braess-journal-compact /absolute/config/gateway.json /absolute/state/archive /absolute/state/checkpoint
```

Stop the router first. Archive and checkpoint destinations must not exist.
Keep backups; these mechanisms have not established power-loss guarantees on all
filesystems and cannot detect every external file replacement or rollback.

## HTTP and shutdown

| Endpoint | Meaning |
| --- | --- |
| `POST /route` | Exactly `{"request":"..."}`; handler result or local fallback. |
| `GET /health` | Liveness. |
| `GET /ready` | 200/503 local admission snapshot; upstream health unchecked. |
| `GET /status` | Budget, admission, rate and uncertainty counters. |

Fallback reports `needs_review`. Audit output on stderr contains IDs and timings,
not request text or credentials. It is not a durable audit trail.
SIGINT and SIGTERM drain requests. Blocking storage work may delay exit beyond the
request deadline; permanently stalled storage has no proven shutdown bound.

## Acceptance still pending

Seven [provider contract cases](PROVIDER_CONTRACT.md) are captured and replayed.
Provider-specific unresolved-work reconciliation and a frozen v1 acceptance run
remain open. These captures do not prove complete provider compatibility. Deployment packaging has synthetic lifecycle checks;
host and workload acceptance still require representative validation. The small captured provider
corpus in the development workspace does not establish a universally accurate mock.
Synthetic CI checks establish local behavior, not production semantic quality.
