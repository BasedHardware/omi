## What

Skipping or denying a permission during onboarding is now a durable **off** for that capability's automatic path. Launch, app reactivation, key load, settings sync, wake, session rotations, and post-onboarding starts no longer raise a macOS permission sheet (or steal focus into System Settings) for a permission the user chose not to grant. Closes #12695. Closes SCA-440.

## Why (the reported loop)

"Skip for now" on the mic step only advanced the flow. `transcriptionEnabled`'s successor (`audioRecordingMode`) stayed on its `onlyMeetings` default, `restorePersistedCaptureServices` ran on launch, `didBecomeActive`, key load, and settings sync, and `AppState.startTranscription()` answered a missing mic grant with `requestMicrophonePermission()` — `NSApp.activate()` + `AVCaptureDevice.requestAccess`. Skip leaves TCC `.notDetermined`, so every restore re-armed the system sheet; dismissing it reactivated the app and the cycle repeated. The same unguarded request lived in `PushToTalkManager.startAudioTranscription` and `ChatToolExecutor.requestMicrophonePermissionDirectly()`.

## Changes

- **Shared policy** — `MicrophoneCaptureAuthorizationPolicy.action(for:userInitiated:)`: a non-`proceed` status on an automatic start resolves to a new `.abandonAutomaticStart` instead of requesting or alerting. One rule, testable without a TCC database.
- **Mic** — `answerMic()` skip writes `audioRecordingMode = .off` (Allow undoes an earlier skip); `startTranscription(userInitiated:)` gates the request on initiation; `PersistedCaptureLaunchPolicy.shouldStartTranscription` now requires a live-answered mic grant so `DesktopHomeView.restorePersistedCaptureServices` never even attempts the start; automatic call sites (wake, mode-change observer, 4h/STT rotations, preferred-mic reconnect, both onboarding completions) pass `userInitiated: false`. The Settings audio-recording switcher requests permission explicitly on enable, matching `CaptureListeningLogic.cycleListening`.
- **Screen** — `answerScreen()` records the user's answer as the standing `screenAnalysisEnabled` intent; `SBOnboardingModel.complete()` no longer force-enables it after a skip (`screenAnalysisIntentAtCompletion` seam) and only calls `startMonitoring` when the grant exists.
- **Sidebar skip ≠ denied** — `SBOnboardingPermissionIntentPolicy`: screen-denied now requires the capture intent on (skip turns it off); accessibility records a durable onboarding skip marker (`onboardingAccessibilitySkipped`) so a deliberate skip stops pulsing as denied. Mic and notifications already read the real TCC answer (notifications startup auto-prompt was already fixed at `startMonitoring` — verified, not regressed).
- **Full Disk Access** — automatic indexer paths (`scheduleInitialFileIndexing` backfill and the 3-hour rescan) probe FDA and drop `Documents`/`Desktop`/`Downloads` from scan roots when it is missing (`FileIndexScanPolicy.automaticScanRoots`), so a background scan can never throw a per-folder consent sheet. Explicit Settings "Rescan files" keeps the full root set.
- **Chat + PTT** — `request_permission` for microphone/notifications checks the current status first: a denied grant is reported honestly (no dead `requestAccess` call, no forced System Settings jump); settings panes open only when the user just declined a fresh sheet. PTT finishes the turn with `.permissionDenied` instead of re-running the no-op request on every press.

## Tests

New `SBOnboardingSkipPermissionIntentTests` (skip mic ⇒ mode off + restore policy refuses; allow-after-skip restores; skip screen ⇒ intent off; allow ⇒ on; completion seam never forces on for a skipped grant; AX skip marker set/cleared; sidebar projections), plus new policy cases in `MicrophoneCaptureAuthorizationPolicyTests` (automatic never requests/surfaces), `PersistedCaptureLaunchPolicyTests` (restore refuses without authorization), and `FileIndexScanPolicyTests` (automatic roots without FDA exclude the TCC-protected folders; with FDA they match standard roots).

Commands run (all green):
- `xcrun swift build -c debug --package-path Desktop`
- `xcrun swift test --package-path Desktop --filter "PersistedCaptureLaunchPolicyTests|MicrophoneCaptureAuthorizationPolicyTests|SBOnboardingSkipPermissionIntentTests|FileIndexScanPolicyTests|SBOnboardingStepTelemetryTests|SBOnboardingPermissionFlowTests|OnboardingPermissionToolTests|FileIndexerServiceTests|SettingsSyncCaptureRestorationTests|ShellListeningCycleTests|PTTWarmMicKeepAliveTests"`

Not exercised live: no named-bundle run of the onboarding flow this session (the changed paths are policy seams covered by the suites above; a live TCC exercise would need interactive consent dialogs).

## Failure-Class

Failure-Class: FC-privileged-consent-resampled-on-timer

## Invariants

`scripts/pr-preflight --suggest` reports no affected product invariants for this diff.
