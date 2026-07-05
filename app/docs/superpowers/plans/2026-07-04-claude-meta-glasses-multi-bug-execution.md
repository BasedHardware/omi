# Claude Meta Glasses Multi-Bug Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the EddyPhone Meta Glasses runtime stable: no app crash, no false "recording into nowhere", no shuttered snapshot cadence, recoverable `videoStreamingError`, and working glasses gestures with hardware proof.

**Architecture:** Treat this as a bug cluster in the DAT runtime state machine. Fix one symptom at a time with a failing regression first, then minimal provider/service/Swift bridge changes, then real-device proof. Keep source tests, analyzer, build, install, and glasses proof as separate lanes.

**Tech Stack:** Flutter/Dart Provider, Meta Wearables DAT Flutter plugin 0.8.0, iOS Swift `MPRemoteCommandCenter`, Xcode CoreDevice install, EddyPhone physical device.

---

## Claude Prompt

You are working in `/Users/Moni11811/OMI4META/app`.

Use maximum brevity. State the theory before each patch. Write the failing test first. Do not ship a new EddyPhone build for a symptom until that symptom has a regression test that fails without the fix. Do not claim done until `scripts/check_meta_glasses_runtime_proof.sh` passes on the pulled EddyPhone proof log.

Current known state:
- Bundle id: `dev.moni11811.omi`.
- EddyPhone CoreDevice id: `2649C7E8-7E64-501B-9108-8BC6038B8C2F`.
- EddyPhone Flutter id: `00008130-000C04D81891401C`.
- Current proof can stop at `meta_glasses_runtime_proof=pending_not_ready`.
- Recent device proof showed DAT devices visible but `connecting`, `linked=false`, `candidate=false`, `stream-started=0`, `frame-event=0`, `frame-captured=0`, `gesture_received=0`.
- Do not use `--dart-define` for the final installed build. Final install must be normal dev profile.

Acceptance proof:
- `MetaGlassStreamDiag stream-started` present.
- `MetaGlassStreamDiag frame-event` present.
- `MetaGlassStreamDiag frame-captured` present.
- `MetaGlassGestureDiag received` present.
- No unhandled `SessionError(code: videoStreamingError, message: videoStreamingError)`.
- No runtime path using shuttered still-photo capture for background frames.

## File Map

- Modify: `lib/providers/meta_wearables_provider.dart`
  - DAT readiness polling, capture state, stream retry, proof logging, gesture handling.
- Modify if needed: `lib/services/devices/meta_wearables_service.dart`
  - Device/link/camera-permission snapshots only.
- Modify if needed: `ios/Runner/AppDelegate.swift`
  - `com.omi/meta_gestures` bridge and `MPRemoteCommandCenter` callbacks.
- Modify: `test/unit/meta_glasses_autostart_regression_test.dart`
  - Provider state-machine tests.
- Modify: `test/unit/meta_glasses_runtime_regression_test.dart`
  - Source/proof/logging contract tests.
- Modify: `test/support/meta_wearables_mock_harness.dart`
  - Mock DAT controls for missing stream events, stale sessions, video frames, gestures.
- Modify if needed: `scripts/check_meta_glasses_runtime_proof.sh`
  - Hard proof gate.
- Modify: `docs/meta-glasses-plans/PROGRESS.md`
  - Record exact proof state.
- Modify: `docs/superpowers/plans/2026-07-04-meta-glasses-runtime-stabilization.md`
  - Keep pending/complete state honest.

---

## Task 1: Prove And Fix Missed DAT Readiness

Theory: visible glasses can remain `connecting` without another DAT device-stream event. Provider logs `not-ready` once, then never refreshes, so capture looks armed but no stream starts.

- [ ] **Step 1: Run the existing polling regression**

Run:

```bash
flutter test --reporter compact test/unit/meta_glasses_autostart_regression_test.dart --plain-name 'auto-start polls not-ready glasses so eligibility is not missed without stream events'
```

Expected before fix:

```text
FAIL or timeout because provider never refreshes not-ready devices
```

- [ ] **Step 2: If it passes accidentally, make it red**

In `test/unit/meta_glasses_autostart_regression_test.dart`, ensure this test exists exactly as a behavior test:

```dart
test('auto-start polls not-ready glasses so eligibility is not missed without stream events', () async {
  await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
  await MetaWearablesDat.pairMockRayBanMeta();
  harness.platform.emitDeviceChanges = false;

  final provider = MetaWearablesProvider();
  await provider.init();
  final controller = RecordingCaptureController();
  provider.attachCaptureController(controller);
  await _drainAutoStart();

  expect(provider.isCapturing, isFalse);
  expect(harness.platform.lastStreamDeviceUuid, isNull);

  await _makeMockEligible();
  await Future<void>.delayed(const Duration(seconds: 4));
  await _drainAutoStart();
  await _waitFor(() => provider.isCapturing);

  expect(provider.devices.single.linkState, DeviceLinkState.connected);
  expect(harness.platform.lastStreamDeviceUuid, RecordingMetaWearablesMockPlatform.uuid);
  expect(harness.platform.frameCaptureCount, 1);
  expect(controller.ingestedImages, hasLength(1));

  provider.dispose();
});
```

Run same command. Expected: fail without provider polling.

- [ ] **Step 3: Implement not-ready polling**

In `lib/providers/meta_wearables_provider.dart`, add timer state near other provider fields:

```dart
static const Duration _notReadyRefreshInterval = Duration(seconds: 2);

Timer? _notReadyRefreshTimer;
bool _notReadyRefreshInFlight = false;
```

Add helpers near `_maybeAutoStartCapture`:

```dart
bool get _shouldPollNotReady =>
    _initialized &&
    _initialRefreshComplete &&
    autoCaptureEnabled &&
    !isCapturing &&
    !_autoStartInFlight &&
    !_captureTransitionInFlight &&
    !_manualStopRequested &&
    isRegistered &&
    devices.isNotEmpty &&
    !_hasSessionCandidateDevice &&
    _captureController != null;

void _scheduleNotReadyRefresh() {
  if (_notReadyRefreshTimer != null || !_shouldPollNotReady) return;
  _appendRuntimeProof('MetaGlassRuntimeProof not-ready-refresh-scheduled interval=${_notReadyRefreshInterval.inSeconds}s');
  _notReadyRefreshTimer = Timer.periodic(_notReadyRefreshInterval, (_) {
    unawaited(_refreshNotReadyDevices());
  });
}

void _cancelNotReadyRefresh() {
  final timer = _notReadyRefreshTimer;
  if (timer == null) return;
  timer.cancel();
  _notReadyRefreshTimer = null;
  _appendRuntimeProof('MetaGlassRuntimeProof not-ready-refresh-cancelled');
}

Future<void> _refreshNotReadyDevices() async {
  if (!_shouldPollNotReady) {
    _cancelNotReadyRefresh();
    return;
  }
  if (_notReadyRefreshInFlight) return;

  _notReadyRefreshInFlight = true;
  try {
    _appendRuntimeProof('MetaGlassRuntimeProof not-ready-refresh');
    await refresh();
    if (_hasSessionCandidateDevice) {
      _cancelNotReadyRefresh();
    }
    await _maybeAutoStartCapture();
  } catch (error, stackTrace) {
    Logger.error('Meta glasses not-ready refresh failed: $error', stackTrace: stackTrace);
    _appendRuntimeProof('MetaGlassRuntimeProof not-ready-refresh-error error=$error');
  } finally {
    _notReadyRefreshInFlight = false;
  }
}
```

In `_maybeAutoStartCapture`, when logging `auto-start-skip reason=not-ready`, call:

```dart
_scheduleNotReadyRefresh();
return;
```

Also call `_cancelNotReadyRefresh()` before returns for disabled auto-capture, manual stop, already capturing, no controller, and candidate ready/start path.

In `dispose()`, add:

```dart
_cancelNotReadyRefresh();
```

- [ ] **Step 4: Prove green**

Run:

```bash
flutter test --reporter compact test/unit/meta_glasses_autostart_regression_test.dart --plain-name 'auto-start polls not-ready glasses so eligibility is not missed without stream events'
```

Expected:

```text
All tests passed
```

---

## Task 2: Prove Background Capture Uses Video Frames, Not Shuttered Photos

Theory: shutter/snapshot sounds mean some background path still calls still-photo capture. Background capture must subscribe to DAT video frames and ingest compressed frames, not call a photo API on an interval.

- [ ] **Step 1: Strengthen source contract**

In `test/unit/meta_glasses_runtime_regression_test.dart`, add or tighten this test:

```dart
test('background camera capture does not use shuttered still-photo APIs', () {
  final provider = File('lib/providers/meta_wearables_provider.dart').readAsStringSync();
  final start = provider.indexOf('Future<void> _startPhotoLoop');
  final end = provider.indexOf('Future<void> _stopPhotoLoop');
  expect(start, isNonNegative);
  expect(end, greaterThan(start));

  final photoLoop = provider.substring(start, end);
  expect(photoLoop, contains('videoFramesStream'));
  expect(photoLoop, contains('MetaGlassStreamDiag frame-event'));
  expect(photoLoop, contains('MetaGlassStreamDiag frame-captured'));
  expect(photoLoop, isNot(contains('capturePhoto(')));
  expect(photoLoop, isNot(contains('takePicture(')));
  expect(photoLoop, isNot(contains('PhotoResult')));
});
```

Run:

```bash
flutter test --reporter compact test/unit/meta_glasses_runtime_regression_test.dart --plain-name 'background camera capture does not use shuttered still-photo APIs'
```

Expected before fix if a still-photo path remains:

```text
FAIL with capturePhoto/takePicture/PhotoResult found
```

- [ ] **Step 2: Patch provider only if test fails**

In `lib/providers/meta_wearables_provider.dart`, keep background capture in `_startPhotoLoop` on `videoFramesStream`. Remove any still-photo capture from the background loop. Keep still-photo APIs only for explicit user-requested photos, if that surface exists.

Required runtime proof lines:

```dart
_appendRuntimeProof('MetaGlassStreamDiag stream-started device=${_sessionTargetUuid ?? 'auto'} mode=background-video');
_appendRuntimeProof('MetaGlassStreamDiag frame-event bytes=${frame.bytes.length}');
_appendRuntimeProof('MetaGlassStreamDiag frame-captured bytes=${jpegBytes.length}');
```

- [ ] **Step 3: Prove no shutter path in tests**

Run:

```bash
flutter test --reporter compact test/unit/meta_glasses_runtime_regression_test.dart --plain-name 'background camera capture does not use shuttered still-photo APIs'
```

Expected:

```text
All tests passed
```

---

## Task 3: Prove `videoStreamingError` Is Recoverable

Theory: `SessionError(videoStreamingError)` leaves a stale native stream session. Next start can fail with an existing session, while UI still believes capture is running.

- [ ] **Step 1: Run existing stale-session regression**

Run:

```bash
flutter test --reporter compact test/unit/meta_glasses_autostart_regression_test.dart --plain-name 'stream start failure during initial capture schedules the bounded camera retry'
```

Expected:

```text
All tests passed after current fix, or FAIL if stale-session handling regressed
```

- [ ] **Step 2: If missing, assert stale native session stop-before-retry**

In `test/unit/meta_glasses_autostart_regression_test.dart`, the test must assert:

```dart
expect(harness.platform.streamStartCallCount, greaterThanOrEqualTo(2));
expect(harness.platform.stopStreamSessionCount, greaterThanOrEqualTo(1));
expect(harness.platform.streamSessionExists, isFalse);
```

- [ ] **Step 3: Patch provider only if test fails**

In `lib/providers/meta_wearables_provider.dart`, in stream-start failure recovery:

```dart
if (_isVideoStreamingError(error)) {
  _appendRuntimeProof('MetaGlassStreamDiag stream-start-failed recoverable=true error=$error');
  await stopPreview();
  _appendRuntimeProof('MetaGlassStreamDiag stop-before-retry');
  if (!_cameraRetryUsed) {
    _cameraRetryUsed = true;
    await Future<void>.delayed(const Duration(milliseconds: 500));
    await _startPhotoLoop();
    return;
  }
  await _enterMicOnlyFallback(reason: 'videoStreamingError');
  return;
}
```

Use existing names if the provider already has equivalent fields/methods. Do not add a second retry system.

- [ ] **Step 4: Prove green**

Run:

```bash
flutter test --reporter compact test/unit/meta_glasses_autostart_regression_test.dart --plain-name 'stream start failure during initial capture schedules the bounded camera retry'
```

Expected:

```text
All tests passed
```

---

## Task 4: Prove Glasses Gestures Reach Dart

Theory: gestures are broken because the iOS remote-command target is either not installed, overwritten, disabled by persisted Dart settings, or not logging the bridge path. Need prove Swift command callback and Dart provider receive path separately.

- [ ] **Step 1: Run existing gesture source contract**

Run:

```bash
flutter test --reporter compact test/unit/meta_glasses_runtime_regression_test.dart --plain-name 'iOS glasses gesture bridge is instrumented and target-safe'
```

Expected:

```text
All tests passed, or FAIL with missing bridge/target instrumentation
```

- [ ] **Step 2: Run gesture migration regressions**

Run:

```bash
flutter test --reporter compact test/unit/meta_glasses_autostart_regression_test.dart --plain-name 'old installs with gestures persisted off are migrated on once'
flutter test --reporter compact test/unit/meta_glasses_autostart_regression_test.dart --plain-name 'gesture migration preserves explicit off after the migration marker exists'
```

Expected:

```text
All tests passed
```

- [ ] **Step 3: Patch Swift bridge only if source contract fails or hardware logs show no Swift callback**

In `ios/Runner/AppDelegate.swift`, the gesture bridge must:

```swift
private let metaGesturesChannelName = "com.omi/meta_gestures"
```

It must remove stale targets before adding new ones:

```swift
let commandCenter = MPRemoteCommandCenter.shared()
commandCenter.playCommand.removeTarget(nil)
commandCenter.pauseCommand.removeTarget(nil)
commandCenter.togglePlayPauseCommand.removeTarget(nil)
commandCenter.nextTrackCommand.removeTarget(nil)
commandCenter.previousTrackCommand.removeTarget(nil)
```

Each command callback must log and invoke Dart:

```swift
NSLog("OmiMetaGestures received %@", gesture)
metaGesturesChannel?.invokeMethod("gesture", arguments: ["gesture": gesture])
return .success
```

- [ ] **Step 4: Patch Dart provider only if Swift callback exists but Dart proof is missing**

In `lib/providers/meta_wearables_provider.dart`, gesture receive path must append:

```dart
_appendRuntimeProof('MetaGlassGestureDiag received gesture=$gesture enabled=$gesturesEnabled capturing=$isCapturing');
```

If disabled:

```dart
_appendRuntimeProof('MetaGlassGestureDiag ignored reason=disabled gesture=$gesture');
```

Gesture actions must be state-safe:
- start only if not capturing and candidate device exists,
- stop only if capturing,
- pause/resume must not kill the native stream unless user requested stop.

- [ ] **Step 5: Prove tests green**

Run:

```bash
flutter test --reporter compact test/unit/meta_glasses_runtime_regression_test.dart --plain-name 'iOS glasses gesture bridge is instrumented and target-safe'
flutter test --reporter compact test/unit/meta_glasses_autostart_regression_test.dart --plain-name 'old installs with gestures persisted off are migrated on once'
flutter test --reporter compact test/unit/meta_glasses_autostart_regression_test.dart --plain-name 'gesture migration preserves explicit off after the migration marker exists'
```

Expected:

```text
All tests passed
```

---

## Task 5: Prove The App Crash Signature Before Patching Crash Guards

Theory: "app is crashing" is not actionable until tied to one crash signature. The likely suspects are async stream teardown, stale native DAT session, null active device, or gesture callback during provider disposal.

- [ ] **Step 1: Pull latest device/app proof**

Run:

```bash
./scripts/pull_meta_glasses_runtime_proof.sh || true
scripts/check_meta_glasses_runtime_proof.sh || true
```

Expected if hardware still not ready:

```text
meta_glasses_runtime_proof=pending_not_ready
```

- [ ] **Step 2: Capture crash/system logs**

Run:

```bash
xcrun devicectl device log stream --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F --style compact --predicate 'process == "Runner" OR eventMessage CONTAINS "dev.moni11811.omi" OR eventMessage CONTAINS "MetaGlass" OR eventMessage CONTAINS "SessionError" OR eventMessage CONTAINS "videoStreamingError"' > /tmp/omi-meta-glasses-crash-live.log
```

While it runs, launch the app and reproduce the crash. Stop the log stream after the crash.

Summarize with:

```bash
node - <<'NODE'
const fs = require('fs');
const p = '/tmp/omi-meta-glasses-crash-live.log';
const s = fs.existsSync(p) ? fs.readFileSync(p, 'utf8').split('\n') : [];
const hits = s.filter(l => /crash|fatal|exception|SessionError|videoStreamingError|MetaGlass|gesture|Runner/i.test(l));
console.log(hits.slice(-120).join('\n'));
NODE
```

- [ ] **Step 3: Add one regression for the exact crash**

Pick the matching crash signature:

If crash mentions disposed provider/timer, add test:

```dart
test('not-ready refresh timer is cancelled on dispose', () async {
  await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
  await MetaWearablesDat.pairMockRayBanMeta();
  harness.platform.emitDeviceChanges = false;

  final provider = MetaWearablesProvider();
  await provider.init();
  provider.attachCaptureController(RecordingCaptureController());
  await _drainAutoStart();
  provider.dispose();

  await Future<void>.delayed(const Duration(seconds: 3));
  expect(harness.platform.streamStartCallCount, 0);
});
```

If crash mentions active device null, add test:

```dart
test('refresh with visible devices and no active device does not crash', () async {
  await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
  await MetaWearablesDat.pairMockRayBanMeta();
  harness.platform.reportsActiveDevice = false;

  final provider = MetaWearablesProvider();
  await provider.init();
  await provider.refresh();

  expect(provider.devices, isNotEmpty);
  provider.dispose();
});
```

If crash mentions stream teardown after error, extend the existing `videoStreamingError` test instead of adding a duplicate test.

- [ ] **Step 4: Run the new crash regression red**

Run the exact test by `--plain-name`.

Expected:

```text
FAIL without the crash guard
```

- [ ] **Step 5: Patch only the proven crash path**

Patch the smallest guard:
- cancel timers before dispose completes,
- ignore async completions after dispose,
- null-check active device only at DAT boundary,
- always stop native stream before retry/fallback,
- never call `notifyListeners()` after dispose.

- [ ] **Step 6: Prove crash regression green**

Run the exact test again.

Expected:

```text
All tests passed
```

---

## Task 6: Run Full Source Gate

Theory: fixes touch shared provider state. Need run all touched tests before build.

- [ ] **Step 1: Run focused touched tests**

Run:

```bash
flutter test --reporter compact \
  test/providers/capture_provider_test.dart \
  test/unit/meta_glasses_autostart_regression_test.dart \
  test/unit/meta_glasses_runtime_regression_test.dart \
  test/unit/meta_glasses_device_sanitize_test.dart \
  test/unit/omi4meta_reconstruction_contract_test.dart
```

Expected:

```text
All tests passed
```

- [ ] **Step 2: Run analyzer and count only errors**

Run:

```bash
flutter analyze > /tmp/omi-flutter-analyze.log || true
node - <<'NODE'
const fs = require('fs');
const s = fs.readFileSync('/tmp/omi-flutter-analyze.log', 'utf8').split('\n');
const errors = s.filter(l => /^\s*error\s+-/.test(l));
console.log(`error_lines=${errors.length}`);
console.log(errors.slice(0, 80).join('\n'));
NODE
```

Expected:

```text
error_lines=0
```

---

## Task 7: Build, Install, Launch, And Pull Proof On EddyPhone

Theory: source green is not hardware proof. Install proof and glasses proof are separate.

- [ ] **Step 1: Repair Flutter SwiftPM target**

Run:

```bash
./scripts/repair_flutter_spm_ios_target.sh
```

Expected:

```text
script exits 0
```

- [ ] **Step 2: Build normal dev profile**

Run:

```bash
flutter build ios --profile --flavor dev -t lib/main.dart --no-pub
```

Expected:

```text
Built build/ios/iphoneos/Runner.app
```

- [ ] **Step 3: Install on EddyPhone**

Run:

```bash
xcrun devicectl device install app --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F build/ios/iphoneos/Runner.app
```

Expected:

```text
installed app dev.moni11811.omi
```

- [ ] **Step 4: Terminate stale Runner if needed**

Run:

```bash
pid="$(xcrun devicectl device info processes --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F | awk '/Runner/ {print $1; exit}')"
if [ -n "$pid" ]; then
  xcrun devicectl device process terminate --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F --pid "$pid" --kill || true
fi
```

Expected:

```text
no stale Runner remains
```

- [ ] **Step 5: Launch**

Run:

```bash
xcrun devicectl device process launch --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F dev.moni11811.omi
```

If launch says device locked, retry after 30 seconds, then 90 seconds. Do not call install complete until launch succeeds or locked-device blocker is recorded separately.

- [ ] **Step 6: Exercise hardware**

On glasses:
- verify linked/eligible state,
- start capture or let auto-start run,
- wait for video frames,
- press the expected glasses gesture controls,
- listen for shutter sounds,
- watch for red `SessionError(videoStreamingError)` UI.

- [ ] **Step 7: Pull proof**

Run:

```bash
./scripts/pull_meta_glasses_runtime_proof.sh
scripts/check_meta_glasses_runtime_proof.sh
```

Expected final pass:

```text
meta_glasses_runtime_proof=passed
```

If still pending:

```text
meta_glasses_runtime_proof=pending_not_ready
```

Then do not claim runtime complete. Continue with exact reason from the proof log.

---

## Task 8: Update Progress And Handoff Truth

Theory: stale "done" docs cause repeated false builds. Docs must say exact lane truth.

- [ ] **Step 1: Update progress**

In `docs/meta-glasses-plans/PROGRESS.md`, write one concise current line:

```text
runtime - partial 2026-07-04 - source tests/build/install status: <state>; EddyPhone glasses proof: <passed|pending_not_ready|locked|failed>; proof log: /tmp/omi-meta-glasses-runtime-proof-pulled.log; next action: <one action>.
```

- [ ] **Step 2: Update plan state**

In `docs/superpowers/plans/2026-07-04-meta-glasses-runtime-stabilization.md`, keep the runtime state as partial unless `scripts/check_meta_glasses_runtime_proof.sh` prints `meta_glasses_runtime_proof=passed`.

- [ ] **Step 3: Final report**

Report only:
- tests run and result,
- analyzer error count,
- build/install/launch state,
- proof checker result,
- remaining bug if proof not passed,
- exact next action.

Do not say "fixed" unless proof checker passed.
