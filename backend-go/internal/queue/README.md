# queue

A durable, fenced job queue on Postgres. It knows no job kind: a kind supplies a handler and its
own causes, and the queue supplies everything about when and whether work runs.

## What a kind gets

| Need | API |
| --- | --- |
| Declare the kind: name, formats, steps, causes | `Kind`, passed to `Open` |
| Enqueue once per key | `Store.Enqueue`, or `Scope.Enqueue` inside `Store.Tenant` when admission must do more under the erasure barrier |
| Bind a job to its subject before it can run | `NewJob.Initializing`, then `Scope.Activate` or `Scope.CancelInitialization`; `Scope.Subject` serializes admissions for one subject |
| Run work with bounded concurrency | `Start` with a `Handler` per kind; `Workers.Drain` for bounded shutdown, `Workers.Stop` for immediate cancellation |
| Report what happened in `Work` | one of the sealed outcomes: `Done`, `DoneWith`, `DoneAt`, `Retry`, `Fail`, `Yield`, `Hold`, `Fence`, `Activate`, `BlockForSecret`, `Abort` |
| Report what had already happened in `Exhausted` | one of the sealed resolutions: `Resolved`, `ResolvedWith`, `Fenced`, `Park`, `Later`, `Dropped` |
| Turn an error into an outcome | `FromError`, `LaterOnError`; adapters wrap with `Classify` |
| Save progress under the lease | `Run.Save`, `Run.SetStep` |
| Call anything outside the database | `Run.Guard`, which hands the call a `Guarded` |
| Give an external operation a stable identity | `Guarded.Operation` |
| Order work per key | `NewJob.OrderKey`, `OrderAt`, `SortKey` |
| Delay work | `NewJob.RunAt`, `Yield` with a delay |
| Hold new platform-funded units pending an owner entitlement change | `Kind.PaidProcessing`, `HoldCondition`, `Release`, `CheckEntitlements` |
| Keep a whole tenant off the schedule | `Hold` |
| Run only when a caller presents a secret | `NewJob.Gated`, `Workers.Resume` |
| Inspect and redrive | `Store.Get`, `Store.Parked`, `Store.Redrive`, `Store.Stats`, `Store.Stranded` |
| Erase a tenant | `Store.Erase` |
| Test a handler on real workers | `queuetest.Open`, `Harness.Start`, `Harness.Settled` |

## Rules and the test for each

Scheduling decisions are pure functions in `rules`, tested as tables. Everything else is tested
against Postgres, each test in its own database (`internal/platform/pgtest`).

| Rule | Where it is decided | Test |
| --- | --- | --- |
| Held paid admissions have no due time or active lane slot. One owner check covers both routes. A release settles expired units and rejoins the rest in capture order. | `Scope.enqueuePaid`, `Scope.ObserveEntitlement`, `Store.CheckEntitlements` | `TestEntitlementOwnerReplay`, `TestGrantRacesPaidIntakeAndExpiry`, `TestEraseWhileEntitlementHeld` |
| Drain stops intake while running handlers can renew and save | `Workers.Drain` | `TestDrainLetsRunningHandlerSaveAndFinish` |
| At the deadline, drain refunds each still-owned claim once, preserving its checkpoint, terminal intent, and secret requirement | `Store.releaseClaims` | `TestDrainDeadlineRefundsWorkAndReconciliationForAnotherReplica` |
| Enqueue is idempotent on the key; the first enqueue fixes the input | `Scope.Enqueue` | `TestEnqueueIdempotencyProperty` |
| A kind, format or step nobody declared is refused at enqueue and at save | `Scope.admissible`, `Run.Save` | `TestUndeclaredKindFormatAndStepAreRejected` |
| Invalid policy or declarations fail at `Open`, before any connection | `Config.Validate`, `newRegistry` | `TestOpenRejectsInvalidPolicyAndDeclarations` |
| A replica claims only the kinds it has a handler for and the formats it declares; the rest stays untouched for a replica that can run it, and is reported | `candidate` in `claim.go`, `Store.Stranded` | `TestReplicaClaimsOnlyKindsAndFormatsItDeclares`, `TestWorkersLeaveKindsTheyHaveNoHandlerFor`, `TestStartRejectsWhatIsNotDeclared` |
| One lease holder at a time; a takeover gets a larger token; a stale holder can neither save nor call out | `Store.lease`, `Run.transition`, `Run.Guard` | `TestSingleLeaseProperty`, `TestGuardReadsLeaseAfterWaitingForErase` |
| The heartbeat keeps a long handler's lease while it saves progress | `Run.execute`, `Store.renewUntilDone` | `TestWorkersRenewTheLeaseWhileTheHandlerSavesProgress` |
| A claim is charged when it is issued, so a worker that dies has spent it; a yield refunds it | `Store.lease`, `Run.wait` | `TestAttemptAccountingProperty` |
| What follows a transient or deterministic failure | `rules.AfterRetry`, `rules.AfterFail` | `TestAfterRetry`, `TestAfterFail` |
| Backoff doubles from the base and caps at 30 times | `rules.Backoff` | `TestBackoffDoublesFromBaseAndCapsAtThirtyTimes`, `TestBackoffNeverDecreasesAsAttemptsGrow` |
| One automatic requeue per job lifetime, never for a gated job or a deterministic cause | `rules.WillRequeue`, `Run.park` | `TestWillRequeueNeedsEveryCondition`, `TestAttemptAccountingProperty` |
| What a claim does: work, reconcile, or return a gated job to waiting | `rules.OnClaim` | `TestOnClaim` |
| A gated job past initialization reaches `Work` only with its secret | `rules.OnClaim`, `Store.reblock` | `TestOnClaimNeverWorksAGatedJobWithoutItsSecret`, `TestGatedJobNeverWorksWithoutItsSecret`, `TestResumeRunsAGatedJobWithItsSecret` |
| A resume cannot win after the gate's timeout; the database clock decides | `direct` in `claim.go` | `TestResumeAfterTheGateTimedOutIsRefused` |
| Reconciliation has its own budget; when it is spent the job parks with its intent and checkpoint kept, releases its lane, and a redrive resumes the reconciliation | `rules.AfterLater`, `Run.repair`, `Store.Redrive` | `TestAfterLaterBoundsReconciliation`, `TestReconciliationIsBoundedAndRepairKeepsTheIntent` |
| A lane runs one job at a time in `(OrderAt, SortKey, Key)` order; a retrying head holds its successors; parking releases them | `candidate` in `claim.go` | `TestOrderedLaneProperty`, `TestFairnessAndOrderedHold` |
| A lane belongs to one tenant | `candidate`, index `queue_jobs_head` | `TestLanesOfTwoTenantsDoNotShareAHead` |
| A gated job cannot be in an ordered lane | `Scope.admissible`, `Run.block`, a `CHECK` | `TestGatedJobCannotJoinAnOrderedLane` |
| A tenant with a long backlog does not starve others | `candidate` (tenant turn) | `TestFairnessAndOrderedHold` |
| `Hold` refunds the attempt and keeps every job of the tenant off the schedule | `Run.hold` | `TestHoldKeepsTheWholeTenantOffTheSchedule`, `TestHoldPausesTenantBeforeReleasingJob` |
| After an erase returns, no row of the tenant remains, nothing for it is admitted, and no guarded call for it starts | `Store.Erase`, `Store.Tenant`, `Run.Guard` | `TestEraseBarrier`, `TestGuardReadsLeaseAfterWaitingForErase` |
| A `Guarded` is valid only inside its guard, and an operation's identity survives a takeover | `Run.Guard`, `Guarded.Operation` | `TestGuardedStopsBeingValidWhenTheGuardReturns` |
| A handler panic or a missing outcome is retried and reported; the replica keeps running; locks are released | `Run.step`, `Run.Guard` | `TestHandlerPanicIsRetriedAndTheReplicaKeepsRunning`, `TestPanicInsideGuardReleasesItsLocks` |
| A resume after `Stop` reports `ErrStopped` and leaves the job untouched | `Workers.take`, `Run.unclaim` | `TestResumeAfterStopReportsStopped`, `TestScheduledResumeHandsBackClaimWhenStopWinsLaunch` |
| The watcher sleeps until the next timer, and backs off on work it cannot claim | `rules.IdleWait`, `Workers.idle` | `TestIdleWaitSleepsUntilDueWithinBounds` |
| A cause no kind declared is recorded as `unknown` | `registry.known` | `TestUndeclaredCauseIsRecordedAsUnknown` |
| Admission acquires its barrier and checks for erasure in one client statement, reading the tombstone after the lock | `Store.Tenant`, `queue_acquire_tenant` | `TestAdmissionSeesEraseCommittedWhileWaitingForLock`, `TestTenantScopeTakesTwoClientStatements` |
| Queue-only erase waits for guards, purges tenant queue rows, and records the tombstone while preserving the remote-cleanup completion bit | `Store.EraseQueue` | `TestEraseQueueWaitsForGuardAndCascades`, `TestEraseQueueIncludesAdmissionThatCommitsWhileItWaits`, `TestQueueOnlyErasePreservesRemoteCompletion` |
| Every job field is scanned from its matching column | `columns`, `scan` | `TestJobScanMatchesItsProjection` |
| A database whose applied migration differs from the embedded file is refused | `Store.Migrate`, `Store.Ready` | `TestMigrateRefusesAnEditedMigration` |

## The erasure contract, and its limit

`Run.Guard` holds the tenant's shared lock and the job's lock on one database session while the
external call runs. `Store.Erase` takes the tenant's exclusive lock, so it waits for calls in
flight and nothing starts after it.

Those locks live on a database session. If the session dies while the call is still talking to
the remote system, the locks are gone and an erase can finish before the remote write commits.
An idempotency key does not help: it deduplicates a repeat, it does not reject the first late
write. So a remote system that keeps tenant data must refuse the write itself, atomically with
the write. `internal/platform/docstore` does that for Firestore, and
`TestAWriteThatOutlivesItsGuardIsRefusedByFirestoreAfterAnErase` in `internal/adapters/batchdocs`
kills the session mid-call to prove it. A sink that cannot do this gets the weaker guarantee, and
its adapter's README must say so.

### Queue-only account erasure

Workerd can call `Store.EraseQueue(ctx, tenant)` after authenticating the deletion executor
and validating its armed wipe generation. The equivalent SQL is
`SELECT queue_erase_tenant($1::text)` in the queue schema. Both paths wait for shared
guards, delete the tenant and its dependent rows, and record the salted tombstone even if
the tenant never had jobs. Repeating the call after a lost response is safe.

Use a bounded READ COMMITTED transaction. The exclusive transaction lock lasts through commit.
The Go method uses autocommit. An explicit SQL transaction must commit successfully before the
caller acknowledges the wipe generation. The returned boolean is the existing remote-cleanup
completion bit. Both values mean that the SQL operation succeeded. Only `Store.Erase` runs
remote cleanup and marks it complete, under its exclusive session lock.

Migration 003 installs a SECURITY DEFINER function owned by the queue migrator. It binds
the table names to the installation schema and revokes PUBLIC execution. The workerd
runtime needs schema usage and EXECUTE as described in its deployment contract. Check those
privileges before deploying a separately owned runtime. The dedicated recovery role and
its grants require David's approval. The [recovery access migration](access/erase_recovery.sql)
is separate from automatic queue migrations and expects an approved, pre-existing role.
The executor owns rollout, generation checks, and acknowledgement persistence.

## Schema

[`migrations/001_queue.sql`](migrations/001_queue.sql). An applied file is never edited; a change
is a new numbered file. `queue_schema` records each file's checksum and `Migrate` and `Ready`
refuse a mismatch.

| Object | Contents and invariants |
| --- | --- |
| `queue_jobs` | One row per key: tenant, kind, format, subject, input reference, checkpoint, state, step, counters, timers and the lease. `CHECK` constraints close `state` and `outcome` and tie them together: a terminal row has an outcome and no timer. |
| `queue_tenants` | One row per tenant with its dispatch turn and hold time. Erasing it cascades to jobs and lanes. |
| `queue_lanes` | One row per tenant, kind and order key, for indexed lane lookup. |
| `queue_lease_token` | The fencing sequence. Gaps are fine; it only grows. |
| `queue_settings`, `queue_erasure` | The deployment's erasure salt, and one salted hash per erased tenant. |
| `queue_acquire_tenant` | `Store.Tenant` takes the shared tenant barrier, then reads the erasure tombstone with a fresh snapshot. |
| `queue_erase_tenant` | Exclusive transaction barrier, cascading queue purge and salted tombstone. Preserves the remote-cleanup completion bit. |
| `queue_acquire_guard` | The function `Run.Guard` calls: both locks, then a fresh read of the lease. |

## How a claim works

One transaction, and nothing in it leaves the database: pick the tenant served longest ago and
its earliest due job among the kinds and formats this replica runs (`SKIP LOCKED`, so replicas do
not wait on each other); take the tenant and job advisory locks without waiting; decide with
`rules.OnClaim`; issue a new token, count the attempt and advance the tenant's turn in one
statement. Renewals use a separate small pool so a busy work pool cannot starve them.

## Known limits

- A replica learns of work enqueued on another replica when its idle wait ends (at most two
  seconds), not immediately. `LISTEN`/`NOTIFY` would remove that delay.
- A lease renewal that was already waiting on a row lock when the lease expired can still extend
  it, as long as nobody took the job over in between. Once a takeover commits, the old token can
  never write. The fence is the token, not the clock.
- Call `Workers.Drain(ctx)` before cancelling the context passed to `Start`. At the deadline
  it cancels handlers and gives fenced lease cleanup up to three additional seconds. A gated
  job still needs a fresh secret unless it is already reconciling. A guarded call that ignores
  cancellation holds its advisory locks until the call returns or the session closes.
- `Workers.Stop` waits for handlers. A handler that ignores its context delays shutdown, so every
  adapter call needs a deadline.
- A resume scheduled for later keeps its secret in memory until then, on one replica. A restart
  or five busy-lock deferrals drop it and the job waits for the next caller.
