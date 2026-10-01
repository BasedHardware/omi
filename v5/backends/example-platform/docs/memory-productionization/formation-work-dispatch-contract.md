# Formation work one-shot dispatch contract

Status: P3 production-neutral pre-registration, 2026-08-11

## Boundary

This unit dispatches at most one already-accepted formation job per invocation.
It is deliberately not a scheduler, daemon, timer, process supervisor, database
adapter, worker grant, or runtime composition. A later runtime may repeatedly
invoke it only after the real PostgreSQL and release-image gates pass.

The dispatcher receives an already-issued `memories.work.execute` context, asks
the sealed execution repository for the next `formation` job, and passes that
leased job to the inert formation service. It never selects an account, worker,
lease time, lease duration, retry delay, model, strategy, or concurrency level.
Those coordinates remain in the locked authority state and accepted execution
contract.

## Closed outcomes

- `idle`: the repository reported no eligible formation work.
- `completed`: exactly one leased formation job reached durable success or a
  recorded retry/dead failure.
- `stopped`: authorization/context, storage, lease, eligibility, or
  idempotency prevented a terminal transition.

The output contains only closed codes and counts. It never returns a job,
account, evidence, transcript, staged result, commit id, model response, prompt,
provider error, or repository reason string.

## Cost and concurrency

One invocation leases at most one job and therefore can call the formation
producer at most once. Stale-parent rematerialization remains bounded inside
the service and performs no second producer call. There is no parallel dispatch
or polling loop in this unit. Cross-process one-pipeline-per-credential
enforcement remains a future persisted runtime policy, not an in-memory claim.

## Pre-registered acceptance tests

1. Idle returns without invoking the formation executor.
2. One leased formation job invokes the executor exactly once and emits only a
   content-safe completed summary.
3. Authorization and serialization lease outcomes stop before executor access.
   Dependency exceptions are contained as a closed storage stop and never copy
   raw error content.
4. A non-formation job cannot pass the repository facade's formation-only lease
   request, while the formation service independently retains its work-kind
   fence.
5. Every output key is fixed and contains no job, account, commit, result, or
   raw dependency value.
6. Focused/full tests, contract QA, import lint, changed-file TypeScript filter,
   and `git diff --check` pass before the unit is recorded.

## Explicit exclusions

- no route, service boot composition, scheduler, signal handler, health check,
  sleep, timer, worker credential, SQL, pool, or role grant;
- no Listen transcript mapping or subject/bystander/privacy decision;
- no model/provider/default selection or increased parallelism;
- no claim of PostgreSQL lease, race, crash, or reconstruction behavior.
