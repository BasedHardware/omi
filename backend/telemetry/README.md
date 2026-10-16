# Fleet telemetry v1

`POST /v1/telemetry/fleet` uses the existing Firebase ID-token dependency
(`Authorization: Bearer <Firebase ID token>`). Optional platform/device registration and locked-content recovery hooks in
the shared auth dependency are skipped on this content-free endpoint; token
verification, QA admission, deletion/cutover fences and BYOK checks still apply.
The public wire contract is
[fleet_schema.json](fleet_schema.json); [fleet_registry.json](fleet_registry.json)
owns allowed event/outcome pairs and histogram edges. Generate/check it with
`python3 backend/scripts/generate_fleet_schema.py [--check] [--inventory <KB export>]`.
The inventory coverage helper selects the client-side ops mapping rows, excludes
only the three upload events assigned to server observation, and checks exact
name equality. The registry retains inventory names, not arbitrary metric names.

Clients aggregate exact deltas over non-overlapping windows, normally 15 minutes,
and flush on background/exit when the budget permits. Across all devices for one
UID the hard budget is 12 requests in an hour beginning at the first request.
Foreground/background churn must coalesce into that same budget; do not retry 429
before `Retry-After`. Rejected reservations do not increment the Redis budget. This handler emits no
per-attempt logs or customer-store writes; authentication/security-fence reads
still run. Invalid admitted requests consume a slot. Redis
failure returns 503 (fails closed), independent of rate-limit boost/shadow flags.
The limiter uses a dedicated Redis client with one-second socket/connect limits.
The body is limited to 64 KiB while streaming, including chunked/false-length
requests, and a 10-second body-read deadline. Compressed payloads are rejected.

Example (replace timestamps with the current UTC window):

```json
{
  "schema_version": 1,
  "platform": "ios",
  "build_channel": "stable",
  "app_version": "1.0.554",
  "window_start": "2026-10-15T12:00:00Z",
  "window_end": "2026-10-15T12:15:00Z",
  "counters": [{"event": "Device Connected", "outcome": "observed", "count": 3}],
  "histograms": []
}
```

All fields are required; extra fields at every level are rejected. Platforms
are `ios|android|macos|windows|linux`; channels are `stable|beta|dev` (mobile
production maps to stable). `app_version` is bounded metadata and is discarded;
it is never a label or persisted. Times must include an offset; UTC `Z` is
recommended. Windows must be positive, at most one hour, start within 24 hours,
and end no more than five minutes in the future. No uid/device/session IDs,
free text, raw errors, dimensions, or custom labels may be sent. UID is used only
by the shared auth dependency and the expiring Redis rate-limit key.

`observed` counts occurrences without interpreting event properties. For the
seven outcome-bearing names listed in the registry, clients may additionally
classify into `success|failure|skipped`. Emit exactly one of those outcomes per
occurrence; use `observed` for an outcome without a registered classification.
Do not copy arbitrary upstream outcome text. Other events accept only `observed`.
These coarse dimensions are not a replacement for readers needing stage, reason,
unique people, or specific product outcomes; keep those readers on PostHog.

Counters must have unique `(event,outcome)` pairs (maximum 100); histogram names
must be unique (six families maximum). Counts are nonnegative integers. Values
above 10,000 are clamped per window; above 1,000,000, or a total of over 1,000,000
(counter deltas plus each histogram's final bucket), reject the entire summary.
Validation finishes before any event/histogram increments. Success returns
`{"schema_version":1,"accepted":true,"clamped":false}`; clamping sets `clamped`
to true. Errors return bounded `detail.code`, with 422 for schema/allowlist/window
failures, 413 for size, 408 for body timeout, 415 for compression, 429 for the
budget, and 503 for an unavailable limiter. Missing auth returns 401.

Histogram `name` and every ordered `le` must match the registry exactly. Finite
edges are JSON numbers; the final edge is the string `"+Inf"`. Bucket counts
are **cumulative within this window**, nondecreasing and including all samples
in `+Inf`. Submit per-window bucket deltas, never lifetime totals or per-bin
counts. Only include a histogram if its source actually measured that numeric
quantity in the documented unit (seconds, percent, or ratio). Include its associated event
counter from the registry in the same summary; missing pairs are rejected. The server adds bucket counts atomically and exposes
`omi_client_<name>_bucket_total{le,platform,build_channel}` and `_count_total`
as independent Prometheus counters. GMP drops a histogram family without
a sum; these counters preserve every bucket without inventing that missing value.
There is no `_sum`: the payload contains no exact sum, so averages cannot be recovered.
`histogram_quantile` remains available using the cumulative `_bucket_total` counters.

Transport is best effort: no durable event storage, deduplication, per-UID daily
rollup, or exactly-once delivery is provided. Consume each local window once;
do not replay an ambiguously acknowledged window. Crash/restart and scrape
boundaries can lose deltas; retries can double-count. This transport alone
cannot establish the inventory's seven-day production parity gate or authorize
any PostHog filter. No filtering, client changes or reader cutovers ship here.

## Metric contract and cardinality

- `omi_client_events_total{event,outcome,platform,build_channel}` increments by
  each accepted counter delta, not by request count.
- `omi_client_telemetry_rejected_total{reason}` uses the ten closed reasons in
  `config/fleet_telemetry.py`; error bodies contain no submitted values.
- Six client histogram families have only platform/channel and fixed buckets.
- `omi_sync_upload_total{outcome,platform,build_channel}` observes POST requests
  reaching `/v1/sync-local-files` or `/v2/sync-local-files`, including admission
  refusals. `started` is request entry, `accepted` is HTTP 202 custody admission,
  `completed` is synchronous HTTP 2xx other than 202/207, and `failed` is rejection, partial HTTP 207, or
  exception. It does not count client-only network failures or prove async job
  completion. Existing `omi_sync_lane_jobs_total` and conversation-shape
  histograms describe backend work after admission; `omi_sync_intake_total`
  counts created/merged conversations, not upload attempts, so it is not reused.
  Platform comes from bounded `X-App-Platform`, channel from optional bounded
  `X-Build-Channel`. Missing/unsupported headers map to `unknown`; existing
  clients generally lack channel, so do not infer it from a version string.
- Processing is on the backend and already exports completed conversation-shape
  histogram counts. The named desktop Processing Completed/Stalled events are
  emitted by `ProcessingConversationWatcher` for visible rows and its ten-minute
  threshold, including client fetch delay/reopening. Backend completion or stale
  reconciliation is not equivalent. They remain eligible client observations
  here; this lane does not claim their replacement or server/client parity.

Worst-case application series **per scrape target**: 95 event/outcome pairs ×
5 platforms × 3 channels × 2 (`_total`, `_created`) = 2,850; six histograms'
60 bucket/count children × 15 = 900; upload 4 outcomes × 6 platforms × 4
channels × 2 = 192; rejection 10 reasons × 2 = 20; total **3,962**.
The executable `max_series()` is authoritative and the test enforces <5,000.
Only populated children are exposed; Cloud Run mandatory per-instance target
labels multiply this bound across instances. Do not preinitialize all client
pairs: the shared sidecar caps the entire process at 10,000 samples per scrape.

## Deploy and verify

The existing `gcp_backend.yml` calls the shared deploy action. All four services
create a `-base` no-traffic revision, attach the pinned GMP sidecar using the
existing helper plus rendered env-state verification, and validate/promote the
final revision. Sync/backfill/integration now declare port 9090 and receive the
same `omi_.*` allowlist, startup/shutdown scrapes, always-allocated CPU, and
collector resources (1 vCPU/512Mi per active instance) as backend. The helper
accepts a single unnamed ingress (legacy backfill) but rejects ambiguous ones.
The legacy `omi_sync_phase_*` custom export remains intact. The isolated
Cloud Run exporter also includes `backend-integration`; monitoring-plane owners
may instead query these plain, job-agnostic metric names directly through GMP.

Run focused tests through `backend/test.sh`; use the normal auto-dev rollout
and explicit prod dispatch with `environment=prod`, `deploy_targets=cloud-run-only`,
`mode=deploy`, and an exact eligible merged `release_sha`. Record all four
predeploy traffic revisions before dispatch. After promotion, observe 15+
minutes and compare 5xx and container startup/restart signals to the preceding
24–48 hours. Query GMP `sum by(outcome,platform,build_channel)
(rate(omi_sync_upload_total[5m]))` and verify series originate from sync. A live
sidecar or `up=1` alone is insufficient evidence of ingestion. The existing manual dev transcription-candidate probe also sends one counter/histogram
summary using its short-lived release-probe token, after checking the candidate
URL against the dev service. A shared-UID 429 fails acceptance without retrying.
Test authenticated summaries only locally/dev; an unauthenticated fleet POST may check 401 in prod.
Rollback uses the recorded four-service traffic snapshot via the existing
release workflow/runbook, preserving the previous images and collector config.
