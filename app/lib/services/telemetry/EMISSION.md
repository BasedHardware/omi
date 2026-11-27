# Flutter client telemetry emission

Migration and PostHog retirement default off. Delete-class changes are active:
routine `Mobile Render Observation` is not sent to PostHog, and
`wal_transcript_coverage` is debug-log only.

PostHog is for product analytics only (David Zhang, 2026-11-23, SCA-3665).
Debugging and health signals belong in the client telemetry collector (#21449)
and Prometheus, not PostHog. PostHog ingestion sampling is configured in
`contracts/analytics/posthog.json`: new events default to 2%, and readers
weight rows by `100 / omi_sample_pct` (see
[Ingestion sampling](../../../../web/admin/docs/posthog-events.md#ingestion-sampling)).
Changing a rate means editing that file in a PR; CI prints the cost and
`scripts/posthog/apply.py` applies it after merge. Cloud Run server events
stay dark.

`Pendant Frames Dropped` and `WAL Reconcile Poll Summary` are typed, count-only
WAL health observations with no client sampling. Drops aggregate by closed
reason across each nonempty flush window; a summary is emitted once per
anomalous reconcile pass with an admitted poll: backlog beyond the minute's
18-request budget, transient/throttle results, or missing-job confirmation.
Missing confirmation, network transients, and local deferrals are separate
counts. Routine successful/nonterminal polling and empty/budget-only wakes
emit nothing. The existing request budget also bounds summary volume.
No content, account/device/job/WAL identifiers or raw errors are properties.
`disk_space_unknown` and `storage_write_failed` remain distinct from
`disk_reserve`; `count_cap` should be zero after the capture hotfix.

These are health signals: their fleet counts belong in the collector, not in
PostHog. Since SCA-3665 (2026-11-23) PostHog drops both at ingestion
(`contracts/analytics/posthog.json`), so the WAL backlog consumer reads
nothing from PostHog until it moves to the collector. Do not add them back. This
repository change does not deploy an alert, bypass consent, or guarantee SDK
delivery. The executable consumer is
`contracts/analytics/consumers/wal-backlog-health.json`.

`Recording Requested` stays on PostHog. It means capture-session preparation,
not a confirmed user attempt and not audio start. `request_origin` is
`explicit_user` only for `PhoneStartRequested` and explicit Transcribe Later,
`automatic_roll` only for a batch-mode phone session roll, and `unknown`
otherwise.

The `mobile_lag_*` lag capture (`lib/utils/analytics/lag_recorder.dart`) is
local debug-log only, behind the same Debug logs switch, and never transmitted.
It shares the render observations' `mobile_render_diagnostic` log type; its
`event` field names the lag event.

Replacement observations use `POST /v1/telemetry/client/batches` only when
`OMI_CLIENT_TELEMETRY_MIGRATION` is enabled. The outbox flushes after 30
seconds, at 100 observations, and best-effort on background. HTTP 202 is
`accepted`. A later `completed` is emitted only after durable job confirmation.
Paced 429 is `deferred`. Native `unverified_since_ms` is a timestamp, so
ingress omits `unverified_duration_ms` rather than inventing one. The
10-second pendant drain, WAL custody, and upload scheduling are unchanged.

Real collector deployment and seven-day canary acceptance are pending. Do not
enable the migration or retirement flags in this lane.

## Firmware adoption

`Firmware Update Started`, `Firmware Update Upload Finished`, `Firmware Update
Install Requested`, `Firmware Update Completed`, and `Firmware Update Failed`
use `AnalyticsManager.track` and its consent/identity/retry queue, then
`PostHogAnalyticsAdapter` (default host `https://us.i.posthog.com`). They remain
on that route when `posthogRetirementEnabled` is true; the frozen client-batch
schema has no firmware family. One random attempt id joins the funnel. Only a
fresh DIS revision after DFU can produce Completed (`verified: true`);
`to_version` is observed, never the requested version. A known starting
revision must change, even when it equals the target. Only an unknown starting
revision may be verified by matching the target.

Device Connected/Paired carry `firmware_revision`, `model`, `hardware_family`.
Device Session Ended deliberately remains on PostHog with retirement enabled:
its client-batch replacement lacks those adoption dimensions. Missing metadata
is `unknown`. The reconnect owner refreshes DIS before emitting Connected.

`contracts/analytics/posthog.json` keeps Device Paired/Session Ended in the
keep-list; Device Connected and unlisted long-tail events, including the
firmware funnel, are at 2%. Firmware funnel counts weight rows by
`omi_sample_pct` instead of asking for a keep-list entry; keeping one at 100%
takes a PR with a measured estimate and a reader. No collector schema,
production account, or remote flag is changed.
