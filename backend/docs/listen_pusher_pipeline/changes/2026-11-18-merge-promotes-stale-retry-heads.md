# Ordered merge promotes an owner's due retry heads

## Problem

About 80% of sealed recordings waited the full 60 s merge head wait. The owner's earliest pending row was a
`retry` job that was days past its `available_at`, unleased, and never re-run. The head-wait bypass then committed
the new recording 60 s late.

Due retries rejoin the scheduler only through `Scheduler.recover`, which requeues the oldest-due page of 100 per
pass on the serving maintenance leader and the GPU pump leader. Prod, read-only, 2026-11-18 08:40–08:50Z:

- 1,100,972 jobs in `retry`; 1,076,409 already due; 58 `ready`, 43 `leased`.
- The oldest due row was 93.8 h overdue. Over 155 s the front advanced 184 s of `available_at`, about 3 rows/s.
  At that rate the 94 h lag takes about 20 days to clear.
- About 95% of due rows at every depth (samples at 1, 6, 24, 48, 72, 90 h) are `held / allowance_exhausted`. The
  GPU worker image `ef42ee8` predates allowance parking, so its pump requeues them and its defer re-holds them for
  2 h. They cycle back through the same page.
- A page snapshot fully turned over in 32 s: 91 of 100 rows were allowance holds re-deferred for 2 h.
- Heads of 126 owners whose rows were committed through the head-wait bypass in the last hour: 27 of 40 strict
  heads and 27 of 42 fresh heads were `retry`. 46 of them had compute `allowed / entitled` and were due 15–91 h
  earlier, untouched since 2026-11-14…17.

The allowance-parking rollout (`docs/runbooks/batch-allowance-parking.md`) removes the cycling holds. It needs the GPU
roll and a migration estimated at 12.6 days. It does not change how fast an entitled retry reaches the front.

## Change

`OrderedMerge.commit_next` records any `retry` row it reads as the owner's strict head (`first_pending`) or fresh head
(`fresh_first_pending`). When one is due and the strict and tx-fresh attempts committed nothing, the merge promotes it
before the probe and head wait. It also promotes the owner's
due `retry` rows from the existing fresh-pending page (`fresh_pending`, 32 rows). At most 8 rows are promoted per
call, in capture order. An owner with more continues on its next drain.

Promotion is `scheduler.requeue_due_retry`, the transition `recover` already performs, now shared by both callers:

- an allowance-held row parks (`allowance_held`, `merge_pending=false`) and stops blocking the owner;
- any other due row returns to `ready` through the owner's DRR queue and runs under ordinary admission.

Each row is re-read in its own transaction and must still be this owner's `merge_pending`, due `retry` row. A failed
promotion is logged (`event=batch_merge outcome=stale_head_promote_retry`) and leaves the row to `recover`.

The bound follows from existing transitions. A promoted row that fails again backs off (`_defer`, 5·2^(attempt−1) s)
and is promoted on its next blocked drain. At `max_attempts` (5) the worker failure quarantines it, which clears
`merge_pending` and uses the existing held-recovery presentation. No audio, result or obligation is dropped.

## Cost

- No new query or index. `fresh_pending` runs only when a due retry head was read, or an owner's previous promotion
  was capped.
- One transaction per promoted row, the same reads and writes as one `recover` requeue.
- Rows run sooner, not more often; retry attempt accounting is unchanged.

## Readback

`event=batch_merge outcome=stale_head_promoted action=requeued|allowance_parked count=N`, from the serving drains.
Expect a short burst after deploy. Then `outcome=head_wait_bypass` falls as owners' stale prefixes commit or park.

## Rollout

Default on with the backend release. The GPU pump keeps its old merge until its next image roll; serving drains
promote for every owner meanwhile. Rollback is a revert.
