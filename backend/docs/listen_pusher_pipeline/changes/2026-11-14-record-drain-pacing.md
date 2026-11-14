# Idle record-drain pages without parent-row progress

Full pages previously rescanned immediately even when every selected recording
was deferred, failed, or still behind its upload barrier. The drain now keeps
the idle wait unless a selected parent row leaves `record_pending` for a
non-dead state. Dead-letter expiry still records its metric without counting
as admission progress.

The [pacing contract](../../listen_pusher_pipeline.mdx#record-drain-pacing)
documents the default-on `RECORD_DRAIN_IDLE_WITHOUT_PROGRESS` control and its
`off` rollback value. Due rows remain eligible for subsequent pages, at one
page per idle interval when no parent row progresses. Partial-record
coordinators can admit child units while remaining pending; those passes also
idle for 20 seconds. This conservative signal avoids treating unchanged
inventory polls as progress, at the cost of that delay for productive partial
pages.

After deployment to backend-integration, verify that
`omi_firestore_billed_reads_by_caller_total` for
`database.batch_pipeline_store:due` falls toward 100 reads/second, that
`database.batch_pipeline_store:get` falls, and that record admissions per
minute stay unchanged. In particular, watch partial-record backlog throughput.
If admissions regress, use the rollback switch. Leave the privacy-defer
setting unchanged until these deployment checks pass.

Regression coverage: `test_record_drain_pacing.py`,
`test_record_drain_privacy_defer.py`, `test_batch_pipeline_live.py`, and
`test_record_drain_barrier_backoff.py`. These cover idle and productive pages,
partial pages, no-op polls, rollback, and dead-letter progress accounting.

PR: https://github.com/BasedHardware/omi/pull/24882
