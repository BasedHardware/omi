# Legacy proposition migration runtime contract

Status: P4 route-free service boundary and PostgreSQL adapter implemented and
qualified locally, 2026-08-13. No source connector, copier loop, route, or
runtime activation is included.

## Purpose

Legacy product data may name the same source item repeatedly while a migration
is resumed after interruption. This unit gives that item one durable,
owner-local, opaque proposition identity without rewriting historical source
identifiers. It also makes an item tombstone dominate every later resume so a
deleted source cannot be resurrected by a restarted copier.

The public service port exposes only two named operations:

- `resumeMapping` checks for a retained tombstone, reuses an existing mapping,
  asks the caller to allocate an opaque proposition id when none was supplied,
  or inserts the first valid mapping;
- `recordTombstone` records or exactly replays one migration-item tombstone.

Both operations require an already-issued `AuthorizedLedgerWriteContext` with
the exact `memories.project` capability. The port strictly detaches requests,
recomputes their digests, validates implementation outcomes, and exposes no SQL
or connection capability.

## Persistence and races

Migration 0033 adds fixed `SECURITY DEFINER` functions over the P4 mapping and
tombstone tables introduced by migration 0005. The application role receives
function execution only; direct table access is revoked. Every function checks
the transaction-local account, nonempty principal, and exact capability.

Both functions acquire the same length-framed advisory transaction lock for an
exact `{account, legacy_source_id}` pair. Resume then checks the tombstone
before the mapping. A first insert becomes the durable winner; later proposals
reuse that winner. Tombstones exactly replay only when their sequence,
operation, event time, and request digest all match. Changed bytes conflict.
Once a tombstone exists, resume returns `tombstoned` even if an older mapping
also exists.

The PostgreSQL adapter uses the existing authorized serializable transaction
boundary. Database authority is re-locked before any replay or mutation.
Provider messages and source identifiers never enter returned errors; only
closed outcomes escape.

## Qualification evidence

The pinned PostgreSQL 18.4 test runs the adapter as
`omi_platform_application` and proves:

- allocation-required, first insert, durable-winner reuse, and exact tombstone
  replay/conflict;
- tombstone-before-resume and tombstone-after-mapping both dominate later
  resume;
- concurrent resume and tombstone serialize to one tombstone-dominated final
  state;
- an injected post-insert failure rolls back the mapping completely;
- account substitution through the fixed function is denied;
- direct reads of both tables are denied to the application role; and
- grant revocation is observed before an otherwise replayable operation.

The same real-database corpus passes under pinned Bun 1.3.14 and Node 24.19.0.

## Explicit exclusions

This unit does not identify a legacy source system, enumerate its rows, allocate
ids on behalf of a caller, create product propositions, or advance a migration
cursor. It adds no route, poller, default composition, deployment, or product
read behavior. A future copier must still prove a complete source manifest,
source-specific deletion/tombstone semantics, exact resumption cursor, and
authorized proposition-birth write before activation.
