# 2026-11-18: a sealed recording no longer waits 60 s behind a starved merge head (canary)

Contract: [stale merge head skip](../../listen_pusher_pipeline.mdx#stale-merge-head-skip-canary).

## What changed

`OrderedMerge.commit_next` keeps the bounded head wait (`BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS`, default 60).
For an owner listed in `BATCH_PIPELINE_MERGE_STALE_HEAD_UID_ALLOWLIST`, the wait is skipped when the owner's
strict head is unready and was enqueued at least 1,800 s ago (`MERGE_STALE_HEAD_SECONDS`). The skip commits
the row the expired wait would commit: the owner's earliest ready pending row, through the same transaction
body. That row must be a native record unit whose earlier binding units are committed or held without
recovery; the transaction re-reads the head and refuses if it is no longer stale. The bypassed head later
appends as `late_capture`, as it does today after 60 s.

## Why

Prod, 2026-11-18 (600 random `batch_live_v1` rows with `record_sealed_at`, sealed 45 min to 8 h before
07:50Z): the last unit of a recording took p50 9 s from admission to GPU result, then p50 62 s more to
commit. 346 of 432 fully committed recordings (80%) committed their last unit through the head-wait bypass
(p50 67 s single-unit, 98 s multi-unit); without the bypass the commit took 0.1 s. In 20 of 20 sampled
owners, the earliest pending fresh-class row was a native record job in `retry`, captured 36–215 h earlier
and due long ago. `fresh_capture` is fixed at admission, so the tx-fresh gate and `_fresh_pick` treat these
rows as fresh heads, and every new recording waits out the full head wait.

## Scope and rollout

- Unset or empty allowlist: no behavior change for anyone. The flag is read on each commit.
- Unchanged: head wait off (`<=0`/`off`), non-record rows, an unready earlier unit of the same
  recording, and heads enqueued less than 30 minutes ago. All of these keep the ordinary wait.
- CPU serving merges run this code after a backend roll. The dedicated GPU pump image (`ef42ee8` on
  2026-11-18) keeps its 60 s wait until it rolls; both writers share the owner transaction, so mixed
  versions are safe. Until the GPU rolls, a listed owner commits on the next CPU serving maintenance
  pass (`BATCH_PIPELINE_SERVING_TICK_SECONDS=10` on prod backend-integration) rather than at publication.
- Starved `retry` heads are a separate scheduler problem; this change does not touch their leasing.

## Cost

No new query or poll. A skipped wait reads at most i predecessor jobs for unit i inside the existing commit
transaction (zero for a single-unit capture), only for listed owners.

## Rollback

Remove the uid from `BATCH_PIPELINE_MERGE_STALE_HEAD_UID_ALLOWLIST` (or unset it). Already committed rows keep
their order; no migration.

## Readback

`event=batch_merge outcome=stale_head_skip` logs; per recording, `batch_pipeline_prod_results.committed_at`
minus `batch_pipeline_prod_jobs.ready_at` for the listed owner's last unit.
