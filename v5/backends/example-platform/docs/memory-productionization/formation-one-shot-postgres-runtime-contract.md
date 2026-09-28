# Route-free PostgreSQL formation runtime contract

Status: implemented and real-PostgreSQL qualified, inert by construction.

The production-shaped formation seam is
`drivers/postgres/formation-one-shot-runtime.ts`. It composes the accepted-work,
execution-state, exact-input, normalized-result, atomic-success, and graph-head
PostgreSQL adapters behind three bounded operations:

- `accept(context, request)` stages the exact sensitive input before accepting
  the immutable job;
- `runNext(context)` leases and executes at most one formation job; and
- `recoverExpired(context, job_id)` records one explicitly named expired lease
  as worker loss.

The constructor takes an exact formation strategy registry, an injected model
resolver, an explicit parent-rematerialization bound, and an already-created
PostgreSQL transaction pool. It does not mint authority, choose a model,
schedule work, poll, open a route, read environment variables, or integrate the
Listen finalization path. Callers must present separately issued
`memories.work.accept` and `memories.work.execute` contexts.

Strategy lookup is by the immutable execution-contract digest persisted with
the job. Unknown, duplicate, or non-formation contracts fail closed. Every
materialization reloads the current account-local graph parent through the
authorized graph repository; a stale-parent response rematerializes the already
staged result and never repeats the model call.

## Qualification

The pinned PostgreSQL 18.4 real-adapter test proves:

1. an injected acceptance rollback leaves one inert exact input and no accepted
   job;
2. retrying the same ingestion reuses that exact stage and accepts once;
3. an injected failure after result staging leaves one staged result, a leased
   job, no success row, and no graph mutation;
4. explicit lease recovery plus a later one-shot execution uses zero additional
   model calls; and
5. the recovered run commits exactly one formation outcome, success row, graph
   transition, and success outbox event.

The same suite runs its PostgreSQL/Postgres.js parity corpus under pinned Bun
1.3.14 and Node 24.19.0. The local harness stops the managed runtime and
preserves the labelled synthetic volume after the run.

This contract does not ratify a production timing value, polling worker,
deployment topology, Listen ingestion mapping, provider credential, default
model, subject-tier policy, bystander boundary, compose voice, or rollout
cohort.
