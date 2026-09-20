# Offline inspection and configuration migration

Stop the service before maintenance. Keep its budget, journal, original configuration
and rubric together. Do not initialize a replacement budget, delete unresolved
entries, or infer upstream completion from a timeout, TTL, EOF or process death.

## Inspect without modifying state

```sh
braess-journal-compact /absolute/config/gateway.json --inspect
```

Inspection takes the same exclusive budget and journal locks as other maintenance.
It refuses an active owner, malformed state or a mismatched configuration. The JSON
report includes spent reservations, total begun/completed attempts, pending count
and bounded pending details. Details may be truncated; use the total pending count.
Inspection does not append records, release reservations, or probe an upstream.

## Migrate a completed history

Scope-bound changes, including rubrics, endpoints, admission limits and rate policy,
require explicit migration. Prepare a separate new configuration and, if needed, a
separate new rubric. Preserve the old files unchanged for inspection and recovery.
Both configurations must name exactly the same budget path, journal path and maximum
call count. Budget extension and state relocation are not supported by this command.

```sh
braess-journal-compact /absolute/config/old.json \
  /absolute/state/pre-migration.archive \
  /absolute/state/migration.checkpoint \
  --migrate-to /absolute/config/new.json
braess-journal-compact /absolute/config/new.json --inspect
```

Archive and checkpoint paths must be new names in the journal's directory. Migration
requires zero unresolved attempts. It validates both configurations, holds the budget
lock throughout replacement, creates and syncs a checkpoint, archives the original
journal, verifies checkpoint replay, replaces the journal and syncs its directory.
Counters, next request identity and spent budget are preserved. It performs no
provider calls and does not edit either configuration file.

After successful inspection, update the service to use the new configuration and
start it. The old configuration will fail the journal scope check. In an installed
bundle whose unit points to `config/gateway.json`, activate the prepared configuration
at that path while stopped; retain the old configuration and rubric separately.

## Interrupted migration

A nonzero exit does not necessarily mean replacement did not occur. Leave the
service stopped and preserve every file. Run `--inspect` with each saved configuration:

- If only the old configuration opens, the journal still has its original scope.
- If only the new configuration opens, replacement occurred; verify the counters
  and archive before activating the new configuration.
- If both open, their scope-bound fields are identical; this check cannot distinguish
  them. Compare the preserved archive and migration output.
- If neither opens, do not reset or repair state automatically. Investigate lock
  ownership, file integrity and configuration paths before taking further action.

Do not overwrite existing archives or checkpoints when retrying. The test suite
injects errors at checkpoint sync, archive sync, replacement and directory sync;
it verifies preserved budget bytes and replayable old/new scopes. Those tests are
not proof of machine power-loss durability on every filesystem.

## Unresolved work

Migration and restart cannot clear uncertainty. A request with no validated completion
continues consuming endpoint capacity. The operator can inspect the records and
investigate upstream outcomes, but this release has no command to attest completion
or force-release an unresolved charge. Preserve evidence and keep affected admission
closed; never edit the journal to manufacture a completion. Provider/handler-specific
reconciliation remains a separate acceptance requirement.
