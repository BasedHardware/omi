# Durable work result staging and replay contract

Status: P3 core contract and PostgreSQL staging adapter implemented, 2026-08-11

## Purpose

Close the crash/head-conflict gap between a successful model response and the
atomic graph/job/outbox commit. Once a normalized result is durably staged, a
new lease or a rebuilt graph parent must reuse those exact bytes and must not
call the model again.

This cannot promise exactly-once provider calls: a process can die after the
provider answers but before the stage commits unless that provider offers a
separately qualified idempotency primitive. It does guarantee no repeated model
call after a committed stage and makes the remaining pre-stage crash window
explicit instead of hiding it.

## Staged artifact

One accepted job has at most one immutable staged result. It binds:

- owner, job id, accepted-work digest, work kind, input frontier, and complete
  execution-contract digest;
- the producing lease's attempt, fence, and context-derived worker principal;
- a bounded printable result-contract version;
- the exact provider response digest, but never raw provider output;
- one detached, canonical, bounded normalized-result JSON object and its exact
  digest; and
- a deterministic opaque staged-result id and request digest over all of the
  above.

The normalized artifact is sensitive memory content. It is not content-safe,
must not enter logs/outbox/telemetry/errors, and is never returned by a product
route. The public repository port requires `memories.work.execute`, exposes only
`load` and `stage`, and has no SQL, clock, model, grant, retry, or arbitrary
query surface.

The stage parser is intentionally structural rather than a substitute for each
work kind's semantic validator. The executor must produce the artifact through
the selected versioned result contract. Before authority changes, the existing
ledger/success boundaries still validate the complete graph transition, total
formation outcome where applicable, honest work origin, and exact digests.

## Replay behavior

On a lease, the worker first loads by the accepted-work coordinate:

1. If a stage exists, it is re-parsed and must match the current job's immutable
   accepted-work, work kind, frontier, and execution contract. The worker skips
   the model and materializes a new parent-bound append from those staged bytes.
2. If absent, the worker invokes the selected model/result contract once, drops
   raw provider bytes after parsing, and attempts insert-if-absent staging.
3. Same bytes replay. Different bytes for the same accepted job are an explicit
   idempotency conflict; no last-writer-wins replacement exists.
4. `stale_parent` rematerializes only the append attempt against the new head.
   It reuses the stage and never changes the response or normalized-result
   digest.
5. After process loss, an expired lease is recovered explicitly. A later lease
   can load the earlier stage because it binds immutable accepted work, while
   the final success remains authorized by the new current lease/fence.

## Atomic success linkage

Every success request carries the exact staged result. Owner, job, accepted
digest, work kind, frontier, execution contract, and response digest must equal
the leased job and success request. `successful_empty` uses the staged normalized
result digest as its result digest. Non-empty success continues to use the exact
parent-bound append request digest as its result digest.

A new checksummed migration stores the sensitive stage in an account-scoped
table, links its producing attempt/fence to an actual leased state, and adds an
exact staged-result foreign key to every success row. Earlier migration bytes
do not change. The application role receives no table privilege. It can access
the stage only through fixed `SECURITY DEFINER` functions that require the
transaction-local owner and `memories.work.execute` capability, and that prove
the current non-expired lease belongs to the transaction-local principal. A
later lease may read the immutable result produced by an earlier lease for the
same accepted work; an insert must match the exact current lease, attempt,
fence, state digest, and producer principal.

## Implemented PostgreSQL slice

`createPostgresDurableMemoryWorkResultRepository` is a sealed adapter over one
authorized serializable transaction and one checked-out connection. It first
revalidates the account, credential, grant, epoch, and database clock, then
checks the exact current work head before calling either fixed result function.
Loaded rows are strictly parsed and their content hash is recomputed before any
normalized result is returned. Same-stage replay is byte-identical; changed
bytes return an idempotency conflict rather than replacing memory content.

The real PostgreSQL 18.4 qualification covers missing, stage, exact replay,
later-lease reuse, direct sensitive-table denial, and wrong-principal function
denial under the application role. The same migration and adapter corpus passes
under Bun 1.3.14 and Node 24.19.0. The managed local runtime is stopped after the
gate and its labelled synthetic volume is preserved for repeatable reapply
tests.

## Pre-registered acceptance tests

1. Stage rejects wrong capability, owner, epoch, job, work kind, frontier,
   execution contract, non-leased/wrong-principal producer, malformed digest,
   oversized/non-object/non-plain/proxy/accessor/sparse/aliased JSON, or request
   identity before the adapter.
2. Normalization detaches and deeply freezes the artifact; key order does not
   change identity, while any value/contract/response/job/fence change does.
3. Load accepts a later valid lease for the same immutable accepted work and
   refuses cross-owner, changed accepted digest/frontier/contract, raw fields,
   or malformed driver results.
4. Insert replay returns byte-identical staged identity. A different result for
   one job is `idempotency_conflict`, never replacement.
5. Success rejects a missing, forged, cross-job, cross-contract, or response-
   mismatched stage. Empty success binds its staged normalized-result digest;
   non-empty success still binds the graph append digest.
6. Migration bytes are checksummed and static tests prove account scoping,
   immutable one-stage-per-job identity, exact leased-producer linkage, bounded
   JSON, success-stage FK, absence of sensitive table grants, and fixed
   principal-bound function grants only.
7. A hermetic worker-composition test proves stage hit means zero model calls;
   stage miss means one model call; stale parent rematerializes with no second
   model call; and restart/new lease reuses the same stage.
8. Focused/full tests, contract QA, import lint, strict changed-file TypeScript
   filter, bundle parse/build, and `git diff --check` pass before recording the
   unit.

## Explicit exclusions

- Real PostgreSQL migration, role, transaction, and adapter behavior is
  qualified locally; no service route, scheduler, provider, polling worker, or
  production runtime is activated.
- Atomic success persistence is still a separate adapter. Staging alone does
  not advance the graph head, complete a work item, or emit success outbox.
- No raw provider response is persisted.
- No exactly-once-provider-call claim exists before a provider-specific
  idempotency gate.
- Subject tiers, bystander/privacy policy, identity authority, compose voice,
  blind grading, data disposition, and cohort activation are unchanged.
