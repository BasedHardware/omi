# Durable predicate-batch input persistence contract

Status: P3 production-neutral contract and inert PostgreSQL adapter implemented and qualified, 2026-08-12.

## Purpose

A predicate-batch manifest identifies the graph frontier and predicate
revisions, but it cannot reconstruct the exact bounded question after the
process is lost or the owner vocabulary changes. Every newly accepted
`predicate_batch` job therefore requires one immutable input snapshot before
acceptance can commit.

The snapshot contains the owner, deterministic job id, graph frontier, exact
batch-question digest, and complete predicate revisions selected for that one
question. It does not contain transcript excerpts, model output, a provider
credential, or a settlement decision.

## Ordering and failure model

The scheduler stages the parsed snapshot in one authorized transaction and
then calls the generic accepted-work repository in a second authorized
transaction:

- failure after staging may leave an inert orphan;
- exact retry replays the orphan and accepts once;
- changed accepted-work bytes under the same owner/job conflict; and
- an accepted predicate job cannot exist without the exact committed input.

A deferred constraint trigger binds every new predicate-batch acceptance to
the staged owner, job, epoch, accepted-work digest, input frontier, manifest
digest, and execution contract. Existing rows are not rewritten. No runtime
role can delete staged input; any future orphan cleanup must first prove that no
accepted job references it.

## Storage and execution boundary

`memory_predicate_batch_work_inputs` is owner-scoped, append-only, capped at
512 KiB, and has no direct application-role table grant. Fixed
`SECURITY DEFINER` functions permit:

- insertion only under `memories.work.accept` for the transaction-local owner;
- acceptance-time read for exact idempotent replay; and
- execution-time read only for the current database-observed, unexpired lease
  owned by the calling principal.

The PostgreSQL adapter reparses the strict snapshot and verifies its complete
content hash on every read. The scheduler stages before acceptance. The
existing predicate adapter can consume the repository's leased snapshot, but
this unit does not compose a worker, choose a model, schedule polling, open a
route, or activate predicate consolidation.

## Qualification

The pinned PostgreSQL 18.4 suite proves that acceptance without a committed
input is rejected; an injected acceptance rollback leaves exactly one staged
input and no acceptance; retry accepts once; exact replay is stable; changed
accepted-work bytes conflict before acceptance; a later leased worker reloads
the exact snapshot; and the application role cannot read the table directly.
The same harness passes its Postgres.js corpus under pinned Bun 1.3.14 and Node
24.19.0, then stops the managed runtime while preserving the labelled
synthetic volume.

Cross-batch candidate coverage and consolidation quality remain explicitly
unmeasured. Production activation still requires a bounded route-free worker,
copied-store conservation/replay evidence, and the existing David policy gates.
