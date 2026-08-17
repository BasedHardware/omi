# Route-free PostgreSQL predicate-batch runtime contract

Status: implemented and real-PostgreSQL qualified, inert by construction.

The production-shaped predicate consolidation seam is
`drivers/postgres/predicate-batch-one-shot-runtime.ts`. It composes the durable
acceptance, execution-state, exact predicate-input, normalized-result,
atomic-success, and graph-parent PostgreSQL adapters behind three bounded
operations:

- `schedule(context, request)` stages the exact predicate batch before
  accepting its immutable job;
- `runNext(context)` leases and executes at most one predicate-batch job; and
- `recoverExpired(context, job_id)` records one explicitly named expired
  predicate lease as worker loss.

The constructor takes an exact predicate strategy registry, an injected model
resolver, an explicit parent-rematerialization bound, and an already-created
PostgreSQL transaction pool. It does not mint authority, select a default
model, schedule a timer, poll, open a route, read environment variables, or
activate identity-cluster or promotion work. The dispatch lease filter accepts
only `predicate_batch`. Callers must present separately issued
`memories.work.accept` and `memories.work.execute` contexts.

Strategy lookup is by the immutable execution-contract digest persisted with
the job. Unknown, duplicate, or non-predicate contracts fail closed. The exact
batch input is loaded from PostgreSQL after lease acquisition. Every
materialization reloads the current account-local graph parent through the
authorized graph repository; a stale-parent response rematerializes the
already staged result and never repeats the model call.

## Qualification

The pinned PostgreSQL 18.4 real-adapter test proves both terminal paths:

1. the exact predicate batch is staged and accepted once;
2. an injected failure after normalized result staging leaves one staged
   result, a leased job, no success row, and no graph-head movement;
3. explicit lease recovery plus a later one-shot execution uses zero
   additional model calls; and
4. the recovered run commits exactly one success row and success outbox event,
   while preserving the graph sequence because the model returned no
   assertions; and
5. a second exact batch over two already committed predicate revisions accepts
   one role-checked alias assertion, commits its predicate-assertion revision,
   and advances the graph head exactly once.

Core adapter tests separately prove deterministic non-empty assertion planning,
bounded parent rematerialization, and no second producer call.

The real suite also runs its PostgreSQL/Postgres.js parity corpus under pinned
Bun 1.3.14 and Node 24.19.0. The local harness stops the managed runtime and
preserves the labelled synthetic volume after the run.

This contract does not ratify a polling worker, deployment topology, provider
credential, default model, identity or promotion activation, subject-tier
policy, bystander boundary, compose voice, product-projection materialization
subject, public route, or rollout cohort.
