# queue

A durable, fenced job queue on Postgres. It knows no job kind: a kind supplies a handler and its
own causes, and the queue supplies everything about when and whether work runs.

## What a kind gets

| Need | API |
| --- | --- |
| Enqueue once per key | `Store.Enqueue`, or `Scope.Enqueue` inside `Store.Tenant` when admission must do more under the erasure barrier |
| Bind a job to its subject before it can run | `NewJob.Initializing`, then `Scope.Activate` or `Scope.CancelInitialization`; `Scope.Subject` serializes admissions for one subject |
| Run work with bounded concurrency | `Start` with a `Handler` per kind; `Workers.Stop` |
| Report what happened | return one of the sealed outcomes: `Done`, `DoneWith`, `Retry`, `Fail`, `Yield`, `Fence`, `Activate`, `BlockForSecret`, `Abort` |
| Turn an error into an outcome | `FromError`; adapters implement `Classified` |
| Save progress under the lease | `Run.Save`, `Run.SetStep` |
| Call anything outside the database | `Run.Guard` |
| Order work per key | `NewJob.OrderKey`, `OrderAt`, `SortKey` |
| Delay work | `NewJob.RunAt`, `Yield` with a delay |
| Run only when a caller presents a secret | `NewJob.Gated`, `Workers.Resume` |
| Inspect and redrive | `Store.Get`, `Store.Parked`, `Store.Redrive`, `Store.Stats` |
| Erase a tenant | `Store.Erase` |

## Rules and the test for each

| Rule | Where it is decided | Test |
| --- | --- | --- |
| Enqueue is idempotent on the key; the first enqueue fixes the input | `Scope.Enqueue` | `TestEnqueueIdempotencyProperty` |
| One lease holder at a time; a takeover gets a larger token; a stale holder can neither save nor call out | `Store.lease`, `Run.transition`, `Run.Guard` | `TestSingleLeaseProperty`, `TestGuardReadsLeaseAfterWaitingForErase` |
| A claim is charged when it is issued, so a worker that dies has spent it; a yield refunds it | `Store.lease`, `Run.wait` | `TestAttemptAccountingProperty` |
| What follows a transient or deterministic failure | `rules.AfterRetry`, `rules.AfterFail` | `rules` `TestAfterRetry`, `TestAfterFail` |
| Backoff doubles from the base and caps at 30 times | `rules.Backoff` | `rules` `TestBackoffDoublesFromBaseAndCapsAtThirtyTimes`, `TestBackoffNeverDecreasesAsAttemptsGrow` |
| One automatic requeue per job lifetime, never for a gated job or a deterministic cause | `rules.WillRequeue`, `Run.park` | `rules` `TestWillRequeueNeedsEveryCondition`, `TestAttemptAccountingProperty` |
| A claim reconciles instead of working when the last attempt died or a gate timed out | `rules.OnClaim`, `Store.recovery` | `rules` `TestOnClaim` |
| A lane runs one job at a time in `(OrderAt, SortKey, Key)` order; a retrying head holds its successors; parking releases them | `candidate` in `claim.go` | `TestOrderedLaneProperty`, `TestFairnessAndOrderedHold` |
| A tenant with a long backlog does not starve others | `candidate` (tenant turn) | `TestFairnessAndOrderedHold` |
| After an erase returns, no row of the tenant remains, nothing for it is admitted, and no guarded call for it starts | `Store.Erase`, `Store.Tenant`, `Run.Guard` | `TestEraseBarrier`, `TestGuardReadsLeaseAfterWaitingForErase` |
| An idle dispatcher sleeps until the next job is due, within bounds | `rules.IdleWait`, `Workers.idle` | `rules` `TestIdleWaitSleepsUntilDueWithinBounds` |
| A cause no kind registered is recorded as `unknown` | `Store.known` | covered by the conformance kit's metrics case |

The integration tests need a disposable Postgres 16: set `QUEUE_TEST_DATABASE_URL`. Without it
they skip, and `make check` in CI sets it.

## Schema

[`migrations/001_queue.sql`](migrations/001_queue.sql) and the guard function in
[`migrations/002_guard.sql`](migrations/002_guard.sql).

| Object | Contents and invariants |
| --- | --- |
| `queue_jobs` | One row per key: tenant, kind, subject, input, checkpoint, state, step, counters, timers and the lease. A terminal row has no `ready_at`. `state` and `outcome` are closed by `CHECK`. |
| `queue_tenants` | One row per tenant with its dispatch turn. Erasing it cascades to jobs and lanes. |
| `queue_lanes` | One row per tenant, kind and order key, for indexed lane lookup. |
| `queue_lease_token` | The fencing sequence. Gaps are fine; it only grows. |
| `queue_settings`, `queue_erasure` | The deployment's erasure salt, and one salted hash per erased tenant. |
| `queue_schema` | Applied migration file names. |

## How a claim works

One transaction: pick the tenant served longest ago and its earliest due job (`SKIP LOCKED`, so
replicas do not wait on each other); take the tenant and job advisory locks without waiting;
run the preflight; issue a new token and count the attempt in one statement; advance the
tenant's turn. Renewals use a separate small pool so a busy work pool cannot starve them.

## Known limits

- A replica learns of work enqueued on another replica when its idle wait ends (at most two
  seconds), not immediately. `LISTEN`/`NOTIFY` would remove that delay.
- Advisory locks fence calls between live replicas. After a hard process death the remote end
  may already have acted, so every guarded call needs its own idempotency key or conditional write.
