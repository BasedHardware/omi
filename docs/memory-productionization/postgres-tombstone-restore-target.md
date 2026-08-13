# Inert PostgreSQL tombstone restore target

Status: target-side P7 participant only. It is not a restore runner, source
adapter, traffic gate, or production activation.

## Narrow claim

`PostgresTombstoneRestoreTarget` accepts one already-validated PostgreSQL
restore coordinate and terminal manifest records. Inside one serializable
transaction it assumes the separately provisioned `omi_platform_restore` role,
sets transaction-local restore coordinates through a fixed security-definer
operation, and installs an account-scoped terminal safety fence for each
record. It appends one content-free application receipt per `(account,
restore)` and returns the core `TerminalApplicationOutcome` shape.

Exact replay returns the original result and timestamp-derived target receipt.
A changed terminal record or restore coordinate under the same identity is a
closed conflict. Existing higher deletion epochs and already-deleted or absent
accounts cannot be weakened; they produce `already_absent`. A higher epoch is
the receipt's retained witness, so replay does not insert a redundant lower
fence. Started callback
operations are drained before the transaction may commit, and an ignored
failure rolls the transaction back.

The restore role receives only schema usage and the two named functions. It
receives no table read/write privilege, arbitrary SQL capability, application
role, migration authority, or traffic authority. The retained fence and
receipt tables contain only opaque account/restore coordinates, versions,
digests, closed results, and timestamps.

The held API can apply multiple records in one serialized transaction. The
coordinator-compatible `applyTerminalRecord` seam intentionally opens one
serialized transaction per record; the outer source-feed fence still surrounds
the complete manifest loop. It does not claim one PostgreSQL transaction for
the whole manifest, and durable per-record receipts make partial progress
explicit and replayable.

Migration 0026 deliberately does not create a database principal. Local test
and deployment infrastructure must provision the distinct NOLOGIN
`omi_platform_restore` role before applying the migration, just as it owns the
other runtime roles.

## Exact nonclaims

- The target does not obtain, verify, or self-attest the retention-locked
  terminal set, source snapshot, source high-water mark, or held source-feed
  fence. Those belong to the restore coordinator's independent source ports.
- The target does not prove that the supplied restored-snapshot digest names
  the database connected to this pool. Infrastructure must bind the pool to
  the restored generation before constructing the participant.
- Installing a retained target fence does not mutate the subordinate legacy
  control projection, dispose product data, open traffic, mint authority, or
  satisfy the complete replay checkpoint by itself.
- Current application authorization paths do not yet consume the restored
  terminal fence. A pre-traffic gate and a real deletion-race restore drill
  must prove that no request can bypass it before this result can support
  cohort activation.
- Backup/PITR, legacy restore targeting, external/search/vector/stranded-data
  cleanup, RPO/RTO, approvals, and manual traffic release remain separate
  gates.

## Verification boundary

Fake-driver tests prove named-operation order, exact outcome construction,
hostile-input rejection, closed error mapping, callback escape denial, and
draining of unawaited operations. Static schema tests prove expand-only table
classification, account-scoped keys, immutable migration bytes, dedicated
function grants, transaction-local coordinates, and absence of table mutation
grants. A real PostgreSQL test is still required before claiming SQL/runtime
behavior.
