# Batch maintenance: one contended step no longer starves the sweep

Status: shipped on the batch record lane. Owner: batch record lane / rollout lead.
Flag: `BATCH_PIPELINE_MAINTENANCE_CONTINUATION_ENABLED` (default on; kill switch
restores the abort-at-first-failure sweep).

## What problem this solves

The worker's maintenance tick (`utils/batch_pipeline/pump.py` `_maintain`) and
the lease-expiry recovery loop it drives
(`utils/batch_pipeline/scheduler.py` `recover`) run independent work in a fixed
order under one leader: pending projections, expired-lease recovery, the
`result_ready` page probe, its per-owner drain, and the durable hold markers.
Every step before the hold markers ran bare: the first exhausted contention
budget — `firestore_transaction_contention ... outcome=exhausted` bubbling out
of a `batch_recover` item transaction — aborted the whole sweep. The 1-second
maintenance loop then re-ran the full sweep from the top, re-striking the same
hot document while every step behind the failure stayed starved: no
`result_ready` drain, no hold markers, and every expired lease behind the
failing item unrecovered. The prod signature is the Loop S sensor's
`event=batch_maintenance outcome=retry exception_type=FirestoreContentionExhausted
site=firestore_transaction_retry.py:` (x180/30m), and every one of those events
means an entire sweep's worth of independent work was skipped that tick.

The store-level contention storm damper (see
`batch-contention-storm-damper.md`) already spaces re-strikes of an exhausted
operation; it cannot stop the sweep from abandoning its own remaining steps.
`recover` itself recovered only one item per pass behind a hot item: its
per-item loop caught `BatchPrivacyBlocked` and continued, but a
`FirestoreContentionExhausted` from item k killed items k+1..N for that pass,
and — because the whole sweep aborted — for every 1-second retry pass too.

Failure-Class: FC-immediate-retry-loses-shared-cas

## Design

- Sweep steps are individually bounded (`pump._maintain_leader_steps`): the
  projection step, the recovery pass, the `result_ready` page probe, the page
  drain and the marked-hold page each run under `_maintenance_step`, which logs
  a lost step as `event=batch_maintenance outcome=retry step=<projection |
  recover | ready_due | marked_page> exception_type=<class> site=<file:line>`
  and lets the sweep continue with the remaining steps. A lost step retries at
  the next sweep (>=5s later); the sweep cadence bounds the re-strike and the
  store-level damper spaces it. Already-isolated paths keep their existing
  scoped logs (`ready_page`, `marker`, `held` re-offer) and semantics.
- Recovery continues past a lost item (`scheduler.recover`): a
  `FirestoreContentionExhausted` from one item's `batch_recover` transaction is
  logged as `event=batch_recover outcome=retry scope=item exception_type=...
  site=...` and the loop moves to the next due item, which recovers this pass.
  The lost item stays due and is re-decided at the next sweep. The pre-loop
  legacy migration gets the same treatment with `scope=migrate`. Any other
  exception still aborts the pass (fail-noisy on real bugs) — only the closed
  contention class continues.
- The sweep cadence contract tightens: the leader-gated block now completes
  (steps ran or logged their loss), so `_last_recovery` updates even when every
  step lost, and the next sweep waits out the 5-second recovery interval
  instead of the legacy 1-second full-sweep re-strike. Metrics sampling keeps
  its own 15-second cadence and is unaffected by step losses.
- Kill switch: `BATCH_PIPELINE_MAINTENANCE_CONTINUATION_ENABLED=false` restores
  the previous behavior byte-for-byte — first failure aborts the sweep, the
  exception propagates to the maintenance loop's
  `event=batch_maintenance outcome=retry` log, and `_last_recovery` stays
  unupdated so the next loop tick re-runs the full sweep.

## Contracts that do not change

- Step order and inputs: projection before recovery before the `result_ready`
  page (limit 100) before its drain before the marked-hold page (limit 50);
  `time.time()` is still evaluated per step, in the same order.
- The leader gate: non-leader pumps skip the gated steps and still re-offer
  their held owners; a leader-lease acquisition failure still fails the tick
  (it is the gate itself, not a step behind it).
- Recovery decisions: a successful item transition still runs the same
  fenced commit — quarantine on the attempt cap, requeue on a due `retry`
  item, `BatchPrivacyBlocked` still quarantines fenced and continues.
- Observability volume: successful steps and items log nothing new; only
  losses log, with static fields (no uid, no segment id).
- The maintenance loop's catch-all log remains the last-resort net for
  failures outside the isolated steps.

## Rollback

Flip `BATCH_PIPELINE_MAINTENANCE_CONTINUATION_ENABLED=false` (env) or revert
the two call sites; no durable state is introduced — skipped steps and items
are exactly the work the legacy sweep would have abandoned, retried at the
next sweep instead of never.
