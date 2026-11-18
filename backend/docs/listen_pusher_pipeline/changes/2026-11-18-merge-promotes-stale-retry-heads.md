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
(`fresh_first_pending`). When one is promotable and the strict and tx-fresh attempts committed nothing, the merge
promotes it before the probe and head wait. It also promotes the owner's promotable rows from the existing
fresh-pending page (`fresh_pending`, 32 rows), in capture order.

A row is promotable only when its next attempt is bounded:

- a worker-failure or lease-expiry retry (latest decision allowed, unattempted or none, no refusal streak), which
  charges an attempt when it fails again;
- a parkable allowance hold (`held / allowance_exhausted` with parking on), which parks.

A non-allowance policy hold (fair use, budget) and an unevaluated refusal are not promoted. `Scheduler.defer` refunds
their attempt, so promoting them could cycle. They stay with recovery and the head-wait bypass, unchanged.

Promotion re-reads the row in its own transaction. It must exist, belong to the owner, be `merge_pending`, still be a
due promotable `retry`, and have fewer than 3 promotions (`stale_head_promotions`). Then:

- an allowance hold parks (`allowance_held`, `merge_pending=false`) and stops blocking the owner;
- any other row returns to `ready` through `scheduler.requeue_due_retry`, the transition `recover` uses. Its
  service class drops by capture age the way record intake classifies (`config.record_drain.capture_age_priority`:
  FRESH within 10 min, RECENT within 7 days, DEEP after), never rises. The admission value moves to
  `admitted_priority`, which both identity checks (`enqueue_in_transaction`, provider admission) compare, so an
  idempotent re-admission still matches. A days-old head cannot outrank a live capture in the FRESH ring.
- a commit-boundary `BatchPrivacyBlocked` takes recovery's disposition, `store.quarantine_fenced`.

Protected-share eligibility is not consulted: like recovery's ordinary oldest-due page this is a plain requeue,
and lease admission still applies.

## Bounds

- Per merge call: 8 rows. Per process: a token bucket of 2 promotions/s, burst 16, shared by every drain.
- Per row: 3 promotions. A promoted row either completes, fails again and is charged an attempt, or is refused by
  admission and stops being promotable. After 3 promotions recovery and the head wait own it again. Worker
  failures still quarantine at `max_attempts` (5), which clears `merge_pending`.
- Owners continued after a bound are tracked in an LRU of 1,024 entries that expire after 600 s.
- A failed promotion is logged (`event=batch_merge outcome=stale_head_promote_retry`) and leaves the row to `recover`.

## Cost

- No new query or index. `fresh_pending` runs only when a promotable head was read, or an owner's previous
  promotion stopped at a bound.
- One transaction per promoted row, the same reads and writes as one `recover` requeue, plus the counter field.
- At most 7,200 promotions per process-hour.

## Readback

`event=batch_merge outcome=stale_head_promoted action=requeued|allowance_parked|privacy_fenced count=N` from the
serving drains. Expect a short burst after deploy. Then `outcome=head_wait_bypass` falls as owners' stale prefixes
commit or park.

## Rollout

`BATCH_PIPELINE_MERGE_STALE_HEAD_PROMOTE_ENABLED` (ops kill, default on). `false` restores waiting for recovery.
Rows already demoted keep `admitted_priority`. The GPU pump keeps its old merge until its next image roll; serving
drains promote for every owner meanwhile.

Mixed versions: a demoted row needs a reader of `admitted_priority`. Code before this change compares the stored
(demoted) `priority` and refuses an idempotent re-enqueue of that segment as reused work. Before rolling a CPU image
back past this change, set the kill switch to `false` first; rows it already demoted still refuse an old-image
re-enqueue until they finish.

An `allowance_parked` promotion unblocks the head but returns no commit from that call; the owner's next ready row
commits on the next wake or serving tick (10 s).

Emulator proof: `backend/scripts/merge_stale_head_emulator_test.py` (sim + Firestore emulator, in
`run-emulator-proofs.sh`).
