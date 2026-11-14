# Queued transcription remains Transcribing

The [Home presentation contract](../../listen_pusher_pipeline.mdx#home-transcription-presentation)
now computes a 24-hour read bound instead of treating the old two-hour SLA stamp
as an observed transcription failure. Existing rows heal at their next read;
there is no backfill, lifecycle write, job lookup, or extra Firestore document
read. The same projection covers episode member steps and all-pending episode
titles. Explicit failure receipts still win; expired waits belong to Activity.
The wait starts at the server's pending stamp, never capture end. If only the
deadline survived, subtract the configured deadline interval; use creation only
without either stamp. New upload revisions may start a new bounded wait, while
reads and same-generation retries cannot renew it. Offline capture age therefore
cannot make a newly arrived recording fail immediately.

`HOME_TRANSCRIPTION_QUEUE_HOLD_ENABLED=true` and
`HOME_TRANSCRIPTION_MAX_AGE_SECONDS=86400` are pinned for backend-listen, pusher,
backend, backend-sync, backend-sync-backfill and backend-integration in both
environments and the matching listen/pusher charts. The original
`HOME_TRANSCRIPTION_DEADLINE_SECONDS=7200` writer stamp stays unchanged.
Roll Cloud Run backend for `api.omi.me` Home REST reads and backend-integration
for MCP/integration reads, so existing rows heal. The live URL map routes only
listen WebSockets to GKE backend-listen. The listen/pusher and sync finalization
writers do not need a stamp migration. Rollback: set the queue hold switch false on readers.

The mobile retry chip also accepts `home_step=failed`, independently of
`summary_retryable`; queued rows must therefore lose both retry signals.
Reprocess runs notes over the current transcript and does not requeue a batch
record seal. It must not be advertised as queued transcription recovery.

Focused hermetic tests cover old stamps, the exact 24-hour boundary, retry
suppression, explicit errors, episode titles, rollback, field masks and runtime
pins. Deployment, phone refresh and production acceptance require lead readback.
