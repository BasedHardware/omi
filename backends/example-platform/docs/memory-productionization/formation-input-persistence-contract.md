# Durable formation input persistence contract

Status: P3 production-neutral contract and inert PostgreSQL adapter implemented, 2026-08-12

## Purpose

An input manifest proves which units were accepted, but cannot reconstruct the
session context, evidence excerpts, temporal clock, policy frontier, entity
candidates, or identity-authority context after a worker process is lost. An
accepted formation job therefore requires one exact immutable input snapshot
before acceptance can commit.

## Ordering and failure model

Formation ingestion stages the exact parsed snapshot in one authorized
transaction, then commits the generic accepted work in a second authorized
transaction. This ordering is deliberate:

- a crash after input staging but before acceptance may leave an inert orphan;
- exact retry reuses that orphan and proceeds to acceptance;
- changed bytes under the same owner/job conflict; and
- an accepted formation job can never exist without its exact committed input.

A deferred constraint trigger verifies every newly inserted formation
acceptance against the staged owner, job, epoch, accepted-work digest, input
frontier, input-manifest digest, and execution-contract digest. Historical rows
are not rewritten. Orphan cleanup is a later bounded maintenance concern; no
runtime role has delete authority, and a future cleanup operation must prove no
accepted work references the row before deletion.

## Sensitive storage boundary

`memory_formation_work_inputs` is append-only, owner-scoped, capped at the same
512 KiB JSONB defense-in-depth envelope as durable normalized results, and has
no direct application-role table grant. Fixed `SECURITY DEFINER` functions:

- insert only under `memories.work.accept` with the transaction-local owner and
  a nonempty principal; and
- read under acceptance for exact replay, or under `memories.work.execute` only
  while the database observes a current unexpired lease owned by the principal.

The driver reparses the complete snapshot and recomputes its content digest on
every read. Snapshot JSON, excerpts, source identities, and database errors
never enter outbox or telemetry.

## Runtime boundary

The formation service now owns the input repository. Acceptance always stages
input before the generic work repository, and execution loads input only through
the current leased repository. The model edge receives the same strict snapshot
that produced the accepted manifest. No scheduler, route, polling loop, model
selection, timing default, Listen hook, or production runtime is activated.

## Acceptance evidence

- strict repository tests cover exact stage/replay, later-process load,
  changed evidence, wrong capability, bad digest, and accessor non-execution;
- static migration tests cover the table, deferred acceptance trigger, fixed
  functions, current-lease predicate, account scoping, and absence of grants;
- PostgreSQL 18.4 proves missing-input acceptance rollback, exact stage/replay,
  application-role direct-table denial, lease-bound reload, all earlier
  retry/dead/result/success behavior, and Bun/Node parity; and
- managed teardown stops the runtime while preserving only the labelled
  synthetic volume.

The next unit is an inert PostgreSQL-backed one-shot formation assembly and a
process-loss test proving the staged input and staged result eliminate repeat
model calls across restart.
