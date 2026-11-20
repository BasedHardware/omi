# 2026-11-20: An empty first-summary merge records debt instead of failing the write

Contract: [Recording-derived conversations v3](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3).

`merge_result` raised `SummaryOutputUnavailable` for every open first-summary
obligation whose structured output was empty. Only the enrichment consumer
catches it and records a bounded empty-output strike; request paths
(from-segments, finalize) and direct sync persists let it escape, aborting the
completed write and surfacing as a 500 on
`POST /v1/dev/user/conversations/from-segments`.

The fence now raises only where a caller can act on it:

- A consumer owns the write (`PROCESS_CONTEXT`): raise, so the consumer records
  the bounded strike before releasing the lease.
- A finalization job owns the row and the repair pass refuses it as
  `generation_owned` (`finalization_job_id` set, no verified batch-projection
  handoff): raise, so the job stays retryable and its next attempt can still
  deliver a summary.
- No consumer and no retryable job (from-segments, direct sync persist): commit
  the empty attempt with `summary_due_at` still armed. The repair pass re-wakes
  the row and the consumer's three-strike budget bounds the retries.

An empty structured is still never a delivered summary. Prompt content, model
routing, metering and the from-segments identity/retry contract are unchanged.
The consumer also acks an empty reprocess output on an already-enriched row
instead of retrying it forever.

Rollout: no flag. The kill switch is reverting the empty-output handling, which
restores the previous raise-and-retry behaviour. No data migration is involved.

Regression evidence in [PR #25890](https://github.com/BasedHardware/omi/pull/25890)
covers empty then success, empty twice, an import whose merge carries an empty
summary, a finalization-owned empty attempt that keeps its job retryable, and a
projection-verified row that commits with debt.
