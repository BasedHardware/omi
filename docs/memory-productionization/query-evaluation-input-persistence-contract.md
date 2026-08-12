# Query-evaluation input persistence contract

Status: implemented and real-PostgreSQL qualified, route-free and inactive,
2026-08-12.

## Purpose

Persist the exact sensitive query coordinate required to restart an isolated
read-path experiment without inventing query bytes from graph or product
authority. One input binds owner, account epoch, opaque input and source refs,
query text, account timezone, graph generation, and the canonical digest of the
complete coherent graph snapshot.

The record is experiment input, not memory truth. It never becomes a claim,
product projection, search document, answer, recall trace, grade, or promotion
decision.

## Authority and replay

Every stage and load runs inside the sealed `memories.experiments.shadow`
PostgreSQL transaction boundary. Live account, credential, grant, lifecycle,
epoch, principal, and destination state are locked and revalidated before any
lookup, including replay.

The service constructor accepts only an exact plain input body and a verified
authorized context. It validates an opaque `mqir1_` input ref, a bounded query,
an actual IANA timezone, the same-owner graph, and a nonnegative safe graph
generation. It derives:

- `mqes1_`: owner + epoch + input-ref source identity;
- `mqef1_`: exact graph generation + graph-snapshot digest frontier; and
- the full stage request digest over every sensitive and structural field.

The PostgreSQL row is append-only. An exact repeat returns `replayed`; changed
bytes under the same source return `idempotency_conflict`. Concurrent insert
races use insert-if-absent followed by exact row verification. Stored rows are
strictly reparsed and every derived coordinate is recomputed before return.

## Exact graph source

The route-free graph source first reloads the persisted query input under live
authority, then loads a fresh coherent authoritative graph under another live
authority check. It returns query bytes only when source ref, input frontier,
graph generation, and full graph digest still match. Any drift returns
`not_found`; a later producer load provides the final pre-persistence
revalidation already required by the query-grounding contract.

The two coherent loads deliberately do not pretend to be one database
snapshot. Monotone graph generation plus the exact digest makes intervening
graph changes visible, and the producer performs a second source load before
accepting the model result.

## PostgreSQL qualification

Migration `0024-memory-query-evaluation-input.sql` adds one account-scoped
sensitive table. The application role receives only `SELECT` and `INSERT`; it
cannot update, delete, truncate, mutate graph/product/work state, run a model,
open a route, or promote a strategy.

The pinned PostgreSQL 18.4 gate proves migration apply/reapply, stage, exact
replay, reconstruction through a new repository instance, exact graph-source
load, authority revocation before stored-input replay, and application-role
update/delete denial. The same gate runs the Postgres.js corpus under pinned
Bun 1.3.14 and Node 24.19.0. The managed local runtime is stopped afterward and
the labelled synthetic volume is preserved.

## Explicit exclusions

- no route, default service composition, production credential, model call,
  scheduler, worker loop, deployment, or traffic;
- no accepted/STM overlay or application-grant product projection;
- no blind grading, statistics conclusion, promotion, or cohort decision;
- no `subject:*`, bystander/privacy, identity authority, compose voice, or data
  disposition change;
- no claim that the still-inert end-to-end PostgreSQL query runtime has been
  composed or that assertion-local evidence has been human-graded.
