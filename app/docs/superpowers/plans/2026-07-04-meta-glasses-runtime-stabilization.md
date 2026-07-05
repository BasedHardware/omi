# Meta Glasses Runtime Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current Meta Glasses build stable on EddyPhone: no app crash, no `SessionError(videoStreamingError)`, no shutter/snapshot cadence during background capture, and working glasses gestures.

**Architecture:** Treat this as a runtime stabilization pass, not another feature pass. First capture evidence from the real device, then add failing regression tests, then fix one root cause at a time. The likely failure boundary is the DAT camera stream/session state machine plus the iOS remote-command gesture bridge, so changes stay scoped to `MetaWearablesProvider`, `MetaWearablesService`, the vendored DAT plugin only if required, and `AppDelegate.swift`.

**Tech Stack:** Flutter/Dart Provider, Meta Wearables DAT Flutter plugin 0.8.0, iOS Swift `MPRemoteCommandCenter`, Xcode device install, EddyPhone physical device.

---

## Claude Prompt

You are Claude Code working in `/Users/Moni11811/OMI4META/app`.

Hard rules:
- Read `/Users/Moni11811/OMI4META/AGENTS.md`, `/Users/Moni11811/OMI4META/app/AGENTS.md`, and this file before changing code.
- State the bug theory before every patch.
- Write the failing test first. Run it. Confirm it fails for the expected reason.
- Forbidden: install/build "N+1" until the current symptom has a regression test that fails without the fix.
- Do not push, open PRs, merge, or reset.
- Keep `ios/Flutter/Flutter.podspec` deployment target at `17.0`.
- No `--dart-define` install on EddyPhone. Final install must be a normal `dev` profile build.
- If three fix attempts fail on the same symptom, stop and question the architecture.

Known current facts:
- Plans `01` through `09` in `docs/meta-glasses-plans/PROGRESS.md` are marked done.
- EddyPhone Flutter device id: `00008130-000C04D81891401C`.
- EddyPhone CoreDevice id: `2649C7E8-7E64-501B-9108-8BC6038B8C2F`.
- Current installed bundle id: `dev.moni11811.omi`.
- Last direct install and launch succeeded via `devicectl`; process was still running after 5 seconds.
- User-visible bugs remain: app crashes, `SessionError(code: videoStreamingError, message: videoStreamingError)`, glasses gestures broken, capture appears to record into nowhere, and glasses still make shutter/snapshot sounds. Desired behavior: background video frames, no shuttered still-photo cadence.
- Important code points:
  - `lib/providers/meta_wearables_provider.dart`
  - `lib/services/devices/meta_wearables_service.dart`
  - `ios/Runner/AppDelegate.swift`
  - `third_party/meta_wearables_dat_flutter/lib/meta_wearables_dat_flutter.dart`
  - `third_party/meta_wearables_dat_flutter/ios/meta_wearables_dat_flutter/Sources/meta_wearables_dat_flutter/MetaWearablesDatPlugin.swift`
  - Tests under `test/unit/meta_glasses_*`

## File Map

- Modify: `test/unit/meta_glasses_runtime_regression_test.dart`
  - New regression tests for no shuttered background capture, stream-error recovery, and gesture bridge instrumentation.
- Modify: `lib/providers/meta_wearables_provider.dart`
  - Owns capture state, background frame ingestion, stream retry/fallback, gesture actions.
- Modify if needed: `lib/services/devices/meta_wearables_service.dart`
  - Owns DAT service wrapper and should expose only real SDK methods.
- Modify if needed: `third_party/meta_wearables_dat_flutter/lib/meta_wearables_dat_flutter.dart`
  - Only if a missing real DAT stream/error API must be surfaced to Dart.
- Modify if needed: `third_party/meta_wearables_dat_flutter/ios/meta_wearables_dat_flutter/Sources/meta_wearables_dat_flutter/MetaWearablesDatPlugin.swift`
  - Only if native iOS plugin must forward stream errors or frame data differently.
- Modify: `ios/Runner/AppDelegate.swift`
  - Owns `com.omi/meta_gestures` and `MPRemoteCommandCenter` target registration.
- Modify: `docs/meta-glasses-plans/PROGRESS.md`
  - Append runtime proof notes after real-device verification.

## Task 1: Capture Real Evidence First

**Files:**
- Read: `/tmp/omi_eddyphone_devicectl_install.log`
- Read: `/tmp/omi_eddyphone_launch.log`
- Create: `/tmp/omi-meta-glasses-runtime.log`

- [ ] **Step 1: Confirm current build identity on EddyPhone**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
DEVICE=2649C7E8-7E64-501B-9108-8BC6038B8C2F
BUNDLE=dev.moni11811.omi
xcrun devicectl list devices | grep -E 'EddyPhone|Identifier|available'
xcrun devicectl device process launch --device "$DEVICE" "$BUNDLE"
sleep 5
xcrun devicectl device info processes --device "$DEVICE" | grep -E 'Runner|dev.moni11811.omi'
```

Expected:
- EddyPhone is `available (paired)`.
- Launch exits `0`.
- Process list contains `/Runner.app/Runner`.

- [ ] **Step 2: Capture runtime logs while reproducing**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
DEVICE=2649C7E8-7E64-501B-9108-8BC6038B8C2F
xcrun devicectl device log stream --device "$DEVICE" --style compact --predicate 'process == "Runner"' \
  | tee /tmp/omi-meta-glasses-runtime.log
```

If this command prints a usage error, run:

```bash
xcrun devicectl device log stream --help
```

Then use the equivalent `devicectl` log-stream syntax shown by help. Record the exact replacement command at the top of `/tmp/omi-meta-glasses-runtime.log`.

- [ ] **Step 3: Reproduce all symptoms in one run**

On EddyPhone:
- Open Omi dev app.
- Ensure Meta glasses are connected/registered.
- Start glasses capture if auto-capture did not start.
- Leave it running for 2 minutes.
- Press the glasses gesture controls that should start/stop/pause/resume capture.
- Listen for shutter/snapshot sounds.
- Watch for red crash/error UI, especially `videoStreamingError`.

- [ ] **Step 4: Summarize evidence before patching**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
grep -E 'SessionError|videoStreamingError|MetaWearablesProvider|MetaGlass|gesture|OmiMeta|capturePhoto|videoFramesStream|startStreamSession|stopStreamSession|crash|fatal|exception' /tmp/omi-meta-glasses-runtime.log | tail -200
```

Expected:
- You can state which boundary fails:
  - stream start/session creation,
  - frame subscription,
  - capture routing,
  - gesture remote command delivery,
  - app crash unrelated to Meta.

Do not patch before this theory is written.

## Task 2: Add Runtime Regression Tests

**Files:**
- Create: `test/unit/meta_glasses_runtime_regression_test.dart`

- [ ] **Step 1: Write the failing tests**

Create `test/unit/meta_glasses_runtime_regression_test.dart` with exactly this starting content:

```dart
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

String _functionBody(String source, String functionName) {
  final start = source.indexOf(functionName);
  if (start < 0) {
    fail('Missing function $functionName');
  }

  final open = source.indexOf('{', start);
  if (open < 0) {
    fail('Missing opening brace for $functionName');
  }

  var depth = 0;
  for (var i = open; i < source.length; i++) {
    final char = source.codeUnitAt(i);
    if (char == 123) depth++;
    if (char == 125) depth--;
    if (depth == 0) return source.substring(open, i + 1);
  }

  fail('Missing closing brace for $functionName');
}

void main() {
  group('Meta glasses runtime regressions', () {
    test('background camera capture does not use shuttered still-photo loop', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');
      final automaticLoop = _functionBody(provider, '_startPhotoLoop');

      expect(provider, contains('videoFramesStream'), reason: 'background capture must subscribe to DAT video frames');
      expect(
        automaticLoop,
        isNot(contains('capturePhoto')),
        reason: 'automatic background capture must not trigger glasses still-photo shutter sounds',
      );
      expect(
        automaticLoop,
        isNot(contains('takePicture')),
        reason: 'automatic background capture must not call any still capture API',
      );
    });

    test('video streaming errors are caught and moved to recoverable state', () {
      final provider = _read('lib/providers/meta_wearables_provider.dart');

      expect(provider, contains('videoStreamingError'));
      expect(provider, contains('MetaGlassStreamDiag'));
      expect(provider, contains('recoverFromVideoStreamingError'));
      expect(provider, contains('streamFailureCount'));
      expect(provider, contains('micOnlyFallback'));
    });

    test('iOS glasses gesture bridge is instrumented and target-safe', () {
      final appDelegate = _read('ios/Runner/AppDelegate.swift');

      expect(appDelegate, contains('OmiMetaGestures'));
      expect(appDelegate, contains('MPRemoteCommandCenter.shared()'));
      expect(appDelegate, contains('removeTarget(nil)'), reason: 'remote command targets must not double-register');
      expect(appDelegate, contains('playCommand'));
      expect(appDelegate, contains('pauseCommand'));
      expect(appDelegate, contains('togglePlayPauseCommand'));
      expect(appDelegate, contains('nextTrackCommand'));
      expect(appDelegate, contains('previousTrackCommand'));
      expect(appDelegate, contains('invokeMethod("onGesture"'));
    });
  });
}
```

- [ ] **Step 2: Run the tests and confirm red**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
flutter test --reporter compact test/unit/meta_glasses_runtime_regression_test.dart
```

Expected:
- FAIL before fixes.
- At least one failure must mention shuttered still-photo loop, missing `videoStreamingError` recovery, or missing gesture instrumentation.

- [ ] **Step 3: Do not loosen these tests**

If a test fails because the desired runtime behavior is missing, fix production code. Do not weaken the test.

## Task 3: Fix Background Capture So It Uses Video Frames, Not Still Photos

**Files:**
- Modify: `lib/providers/meta_wearables_provider.dart`
- Modify if needed: `lib/services/devices/meta_wearables_service.dart`
- Modify if needed: `third_party/meta_wearables_dat_flutter/lib/meta_wearables_dat_flutter.dart`

- [ ] **Step 1: State theory**

Write in your response before patching:

```text
Theory: automatic background capture still reaches a still-photo path or repeatedly starts a stream session, causing shutter sounds and stream-session errors. The fix is to make automatic capture consume one DAT video frame stream subscription and reserve still-photo APIs only for explicit user photo capture.
```

- [ ] **Step 2: Inspect DAT API existence**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
grep -R "videoFramesStream\|startStreamSession\|stopStreamSession\|capturePhoto" -n \
  third_party/meta_wearables_dat_flutter \
  ios/Flutter/ephemeral/Packages/.packages/meta_wearables_dat_flutter \
  ios/Flutter/ephemeral/Packages 2>/dev/null | head -120
```

Expected:
- Real DAT/plugin frame stream API exists before calling it.
- If a needed method is missing, wire all layers: facade -> platform interface -> method channel -> native Swift. No Dart-only method.

- [ ] **Step 3: Replace automatic still-photo loop**

In `lib/providers/meta_wearables_provider.dart`:
- Keep manual explicit photo capture if the app still needs it.
- Change automatic capture so `_startPhotoLoop` no longer calls `capturePhoto`, `takePicture`, or any still capture API.
- Subscribe to `videoFramesStream` once per active capture session.
- Downscale/compress frames as existing plan 04 intended.
- Send frames to the existing capture queue/backend path.
- Add log lines with the exact prefix `MetaGlassStreamDiag`.

Required behavior:
- One active stream session per device capture.
- No stream start/stop per frame.
- No shutter sound path for background capture.
- On app background/foreground, stream state is explicit: active, paused, stopped, or mic-only fallback.

- [ ] **Step 4: Add targeted source/behavior assertions if needed**

If production code needs a new helper, add a unit test in `test/unit/meta_glasses_continuous_vision_test.dart` or `test/unit/meta_glasses_background_stream_contract_test.dart` that proves:
- continuous/background capture uses frame stream,
- session start count stays `1`,
- failed frame does not crash capture.

- [ ] **Step 5: Run green for this task**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
dart format --line-length 120 lib/providers/meta_wearables_provider.dart test/unit/meta_glasses_runtime_regression_test.dart
flutter test --reporter compact test/unit/meta_glasses_runtime_regression_test.dart test/unit/meta_glasses_continuous_vision_test.dart test/unit/meta_glasses_background_stream_contract_test.dart
```

Expected:
- Runtime regression test passes the no-shutter check.
- Existing continuous/background tests pass.

## Task 4: Make `videoStreamingError` Recoverable

**Files:**
- Modify: `lib/providers/meta_wearables_provider.dart`
- Modify if needed: `lib/services/devices/meta_wearables_service.dart`
- Modify if needed: native plugin if stream errors are swallowed or misclassified.

- [ ] **Step 1: State theory**

Write:

```text
Theory: `SessionError(videoStreamingError)` escapes the stream-start/frame-subscription path and leaves provider state half-started. The fix is to catch it at the session boundary, tear down only the camera stream, keep mic capture alive when possible, and expose a recoverable state with bounded retry.
```

- [ ] **Step 2: Implement bounded recovery**

In provider/service code:
- Add `int streamFailureCount`.
- Add `bool micOnlyFallback`.
- Add a method named `recoverFromVideoStreamingError`.
- Catch errors whose code/string contains `videoStreamingError`.
- Stop/clear only camera stream resources.
- Keep audio/mic capture running if already active.
- Retry camera stream at most once after a short condition-based wait.
- If retry fails, set `micOnlyFallback = true` and log `MetaGlassStreamDiag micOnlyFallback`.
- Do not loop forever.

- [ ] **Step 3: Add a real test for recovery**

Add a test in `test/unit/meta_glasses_runtime_regression_test.dart` or an existing fake-service test file. The test must prove:
- a fake `videoStreamingError` does not throw out of capture start,
- `streamFailureCount` increments,
- `micOnlyFallback` becomes true after retry exhaustion,
- capture state is not reported as full camera capture after fallback.

- [ ] **Step 4: Run green for this task**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
dart format --line-length 120 lib/providers/meta_wearables_provider.dart test/unit/meta_glasses_runtime_regression_test.dart
flutter test --reporter compact test/unit/meta_glasses_runtime_regression_test.dart test/unit/meta_glasses_session_pause_test.dart test/unit/meta_glasses_contract_behavior_test.dart
```

Expected:
- Tests pass.
- No unhandled `videoStreamingError` path remains in provider/service.

## Task 5: Fix Glasses Gesture Delivery

**Files:**
- Modify: `ios/Runner/AppDelegate.swift`
- Modify: `lib/providers/meta_wearables_provider.dart`
- Modify: `test/unit/meta_glasses_runtime_regression_test.dart`

- [ ] **Step 1: State theory**

Write:

```text
Theory: glasses gestures are transported through iOS media remote commands, but command targets are either not active, double-registered, or not backed by an active now-playing/audio session. The fix is to register target-safe remote commands during glasses capture, log every bridge boundary, and unregister on stop.
```

- [ ] **Step 2: Make AppDelegate target-safe and observable**

In `ios/Runner/AppDelegate.swift`:
- Keep method channel name `com.omi/meta_gestures`.
- Add log prefix `OmiMetaGestures`.
- Before every `addTarget`, call `removeTarget(nil)` on:
  - `playCommand`
  - `pauseCommand`
  - `togglePlayPauseCommand`
  - `nextTrackCommand`
  - `previousTrackCommand`
- On handler fire, log command name and call Dart `onGesture`.
- On stop, remove targets and log stop.
- If evidence shows commands never fire, activate the minimum now-playing/audio-session state required for remote command delivery without disrupting recording audio. Do not guess; prove from logs first.

- [ ] **Step 3: Keep Dart gesture action serialized**

In `lib/providers/meta_wearables_provider.dart`:
- Ensure `_handleGesture` logs with `MetaGlassGestureDiag`.
- Ensure gesture actions use the same serialized start/stop path as buttons.
- Ignore duplicate gesture events within a short debounce window.
- Do not let gesture stop leave the camera stream active.

- [ ] **Step 4: Run native compile check**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
./scripts/repair_flutter_spm_ios_target.sh
xcodebuild -workspace ios/Runner.xcworkspace \
  -scheme dev \
  -configuration Profile-dev \
  -destination 'generic/platform=iOS' \
  -derivedDataPath /tmp/omi4meta-dev-profile-runtime-dd \
  CODE_SIGNING_ALLOWED=NO \
  COMPILER_INDEX_STORE_ENABLE=NO \
  build
```

Expected:
- `** BUILD SUCCEEDED **`.

- [ ] **Step 5: Run green for this task**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
dart format --line-length 120 lib/providers/meta_wearables_provider.dart test/unit/meta_glasses_runtime_regression_test.dart
flutter test --reporter compact test/unit/meta_glasses_runtime_regression_test.dart test/unit/meta_glasses_contract_behavior_test.dart
```

Expected:
- Tests pass.
- Gesture contract verifies target-safe bridge and instrumentation.

## Task 6: Reinstall Normal Build on EddyPhone

**Files:**
- Build product: `build/ios/iphoneos/Runner.app`

- [ ] **Step 1: Build normal dev profile**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
DEVICE_FLUTTER=00008130-000C04D81891401C
DEVICE_CORE=2649C7E8-7E64-501B-9108-8BC6038B8C2F
BUNDLE=dev.moni11811.omi
./scripts/repair_flutter_spm_ios_target.sh
flutter build ios --profile --flavor dev -t lib/main.dart --no-pub
```

Expected:
- Build succeeds.
- `build/ios/iphoneos/Runner.app` exists.

- [ ] **Step 2: Install directly**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
DEVICE_CORE=2649C7E8-7E64-501B-9108-8BC6038B8C2F
xcrun devicectl device install app --device "$DEVICE_CORE" build/ios/iphoneos/Runner.app
xcrun devicectl device process launch --device "$DEVICE_CORE" dev.moni11811.omi
sleep 5
xcrun devicectl device info processes --device "$DEVICE_CORE" | grep -E 'Runner|dev.moni11811.omi'
```

Expected:
- Install exits `0`.
- Launch exits `0`.
- Process check shows `Runner.app/Runner`.

## Task 7: Real Glasses Acceptance Proof

**Files:**
- Create: `/tmp/omi-meta-glasses-runtime-after-fix.log`
- Modify: `docs/meta-glasses-plans/PROGRESS.md`

- [ ] **Step 1: Capture proof log**

Run:

```bash
cd /Users/Moni11811/OMI4META/app
DEVICE_CORE=2649C7E8-7E64-501B-9108-8BC6038B8C2F
xcrun devicectl device log stream --device "$DEVICE_CORE" --style compact --predicate 'process == "Runner"' \
  | tee /tmp/omi-meta-glasses-runtime-after-fix.log
```

- [ ] **Step 2: Prove no shuttered background capture**

On glasses:
- Start capture.
- Let it run for 2 minutes.
- Confirm no shutter/snapshot sound occurs.

In logs, prove:
- `MetaGlassStreamDiag` shows frame stream started once.
- Frames arrive.
- No `capturePhoto` automatic path.
- No `videoStreamingError`, or if one occurs, recovery enters bounded retry or mic-only fallback without crash.

Run:

```bash
grep -E 'MetaGlassStreamDiag|videoStreamingError|capturePhoto|frame|micOnlyFallback|crash|fatal|exception' /tmp/omi-meta-glasses-runtime-after-fix.log | tail -200
```

- [ ] **Step 3: Prove gestures work**

On glasses:
- Trigger each supported gesture once.
- Confirm app responds to configured action.

In logs, prove:
- `OmiMetaGestures` command handler fired.
- `MetaGlassGestureDiag` received Dart event.
- Provider performed the mapped action.
- Duplicate events, if present, were debounced.

Run:

```bash
grep -E 'OmiMetaGestures|MetaGlassGestureDiag|onGesture|startCapture|stopCapture|debounce' /tmp/omi-meta-glasses-runtime-after-fix.log | tail -200
```

- [ ] **Step 4: Update progress**

Append one line to `docs/meta-glasses-plans/PROGRESS.md` only after the proof checker passes:

```text
runtime — verified 2026-07-04 — stabilized Meta glasses capture/gesture runtime on EddyPhone with background video frames, recoverable videoStreamingError handling, and gesture proof logs — needs on-device check: no, `scripts/check_meta_glasses_runtime_proof.sh` passed against `/tmp/omi-meta-glasses-runtime-after-fix.log`.
```

If hardware proof cannot be completed, use this exact line instead:

```text
runtime — partial 2026-07-04 — code/tests for Meta glasses runtime stabilization are complete, but hardware proof is still needed for shutter-free frame capture and gesture delivery — needs on-device check: yes, run Task 7 on EddyPhone with glasses.
```

Current known hardware state:

```text
latest_source_gate=pass
latest_profile_build=pass
latest_install=pass
latest_launch=blocked_locked_device
previous_proof_stream-started=1
previous_proof_frame-event=1
previous_proof_frame-captured=1
previous_proof_MetaGlassGestureDiag listening-started=1
previous_proof_MetaGlassGestureDiag received=0
previous_proof_stream-start-failed=0
previous_proof_videoStreamingError=0
```

## Final Green Gate

Run all commands:

```bash
cd /Users/Moni11811/OMI4META/app
dart format --line-length 120 \
  lib/providers/meta_wearables_provider.dart \
  test/unit/meta_glasses_runtime_regression_test.dart
flutter analyze lib --no-fatal-infos --no-fatal-warnings
flutter test --reporter compact \
  test/unit/meta_glasses_runtime_regression_test.dart \
  test/unit/omi4meta_reconstruction_contract_test.dart \
  test/unit/meta_glasses_device_sanitize_test.dart \
  test/unit/meta_glasses_contract_behavior_test.dart \
  test/unit/meta_glasses_continuous_vision_test.dart \
  test/unit/meta_glasses_background_stream_contract_test.dart \
  test/unit/meta_glasses_session_pause_test.dart
./scripts/repair_flutter_spm_ios_target.sh
xcodebuild -workspace ios/Runner.xcworkspace \
  -scheme dev \
  -configuration Profile-dev \
  -destination 'generic/platform=iOS' \
  -derivedDataPath /tmp/omi4meta-dev-profile-runtime-dd \
  CODE_SIGNING_ALLOWED=NO \
  COMPILER_INDEX_STORE_ENABLE=NO \
  build
```

Expected:
- `flutter analyze` exits `0` with no errors. Existing warnings are acceptable only with `--no-fatal-warnings`.
- All listed tests pass.
- Xcode build reaches `** BUILD SUCCEEDED **`.
- Final EddyPhone install is normal dev profile, no `--dart-define`.

## Final Response Required From Claude

Reply with only:
- theory proven,
- files changed,
- tests run and exact pass/fail,
- EddyPhone install result,
- real glasses proof result,
- remaining bugs, if any.

Do not claim fixed unless Task 7 proof exists.
