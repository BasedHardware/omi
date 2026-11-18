# Quiet recovery of a capture with a placeholder title

A short, decoded capture with only a fallback label can reuse the quiet recovery
minimum without calling the notes model. The existing path also accepts a
transcript-derived `server_minimum` title. For either title, quiet recovery
requires an empty gist, default structured metadata and no owner corrections.
Longer captures, captures with previous Home metadata and captures with owner
corrections continue through normal notes processing.

The [placeholder admission change](2026-11-18-recovery-admits-placeholder-stub.md)
allows these jobs into recovery. Both the short-transcript minimum and the
final-attempt fallback after an empty notes response use the same metadata
guard. If the final attempt cannot produce useful notes for a protected row,
recovery keeps the existing refusal and leaves the stored content intact.
The batch-audio handoff is unchanged.

See [the server recovery contract](../../listen_pusher_pipeline.mdx#replay-without-changing-listen-admission).

Deploy to the backend finalization worker with the existing
`LISTEN_FINALIZATION_RECOVERY_MINIMUM_TERMINAL_ENABLED` setting. Check the
`selfheal_guard` events for `kept_minimum/content_below_floor` and finalization
dead letters after the rollout. Revert the commit if the change regresses
quiet recovery.
