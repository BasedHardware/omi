# Historical memory repair

Historical `users/{uid}/memories` rows are retained compatibility data, not a
second product authority. Normal reads need no migration. Normal edits and
deletes use `MemoryService` lazy materialization/tombstoning automatically.

## Diagnose

Use read-only, content-redacted inspection to identify the UID, stable memory
ID, physical origin, canonical revision/generation, and historical override
state. Confirm the released surface result before considering a repair.

## Supported repairs

- Repair one malformed canonical control/head document only with the existing
  dry-run-first, `--confirm-uid` utility for that exact document.
- Reconcile a known legacy-backfill artifact only through the deterministic
  remediation planner/executor, preserving evidence and canonical journals.
- Retry historical row/vector cleanup only after an active override or
  tombstone is durably visible.
- Rebuild derived keyword/vector state from authoritative canonical items and
  outbox fences; never treat a provider row as authority.

Every mutating repair is single-UID, explicit-ID or bounded-plan, dry-run first,
and generation-fenced. It must not grant product access, change a cohort, scan
all users, invoke an LLM, or bulk re-embed historical data.

## Forbidden operations

- enrolling or activating a UID;
- general legacy-to-canonical account backfill;
- writing a new historical memory row;
- deleting historical content before the canonical override/tombstone commits;
- bypassing account generation, locked-memory, ownership, or privacy checks;
- using text similarity to choose identity or deletion precedence.

If a repair utility still requires a whitelist acknowledgement or describes an
account as enrolled/dogfood, stop and update the utility to the universal
authority before using it.
