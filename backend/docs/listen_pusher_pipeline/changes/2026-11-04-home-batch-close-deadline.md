# Bounded pending members at batch audio close

PR #24544 stamps a fixed pending-transcription start/deadline atomically with
episode membership. It reuses the batch timeliness 2h alarm bound (30m target).
Home returns an honest processing placeholder before delivery, and a failed
outcome after a finalization dead letter, failed status/upload or deadline.
Successful late projection restores ordinary metadata; retained audio and retry
work are preserved. The read-observed overdue counter has no labels. Its info
alert is staged in `charts/monitoring/pending/episode-batch-pending.json`,
alongside batch timeliness monitoring, without provisioning.

`EPISODE_BATCH_CLOSE_ATTACH_ENABLED` is on unless explicitly disabled. Off
restores attach-after-transcription while leaving other episode paths enabled.
Canonical recorded-component close replays leave versions, links and the timeline
fence unchanged. Deadline stamping is idempotent, including existing membership.

Contract: [batch capture](../../listen_pusher_pipeline.mdx#server-batch-only-capture-by-platform).
Guards: `tests/unit/test_episode_batch_audio_close.py`,
`tests/unit/test_episode_home_read.py`, `tests/unit/test_recorded_span.py`,
`tests/unit/test_late_audio_recorded_time.py`, `tests/unit/test_batch_pipeline_timeliness.py`, `tests/unit/test_episode_batch_pending_alert.py`.
