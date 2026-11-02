# Heavy-account profile benchmark

The fixture is synthetic: 2,000 conversations, a long newest transcript,
40 people, summary action items, 50 Tasks items and 6,500 pending WAL records.
No account sign-in is performed. Dart HTTP is restricted to an in-process
loopback server; uploads receive a delayed 429 so the backlog stays pending.
Preferences and secure storage use memory implementations. Documents, support
and temporary paths point at a new fixture-owned directory before any WAL I/O.
The benchmark never cleans up app audio or changes WAL lifecycle policy.

From the product repository root on an Apple Silicon Mac with the configured
Flutter 3.44.5 SDK and prepared development signing:

```bash
bash app/tool/perf_device_run.sh --accept-baseline
```

Physical-device installation needs the device owner's approval. Use the DEV
flavor only; the production bundle and data are outside this harness. Keep the
phone connected and unlocked during runs. Three fresh launches reuse one built
app binary; source revision, Flutter version and binary hash accompany receipts.
Runtime OS version is also part of identity; an OS update invalidates comparison.
Do not compare different phones, refresh rates, thermal states or host loads.

The [runner guide](../../tool/perf/README.md) covers device selection, comparison
and qualification failures. On macOS, signing needs the GUI login session. If
`launchctl managername` says `Background` and codesign returns
`errSecInternalComponent`, use an approved Aqua terminal session as described in
[local-code-signing.md](../../../desktop/macos/docs/local-code-signing.md).
Do not replace the signing identity, use ad-hoc signing or alter key ACLs to
work around it. Flutter discovery needs the launching app's Local Network
permission on the Mac and the DEV app's local-network permission on the phone.
The qualification host grants iTerm Local Network, but its Automation/modal
path needs owner attention. The approved overnight route uses Aqua Terminal
and accepts USB discovery fallback; no permission settings are changed.
USB log discovery may recover slowly after a multicast denial; that warning is
not a completed measurement. Keep Auto-Lock at Never for the approved session
if no harness wake plugin is installed, then restore the owner's setting.

Flutter forbids profile/release compilation for iOS simulators. On m1's already
booted simulator, use `app/tool/perf_sim_profile.sh` with
`--simulator-qualification --device <UDID>`. This
uses debug mode and produces **scenario-only, not a perf baseline** evidence.
Simulator build overrides are invocation-only; no production/release Xcode
settings, signing, architecture or lifecycle plist is changed.

Five windows measure Home shell mount/cache restore, conversation flings,
conversation detail/transcript, Home/Tasks switching, and lifecycle transitions
with the WAL service active. Cold start means shell/cache initialization, not
native process/Firebase/onboarding startup. Lifecycle transitions are delivered
through the binding; this does not claim OS suspension/resume coverage.

Before those windows, a quiet blank widget verifies that the test framework is
not generating continuous idle frames. Flutter3.44.5's live binding requests
another engine frame after every draw even under benchmarkLive. The harness
suppresses that test-only tail while preserving genuine framework requests.
An idle-frame probe and nonempty scenario frames guard both directions. The
native buffered initial lifecycle state initializes the test dispatcher only
when its state is absent; live lifecycle events remain authoritative.
The existing foreground-task plugin also reads the native app-active state.
Both native active and Flutter resumed are required before fixture I/O. This
never overrides Flutter lifecycle state or bypasses a native alert. If both
remain inactive, stop bounded retries and ask the device owner to resolve it;
do not capture a personal phone's screen or tap its dialogs.

Each `receipt-N.json` reports engine build/raster/total p50/p90/p99 in
microseconds, frames over 16/32/100 ms, worst total frame and frame count.
Timings drain before the next window because the engine batches callbacks.
Total span includes pipeline latency; build/raster percentiles remain separate.
The report requires all five nonempty windows, successful cache restore, matching
dataset/mode and at least three runs. Variance is `(max p90 - min p90) / min p90`
and must be at most 15% for each reported p90. Debug evidence never becomes
profile acceptance. Do not discard slow runs or relax fixture sizes to pass.

Use `--timeline --runs 1` for a separate streamed VM trace. Tracing has material
overhead and is explicitly ineligible for acceptance. Import `receipt-N-timeline.json` in
Dart DevTools Performance. `heavy.<scenario>` tasks identify windows. Rank UI
isolate work from the trace, keeping raster-thread work and startup work apart.
Do not rank a static code hypothesis as a measured cost. CPU samples accompany
the opt-in attribution run. The default frame baseline disables timeline
recording and CPU-table export; profiler overhead must match in comparisons.
The runner disables DDS so the in-app integration timeline client reaches its
own VM service, and the fixture network guard permits only loopback connections
(the fixture API plus that VM service). `receipt-N-cpu.json` contains raw
main-isolate samples; the summary ranks sampled exclusive functions. These are
CPU samples, not measured wall milliseconds, and exclude fixture generation.

## Field signal design (watch only)

Current main sends diagnostics through the local `mobile_render_diagnostic`
log path only when `devLogsToFileEnabled` is true. Routine PostHog emission has
been removed (`MobilePerformanceTelemetry._send` and `main.dart`'s emitter).
There is therefore no verified current fleet-wide PostHog `mobile_lag_stall`
feed. A dashboard is blocked on a separately reviewed, privacy-preserving
aggregate transport plus foreground exposure telemetry; this PR adds neither.
Do not enable a nonexistent gate or infer fleet health from missing events.

The proposed PostHog event is `mobile_lag_stall`; existing local fields are
`surface`, `interaction`, and `blocked_ms`. Add build/version, channel, platform,
OS and device-class metadata at the aggregate transport boundary without
conversation IDs/content or account identifiers. A dashboard must not silently
drop missing values. Include an explicit unknown bucket. Group by platform,
build number/app version, release channel, surface and device class. Display:

- Stalls per 10 foreground minutes and sessions/devices with at least one stall.
- Stall duration p50/p90/p99 and worst duration, with event and device counts.
- Separate foreground scrolling/navigation from background/lifecycle gaps.
- Split Home conversations, detail and other tabs; compare like device classes.

The denominator must be foreground exposure from the same build/channel/device
cohort, not all installs or all sessions. If that exposure signal is absent,
report the missing denominator and show event counts without calling them rates.
Show rollout share, sampling/consent coverage and the time window alongside each
comparison. Never compare David's one heavy account to the whole store cohort.

A watch-only TestFlight-versus-store gate compares overlapping windows on the
same OS/device class with adequate foreground exposure. Require at least 30
devices and 100 foreground device-hours per arm before a cohort-level verdict;
smaller samples remain insufficient evidence. Alert the release owner when both
stall rate and affected-device rate worsen, or repeated >100 ms foreground
stalls appear on the candidate. Include counts and uncertainty intervals; avoid
one arbitrary percentage deciding a rollout. This gate observes only: it does
not flip flags, change traffic or stop/ship a release. The release owner records
the decision. Exact alert thresholds require a measured historical baseline.

Telemetry caveat: #23594 already changed the lag watchdog to suspend on every
non-resumed lifecycle state and changed `wal_admission_pressure` to once per
count-cap episode. Compare builds containing that fix separately from older
builds; their event counts do not share the same measurement behavior.

## Dedicated Android device / nightly setup

Prepare a dedicated phone without production Omi accounts, enable Developer
Options and USB debugging, connect USB, and approve that host's RSA prompt.
Confirm `adb -s <serial> get-state` says `device`; keep the phone powered, awake,
unlocked and in a stable thermal state. Install the Android SDK/JDK and prepare
the repository via its documented app setup. The harness builds DEV, never PROD.
Run the same command above with `--platform android --device '<adb serial>'`.
Physical Android is required; emulator results are refused for acceptance.

After a successful manual three-run qualification, an existing scheduler on the
always-on host can invoke:

```bash
OMI_PERF_DEVICE='<dedicated adb serial>' \
OMI_PERF_ARTIFACT_ROOT=/Volumes/Ephemeral/scratch/mobile-heavy-nightly \
OMI_HEAVY_BIN="$HOME/workspace/omi/bin/omi-heavy" \
  bash app/tool/perf_nightly.sh
```

The nightly script uses a lock, a clean pinned checkout, one build and three
serial driver runs. It never pulls, merges, deploys, signs into an account,
uninstalls another app, installs a scheduler or deletes prior artifacts. An
existing host scheduler owns cadence and failure notification. Preserve all
receipts and failures; no automatic rebaseline or retry hides a regression.
Android execution remains unqualified until the purchased device is available.
