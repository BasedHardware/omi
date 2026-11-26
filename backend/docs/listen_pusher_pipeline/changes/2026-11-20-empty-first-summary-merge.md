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

## 2026-11-22 follow-up: the legacy `sync_handler` path no longer re-raises

The consumer path already recorded the bounded strike, but the legacy
`utils.enrichment.outbox.run` path (the default `ENRICHMENT_ROUTE=sync_handler`,
reached by `/v2/sync-jobs/run`, `/v1/conversation-finalization-jobs/run` and the
batch-pipeline enrichment RPC) still re-raised `SummaryOutputUnavailable` on the
first two strikes and on an already-enriched row's empty reprocess. Both escaped
as a 500 on the request.

`run` now settles the same way the consumer does:

- Already-enriched row (no `PROCESS_CONTEXT`): settle the reprocess instead of
  raising; the delivered summary is untouched.
- Strike 1-2 (`EmptyFailureOutcome.RETRY`): the strike is recorded and the row is
  re-armed under `deferred_reason=empty_output` for its bounded retry
  (`LIVE_DEFER_SECONDS`), so the debt and wake stay intact.
- Strike 3 (`EmptyFailureOutcome.BLOCKED`): unchanged terminal outcome
  (`summary_blocked_reason`, dormant row).

An empty structured is still never a delivered summary. No prompt, routing,
metering or from-segments contract change; no data migration. The kill switch is
still reverting the empty-output handling.

## 2026-11-22 follow-up: the strike write itself can no longer fail the request

The residual `SummaryOutputUnavailable` events after the 11-20 serving were not
the raise escaping: the consumer caught it and called `record_empty_failure`,
whose Firestore transaction then failed. `_Transactional` replays the same
transaction id on contention, which cannot work once Firestore has retired that
id, so the commit came back `400 The referenced transaction has expired or is no
longer valid` (or `409 Aborted` once contention was exhausted). That error
escaped the consumer's `except` block as a 500, with the caught
`SummaryOutputUnavailable` as its context — which is what Error Reporting
grouped.

`record_empty_failure` now runs through `run_transactional`, which restarts an
expired transaction with a fresh id. A strike that still cannot land returns
`EmptyFailureOutcome.UNAVAILABLE` instead of raising; both callers (the consumer
and the legacy `run`) re-arm the row for a bounded retry, so the debt and wake
stay intact and the next attempt records the strike. A permanent rejection
(permission denied, document size) still raises. An empty structured is still
never a delivered summary; no prompt, routing, metering or from-segments change.
