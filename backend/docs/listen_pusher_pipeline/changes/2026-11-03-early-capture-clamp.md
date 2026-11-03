# Recover reset-clock sync uploads

V2 now accepts well-formed pre-2024 filename stamps under the default-on
`SYNC_EARLY_CAPTURE_CLAMP_ENABLED` kill switch. Malformed and implausibly future
stamps keep their existing rejection policy. No client change is required to
admit a retry; clients with the old nonworking Retry button still need an update.

The raw filename remains the content/dedupe identity and ordering source.
Stored early-clock spans move together to server receipt time, preserving
duration and order. Their age remains untrusted and their work uses backfill
pacing. Both the batch and legacy sync paths consume the normalized clock.

Deploy through the backend and backend-sync Cloud Run train (including the
backfill worker). Observe `omi_sync_capture_time_total{outcome="accepted_early_clamped"}`
and the content-free `event=sync_capture_time` log. Roll back admission with
`SYNC_EARLY_CAPTURE_CLAMP_ENABLED=false`; retained raw filenames remain retryable.

Contract: [sync admission](../../listen_pusher_pipeline.mdx).
