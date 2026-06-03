# Desktop: Meeting-Gated System Audio Capture — Design

**Date:** 2026-06-03
**Component:** Omi macOS desktop app (Swift)
**Branch:** `feat/desktop-meeting-gated-system-audio`
**Status:** Approved (design decisions confirmed); ready for implementation planning

## 1. Summary

Give desktop users a setting that controls **when** system audio (audio from other
apps — Zoom, Meet, music, etc.) is captured during a recording. Today system audio is
captured for the entire duration of every recording (when available). This feature adds a
**tri-state mode**:

- **Always** (default — unchanged behavior): capture system audio for the whole recording.
- **Only during meetings**: capture system audio only while a conferencing call is detected,
  starting/stopping the system-audio tap dynamically within a recording.
- **Never**: never capture system audio (surfaces today's hidden `disableSystemAudioCapture`
  debug flag as a visible option).

The microphone is always captured while recording; only the **system-audio tap** is gated.

## 2. Goal & non-goals

**Goal:** Let privacy-conscious users avoid capturing background app audio (and the
performance cost of the Core Audio tap) except when they're actually in a call, without
having to manually toggle anything.

**Non-goals (this spec):**
- No backend changes. The mixed audio wire format sent to `/v4/listen` is unchanged; this
  only changes *whether* system-audio samples are present at a given moment.
- No new permissions are required. Meeting detection uses signals the app already reads.
- No microphone-side changes. Mic capture is untouched.
- Not building general "meeting state" infrastructure for other features (focus, tasks, etc.).

## 3. Background — current behavior (verified)

- System audio is captured by `SystemAudioCaptureService` (Core Audio process taps, macOS
  14.4+): `desktop/Desktop/Sources/SystemAudioCaptureService.swift`.
  - `startCapture(onAudioChunk:onAudioLevel:) async throws` and `stopCapture()` both guard
    re-entrancy (`guard !isCapturing` / `guard isCapturing`) and serialize all HAL work on a
    private serial `audioQueue`. Re-calling start after stop rebuilds the tap/aggregate device.
    → **Dynamic start/stop on a single instance is safe** (serial queue preserves teardown→setup
    ordering). Exposes `var capturing: Bool`.
- Capture lifecycle lives in `AppState`
  (`desktop/Desktop/Sources/AppState.swift`):
  - Property `systemAudioCaptureService: Any?` (line ~328), `audioMixer: AudioMixer?` (~329).
  - `startTranscription()` (~1420) creates the service at ~1499–1509, gated only by the hidden
    UserDefault `disableSystemAudioCapture` and `#available(macOS 14.4, *)`.
  - `startMicrophoneAudioCapture()` (~1631) starts mic, then **unconditionally** starts system
    audio at ~1674–1698 (the inline `systemService.startCapture(...)` closures).
  - `stopAudioCapture()` (~2142) stops system audio at ~2158–2163, then mic, mixer, transcription.
- **Two STT sinks** depending on hardware:
  - Apple Silicon default (`useLocalSTT == true`): mic → `localMicService`, system →
    `localSystemService` (separate on-device Parakeet instances, **not** the mixer).
  - Cloud / Intel: mic + system → `AudioMixer` → `/v4/listen` WebSocket.
  - Gating at the `SystemAudioCaptureService` level is **sink-agnostic** — when system capture
    stops, the relevant sink simply stops receiving system samples.
- `AudioMixer` (`AudioMixer.swift`) already tolerates one source stalling: after
  `sourceTimeout = 2.0s` with no system data it switches to mic-only (pads silence) and logs
  "System audio source stalled"; it auto-recovers and logs "recovered" when samples resume. So
  starting/stopping system audio mid-recording degrades gracefully in cloud mode with no special
  handling. In local mode, `localSystemService` simply receives a gap of silence.
- Meeting-detection building blocks already exist in
  `ProactiveAssistants/ProactiveAssistantsPlugin.swift` (today used only to throttle screen
  capture):
  - `static let videoCallApps: Set<String>` (~86): `Microsoft Teams, zoom.us, FaceTime, Webex,
    Cisco Webex Meetings, GoTo Meeting, GoToMeeting`.
  - `static let browserApps: Set<String>` (~131) and `static let videoCallBrowserKeywords:
    [String]` (~124: `Google Meet, meet.google.com, Teams - Microsoft`).
  - `isVideoCallApp(appName:windowTitle:)` (~1328): native app match OR browser app + title keyword.
  - `WindowMonitor` (`ProactiveAssistants/Core/WindowMonitor.swift`) wraps
    `NSWorkspace.didActivateApplicationNotification` and exposes static window-info lookups.
- Settings pattern: `AssistantSettings` singleton (`ProactiveAssistants/Services/AssistantSettings.swift`)
  owns UserDefaults-backed properties (register defaults in `init`, getter/setter posts a
  `NotificationCenter` change notification). UI lives in `MainWindow/Pages/SettingsPage.swift`
  (`@State` + `Toggle`/`Picker` + handler) and must be registered for search in
  `MainWindow/SettingsSidebar.swift`. **The desktop app has no localization** — strings are
  hardcoded Swift (the ARB/l10n rule in AGENTS.md is Flutter-only).

## 4. Approved decisions

1. **Meeting signal:** conferencing app in a call — reuse the existing `videoCallApps` /
   browser-keyword detection. No calendar, no audio-content VAD (the latter would require the
   tap to be running to detect, defeating the purpose).
2. **Setting shape:** tri-state picker **Always / Only during meetings / Never**; default
   **Always** (current behavior preserved). Absorbs the hidden `disableSystemAudioCapture` flag.
3. **Gating timing:** dynamic during recording — start/stop the tap live as calls begin/end.

## 5. Architecture

```
                         AssistantSettings.systemAudioCaptureMode  (UserDefaults)
                                          │  (.transcriptionSettingsDidChange)
                                          ▼
   MeetingDetector ── isMeetingActive ─► AppState.reconcileSystemAudio()
   (poll + NSWorkspace events)                   │
        │ uses                                    ├─ start ─► SystemAudioCaptureService.startCapture()
        ▼                                         └─ stop  ─► SystemAudioCaptureService.stopCapture()
   ConferencingApps (shared catalog)                          │ onAudioChunk
                                                              ▼
                                                  AudioMixer / localSystemService (unchanged)
```

Four units, each independently understandable and testable:

### 5a. `ConferencingApps` (shared catalog) — new

`desktop/Desktop/Sources/ConferencingApps.swift`

Single source of truth for "what is a conferencing app / call window." Houses the constants
currently private to `ProactiveAssistantsPlugin` so both the plugin and the new detector share them.

```swift
enum ConferencingApps {
    static let nativeCallApps: Set<String>      // = today's videoCallApps
    static let browserApps: Set<String>
    static let browserCallKeywords: [String]    // = today's videoCallBrowserKeywords

    /// True if a single window (owner app + optional title) indicates a call.
    /// Native call app  -> true (owner name alone; no title/permission needed).
    /// Browser app      -> true iff title contains a call keyword (title needs Screen Recording).
    static func isCallWindow(ownerName: String?, title: String?) -> Bool

    /// Scan all on-screen windows; true if any is a call window.
    /// Uses CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID).
    static func isMeetingActiveNow() -> Bool
}
```

`isCallWindow` is exactly the existing `isVideoCallApp` semantic, factored out.
`ProactiveAssistantsPlugin` is refactored to reference `ConferencingApps.*` and to implement
`isVideoCallApp` by delegating to `ConferencingApps.isCallWindow` — a small, behavior-preserving
de-duplication (the only change to existing code outside AppState/Settings).

**Detection rule (v1):** a meeting is "active" if any on-screen window is a call window.
- Native call apps are matched by owner name (available **without** Screen Recording permission).
- Browser-based calls (Google Meet, Teams web) are matched by window title, which requires
  Screen Recording permission (already granted for Rewind in the common case). Without it,
  native calls are still detected; browser calls degrade to undetected. This degradation is
  logged once and documented in the setting's caption.

Scanning *all* on-screen windows (not just the frontmost, as the existing plugin does) is
intentional: you stay "in a meeting" while taking notes in another app with the call window behind it.

Known limitation (documented, accepted for v1): a native call app left running but idle counts as
"active." Mitigated by the off-grace period (§5b) and the reality that users typically quit these
apps. Per-app in-call window-title signatures and mic-in-use detection are explicit future work
(§10), kept out of v1 to avoid fragile per-app tables.

### 5b. `MeetingDetector` — new

`desktop/Desktop/Sources/MeetingDetector.swift`, `@MainActor`.

Owns the live meeting-active signal. Runs **only** while a recording is active in
"Only during meetings" mode (so there is zero overhead otherwise).

```swift
@MainActor
final class MeetingDetector {
    private(set) var isMeetingActive: Bool
    init(pollInterval: TimeInterval = 4.0,
         offGracePeriod: TimeInterval = 8.0,
         isMeetingNow: @escaping () -> Bool = { ConferencingApps.isMeetingActiveNow() },
         onChange: @escaping (Bool) -> Void)
    func start()   // begin observing + polling; emits initial state
    func stop()    // remove observers, invalidate timer
}
```

- **Triggers:** a repeating `Timer` (`pollInterval`, default 4s) **plus** `NSWorkspace`
  `didActivate` / `didLaunchApplication` / `didTerminateApplication` notifications for
  responsiveness when apps open/close/switch. Browser tab-title changes — e.g. joining a Google Meet in an already-foreground tab — fire no `NSWorkspace` event, so meeting-on can lag up to `pollInterval` (~4s); acceptable for v1.
- **Hysteresis:** transitions **on** immediately; transitions **off** only after `offGracePeriod`
  (default 8s) of sustained "no meeting", to avoid flapping when a call window briefly disappears
  (screen share popups, window focus changes). Implemented with a pending-off timestamp checked on
  each evaluation.
- `onChange` fires only on actual edges. Injectable `isMeetingNow`/clock-free timer make it unit-
  testable without real apps (drive `evaluate()` directly in tests).

### 5c. `AssistantSettings.systemAudioCaptureMode` — extend existing

Add to `AssistantSettings`:

```swift
enum SystemAudioCaptureMode: String { case always, onlyDuringMeetings, never }

var systemAudioCaptureMode: SystemAudioCaptureMode { get set }   // key "systemAudioCaptureMode", default .always
```

- Getter reads the string key (default `.always`); setter writes it and posts
  `.transcriptionSettingsDidChange` — the existing notification `AssistantSettings` already posts
  on recording-setting changes. Note: this notification currently has **no** `AppState` observer;
  §5d adds one. (It is posted from `AssistantSettings` but observed nowhere today.)
- **Migration / back-compat:** the existing hidden `disableSystemAudioCapture` debug flag is
  preserved as an override. Effective mode is computed in AppState (§5d), not stored:
  `effectiveSystemAudioMode = disableSystemAudioCapture ? .never : systemAudioCaptureMode`.
  This keeps `defaults write … disableSystemAudioCapture` working and means existing users with
  that flag set keep getting no system audio.
- Add `systemAudioCaptureModeKey` to `register(defaults:)` and reset it in `resetToDefaults()`.

### 5d. `AppState` integration — modify existing

Replace the unconditional system-audio start with a reconciler, and add observers.

**New/changed members:**
- `private var meetingDetector: MeetingDetector?`
- `private var systemAudioGateInFlight = false` and `private var systemAudioReconcilePending = false`
  (coalesce overlapping async start/stop).
- `private var effectiveSystemAudioMode: AssistantSettings.SystemAudioCaptureMode` (computed; see §5c).

**`startTranscription()` (~1496–1509):** create `systemAudioCaptureService` when
`effectiveSystemAudioMode != .never` and `#available(macOS 14.4, *)` (i.e. for both `.always` and
`.onlyDuringMeetings`). Log the chosen mode.

**`startMicrophoneAudioCapture()` (~1674–1698):** remove the inline unconditional
`systemService.startCapture(...)`. After mic capture is up, call `await reconcileSystemAudio()`.
Factor the system-audio start wiring into:

```swift
@available(macOS 14.4, *)
private func startSystemAudioCaptureIfNeeded() async   // calls systemService.startCapture with the
                                                       // existing onAudioChunk/onAudioLevel closures
```

(closures identical to today's lines 1677–1689: route to `localSystemService` in local mode or
`audioMixer?.setSystemAudio` in cloud mode; `AudioLevelMonitor.shared.updateSystemLevel`.)

**`reconcileSystemAudio()` — new, `@MainActor`, the state machine:**

```
guard isTranscribing else { return }
guard #available(macOS 14.4, *), let service = systemAudioCaptureService as SystemAudioCaptureService
      else { meetingDetector?.stop(); meetingDetector = nil; return }
if systemAudioGateInFlight { systemAudioReconcilePending = true; return }   // coalesce

switch effectiveSystemAudioMode {
  case .never:
      meetingDetector?.stop(); meetingDetector = nil
      if service.capturing { service.stopCapture() }
  case .always:
      meetingDetector?.stop(); meetingDetector = nil
      if !service.capturing { gate { await startSystemAudioCaptureIfNeeded() } }
  case .onlyDuringMeetings:
      if meetingDetector == nil {
          meetingDetector = MeetingDetector(onChange: { [weak self] _ in
              Task { @MainActor in self?.reconcileSystemAudio() } })
          meetingDetector!.start()
      }
      let want = meetingDetector!.isMeetingActive
      if want && !service.capturing { gate { await startSystemAudioCaptureIfNeeded() } }
      if !want && service.capturing { service.stopCapture() }
}
```

`gate { … }` sets `systemAudioGateInFlight = true`, runs the async work in a `Task`, then clears
the flag and, if `systemAudioReconcilePending`, clears it and re-runs `reconcileSystemAudio()` to
converge (handles state that changed mid-start).

**Settings-change observer:** in AppState's notification setup, observe
`.transcriptionSettingsDidChange` → `reconcileSystemAudio()` (covers the user changing the mode
mid-recording: Always↔OnlyDuringMeetings↔Never all converge correctly, including creating the
service lazily if it didn't exist — see edge cases §6).

**`stopAudioCapture()` (~2157–2163):** before stopping the service, `meetingDetector?.stop();
meetingDetector = nil`. Existing `systemService.stopCapture()` + `systemAudioCaptureService = nil`
stay.

### 5e. Settings UI — modify existing

In `SettingsPage.swift`, in the **General** section near the existing Audio Recording controls,
add (only shown on `#available(macOS 14.4, *)`):

- A labeled control **"System audio"** using a `Picker` (menu style) bound to a new
  `@State private var systemAudioCaptureMode` initialized from
  `AssistantSettings.shared.systemAudioCaptureMode`, with a handler that writes the setting.
  Options: "Always", "Only during meetings", "Never".
- A caption under it: *"When set to Only during meetings, Omi captures other apps' audio only
  while a call app like Zoom, Google Meet, or Teams is active."* (Plus a one-line note that
  browser-based call detection needs Screen Recording permission.)
- Disable the control (or show "Requires macOS 14.4+") when system audio is unavailable.

Register a `SettingsSearchItem` in `SettingsSidebar.swift` (keywords: "system audio, meeting,
zoom, call, capture, recording") pointing at the General section so it's discoverable via search.

Persisting the setting posts `.transcriptionSettingsDidChange`; AppState's observer applies it
live if a recording is in progress.

## 6. Edge cases & error handling

- **macOS < 14.4:** `SystemAudioCaptureService` unavailable → service never created; reconciler
  no-ops; UI control hidden/disabled. No behavior change vs today.
- **Mode change mid-recording:**
  - Always→OnlyDuringMeetings: stop tap if currently on and no meeting; start detector.
  - OnlyDuringMeetings→Always: stop detector; ensure tap on.
  - →Never: stop detector + tap.
  - Never→(Always|OnlyDuringMeetings) mid-recording: service may be `nil` (not created at start).
    Reconciler must lazily create it: if `service == nil && effectiveMode != .never && 14.4`,
    create `SystemAudioCaptureService()` before gating. (Add this guard to the reconciler.)
- **Tap start failure:** already non-fatal (caught in `startSystemAudioCaptureIfNeeded`); mic-only
  continues. In OnlyDuringMeetings mode the next meeting edge retries naturally.
- **Rapid call open/close (flapping):** off-grace hysteresis (§5b) + the in-flight/pending
  coalescing (§5d) prevent thrashing the HAL.
- **Concurrent start/stop:** `systemAudioGateInFlight` serializes; `…ReconcilePending` ensures the
  final desired state is applied after an in-flight start completes.
- **Screen Recording permission absent:** native-app calls still detected; browser calls not. The
  caption documents this; no crash, no error dialog.
- **BLE (wearable) source:** system audio only applies to the microphone source path
  (`startMicrophoneAudioCapture`); BLE path unaffected (it never used system audio).
- **App sleep/wake & 4-hour restart:** these go through `stopAudioCapture()` →
  `startTranscription()`, which rebuilds the service + detector from the current mode. No special
  handling needed.

## 7. Performance & privacy

- "Only during meetings" reduces the Core Audio tap's lifetime to actual calls, lowering CPU and
  avoiding capturing incidental audio (music, videos) — the privacy/perf win the feature exists for.
- `MeetingDetector` polls `CGWindowListCopyWindowInfo` every 4s only while recording in that mode;
  the proactive plugin already calls equivalent APIs, so the added cost is negligible.
- No new entitlements/permissions. No new data leaves the device; the wire format is unchanged.

## 8. Testing plan

**Unit (Swift, where feasible):**
- `ConferencingApps.isCallWindow` truth table: native app (no title), browser app + keyword,
  browser app without keyword, unknown app, nil owner.
- `MeetingDetector` edges via injected `isMeetingNow` + manual `evaluate()`: off→on immediate;
  on→off only after grace period; no spurious `onChange` when state is stable.
- `AssistantSettings.systemAudioCaptureMode` persistence + `disableSystemAudioCapture` override →
  `effectiveSystemAudioMode`.

**Local end-to-end (named bundle, per AGENTS.md):**
1. `OMI_APP_NAME="omi-mtg-sysaudio" ./run.sh`; seed auth; `omi-ctl wait-ready`.
2. Settings → General: verify the "System audio" picker appears with three options; default Always.
3. Set **Only during meetings**. Start a recording. With no call app open, confirm logs show the
   system tap is **not** started ("System audio gated: no meeting"). Open a real call (e.g. a
   Google Meet tab or Zoom test meeting `zoom.us/test`) and confirm the tap starts ("System audio
   capture started (meeting detected)") and `AudioLevelMonitor` system level moves; end the call
   and confirm the tap stops after the grace period.
4. Set **Always**: confirm the tap starts immediately with recording (today's behavior).
5. Set **Never**: confirm the tap never starts.
6. Toggle the mode **mid-recording** through all three and confirm the reconciler converges (logs).
7. Evidence: `agent-swift screenshot` of the setting; log excerpts for each transition.

Verification is via the in-process automation bridge + logs (`/private/tmp/omi-dev.log`) and
`agent-swift`, not just a compile.

## 9. Files touched

- **New:** `desktop/Desktop/Sources/ConferencingApps.swift`
- **New:** `desktop/Desktop/Sources/MeetingDetector.swift`
- **Modify:** `desktop/Desktop/Sources/ProactiveAssistants/Services/AssistantSettings.swift`
  (add `SystemAudioCaptureMode` + property + default + reset)
- **Modify:** `desktop/Desktop/Sources/AppState.swift` (reconciler, observers, lazy create,
  factor `startSystemAudioCaptureIfNeeded`, detector lifecycle)
- **Modify:** `desktop/Desktop/Sources/ProactiveAssistants/ProactiveAssistantsPlugin.swift`
  (reference `ConferencingApps`; behavior-preserving)
- **Modify:** `desktop/Desktop/Sources/MainWindow/Pages/SettingsPage.swift` (picker + caption + handler)
- **Modify:** `desktop/Desktop/Sources/MainWindow/SettingsSidebar.swift` (search entry)
- **Modify:** `desktop/CHANGELOG.json` (`unreleased`: user-facing one-liner)

No backend (Python or Rust) changes. No Mintlify/listen_pusher_pipeline doc changes (wire
format and conversation lifecycle unchanged).

## 10. Out of scope / future work (YAGNI)

- Per-app in-call window-title signatures (distinguish "Zoom open" vs "Zoom in a call") and
  microphone-in-use detection for higher precision.
- Calendar-aware suppression/confirmation of meetings.
- A live in-app indicator ("System audio: waiting for a meeting"); v1 relies on the existing
  system-audio level indicator (silent when gated off) + the settings caption.
- Slack huddles / Discord voice / other voice channels in the catalog (easy to add later).
- Per-meeting analytics beyond a single mode-change event.
