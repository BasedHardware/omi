# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.7.1

Documentation-only release: README and getting-started guides now show
`^0.7.0` (the install snippet in the 0.7.0 pub publish still said
`^0.2.0` because docs were updated on GitHub after that upload).

## 0.7.0

Aligns the plugin version with Meta's native DAT SDKs and adds **Display
Access**.

### Display Access (new)

- Bridge Meta DAT 0.7.0's `MWDATDisplay` (iOS) / `mwdat-display`
  (Android) module: render a declarative UI tree on Ray-Ban Display
  glasses.
- New Dart API: `startDisplaySession({deviceUUID?})`,
  `sendDisplayView(DisplayView)`, `stopDisplaySession()`, and
  `displayStateStream()` (`DisplayState`:
  `starting/started/stopping/stopped`).
- Component DSL with `toJson` serialization and callback ids: `FlexBox`,
  `DisplayText`, `DisplayImage`, `DisplayButton`, `DisplayIcon`,
  `VideoPlayer`, plus layout / style enums and `onTap` / `onClick` /
  `onPlaybackEvent` callbacks dispatched over a new `display_events`
  EventChannel. Display lifecycle is reported on a new `display_state`
  EventChannel.
- Native `MetaDisplayManager` on both platforms rebuilds the SDK DSL from
  JSON and routes interaction + playback callbacks back to Dart by id.
- New sample app `samples/display_access/` porting Meta's official "Car
  Maintenance" Display sample (list → detail → steps → video).
- New `doc/display_access.md`, `display-access` skill, and Cursor rule
  entries.

### SDK bump

- Update native pins `0.6.0 → 0.7.0` (iOS SPM `meta-wearables-dat-ios`
  + `MWDATDisplay`; Android Maven `mwdat-*` + `mwdat-display`).
- Adapt the camera bridge to 0.7 renames (`Stream` /
  `StreamConfiguration` / `StreamState`) with resilient,
  string-based state/error encoding.
- Add `DeviceSessionError.datAppOnTheGlassesUpdateRequired`
  (`error.isDatAppUpdateRequired`).

## 0.2.0

### Android live preview — correct colours

- Rewrite `YuvToArgb` to mirror the official Meta DAT Android sample's
  `YuvToBitmapConverter`: tightly-packed I420 only (no layout sniffing)
  with BT.709 limited-range coefficients. The previous BT.601 matrix
  produced a green/purple cast on real glasses frames; BT.709 matches
  the codec's advertised `raw.color.matrix = 1`.
- Cache the YUV byte buffer and ARGB int buffer across frames in
  `YuvToArgb` so the hot path is allocation-free. Eliminates ~150 MiB/s
  of GC pressure on a 720p stream and stops mid-stream frame stalls.
- **Fix the "wrong-colour / squashed preview" bug**: call
  `SurfaceTexture.setDefaultBufferSize(width, height)` the first time
  we see a frame (or whenever the resolution changes). Without this
  the canvas returned by `Surface.lockHardwareCanvas()` was sized to
  Flutter's default 1×1 producer buffer and the scale-fit was clamping
  the bitmap into a tiny destination — the preview looked like a flat
  one-colour image even when YUV decode was correct.

### Android session reliability

- Replace `AutoDeviceSelector` with `SpecificDeviceSelector` driven by
  the paired device UUID (matches the iOS path). Resolves
  `SESSION_ERROR: No eligible device found` on the first start when
  Meta AI has just released the device.
- Add an in-process retry loop around `Wearables.createSession` (6
  attempts × 1.5 s) for the transient warm-up failures the underlying
  SDK throws while the glasses transition from `AVAILABLE` to
  `ELIGIBLE_FOR_DAT`.
- Make `AndroidManifest.xml` Developer-Mode-ready in both bundled
  apps: `APPLICATION_ID = "0"`, `CLIENT_TOKEN = "0"`,
  `ANALYTICS_OPT_OUT = "true"`, `DAM_ENABLED = "true"`.

### Sample app

- `samples/camera_access` now fetches the paired device UUID before
  calling `startStreamSession` and shows a "Connecting…" spinner on
  the **Start** button while the retry loop is in flight, so the user
  knows the first tap is doing something. The button is disabled
  during the warm-up window.

### Diagnostics

- Add per-frame Y / chroma min/mean/max diagnostics to `logcat` for
  the first 10 frames of a stream and a 1 Hz heartbeat afterwards.
  Flat Y → SDK is streaming placeholders (glasses not worn). Flat
  chroma + varying Y → real monochrome scene. Catches root-cause
  questions before a screen-recording round-trip with users.

### Docs

- README, `doc/getting_started.md` and `doc/troubleshooting.md` now
  document every Android Developer-Mode meta-data key (including the
  newly-required `DAM_ENABLED`), call out that **Developer Mode in the
  Meta AI app itself must be turned on** as a one-time per-phone step,
  and add a dedicated troubleshooting entry for "No eligible device
  found".

## 0.1.5

- Fix Android `CLIENT_TOKEN` in both bundled apps (`example/` and
  `samples/camera_access/`) — was an empty string `""`, which causes
  the SDK to throw `TOKEN_NOT_CONFIGURED` and silently refuse to
  register even when Developer Mode is on. Set to
  `"developer-mode-placeholder"` (the SDK doesn't validate the value
  when `APPLICATION_ID = "0"`).
- Add `ANALYTICS_OPT_OUT = true` to both Android manifests so failed
  analytics uploads to Meta's servers don't surface as misleading
  "Internal error" toasts during developer testing.
- Same fixes applied to the README and `doc/getting_started.md`
  snippets.

## 0.1.4

- Bump the recommended Android NDK to **28.2.13676358** in the README
  and both bundled samples (`example/`, `samples/camera_access/`).
  Newer Flutter plugin transitive deps (notably `jni`, pulled by
  `share_plus`) require r28.2; AGP enforces "use highest" so any
  consumer that pulls one of those breaks against r27. Meta's
  `mwdat-core` AAR (built against r27) is fine on r28.2 — NDK is
  backward compatible.

## 0.1.3

- Inline the full iOS and Android setup walkthrough in the README so
  the complete setup (deployment target, `MWDAT` dict with Developer
  Mode `MetaAppID = "0"`, `CFBundleURLTypes`,
  `LSApplicationQueriesSchemes`, `UIBackgroundModes`, Bonjour,
  external-accessory protocol, `SceneDelegate.swift`,
  `AndroidManifest.xml` meta-data + deep-link intent-filter,
  GitHub Packages Maven repo) is visible directly on pub.dev — no
  click-through to `doc/getting_started.md` required.
- Add a dedicated "Enable Developer Mode in the Meta AI app" section
  at the top of the setup so the two-sided contract (Meta AI toggle
  ↔ `MetaAppID = "0"`) cannot be missed.

## 0.1.2

- Refresh README title and introduction to match the SDK's full name
  ("Meta Wearables Device Access Toolkit for Flutter") and improve
  first-impression clarity on pub.dev and GitHub.

## 0.1.1

Documentation, deprecation, and discoverability fixes only — no
runtime behaviour changes vs. 0.1.0.

### Deprecated

- `MetaWearablesDat.startRegistration({appId, urlScheme})` — both
  named parameters are now annotated `@Deprecated`. They have always
  been ignored on iOS (`Wearables.shared.startRegistration()` reads
  `MetaAppID` / `AppLinkURLScheme` from `Info.plist.MWDAT`) and on
  Android (`Wearables.startRegistration(activity)` reads the same
  values from `<meta-data>` and the activity's `<intent-filter>`).
  Call sites should drop the arguments. The parameters will be
  removed in v0.2.0.

### Documentation

- Fix the `Info.plist` `AppLinkURLScheme` snippet in
  `doc/getting_started.md` and `.claude/skills/getting-started.md` to
  end with `://`. Meta AI builds the registration callback URL by
  literally concatenating this value with the query string, so
  without the `://` separator the callback becomes a malformed URL
  that iOS silently drops. The example app and `doc/troubleshooting.md`
  were already correct; the getting-started doc was the outdated
  one. Added a dedicated troubleshooting bullet so the symptom
  ("Allow → app reopens but nothing happens") is searchable.
- Document the required iOS `SceneDelegate.swift` wiring for scene-based
  Flutter apps (Flutter ≥ 3.32). Without it, Meta AI's registration
  callback URL is silently dropped on iOS and the SDK never advances
  past `registering`. Added a dedicated section to
  `doc/registration_flow.md`, a setup step to `doc/getting_started.md`,
  a fresh troubleshooting entry, and a quick-reference note in
  `README.md`. Verified against
  [`example/ios/Runner/SceneDelegate.swift`](example/ios/Runner/SceneDelegate.swift).
- README and skill snippets no longer pass the vestigial `appId` /
  `urlScheme` arguments to `startRegistration()`.

### Other

- Add `flutter-plugin` to the pubspec topic list for improved
  discoverability on pub.dev.

## 0.1.0

Initial developer-preview release. Full feature and structural parity with
Meta's official iOS / Android DAT 0.6 SDKs.

### Added

- Unified `MetaWearablesDat` Dart facade for Meta's iOS and Android DAT SDKs.
- `requestAndroidPermissions()` — runtime Bluetooth/Internet grant on Android,
  no-op on iOS.
- Registration flow: `startRegistration`, `handleUrl`, `startUnregistration`,
  `getRegistrationState`, `registrationStateStream`, `activeDeviceStream`.
- `requestCameraPermission()` / `checkCameraPermissionStatus()`.
- **Device enumeration & compatibility:** `devicesStream()`, `getDevices()`,
  `compatibilityStream()`. New `DeviceCompatibility` enum
  (`compatible`, `deviceUpdateRequired`, `sdkUpdateRequired`, `unknown`).
- **Streaming:** `startStreamSession`, `stopStreamSession`,
  `pauseStreamSession`, `resumeStreamSession`, `streamSessionStateStream`,
  `streamSessionErrorStream`, `videoStreamSizeStream`. Frames are delivered
  zero-copy via Flutter's texture registry (CVPixelBuffer on iOS,
  SurfaceTexture on Android). New `deviceKinds` parameter for device-kind
  filtering.
- **Device-session lifecycle:** `deviceSessionStateStream()`,
  `deviceSessionErrorStream()`. New `DeviceSessionState` enum
  (`idle`, `starting`, `started`, `paused`, `stopping`, `stopped`).
- **Per-frame video stream:** `videoFramesStream()` emitting `VideoFrame`
  events with raw BGRA (iOS) / I420 (Android) payloads. Subscriber-gated
  so the per-frame copy is free when no Dart listener is attached.
- **HEVC (`hvc1`) codec:** `videoCodec: VideoCodec` parameter on
  `startStreamSession`. iOS routes compressed `CMSampleBuffer`s through a
  `VTDecompressionPipeline`; Android sets `compressVideo = true`.
- **Background streaming:** `enableBackgroundStreaming` /
  `disableBackgroundStreaming` with `BackgroundNotification` model. iOS
  activates `AVAudioSession` and software HEVC decoding; Android starts a
  foreground service with wake lock.
- `capturePhoto({format})` — mid-stream high-res JPEG / HEIC capture.
- **Typed errors:** `DatError` hierarchy with `RegistrationError`,
  `UnregistrationError`, `HandleUrlError`, `DeviceSessionError`,
  `SessionError`, `CaptureError` — each with `is*` convenience getters so
  callers can switch on errors without string-matching codes.
- **Mock Device Kit:** `enableMockDevice`, `disableMockDevice`,
  `isMockDeviceEnabled`, `pairMockRaybanMeta`, `pairedMockDevices`,
  `mockPowerOn`, `mockPowerOff`, `mockDon`, `mockDoff`, `mockFold`,
  `mockUnfold`, `setMockCameraFeed`, `setMockCapturedImage`,
  `setMockPermission`, `setMockPermissionRequestResult`, `mockDevicesStream`.
- `samples/camera_access/` — polished Flutter clone of Meta's official iOS
  and Android Camera Access samples (settings sheet, photo capture, devices
  screen, video recording).
- Long-form documentation in `doc/` (getting started, registration,
  streaming, frame processing, mock device, troubleshooting).
- AI-assisted development config: `AGENTS.md`, `.claude/skills/`,
  `.cursor/rules/`, `.github/copilot-instructions.md`, `install-skills.sh`.

### Notes

- Audio (microphone capture, speaker playback) is intentionally out of scope
  for `0.1.x` — it is handled via standard Bluetooth Hands-Free Profile, not
  Meta's DAT SDK.
- `SessionState` and `sessionStateStream()` / `sessionErrorStream()` are
  deprecated aliases for `StreamSessionState` and
  `streamSessionStateStream()` / `streamSessionErrorStream()`; they will be
  removed in v0.2.0.
