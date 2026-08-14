# macOS Release-Health Metric Specification

**Status:** active · **Schema version:** 4 · **Owner:** desktop/macos · **Tracking:** [#10425](https://github.com/BasedHardware/omi/issues/10425)

This is the **authoritative query contract** for macOS release-health telemetry. It
defines, per signal, the exact numerator, denominator, time window, minimum cohort,
unknown/missing-data behavior, and release-comparison rule so that intermediate
lifecycle events and expected noise **cannot** be read as a customer-visible
regression. It is the long form of the "Product analytics integrity" and "Fallback /
resilience telemetry" sections of `desktop/macos/AGENTS.md`.

Release identity is uniform across surfaces (Sentry + PostHog):

| Dimension | PostHog key | Sentry | Source |
|-----------|-------------|--------|--------|
| App version | `app_version` | `release` (`v{ver}+{build}-macos`) | `CFBundleShortVersionString` |
| App build | `app_build` | `release` (same tag) | `CFBundleVersion` |
| Release channel | `update_channel` (`stable`/`beta`) | `dist` + `update_channel` tag | `AppBuild.currentUpdateChannel` |
| Bundle id | — | `bundle_id` tag | `AppBuild.bundleIdentifier` |

PostHog `app_version`/`app_build`/`update_channel` are registered as super-properties
(`PostHogManager.register`) so **every** event — including `floating_bar_ptt_ended` —
carries release identity. Sentry native crash/app-hang/watchdog events are
build-attributable via `options.releaseName`/`options.dist` set at `SentrySDK.start`.

## Cross-cutting rules

- **Intermediate events are not failures.** A metric's numerator is a *terminal,
  bounded outcome*, never an intermediate lifecycle transition. If a signal has no
  explicit outcome field, it is a building block, not a release-health metric.
- **Expected lifecycle is excluded from error rollups.** Realtime events with
  `expected = true` (`lifecycle_class = "expected"`) — idle teardown and planned
  session rotation — are inspectable but MUST be filtered out of realtime error and
  release-regression rates. Error rate uses `expected = false` only.
- **Minimum cohort.** A rate is `unknown` (not `100%`/`0%`) below the minimum sample.
  Comparisons across releases require both sides to meet the minimum.
- **Comparison basis.** Build-vs-build and beta-vs-stable use the same window and
  denominator definition; a delta is a regression only if both cohorts meet the
  minimum sample and the direction is adverse for the outcome of interest.
- **Privacy.** Custom metric payloads use bounded dimensions only. No transcript,
  audio, prompt, custom device identifier, or free-form local error text is emitted
  in PostHog properties or Sentry tags (enforced by `DesktopDiagnosticsManagerTests` /
  `TelemetryPrivacyBoundaryTests`).

## Metrics

Each metric below maps to a `desktop_release_doctor_report.METRIC_CONTRACTS` name
where one exists; desktop-outcome metrics without a doctor entry are client inputs
the release-evidence layer (`#9523`) will consume.

### PTT terminal-outcome funnel — `ptt_audio_capture_lifecycle`

- **Source event:** `desktop_health_event` with `event = ptt_audio_capture_lifecycle`
  (`telemetry_schema_version >= 2`).
- **Denominator (attempts):** all `ptt_audio_capture_lifecycle` events in the window,
  grouped by `failure_class`. Every terminal disposition — including success — is
  emitted remotely, so the denominator is queryable.
- **Numerator (capture failure):** `failure_class IN
  (capture_never_operational)`. Recovery outcomes
  (`recovery_outcome_recovered`/`_still_silent`/`_not_judgeable`) are joined on
  `recovery_attempt_id`, not counted as fresh failures.
- **Excluded from the failure numerator (NOT regressions):**
  `committed` (success), `released_before_usable_audio` / `too_short_audible`
  (short tap / released early), `cancelled` (user cancel), and
  `zero_or_near_zero_samples` with `turn_disposition = silent_rejected` (quiet
  discard / no speech). `first_chunks_energy_bucket` + `turn_disposition` separate a
  true zero-sample capture failure from a deliberate quiet discard.
- **Deprecated event:** `floating_bar_ptt_ended` (`had_transcript`) collapses all
  four outcomes above into one boolean and MUST NOT be read as a PTT
  success/failure denominator. It is retained only for backward compatibility.
- **Window:** PT24H rolling. **Minimum cohort:** 50 judgeable attempts per build.
  **Missing data:** if no `ptt_audio_capture_lifecycle` events for a build → `unknown`.

### Realtime token-mint — `realtime_token_mint_failed`

- **Source event:** `desktop_health_event` with `event = realtime_token_mint_failed`.
- **Phase (warm vs active):** `phase` is a closed set — `warm` (background pre-warm)
  vs `barge_in_replacement` (socket replacement during an active turn); any other
  value is bucketed to `other`. This is the warm-vs-active dimension.
- **Immediate outcome (degraded/exhausted):** the mint-failure event itself records
  whether the controller started an alternate-provider fallback (`degraded`) or
  had no remaining managed path (`exhausted`). Its later fallback outcome remains
  on the correlated `fallback_triggered`{`area = realtime_hub`} event. Join on
  `mint_attempt_id` (present on both when a mint triggered failover), then provider
  plus a bounded time window.
- **Numerator (mint-exhausted, user-impacting):** `outcome = exhausted` on the
  mint-failure event (no remaining managed path). Use the correlated
  `realtime_hub` fallback event for the detailed replacement path. `degraded`
  (alternate-provider fallback started) is recoverable and is **not** a terminal
  failure numerator.
- **Window:** PT24H. **Minimum cohort:** 30 mint-attempting users per build.
  **Missing data:** `unknown` if no mint events.

### Realtime provider session health — `realtime_provider_*`

- **Source events:** `realtime_provider_expected_idle_teardown`,
  `realtime_provider_expected_session_rotation` (both `expected = true`),
  `realtime_provider_policy_close`, `realtime_provider_session_error`
  (both `expected = false`), and `realtime_provider_close_resolution`.
- **Customer-turn decision:** every provider-close event carries a process-local
  `close_attempt_id`; its paired `realtime_provider_close_resolution` carries the
  closed-set `turn_outcome` and the immediate `recovery_action`/`recovery_result`.
  The id is only valid within the same analytics session and is never a user, device,
  turn, or provider-session identifier.
- **Error rate numerator:** active-turn `realtime_provider_session_error` +
  `realtime_provider_policy_close` (`expected = false`) whose paired resolution has
  `turn_outcome = failed`. `pending_replacement` is an intermediate recovery state,
  not a terminal customer-failure numerator. **Denominator:** active realtime
  sessions (proxy: distinct sessions emitting any `realtime_provider_*`).
- **Excluded:** the two `expected_*` events (`expected = true`) — normal idle teardown
  and planned 60-min OpenAI session rotation. They remain separately inspectable but
  MUST NOT inflate the realtime error or release-regression rate.
- **Window:** PT24H. **Minimum cohort:** 40 active-session users per build.

### Fallback outcomes — `fallback_triggered`  · doctor metric `fallback_outcomes`

- **Source event:** `desktop_health_event` with `event = fallback_triggered`.
- **Dimensions (all closed enums):** `area`, `reason`, `from`, `to`, `outcome`
  (`recovered`/`degraded`/`exhausted`). Unknown `area`/`reason` bucket to `other`.
- **Release-health numerator (customer-visible degradation):** `outcome IN
  (degraded, exhausted)`, grouped by `(area, reason, from, to)`. `recovered` is a
  silent UX heal and is **not** a failure.
- **Known-benign flap:** `area = screen_capture`, `reason = capability_mismatch`,
  `from/to` ∈ {`screen_capture`, `capture_paused`, `recovery_poll`} is the
  ProactiveAssistants screen-capture health flap (target temporarily unavailable then
  restored). It is an expected capability flap — alert on its *rate*, never page on
  absolute counts or on the `recovered` leg.
- **`area = other` policy:** remaining `other` collapses only genuinely-unclassified
  paths; a non-trivial `other` rate is an instrumentation defect to triage, not a
  product regression. Named owners (`screen_capture`, `memory_scope`,
  `desktop_update`, `tts_fallback`, `task_workflow`, `auth_storage`, `realtime_hub`,
  `ptt_cascade`, …) keep known paths out of `other`.
- **Window:** PT24H. **Minimum cohort:** 50 fallback-emitting users per build.

### Crash-free sessions — doctor metric `crash_free_sessions`

- **Source:** Sentry release health (auto session tracking) keyed by
  `releaseName`/`dist`.
- **Numerator:** sessions with a hard crash. **Denominator:** total started sessions
  for the release. Filter by `release` (version+build) and `update_channel`; native
  crashes are now build-attributable via `options.releaseName`/`options.dist`.
- **Window:** PT24H. **Minimum cohort:** 100 sessions per build.
- **Privacy:** native events carry only `update_channel`/`bundle_id` tags +
  `diagnostic_area`/`failure_class`; no user content.

### Proactive advice delivery — doctor metric `proactive_delivery`

- **Availability source:** unique users emitting `Advice Generated`, divided by
  macOS DAU in the same rolling PT24H window. Both sides are scoped to
  `$app_namespace = com.omi.computer-macos` and `$os_name = macOS`.
- **Delivery source:** `Advice Delivery Outcome` terminal events. Eligible delivery
  outcomes are `delivered` plus `failed`; preference/policy suppressions are excluded.
  With at least 10 eligible outcomes, exact-zero delivered outcomes is unhealthy.
- **Alarm:** exact-zero advice users with at least 50 macOS DAU, or exact-zero
  delivered eligible outcomes, is unhealthy. Fewer than 50 DAU or fewer than 10
  eligible delivery outcomes is `unknown`, never success or failure. The scheduled
  `desktop_release_doctor.yml` job runs hourly, keeps one durable GitHub issue
  open while unhealthy, closes it after measured recovery, and treats a broken
  PostHog query as an alarm rather than silently passing.
- **Monitor credentials:** the scheduled job reads the repository Actions secret
  `POSTHOG_PERSONAL_API_KEY` and Actions variables `POSTHOG_PROJECT_ID` and `POSTHOG_HOST`. It deliberately
  does not use the approval-protected `prod` environment, which would leave hourly
  checks waiting for a human. Missing configuration produces a neutral `unconfigured`
  result and no health alarm because no measurement occurred. A configured query that
  fails produces `monitor_error` and opens the durable issue; neither state turns the metric green.
- **Delivery outcomes:** each `Advice Generated` event carries an opaque
  process-local `delivery_id`. `Advice Delivery Outcome` records a closed
  `outcome` (`delivered`, `suppressed`, or `failed`) and bounded `reason`.
  Notification preferences suppress delivery only; they do not suppress analysis.
  A queued floating-bar item is intermediate and MUST NOT count as delivered until
  the presentation boundary accepts it.
- **Privacy:** the query exports aggregate counts only. Neither event's custom
  payload contains advice text, screen content, prompts, transcript, or a device
  identifier. PostHog's standard `person_id` is used in-place only for aggregate
  cardinality and is not returned by the monitor.

### Updater delivery — doctor metric `updater_delivery`

- **Source:** `Update Check Started` joined to its single terminal
  `Update Check Completed` on opaque `attempt_id`. Both carry trigger, source app
  version/build, and a normalized update channel.
- **Failure numerator:** terminal `result = failed`. `no_update` and
  `update_available` are successful check outcomes. `network_unavailable` is an
  automatic background check whose URL error is specifically
  `NSURLErrorNotConnectedToInternet` (-1009); it is reported separately and is not
  an updater defect. Timeouts, DNS, and server reachability errors remain failures so
  a real update-service outage is not masked. A manual check while offline remains
  `failed` so the user receives feedback. The legacy
  `Update Check Failed` event remains diagnostic-only and MUST NOT be used as a
  denominator or user-impact rate.
- **Denominator:** distinct started attempts. Missing terminals are a separate
  instrumentation-health defect (`callback_missing` when the next Sparkle-admitted
  check closes a stale identity). Starts are recorded only at Sparkle's serialized
  `mayPerform` boundary, and the cycle-finish delegate is the final fallback for paths
  that omit an abort callback. Rejected requests create no phantom attempts, and
  duplicate callbacks cannot create extra terminals.
- **Window:** PT24H. **Minimum cohort:** 30 attempts per build.

### Recording (client input)

- **Recording:** `recording_error` PostHog events carry `error_class` only (no audio).
  Numerator = errors; denominator = recording sessions. Below minimum → `unknown`.

### Memory metrics (product analytics — three distinct surfaces)

The macOS "memory" surface is **three independent funnels**, not one. Recording
users are **not** the proactive-memory denominator, and `Memory Created` is **not**
an extracted-memory proxy — it tracks recording/conversation-session
reconciliation with the backend. The three metrics below are the query contract for
the events added to make each funnel measurable. All carry only bounded dimensions;
no screen pixels, OCR/window/app names, memory content, prompts, Gemini responses,
raw model material, conversation ids, transcript text, or exception strings are
emitted (enforced by `MemoryAssistantTelemetryTests` and
`test_conversation_memories_telemetry.py`).

#### 1. Proactive memory-assistant activation — `Memory Assistant Setting Changed`

- **Source event:** `Memory Assistant Setting Changed` (desktop, proactive
  `MemoryAssistant`). Closed properties: `setting` ∈ {`enabled`,
  `notifications_enabled`}, boolean `value`.
- **Why it exists:** analysis is hard-gated on `enabled && notificationsEnabled`
  and notifications default **off**, so the activation cliff at the notifications
  toggle was previously invisible. This event makes the true denominator
  measurable.
- **Emission rule:** exactly one event per **user-initiated persisted change** to
  either setting — never on remote settings sync, app startup, default reads,
  migrations, or programmatic resets. The two UI toggle paths use the dedicated
  user-intent API, which compares old vs new and skips no-ops; raw setters are
  intentionally silent.
- **Activation metric:** proactive extraction users (`Memory Extracted`) ÷
  monitoring users (`Monitoring Started`) with `notifications_enabled = true`,
  scoped `$app_namespace='com.omi.computer-macos'` AND `$os_name='macOS'`. Stop
  dividing extraction by recording users.

#### 2. Proactive analysis-outcome distribution — `Memory Assistant Analysis Run`

- **Source event:** `Memory Assistant Analysis Run` (desktop). Closed properties:
  `outcome` ∈ {`synced`, `filtered_low_confidence`, `no_new_memory`,
  `sync_failed`, `local_persistence_failed`, `sync_state_persistence_failed`,
  `analysis_failed`}; optional `confidence_bucket` (closed decile range, e.g.
  `70_80`) present only for outcomes where the model returned a confidence.
- **Emission rule:** exactly one event per **actual Gemini analysis attempt** —
  not per captured frame, and not on disabled/gated paths. Every reachable
  terminal maps to exactly one outcome. It **supplements** — does not replace or
  alter — the existing `Memory Extracted` success terminal (which still fires only
  after a local SQLite insert, including `synced`, `sync_failed`, and
  `sync_state_persistence_failed`; it never fires after
  `local_persistence_failed`).
- **Metric:** outcome distribution among analysis attempts. `synced` is the only
  fully-successful terminal; `sync_failed` isolates backend-create loss,
  `local_persistence_failed` isolates failed SQLite durability before any backend
  call, and `sync_state_persistence_failed` isolates a failed local synced-state
  receipt after backend success. `filtered_low_confidence` shows the 0.70
  threshold's effect.

#### 3. Transcript conversation memory-extraction success — `Conversation Memories Extracted` (backend)

- **Source event:** `Conversation Memories Extracted` (backend server-side
  transcript-memory path; distinct identity = `distinct_id` = uid). Closed
  properties: `memory_count_bucket` ∈ {`1`, `2`, `3`, `4_9`, `10_plus`},
  `source` ∈ {`transcription`, `external_integration`}, `path` ∈ {`canonical`,
  `legacy`}.
- **Why it exists:** the "did this recording produce memories?" step ran
  server-side and wrote memories to the DB but emitted **no** analytics event —
  the root cause of the recording→memory observability gap.
- **Emission rule:** at most one delivery attempt **after a durable successful
  persistence result**, at the `extract_memories` public boundary. Zero extraction → no event
  (no false success). Persistence exception → propagates, no event. A permanent,
  atomic Firestore marker under the authoritative per-`(uid, conversation)`
  document permits at most one PostHog delivery attempt across
  re-finalization/retries, with no cache TTL or eviction window. The marker is
  claimed before SDK construction/capture: because PostHog capture is queued
  rather than delivery-acknowledged, this is explicitly **at-most-once attempt**
  semantics—optional telemetry can be lost, but retries cannot duplicate the
  value. If the marker cannot be consulted, this optional metric fails closed
  (no capture) while finalization continues. Conversation ids are marker-path
  components only and never PostHog properties. Claim, PostHog construction,
  and capture degradation record the shared bounded fallback signal; none can
  undo a durable extraction.
- **Metric:** transcript memory-extraction success = users emitting
  `Conversation Memories Extracted` ÷ finalized conversations (denominator:
  `Memory Created`, the recording-reconciliation proxy). Join by uid + window.

### Memory reliability (client input, unchanged)

- Memory-operations reliability is still tracked via `memory_scope` fallback
  outcomes (device-scope rejection); no memory *content* is emitted. The three
  metrics above are the activation/funnel/value contract; `memory_scope` remains
  the degradation signal.

### Feature path success — doctor metric `feature_path_success` · backend error rate — doctor metric `backend_error_rate`

Owned by the doctor report and backend respectively; this spec only requires that the
desktop client feeds (chat terminal outcomes, PTT funnel, fallback outcomes) use the
outcome semantics above so the doctor's `feature_path_success` numerator is never an
intermediate event.

## Versioning

Bump `Schema version` and call out the change here when any numerator/denominator
definition, closed enum, or field name changes. `telemetry_schema_version` on the
PTT lifecycle snapshot and the `expected`/`outcome`/`mint_attempt_id`/`phase`/
`close_attempt_id`/`turn_outcome` fields are the machine-readable companions to this
document.
