# Frozen telemetry transport and consumer contract — v1 (2026-10-12)

Architect decision for lanes 1–4. This file overrides ambiguous migration details in
`data/runs/2026-10-12-posthog-cost-FINAL-plan.md`; lanes must not edit it.
No deployment, cloud settings, IAM, cron installation or consumer activation is authorized here.

## 1. Transport, custody and ownership

- Backend: `POST /v1/telemetry/client/batches`, JSON, existing Firebase bearer-token
  authentication. Never accept an account ID from the payload; derive owner from auth.
- Envelope: `{schema_version:1,batch_id:UUID,observations:[Observation]}`.
  Observation: `{event_id:UUID,occurred_at:UTC_ISO8601,platform,channel,family,attributes}`.
  Platform enum: `ios|android|macos`; channel enum: `production|beta`.
  Channel is build metadata, never inferred by missing data. Preserve the admin's
  existing actor/channel classification; exclude mismatches and mark coverage partial.
- Attributes below are exhaustive per family; unknown keys, schema versions, invalid
  enums, negative/nonfinite numbers, future timestamps >5 minutes, or observations
  older than 24 hours reject the entire batch with 422. Optional IDs are UUIDs;
  no email, audio, transcripts, screen text, task text, device address or raw error text.
- At most 100 observations, 128 KiB uncompressed request, 4 KiB per observation.
  Reject 413 before decoding oversized requests; no compression in v1.
- Flush after 30 seconds or 100 observations, and best effort on background/shutdown.
  One in-flight batch. Persist a per-owner outbox, capped at 1,000 observations AND
  1 MiB AND 24 hours. Drop oldest on overflow; record local drop counts by reason.
  Transport failure must never block recording, capture, processing or delivery.
- Snapshot owner at observation creation. Send only with that owner's current token;
  never reattribute on account swap. Logout purges that owner's pending outbox.
  Same-owner token refresh is allowed once after 401; no retry under a different owner.
- Five attempts per batch maximum, timeout 10 seconds each; full-jitter delays with
  caps 2, 4, 8, 16 seconds. Retry timeout/network, 408, 429 and 5xx only.
  Honor Retry-After up to 300 seconds; if longer, park until a later flush within TTL.
  Persist attempt counts across restarts. Permanent 4xx/exhaustion: drop and diagnose.
- Response 200: `{schema_version:1,batch_id,accepted_count,duplicate_count}` after
  durable storage. Counts sum to input length. Atomic all-or-nothing acceptance;
  client removes observations only on matching batch ID and reconciled counts.
  401/403 unauthorized; 422 invalid; 413 size; 429 per-owner rate limit (10 batches/minute).
- Freeze `event_id` when creating an observation, reuse across retries/rebatching.
  Dedup key `(authenticated_owner,event_id)`, retained 48h minimum. Same key with
  different canonical content returns 409 (permanent), never increments twice.
  Operation IDs below join phases but are NOT dedup keys. Retries of an actual
  upload request get a new attempt ID; retries of telemetry keep event IDs.
- Lane 1 uses durable Firestore observations with an atomic dedup claim and aggregate
  updates in the same transaction (or equivalent existing transactional persistence).
  In-memory dedup and process-local Prometheus increments alone are insufficient.
  Raw observations/owner joins retained 30 days; UTC daily aggregates retained 90 days.
  TTL cleanup and query filtering must enforce retention even before physical deletion.
  Grafana reads durable aggregates; request HTTP metrics remain complementary.

## 2. Payloads (snake_case keys; durations are milliseconds)

Common optional operation UUIDs remain in restricted storage only. Counts are
nonnegative integers; durations are integers 0..86,400,000, missing when unknown
(not zero). Session duration permits up to 604,800,000. No client-side sampling
of the following observations; each counter contribution must be exact.

| family | Required attributes | Optional attributes / semantics |
|---|---|---|
| `upload` | `attempt_id`, `phase`, `source` | `http_status`, `failure_class`, `latency_ms`, `operation_id` |
| `conversation_processing` | `operation_id`, `outcome` | `latency_ms`, `latency_basis` |
| `capture_ingress` | `operation_id`, `phase`, `reason`, `subscription_confirmed`, `recovery_outcome`, `recovery_spent`, `reconnect_spent` | `unverified_duration_ms` |
| `capture_wedge` | `operation_id`, `phase`, `trigger`, `outcome` | `latency_ms` |
| `device_session` | `operation_id`, `vendor`, `disconnect_class`, `recovery_outcome`, `duration_ms` | `hci_reason_code`, `intentional` |
| `screen_task` | `operation_id`, all v2 terminal fields listed below | all stage durations listed below |
| `voice_turn` | `operation_id`, `phase`, `population`, `route`, `intent` | `outcome`, `reason`, `latency_ms` |
| `fallback` | `operation_id`, `area`, `from`, `to`, `reason`, `outcome` | `latency_ms` |

Upload phases: `started|accepted|completed|failed|deferred`; source:
`pendant|phone|sdcard|other|unknown`. Emit started for each admitted HTTP attempt.
Exactly one request terminal: completed (synchronous durable success), accepted
(202 queued custody, not processing completion), failed, or deferred (paced 429).
An accepted attempt may later emit completed only when durable completion is
actually confirmed; absence remains pending. Never relabel every HTTP 200/202
as durable completed: inspect the existing acknowledgment contract.
`latency_ms` on request terminal measures monotonic request elapsed time; a later
completed observation measures elapsed since the same started attempt.
`failure_class`: `network|timeout|auth|rate_limited|client_error|server_error|cancelled|unknown`.
Conservation: started = synchronous completed + accepted + failed + deferred +
unresolved request attempts. Later completion is a subset of accepted, not an
extra request terminal. Aggregate query exposes both populations separately.

Conversation processing: outcome `completed|failed|cancelled`; completion occurs
when the CLIENT-visible processing row resolves, not when the server finishes.
`latency_basis`: `processing_observed|request_started|unknown`; use monotonic elapsed
from the selected existing lifecycle anchor; unknown means omit latency.
Do not synthesize a completion if a row remains unresolved or disappears.

Ingress phases: `unknown|subscribing|awaiting_audio|flowing|recovering|action_required|disconnected`.
Map native `actionRequired` to `action_required`; other unmapped native states to
unknown plus local diagnostic. Reasons: `none|cccd_timeout_recovery|subscription_timeout|
no_audio|stale_audio|disconnected|unauthorized|unknown` (joined text is enum, not labels).
Recovery outcome: `none|attempted|recovered|failed|exhausted|unknown`.
Emit once per generation/phase/reason/recovery tuple change. Generation stays local;
operation_id is a generated UUID stable for that ingress generation.

Wedge phases: `detected|resolved`; outcome `pending|recovered|failed|exhausted|unknown`.
Trigger: `zero_bytes|rapid_reconnect|bytes_sent_no_transcript|upload_silence|
ingress_recovery_failed|other|unknown`. Preserve latched episode semantics.
Device vendor: `omi|limitless|other|unknown`; disconnect class:
`intentional|link_loss|timeout|adapter_off|permission|unknown`.
HCI code is optional integer 0..255 in restricted storage, never a metric label.

Screen-task attributes preserve schema-v2 semantics: `schema_version:2`,
`pipeline` (`screen_task_v2|legacy`), `gate_outcome`, `audit_sample`, `extractor`
(`gemini_3_8|legacy|none|unknown`), `outcome`, `error_class`, `fallback_reason`,
`eligible_frames` (0 or 1), `feature_enabled_at_start`, `client_bypass`,
`invalid_items`, `legacy_attempts`, `policy_rejected`, `outbox_saved`, `coalesced`,
`pending_delivered`, `failed`, plus other existing named stage-attempt counters.
Bound enum fields to the EXISTING v2 literals in `TaskAssistant+ScreenTask.swift`;
Lane 1 must read that source, accept those literals and bucket unknowns to `unknown`.
Durations: `ocr_ms,retrieval_ms,gate_ms,extraction_ms,delivery_ms,capture_to_terminal_ms`.
Stage zero retains existing meaning (not completed); only completed stages enter
stage latency histograms. Count every terminal, eligible frame, reject and
pre-upload failure before any optional diagnostic sampling. No delayed delivery
receipt rewrites an earlier frame terminal; retain existing delivery product events.

Voice phase `started|terminal`; population `physical_shortcut|floating_voice`;
intent `hold|locked|legacy|unknown`; outcome `success|failure|excluded|unknown`.
Route and terminal reason map the existing admin reader literals to a bounded
allowlist; unknown becomes `unknown`. Latency counts successful terminals only.
Shadow physical turns AND floating turns separately; no inferred population switch.
Fallback outcome `recovered|degraded|exhausted`; areas `realtime_hub|ptt_cascade|
screen_task_gate|screen_task_extraction|other`; from/to/reason use existing registered
fallback literals, unknown to `unknown`. Preserve existing exhausted triage filters.

## 3. Metrics and query API

Metric prefix `omi_client_`; counters end `_total`, histograms `_duration_seconds`.
Allowed metric labels: platform, channel, family and bounded family enums only.
Never label owner, event/batch/operation/session/device ID, build, URL, timestamp,
raw exception or dynamically derived strings. Histograms use seconds, buckets
`0.05,0.1,0.25,0.5,1,2,5,10,30,60,120,300,900,3600,86400,+Inf`;
session histogram adds `604800`. Preserve sum and count; absent latency adds neither.
Build metadata is optional local diagnostic only; not part of v1 payload.

`GET /v1/telemetry/client/aggregates?days=7&channel=production` (days 1..90;
channel `production|beta|all`), existing backend admin auth; not ordinary user auth.
Admin proxy uses `verifyAdmin` and existing server auth; never browser credentials
for backend privileged reads. Response:
`{schema_version:1,generated_at,coverage_start,complete_through,partial,available,
 rows:[{day,platform,channel,family,dimensions,counters,durations}],voice_rows:[]}`.
Dates are UTC; rows unique by day/platform/channel/family/canonical dimensions.
Counters use attribute counter names plus `observations`, per-phase counters,
and upload `request_completed`,`accepted_completed`,`pending_accepted`.
Durations map duration field to `{count,sum_ms,buckets:[{le_seconds,count}]}`;
buckets cumulative including +Inf. Zero observations ≠ available healthy feed.
Voice rows are objects `{day,channel,actor_id,health_event,outcome,reason,route,intent,
count,duration_ms,population}`: health_event `voice_turn_started|voice_turn_terminal`.
`actor_id` is the authenticated existing analytics identity, admin-only; keep existing
actor/channel classification. Never return identity in generic metric labels.
Return both voice populations explicitly. Bound response to 50,000 rows TOTAL;
overflow returns 503 with code `telemetry_query_truncated`, never silent truncation.
Store/query failure returns 503 `telemetry_unavailable`, not empty successful data.
Coverage fields come from ingestion/rollup health, not query time or a recent event
alone. No health receipt / missing partition => partial/unavailable. No stale-to-zero.

Lane 4 preserves ResponseReliabilityPayload, rates (judged success+failure), excluded
and unresolved counts, daily buckets, latency, routes, channels and voiceSource.
Chat stays on PostHog. Historical dates use PostHog; replacement begins at a single
explicit UTC cutover only after parity. Never sum both sources for one population/day.
Physical source selected explicitly; missing physical data must show unavailable,
never silently fall back to floating. Reader flag defaults off; transport shadow
flag defaults off and retirement flag defaults off, independent of reader flag.

## 4. Final disposition and consumers

| Event | Disposition | Consumer after acceptance |
|---|---|---|
| Recording Upload Started/Completed/Failed | Move after parity; dual-write in canary | durable upload aggregates / Grafana |
| Conversation Processing Completed | Move after parity | client-visible completion aggregates / Grafana |
| Capture Ingress Health; Capture Wedge Detected | Move after parity | ingress/recovery aggregates / Grafana |
| Device Session Ended | Move after parity | session aggregates / Grafana |
| Screen Task Frame Terminal | Move exact counters/histograms after parity | screen-task aggregates / Grafana |
| desktop_health_event | KEEP; shadow voice/fallback now; retire only after both consumers pass | admin voice reader + fallback triage |
| Device Disconnected Detailed (mobile); Device Disconnected (macOS) | KEEP | repaired connection-balance PostHog consumer |
| Device Connected | KEEP, platform/vendor segmented | product + connection balance PostHog |
| Recording Requested | KEEP; add `request_origin=explicit_user|automatic_roll|unknown` | PostHog capture-session preparation; explicit_user only for user-attempt funnel |
| Mobile Render Observation | Delete routine PostHog; bounded opt-in local debug only | local diagnostics |
| wal_transcript_coverage | Delete PostHog duplicate | existing debug log |
| Suggestion Assistant Gate Outcome | KEEP eligible/consumed; suppress repeated skippedDwell/skippedCooldown | PostHog product evaluation outcomes |
| Recording Started/Start Failed, Memory Created, onboarding/chat/purchases/product outcomes | KEEP | existing PostHog consumers |

## 5. Required parity receipt (lanes 2, 3 and 4)

Tests must pass BEFORE finishing. Activation is a later parent-owned gate, not a
lane's permission to switch. Provide deterministic fixtures and comparison tooling
now; explicitly report real canary acceptance as pending if unavailable.
- Exact fixture equality for counts, all terminal/eligible/rejected/pre-upload-failed
  denominators, channel/population splits, exclusions, latency sum/count/buckets.
- Exercise duplicate delivery, retry, crash/restart, logout/account swap, 202 then
  completed, 429 deferral, permanent failure, overflow, stale/partial/unavailable
  feeds, UTC boundary and cutover; no ID leaks or unknown labels.
- Before real switch: seven closed UTC canary days, >=100 upload attempts and
  >=100 voice turns per switched population; sparse populations remain on PostHog.
  Deduped counts within 1% (absolute difference <=1 for bins <100), no lost eligible
  frames in controlled replay, latency mean/p95 within 5% or 100ms, whichever larger.
  No channel/population substitution; at least 99% observations delivered within
  five minutes online; all drops/rejections explained and visible in the receipt.
- Lane 4 supplies fixture-based rendered panel comparisons and fallback-triage
  comparison (recovered/degraded/exhausted and areas); backend fixtures alone do
  not prove consumer parity. Connection balance explicitly maps mobile Detailed
  and macOS Disconnected, keeping reconnect volume separate from unique people.
- Do not alter 10-second pendant drain, WAL retention/custody, upload scheduling,
  recovery latches/reconnects, model pacing or privacy ownership to reduce telemetry.

## 6. Warehouse ruling: no additional aggregate or PostHog GCP copy

Verified repository consumers: `backend/scripts/finops/pull_gcp.py` reads the current
raw GCP BigQuery export; `web/admin/lib/services/gcp-billing.ts` reads that export;
`web/admin/lib/services/plan-economics.ts` reads existing `omi_finops.unit_cost_daily`
and related revenue/reconciliation tables. None needs a PostHog billing copy.
Do not build a speculative day/project/service/SKU table or scheduled query.
Keep existing gross cost, credits (signed), net = gross + credits and reconciliation
semantics. Preserve existing historical partitions/retention, with the existing
three-date settlement window (today and prior two UTC dates) recomputed idempotently;
older corrections use explicit date-range reconciliation, not wholesale replacement.
Lane 1 supplies gross/credits/net reconciliation fixtures, documents existing
retention/cardinality and all raw schemas' disablement, without altering live data.
Parent disables EVERY raw schema (`should_sync:false`, scheduling off), checks
running/retrying jobs, inventories SaaS sources, then admits the $200 DW limit
with $160/$200 notifications. Raw export and direct consumers remain available.
No automatic raw re-enable, grants, cloud settings or promises of $0 aggregate cost.

## 7. Repair-round ruling (2026-10-13, parent, binding)

Enum allowlists: **backend `config/client_telemetry.py` sets are the single source of
truth. Backend widens; clients never rename.** Concretely:
- `SCREEN_ERROR_CLASSES` gains `timeout`, `offline` (already absent from Swift's set —
  Swift adds them; backend adds them to its frozenset too).
- `SCREEN_FALLBACK_REASONS` gains `gate_invalid_response`, `offline` (Swift emits both).
- `VOICE_REASONS` gains the floating failure/cancel reasons Swift emits
  (`ClientTelemetryShadow.swift:346-348`), and Swift's `floatingFailureReasons`/
  `floatingCancelReasons` sets are aligned 1:1 with the widened backend set.
- `_bucket()` already normalizes unknowns to `unknown`; no open-string dimensions may
  be introduced anywhere (sol blocker: allowlists must actually bound values).
All cross-lane schema/enum/histogram changes go through this ruling; lanes do not
re-litigate it. Known histogram fixture mismatch stays: Flutter fixture uses `"inf"`,
wire format is `"+Inf"` — Flutter lane fixes its fixture helper only.
