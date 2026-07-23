# macOS Release-Health Metric Specification

**Status:** active · **Schema version:** 1 · **Owner:** desktop/macos · **Tracking:** [#10425](https://github.com/BasedHardware/omi/issues/10425)

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
| App build | `app_build` | `release` (same tag) / `dist` | `CFBundleVersion` |
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
- **Privacy.** Numerators/denominators are bounded dimensions only. No transcript,
  audio, prompt, device identifier, or free-form local error text is emitted to
  PostHog or Sentry tags (enforced by `DesktopDiagnosticsManagerTests` /
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
- **Outcome (recovered/degraded/exhausted):** a mint failure is point-in-time; its
  terminal fate is the correlated `fallback_triggered`{`area = realtime_hub`} event
  (`outcome` = `recovered`/`degraded`/`exhausted`). Join on `mint_attempt_id` (present
  on both when a mint triggered the failover), then `provider` + bounded time window.
- **Numerator (mint-exhausted, user-impacting):** mint failures joined to a
  `realtime_hub` fallback with `outcome = exhausted` (fell through to the cascade
  with no acceptable path). `degraded` (failed over to the alternate provider) is
  recoverable and is **not** a terminal failure numerator.
- **Window:** PT24H. **Minimum cohort:** 30 mint-attempting users per build.
  **Missing data:** `unknown` if no mint events.

### Realtime provider session health — `realtime_provider_*`

- **Source events:** `realtime_provider_expected_idle_teardown`,
  `realtime_provider_expected_session_rotation` (both `expected = true`),
  `realtime_provider_policy_close`, `realtime_provider_session_error`
  (both `expected = false`).
- **Error rate numerator:** `realtime_provider_session_error` +
  `realtime_provider_policy_close` (`expected = false`). **Denominator:** active
  realtime sessions (proxy: distinct sessions emitting any `realtime_provider_*`).
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

### Updater delivery — doctor metric `updater_delivery`

- **Source:** PostHog updater events (`source_app_version`, `source_app_build`,
  `update_channel`, `target_version`, `target_build`).
- **Numerator:** successful installs (`update_installed`). **Denominator:** started
  update attempts. **Window:** PT24H. **Minimum cohort:** 30 attempts per build.

### Recording & memory (client inputs)

- **Recording:** `recording_error` PostHog events carry `error_class` only (no audio).
  Numerator = errors; denominator = recording sessions. Below minimum → `unknown`.
- **Memory:** memory-operations reliability is tracked via `memory_scope` fallback
  outcomes (device-scope rejection) and memory-extract counts; no memory *content* is
  emitted. Out of scope for a numeric spec until a backend denominator exists —
  client supplies the `memory_scope` degradation signal only.

### Feature path success — doctor metric `feature_path_success` · backend error rate — doctor metric `backend_error_rate`

Owned by the doctor report and backend respectively; this spec only requires that the
desktop client feeds (chat terminal outcomes, PTT funnel, fallback outcomes) use the
outcome semantics above so the doctor's `feature_path_success` numerator is never an
intermediate event.

## Versioning

Bump `Schema version` and call out the change here when any numerator/denominator
definition, closed enum, or field name changes. `telemetry_schema_version` on the
PTT lifecycle snapshot and the `expected`/`outcome`/`mint_attempt_id`/`phase` fields
are the machine-readable companions to this document.
