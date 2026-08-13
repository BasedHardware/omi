# PostgreSQL account-deletion cleanup participant

Status: implemented and qualified as an inert PostgreSQL-owned participant;
full account cleanup composition and production activation remain pending

Decision: David, 2026-08-12 America/New_York

## Scope

This participant disposes the PostgreSQL-owned portions of the deletion inventory after
a caller has already established the complete cleanup eligibility decision. It does not
decide retention, legal hold, recovery, or external-object policy.

The caller supplies the exact deleted-account control revision, deletion epoch, opaque
operation reference, and eligibility digest. One serializable transaction:

1. enters the dedicated `omi_platform_cleanup` role;
2. takes an account-scoped advisory transaction lock;
3. locks and revalidates the exact deleted control and terminal-export records;
4. scans every PostgreSQL-owned inventory surface through named security-definer
   functions;
5. disposes one reviewed dependency group atomically; and
6. appends content-free per-surface receipts in the same transaction.

The role receives no direct table mutation grant. The SQL function's table registry is
statically required to be byte-for-byte equivalent in meaning to the typed TypeScript
registry. The durable-work and staged-result surfaces form one atomic group because the
live foreign-key graph contains immediate dependencies in both directions.

## Transaction and replay behavior

The held session cannot escape its callback. All started operations are tracked and
drained before the transaction may commit; an ignored rejected operation fails the whole
transaction. Reusing the same account, deletion epoch, operation reference, surface group,
and eligibility digest returns the existing receipts. Partial or changed replay fails
closed.

Receipts contain only coordinates, closed result codes, counts, timestamps, and digests.
They reference the terminal deletion export and are retained as deletion-safety evidence.
The terminal export, account/control tombstone, and cleanup receipts are never disposed by
this participant.

## Qualified evidence

The real PostgreSQL 18.4 test proves migration reapply, cleanup-role isolation, exact scan,
atomic two-surface disposal, deterministic replay, rollback with no rows or receipts
committed, zero rescan after commit, terminal-record retention, and denial of a stale
control coordinate. The same qualification run executes its normalized parity corpus on
pinned Bun and Node runtimes.

## Explicit nonclaims

This is not the complete `AccountDeletionCleanupPort`. A later composite must acquire and
revalidate the full eligibility fence and coordinate the remaining surfaces, including
external objects, search/vector stores, and stranded legacy data. This unit does not
choose cleanup scheduling, credentials, approval, retention duration, recovery window,
RPO/RTO, or operator policy. It is not wired to a route, scheduler, deployment, or product
default, and production activation remains false.
