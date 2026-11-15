# Episode membership at batch audio close

Batch-owned captures could finish audio custody with no transcript, title or
episode membership, then wait for finalization as separate timestamp rows on
Home. After the archive-close barrier, the listen controller now attaches their
committed audio span through the existing recorded-time transaction before
queueing finalization. Replays reuse that transaction's membership fences.

The [batch handoff contract](../../listen_pusher_pipeline.mdx) retains the same
archive barrier and conversation reread. Attachment adds no conversation transcript/title or
status write and no paid work. Privacy, locks, deletion, discard and donor guards
remain authoritative. Failed attachment emits shared fallback telemetry and
leaves ordinary finalization as its existing repair path; source rows remain
available while waiting. Existing episode admission and recorded-time kill
switches control this metadata attachment. `EPISODE_BATCH_CLOSE_ATTACH_ENABLED`
additionally restores attach-after-transcription when disabled.

After merging episodes batch 1, pending deadlines share its outer fenced
transaction and candidate reuse. A close replay requires the current canonical
partition proof and committed archive bounds; it does not use processing clocks
or claim completed transcript recovery in the sync memo. Close replay idempotency
also holds when `EPISODE_ATTACH_OPTIMIZATIONS_ENABLED` is off. Sync attachment,
composer settling and foreground-read behavior retain their batch-1 controls.

Backend deployment is owned by the rollout lead. Home settling/title reads are
PR #24497; the mobile joined paint, neutral placeholders and unattached processing
runs are PR #24541. This change is independent of their deployment/build schedule.

Regression coverage: `backend/tests/unit/test_episode_batch_audio_close.py` pins
recorded bounds over arrival clocks, canonical transaction reuse, no paid calls,
policy guards, same-call close/attach/queue ordering and observed failure recovery.
