# Batch store contention storm damper

Status: shipped on the batch record lane. Owner: batch record lane / rollout lead.
Flag: `BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED` (default on; kill switch
restores immediate re-strikes).

## What problem this solves

The bounded contention chain (`database/firestore_transaction_retry.py`) gives
one Firestore transaction five immediate attempts whose inter-attempt gaps sum
to 1.5-3.0 s (the wave-bridge cap). During a real contention storm —
many workers converging on the same hot job/queue/owner documents — every
caller that exhausts its budget
re-strikes the same documents immediately. The whole process burns its
budgets in lockstep and every storm member ends at
`firestore_transaction_contention operation=... attempt=5/5 outcome=exhausted`.
That signature is the largest worker error class in the Loop S prod-log sensor
(x2239/30m at its peak, logged before per-operation attribution shipped).

The worker's pull loop already protects itself with a jittered instance
backoff (`utils/batch_pipeline/scheduler.py`, `event=batch_pull
outcome=backoff`), but every other store entry — merge drains, completion and
failure transitions, intake admission, recovery, maintenance — re-struck
immediately. This closes that gap at the one chokepoint every entry shares.

Failure-Class: FC-immediate-retry-loses-shared-cas

## Design

`FirestoreStore.run` resolves its static operation label, then consults a
per-instance `_ContentionStormDamper` before opening any transaction:

- On `FirestoreContentionExhausted` (the chain's closed outcome), the label
  arms a bounded, jittered window: an exponential ladder
  `0.25s → 0.5s → 1s → 2s → 4s` (equal jitter, `[0.5x, 1x)` of the rung
  maximum) per consecutive failure, capped at 4 seconds. The cap is well
  below the pull loop's 30s ceiling because a store entry is on the
  record-latency path: the damper trades at most a few seconds of wait for
  skipping a doomed immediate collision.
- The next entry of the SAME label sleeps out the residual window first (one
  `sleeper(residual)` call outside the lock) and logs
  `event=batch_store_backoff operation=<label> waited_ms=<int>` at INFO.
  Every other label runs untouched — damping is per operation, matching the
  per-label attribution contract (`database/batch_pipeline_transaction_labels.py`).
- A successful commit clears that label's ladder, but only if no concurrent
  arm happened since the entry consulted (generation guard, mirroring the
  pull loop's generation-based reset). A stale success never clears a live
  storm.
- Non-contention errors never arm; probe/due/oldest/ready_for_capacity reads
  never consult; with either kill switch off
  (`BATCH_PIPELINE_CONTENTION_RETRY_ENABLED`,
  `BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED`) the damper is fully
  dormant and behavior matches pre-damper code.
- One store instance is one process's view of one namespace, and the
  scheduler shards, the pump, intake and maintenance all share it: arming
  damps all of them, not just the caller that exhausted. State is
  instance-scoped (never class-global), bounded to 64 tracked labels (new
  labels beyond the cap run undamped rather than growing state forever).

Clock, sleep and jitter are injectable constructor kwargs
(`storm_damper=_ContentionStormDamper(monotonic=..., sleeper=...,
random_value=...)`) so tests are deterministic and zero-delay.

## Operational notes

- The exhausted `outcome=exhausted` ERROR line is unchanged and still fires
  per exhausted chain; the damper adds only the INFO `batch_store_backoff`
  wait lines (one per damped entry).
- Expected prod effect: fewer chains reaching `attempt=5/5` during storms on
  hot documents — the wasted immediate re-strikes are converted into spaced
  entries that find the abort window expired. Recovery-after-storm is
  unchanged: a success clears the ladder and the next storm starts from the
  base rung.
- Rollback: set `BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false`
  (Helm/Cloud Run runtime env) — consult and arm stop immediately; no other
  behavior depends on it.
- Suite: `backend/tests/unit/test_batch_store_contention_storm_damper.py`
  (damper unit semantics, store integration, production-label inventory,
  deadline/kill-switch interplay, log taxonomy).
