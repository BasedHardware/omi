# Retained batch held expiry and rollback recovery

GPU worker holds gain a seven-day deadline, retained `dead(held_expired)` state,
a bounded nightly re-drive and an agent-tier stock/rate alert. The default-on
`BATCH_HELD_DEAD_LETTER_ENABLED` kill switch stops new stamps and automatic
maintenance; manual requeue remains available. See the
[runbook](../../runbooks/batch-held-dead-letter.md) and
[pipeline contract](../../listen_pusher_pipeline.mdx).

Expiry atomically sets `merge_pending=true` so the existing `redrive_dead` path
can recover rows after a code revert, even before the first nightly pass.
The reason, deadline, encrypted audio references and attempt history remain.
Nothing is deleted and privacy/content fences are unchanged. Rollback recovery
is covered by unit tests and a loopback Firestore race using only the legacy
re-drive with the feature disabled; live execution and alert delivery were not
measured. This PR does not deploy.
