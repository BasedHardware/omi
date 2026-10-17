# Flutter client telemetry emission

Migration and PostHog retirement default off. Delete-class changes are active:
routine `Mobile Render Observation` is not sent to PostHog, and
`wal_transcript_coverage` is debug-log only.

PostHog ingestion-side sampling is also active; see the [sampling table](../../../../web/admin/docs/posthog-events.md#ingestion-sampling-since-2026-10-17).
New events default to 2% unless added to the explicit keep-list or matched by
its keep rules. Cloud Run server events stay dark.

`Recording Requested` stays on PostHog. It means capture-session preparation,
not a confirmed user attempt and not audio start. `request_origin` is
`explicit_user` only for `PhoneStartRequested` and explicit Transcribe Later,
`automatic_roll` only for a batch-mode phone session roll, and `unknown`
otherwise.

Replacement observations use `POST /v1/telemetry/client/batches` only when
`OMI_CLIENT_TELEMETRY_MIGRATION` is enabled. The outbox flushes after 30
seconds, at 100 observations, and best-effort on background. HTTP 202 is
`accepted`. A later `completed` is emitted only after durable job confirmation.
Paced 429 is `deferred`. Native `unverified_since_ms` is a timestamp, so
ingress omits `unverified_duration_ms` rather than inventing one. The
10-second pendant drain, WAL custody, and upload scheduling are unchanged.

Real collector deployment and seven-day canary acceptance are pending. Do not
enable the migration or retirement flags in this lane.
