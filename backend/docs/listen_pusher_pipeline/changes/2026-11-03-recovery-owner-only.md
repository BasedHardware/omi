# Owner-only post-recovery publication

Successful quarantine recovery now requests an explicit owner-only drain. It
commits the recovered owner's ready results, walks the owner's projection
chain, and schedules that walk's durable follow-ups without global discovery
or launching unrelated queued follow-ups. Deferred index work is scoped to the
recovered owner. If owner-chain projection is disabled, its durable receipt
waits for the periodic generic sweep instead of triggering a request-time scan.
Global cleanup, enrichment, lease/retry recovery, projection scans and queue
sampling remain on periodic serving reconciliation. The independent supervisor
waits 20 seconds after each pass; the maintenance lease TTL is 60 seconds.

`BATCH_PIPELINE_RECOVERY_OWNER_ONLY_ENABLED` defaults on. Set it to `false` to
restore the previous full reconciliation request. Existing merge, predecessor,
privacy and paid-intent fences apply. An interrupted request leaves the settled
merge-pending job or pending/persisted result receipt discoverable on the next
periodic pass, including after process replacement.

The handler emits `event=batch_recovery_stage` with `stage=recognition` and
`stage=post_recovery`, plus `duration_seconds`, even when either stage raises.
Recognition includes materialization, VAD, provider work and intent settlement;
it is not a provider-only timer. No identifiers enter these fields.

Deploy verification: post-provider request dwell and post-recovery stage latency
should fall; maintenance aborts should fall; prepared/held age should trend down;
the recovery queue slope should turn negative until caught up. These are
expected directions, not measured post-deploy claims. Queue limits stay at 16
concurrent tasks and 8 dispatches/second. No audio custody or deletion changes.

See the [serving contract](../../batch-pipeline-serving.md) and
[pipeline overview](../../listen_pusher_pipeline.mdx).
