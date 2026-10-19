# Phone Battery Sample v2

The event name stays `Phone Battery Sample`. Each v2 event describes the
observation and its preceding local phone observation, without a person-level
join. The pendant daily event and its emitter are unchanged.

## Properties

| Property | Type / meaning |
| --- | --- |
| `schema_version` | Integer `2` |
| `battery_level` | Existing integer percent, 0–100 |
| `battery_charging` | Existing boolean endpoint snapshot |
| `sampling_trigger` | Existing `lifecycle_foreground`, `lifecycle_background`, `timer_foreground` |
| `seconds_since_previous_sample` | Existing double seconds since persisted sample throttle timestamp; absent without one |
| `os_battery_saver` | Existing optional boolean OS snapshot |
| `battery_sample_at_ms` | Integer observation wall-clock timestamp, after battery read |
| `previous_battery_sample_at_ms` | Nullable integer previous observation timestamp |
| `previous_battery_level` | Nullable integer previous endpoint percent |
| `previous_battery_charging` | Nullable boolean previous endpoint charging |
| `previous_battery_observation_build` | Nullable string previous PackageInfo build number |
| `battery_interval_seconds` | Nullable double elapsed observation time, never delivery time |
| `battery_interval_validity` | `same_build`, `build_changed`, `no_baseline`, `clock_invalid`, `identity_changed` |
| `battery_observation_build` | Nullable string PackageInfo build number at read |
| `foreground_seconds_in_interval` | Nullable double accumulated resumed spans; null across process restarts or clock invalidity |
| `app_lifecycle` | `resumed`, `inactive`, `hidden`, `paused`, `detached` at observation |
| `capture_source` | `pendant`, `phone_mic`, `watch`, `other`, `none`, `unknown` from committed capture ownership |
| `capture_mode` | `live`, `batch`, `none`, `unknown` |
| `seconds_since_build_first_run` | Nullable double durable build age, reset on observed build change; high-water timestamp prevents decreasing age after clock rollback |
| `thermal_state` | Nullable string OS thermal snapshot: iOS `nominal`, `fair`, `serious`, `critical`; Android API 29+ `none`, `light`, `moderate`, `severe`, `critical`, `emergency`, `shutdown` |
| `charging_observed_in_interval` | Nullable boolean; only `true` when a passive phone charging callback occurred strictly between endpoints |

Unknown nullable values remain null at emission; AnalyticsManager omits null
values on the wire, so their PostHog properties are null/missing. No unknown
numeric value becomes zero. Real zero battery levels, elapsed build age at first
observation, foreground spans, and zero battery drops remain valid measurements.
The currently shipping native battery handlers have no passive phone charging
callback, so charging coverage remains endpoints-only (null). The sampler exposes
a passive callback seam but creates no subscription. Thermal values come directly
from [ProcessInfo](https://developer.apple.com/documentation/foundation/processinfo/thermalstate-swift.property)
and [PowerManager](https://developer.android.com/reference/android/os/PowerManager#getCurrentThermalStatus());
unsupported API levels, read failures, and unknown enum values stay null.

## Persistence and selection

One small JSON record stores identity hash, level, charging, build, and timestamp
on this installation. Consent and identity notifications synchronously fence
pending reads and invalidate the in-memory baseline; serialized preference writes
clear the persisted baseline. An upgrade retains it, producing `build_changed`
on the first cross-build interval. A restarted process cannot reconstruct its
foreground coverage and emits null for that interval. The existing five-minute
throttle and fifteen-minute foreground timer remain the only sampling schedule.
A backwards clock jump preserves the original throttle until time catches up;
Android uses suspend-inclusive `SystemClock.elapsedRealtime()` from the existing
phone battery snapshot (`elapsed_realtime_ms`, local only). iOS/desktop keep the
process-local Stopwatch reference. Android reads the snapshot at each lifecycle
transition, including throttled transitions; it never falls back to the Android
Stopwatch, which excludes deep sleep. Every
lifecycle transition and completed sample compares wall-clock and monotonic
deltas; disagreement beyond 90 seconds or a backwards delta marks intervals
spanning that transition `clock_invalid`. Foreground spans use monotonic time.
The monotonic reference is not persisted across process restarts.

The admin route detects v2 presence per OS and observation build, including
invalid baseline rows. It uses only same-build v2 intervals of 900–7200 seconds,
with both charging endpoints explicitly false and no observed charging callback.
The estimand is equal-weight per-interval quantiles; the pooled estimator
(sum of drops / sum of hours) is tracked in the watchdog analysis, not the route.
Zero drops are included; negative drops are excluded. Builds without v2 retain
the v1 person-join fallback and its existing charging/drop semantics. Responses
include `n_pairs` (selected intervals), `n_v1_pairs`, and `n_v2_intervals`
(candidate counts before schema preference). No valid selected intervals yields
`measured_no_valid_pairs`, rather than resurrecting v1 intervals for a v2 build.

## Delivery shadowing audit

No production caller was found to depend on global values replacing event-owned
values. One previous manager test explicitly required that replacement and is
replaced by regressions for preserving event context and schema versions.
The raw callsite audit found these collisions; their emitters are unchanged:

- `Mobile Device Health Daily`: event-owned `app_version` is `version+build`;
  the old global overwrote it with the bare version.
- `auth_token_refresh_failed`, `authenticated_request_401`: event-owned
  `app_version` comes from PlatformManager (`version+build`); the old global
  overwrote it with the bare version.
- `Capture Wedge Detected`: event-owned `app_build` comes from the monitor's
  build provider. Capture-wedge family events also carry an explicit `build`;
  the manager used to replace it with the delivery-global build.
- `App Session Started`: event-owned `app_session_id` equals the session context
  just set by its emitter; preserving it changes no value.

| Event | Schema on the wire after delivery fix |
| --- | --- |
| `Diagnostics Sent` | `2`, from the diagnostics bundle |
| `Diagnostics Send Failed` | `2` when a bundle was built; `1` fallback for a pre-bundle failure (invalid emitter version `0`) |

`device_diagnostics.dart` passes the bundle schema to both analytics events.
Preserving schema `2` on delivery and retry is an intended consequence of this fix;
it is not confined to the local export payload.
Global properties now fill absent keys only. Explicitly null event-owned globals
remain absent on the manager's wire payload. Positive integer event schema
versions survive delivery and retries; invalid versions use the default `1`.
