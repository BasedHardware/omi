# meta_wearables_dat_flutter — AI Instructions

> Full Meta Wearables DAT API reference: <https://wearables.developer.meta.com/llms.txt?full=true>
>
> Meta Wearables Developer docs: <https://wearables.developer.meta.com/docs/develop/>
>
> Plugin docs: [`doc/`](doc/)

This file is the canonical context for AI coding assistants working on
`meta_wearables_dat_flutter`. The `.claude/skills/`, `.cursor/rules/`, and
`.github/copilot-instructions.md` configs are all generated from the same
knowledge captured here.

## Identity

- GitHub org: iSee-Labs
- Repo: <https://github.com/iSee-Labs/meta-wearables-dat-flutter>
- Package name (pub.dev): `meta_wearables_dat_flutter`
- License: MIT
- Copyright holder: iSee Labs
- Maintainer: Talha Ordukaya

## What this project is

An **unofficial** Flutter plugin that bridges Meta's official iOS and
Android Wearables Device Access Toolkit (DAT) SDKs. Provides a unified
Dart API for Flutter apps integrating with Meta AI Glasses
(Ray-Ban Meta, Oakley Meta, Ray-Ban Display).

## What this project is NOT

- NOT a reimplementation of Meta's SDK. Meta's SDKs are closed-source
  binaries that we link as dependencies.
- NOT affiliated with, endorsed by, or sponsored by Meta Platforms, Inc.
  The README must include an unofficial disclaimer at the very top,
  BEFORE the title. "Meta", "Ray-Ban Meta", "Oakley Meta" are trademarks
  of their respective owners.
- NOT for publishing to public app stores yet — Meta DAT is in developer
  preview.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Dart facade                       lib/meta_wearables_dat_flutter.dart
│  • MetaWearablesDat singleton, typed errors, models         │
│  • Public Future<T> / Stream<T> API                         │
└─────────────────────────────────────────────────────────────┘
        │                                  │
   MethodChannel                       EventChannels
   meta_wearables_dat_flutter          • registration_state
                                       • active_device
                                       • devices
                                       • device_session_state
                                       • device_session_errors
                                       • stream_session_state
                                       • stream_session_errors
 • video_stream_size
 • video_frames
 • compatibility
 • mock_devices
 • display_state
 • display_events
        │                                  │
   ┌────┴───────────────────┐    ┌────────┴───────────────────┐
   │ iOS (Swift)            │    │ Android (Kotlin)           │
   │ MetaWearablesDatPlugin │    │ MetaWearablesDatPlugin     │
   │ MetaSessionManager     │    │ MetaSessionManager         │
   │ MetaDisplayManager     │    │ MetaDisplayManager         │
   │ MetaMockDeviceManager  │    │ MetaMockDeviceManager      │
   └────────┬───────────────┘    └────────┬───────────────────┘
            │                             │
       MWDATCore                  com.meta.wearable.mwdat.core
       MWDATCamera                com.meta.wearable.mwdat.camera
       MWDATDisplay               com.meta.wearable.mwdat.display
       MWDATMockDevice            com.meta.wearable.mwdat.mockdevice
```

### Module layout

The Meta DAT SDK is organized into four modules and we keep this
mapping 1-to-1:

- **Core** — registration, device discovery, permissions, selectors
  (`Wearables`, `RegistrationState`, `Device`, `Permission`).
- **Camera** — `DeviceSession`, `Stream`, `VideoFrame`,
  `PhotoData`.
- **Display** — `Display`, `DisplayState`, the component DSL
  (`FlexBox`, `Text`, `Image`, `Button`, `Icon`, `VideoPlayer`) and
  playback events.
- **MockDevice** — `MockDeviceKit`, `MockRaybanMeta`, `MockCameraKit`
  (optional, dev-only).

## Performance constraints (non-negotiable)

- **Texture path:** decoded video frames go through the Flutter texture
  registry (`FlutterTexture` on iOS, `SurfaceTexture` + `TextureRegistry`
  on Android). NEVER serialize decoded preview frames over
  `MethodChannel` for the texture path.
- **`videoFramesStream`:** Per-frame `EventChannel` is opt-in. Gate
  emission on subscriber count so the cost is zero when nobody listens.
  720x1280 BGRA is ~3.7 MB/frame — document the cost.
- **Backpressure:** All event streams must be backpressure-safe. If
  Dart stops listening, native side stops emitting.
- **Texture lifecycle:** `stopStreamSession()` must unregister the
  texture, otherwise GPU memory leaks.

## Coding conventions

- Dart: `very_good_analysis` lint rules, dartdoc on every public API.
- Swift: follow Meta's iOS sample style.
  - `async`/`await` for SDK operations.
  - `AnyListenerToken.cancel()` for publisher listeners.
  - `@MainActor` for UI-touching code.
- Kotlin: follow Meta's Android sample style.
  - `Flow`/`StateFlow` with `collectLatest` for state streams.
  - Coroutine scopes torn down in `stop*` functions.
- All public Dart APIs return `Future<T>` or `Stream<T>`, never
  callbacks.

## Critical native-side requirements

### iOS

- `Info.plist`: `MWDAT` dict (`AppLinkURLScheme` — value MUST end
  with `://` because Meta AI concatenates it with the callback query
  string, `MetaAppID`, `ClientToken`, `TeamID`), `CFBundleURLTypes`,
  `LSApplicationQueriesSchemes` (with `fb-viewapp`),
  `UISupportedExternalAccessoryProtocols` (with `com.meta.ar.wearable`),
  `NSBluetoothAlwaysUsageDescription`, `NSLocalNetworkUsageDescription`,
  `NSBonjourServices`, `UIBackgroundModes`.
- `flutter config --enable-swift-package-manager` once per machine.
- iOS deployment target: **17.0**.

### Android

- `MainActivity` extends `FlutterFragmentActivity` (not
  `FlutterActivity`) — the camera-permission contract requires a
  `ComponentActivity`.
- Maven auth: GitHub Packages requires `GITHUB_TOKEN` env var (or
  `github_token=...` in `local.properties`) with `read:packages` scope.
- `minSdk = 31` (Android 12).
- Plugin merges `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_CONNECTED_DEVICE`,
  `WAKE_LOCK`, `POST_NOTIFICATIONS`, and a `<service>` entry for
  background streaming.

## Public API surface (target: v0.1.0)

### Registration & permissions

- `requestAndroidPermissions()` — Android only, no-op on iOS.
- `startRegistration({appId, urlScheme})`,
  `startUnregistration()`, `handleUrl(url)`.
- `registrationStateStream()`,
  `activeDeviceStream()`,
  `devicesStream()`,
  `compatibilityStream()`,
  `getDevices()`.
- `requestCameraPermission()`,
  `checkCameraPermissionStatus()`.

### Streaming

- `startStreamSession({deviceUUID?, fps, resolution, videoCodec, deviceKinds?})`
  → `int textureId`.
- `stopStreamSession()`.
- `streamSessionStateStream()`,
  `streamSessionErrorStream()`,
  `videoStreamSizeStream()`.
- `deviceSessionStateStream()`,
  `deviceSessionErrorStream()`.
- `videoFramesStream()` — opt-in `VideoFrame` stream.
- `capturePhoto({format})` → `Uint8List`.
- `enableBackgroundStreaming({androidNotification?})`,
  `disableBackgroundStreaming()`.

### Display (DAT 0.7.0)

- `startDisplaySession({deviceUUID?})`,
  `sendDisplayView(DisplayView)`,
  `stopDisplaySession()`.
- `displayStateStream()` → `DisplayState`
  (`starting/started/stopping/stopped`).
- Component DSL: `FlexBox`, `DisplayText`, `DisplayImage`,
  `DisplayButton`, `DisplayIcon`, `VideoPlayer` with `onTap` /
  `onClick` / `onPlaybackEvent` callbacks.

### Mock Device Kit

- `enableMockDevice({initiallyRegistered, initialPermissionsGranted})`,
  `disableMockDevice()`, `isMockDeviceEnabled()`.
- `pairMockRaybanMeta()`, `pairedMockDevices()`.
- `mockPowerOn(uuid)`, `mockPowerOff(uuid)`, `mockDon(uuid)`,
  `mockDoff(uuid)`, `mockUnfold(uuid)`, `mockFold(uuid)`.
- `setMockCameraFeed(uuid, filePath?)`,
  `setMockCapturedImage(uuid, filePath?)`.
- `setMockPermission(permission, status)`,
  `setMockPermissionRequestResult(permission, status)`.
- `mockDevicesStream()`.

## How we work

- Build in vertical slices: one feature working end-to-end
  (Dart → iOS → Android → sample) before starting the next.
- After every slice: `flutter analyze` zero-warnings,
  `flutter test` green, `flutter build ios --debug --no-codesign` green
  in `example/` and `samples/camera_access/`.
- Commit after each completed slice with a clear conventional-commit
  message (e.g. `feat: add devicesStream`).
- When uncertain, STOP and ask. Do not guess at Meta SDK behavior —
  read the reference samples under `meta-glasses-research/` first.

## Reference implementations

Available locally under `meta-glasses-research/`:

- `meta-wearables-dat-ios/` — official iOS SDK + sample app.
- `meta-wearables-dat-android/` — official Android SDK + sample app.
- `flutter_meta_wearables_dat/` — community Flutter plugin (rodcone).
  Reference for design decisions, but we do not copy code wholesale.

## See also

- [`doc/`](doc/) — long-form topic docs (getting started, registration,
  streaming, mock device, troubleshooting).
- [`.claude/skills/`](.claude/skills/) — per-topic AI skill files.
- [`.cursor/rules/`](.cursor/rules/) — Cursor rule with the same content.
- [`.github/copilot-instructions.md`](.github/copilot-instructions.md) —
  Copilot pointer to this file.
