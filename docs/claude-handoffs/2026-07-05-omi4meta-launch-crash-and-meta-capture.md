# Claude Handoff: OMI4META Launch Crash + Meta Capture Stabilization

Date: 2026-07-05
Workspace: `/Users/Moni11811/OMI4META`
App workspace: `/Users/Moni11811/OMI4META/app`
Device: EddyPhone
CoreDevice id: `2649C7E8-7E64-501B-9108-8BC6038B8C2F`
Flutter device id: `00008130-000C04D81891401C`
Bundle: `dev.moni11811.omi`

## User Constraints

- Theory before patch.
- Write failing regression first.
- Do not ship next build until previous symptom has red regression.
- Keep phone mic/audio out of glasses capture path.
- Capture should be through glasses DAT video frames.
- Gestures must be honest: no fake tap/swipe claims.

## Current Goal

Stop launch crash on EddyPhone after Meta glasses runtime/capture changes.

Status: source fixes and build are done. Real launch proof is not done because EddyPhone became locked. Do not claim fixed until unlocked foreground launch is verified.

## Launch Crash Investigation

### Symptom 1

`devicectl process launch` returned success, but Omi did not foreground.

Fresh console launch showed:

```text
The app terminated with the exit code 0.
Application failed to launch: UIScene life cycle is required for apps built with this SDK.
```

Theory: iOS 27 SDK requires UIScene. App had no scene manifest or SceneDelegate.

Red regression added first:

```text
test/unit/ios_launch_regression_test.dart
Runner adopts UIScene lifecycle required by current iOS SDKs
```

Patch:

- Added `ios/Runner/SceneDelegate.swift`.
- Added `UIApplicationSceneManifest` to `ios/Runner/Info.plist`.
- Added `SceneDelegate.swift` to `ios/Runner.xcodeproj/project.pbxproj`.
- SceneDelegate extends `FlutterSceneDelegate`.
- SceneDelegate forwards `openURLContexts` to existing `AppDelegate.application(_:open:options:)`, preserving Meta DAT and auth deep links.

### Symptom 2

After UIScene patch, exact app-path console launch reached Dart VM, then died:

```text
App terminated due to signal 5.
flutter: The Dart VM service is listening...
[Firebase/Crashlytics] Version 11.10.0
[Assert] -[UIApplication statusBarOrientation] API has been deprecated and is a no-op on 27.0 and later.
```

Theory: FirebaseCrashlytics 11.10 pod calls deprecated `UIApplication.statusBarOrientation`; iOS 27 traps.

Red regression added first:

```text
test/unit/ios_launch_regression_test.dart
Crashlytics orientation logging avoids deprecated statusBarOrientation trap
```

Patch:

- Patched `ios/Pods/FirebaseCrashlytics/.../FIRCLSNotificationManager.m`.
- Added `FIRCLSSafeStatusBarOrientation()`.
- Uses `UIApplication.connectedScenes` and `UIWindowScene.interfaceOrientation`.
- Removed direct `[FIRCLSApplicationSharedInstance() statusBarOrientation]`.
- Added persistent CocoaPods post-install patch in `ios/Podfile`:
  - `patch_firebase_crashlytics_status_bar_orientation(installer)`

Build initially failed because `FIRCLSApplicationSharedInstance()` is `id`.

Fix:

```objc
UIApplication *application = (UIApplication *)FIRCLSApplicationSharedInstance();
for (UIScene *scene in application.connectedScenes) { ... }
```

### Symptom 3

AppDelegate launch path had multiple force unwrap crash risks before Dart error handling:

- `controller!.binaryMessenger`
- `session!`
- `registrar(forPlugin: "OmiPhoneCallsPlugin")!`

Red regression added first:

```text
test/unit/ios_launch_regression_test.dart
AppDelegate launch path does not force unwrap native launch dependencies
```

Patch:

- `ios/Runner/AppDelegate.swift`
- Guard missing `FlutterViewController`.
- Use `controller.binaryMessenger`, not `controller!`.
- Unwrap `WCSession` safely.
- Register `OmiPhoneCallsPlugin` only if registrar exists.
- Added `[OmiLaunch]` logs for skipped native channels.

## Meta Capture Work Already In This Session

Do not revert.

Key files:

- `lib/providers/meta_wearables_provider.dart`
- `test/unit/meta_glasses_runtime_regression_test.dart`
- `test/unit/meta_glasses_watchdog_test.dart`

Implemented before launch crash work:

- No still-photo shutter loop for background glasses capture.
- Use DAT video frame stream.
- `startCapture` only enters active capture after first queued frame.
- Stream generation guard drops stale frames.
- Failed start/recovery disables background streaming.
- Capture watchdog uses stream-frame liveness independent of capture frequency.
- Capture frequency no longer delays dead-stream recovery.
- No phone mic or listen websocket for glasses capture.
- Fake media-command gesture support removed/kept unsupported.

## Verification Already Run

Source/tests:

```text
flutter test test/unit/ios_launch_regression_test.dart -r compact
PASS: 3/3

flutter test test/unit/meta_glasses_runtime_regression_test.dart -r compact
PASS: 20/20

flutter test test/unit/meta_glasses_watchdog_test.dart -r compact
PASS: 13/13

flutter analyze lib/providers/meta_wearables_provider.dart lib/pages/meta_wearables/meta_glasses_page.dart test/unit/ios_launch_regression_test.dart
PASS: No issues found

plutil -lint ios/Runner/Info.plist
PASS: OK
```

Build:

```text
export DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer
flutter build ios --profile --flavor dev
PASS: Built build/ios/iphoneos/Runner.app (177.0MB)
```

Install:

```text
xcrun devicectl device uninstall app --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F dev.moni11811.omi
PASS: App uninstalled.

xcrun devicectl device install app --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F build/ios/iphoneos/Runner.app
PASS: App installed.
Installed path: /private/var/containers/Bundle/Application/39CB3224-271B-4DDD-BB04-411E7C8EDD62/Runner.app
```

## Blocker / Current Device State

Foreground launch proof blocked by locked EddyPhone.

Latest launch command failed with:

```text
The request was denied by service delegate (SBMainWorkspace) for reason: Locked
Unable to launch dev.moni11811.omi because the device was not, or could not be, unlocked.
```

Important: before uninstall/reinstall, SpringBoard/Live Activity state kept launching old stale path:

```text
/private/var/containers/Bundle/Application/1F689073-.../Runner.app/Runner
```

After uninstall/reinstall, app database showed fresh path:

```text
/private/var/containers/Bundle/Application/39CB3224-271B-4DDD-BB04-411E7C8EDD62/Runner.app
```

But stale `ClLiveActivityExtension` from old path may still reappear. Kill stale Runner/extension PIDs before launch proof.

## Next Claude Steps

1. Make sure EddyPhone is unlocked.
2. Kill stale Runner/Live Activity extension only:

```bash
xcrun devicectl device info processes --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F
xcrun devicectl device process terminate --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F --pid <Runner-or-ClLiveActivityExtension-pid> --kill
```

3. Launch installed app by bundle id:

```bash
xcrun devicectl device process launch --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F --activate dev.moni11811.omi
```

4. If it exits, launch exact installed path with console:

```bash
xcrun devicectl device process launch --console --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F --environment-variables '{"OS_ACTIVITY_DT_MODE":"YES"}' /private/var/containers/Bundle/Application/39CB3224-271B-4DDD-BB04-411E7C8EDD62/Runner.app
```

5. If a new crash appears, write red regression before patch.
6. If app foregrounds, screenshot and process proof:

```bash
xcrun devicectl device info processes --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F
xcrun devicectl device capture screenshot --device 2649C7E8-7E64-501B-9108-8BC6038B8C2F --destination /tmp/omi4meta-launch-proof.png
```

7. Then test Meta capture on glasses.

## Do Not Repeat

- Do not claim gestures are fixed. Hardware gesture evidence still missing.
- Do not use phone mic/listen socket for glasses capture.
- Do not treat build/install as launch proof.
- Do not trust bundle launch if process path shows old `1F689073...`.
- Do not patch capture again until current launch crash is actually proven past.
