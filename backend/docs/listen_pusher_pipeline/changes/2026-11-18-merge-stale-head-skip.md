# 2026-11-18: a sealed recording no longer waits 60 s behind a starved merge head (canary)

Behavior and switch: [stale merge head skip](../../listen_pusher_pipeline.mdx#stale-merge-head-skip-canary).

## Why

Prod, 2026-11-18 (600 random `batch_live_v1` rows with `record_sealed_at`, sealed 45 min to 8 h before
07:50Z): the last unit of a recording took p50 9 s from admission to GPU result, then p50 62 s more to
commit. 346 of 432 fully committed recordings (80%) committed their last unit through the head-wait bypass
(p50 67 s single-unit, 98 s multi-unit); without the bypass the commit took 0.1 s. In 20 of 20 sampled
owners the earliest pending fresh-class row was a native record job in `retry`, captured 36-215 h earlier
and due for hours without a lease. Sampled owners had 8-134 such rows. All 75 rows ahead for the canary
owner are `retry`, due 10.3-90.3 h (`available_at`) and unleased, so they meet the starved rule.
`fresh_capture` is fixed at admission, so these rows act as fresh heads and every new recording waits
out the full head wait.

## Rollout

- Unset or empty allowlist changes nothing. The canary is one uid on prod backend-integration, the serving
  loop host (`BATCH_PIPELINE_SERVING_TICK_SECONDS=10`): a listed owner commits on the next serving pass.
- The dedicated GPU pump image (`ef42ee8` on 2026-11-18) keeps its 60 s wait until it rolls. Both writers
  commit through the same owner transaction, so mixed versions are safe.
- Starved `retry` rows are a separate scheduler problem; this change does not touch their leasing.

## Cost

No new poll. A skip attempt reads up to 129 pending jobs in one transactional query (same filters, order
and index as `first_pending`), plus at most i predecessor jobs for unit i. Only listed owners pay it.

## Rollback

Remove the uid or unset the variable. Committed rows keep their order; no migration.

## Readback

A skip leaves no durable marker: the result row carries neither `head_wait_bypass` nor a skip field. Readback
relies on the `event=batch_merge outcome=stale_head_skip` log line, plus, for the listed owner's last unit,
`batch_pipeline_prod_results.committed_at` minus `batch_pipeline_prod_jobs.ready_at`.
