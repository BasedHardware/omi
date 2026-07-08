# Ray-Ban Meta as an Omi Capture Device

Ray-Ban Meta glasses are a first-class Omi capture device: pairable from the
Omi app, usable as the active audio source for live transcription, and (in the
DAT-enabled build) able to capture photos into the conversation's visual
context — the same product role as OmiGlass.

## Architecture

Ray-Ban Meta plugs into Omi's existing device abstraction. It is **not** a BLE
GATT Omi device and is never spoofed as one; it enters through the same seam
Apple Watch uses (discoverer → transport → connection), with photos riding the
OmiGlass image pipeline.

```
Meta Wearables DAT (camera/photos)──┐
                                    ├── RayBanMetaHostApiImpl.swift (iOS)
Bluetooth HFP route (microphone) ───┘        │  Pigeon: RayBanMetaHostAPI /
                                             │          RayBanMetaFlutterAPI
                                             ▼
                     RayBanMetaFlutterBridge (lib/services/bridges/)
                                             ▼
                     RayBanMetaTransport (synthetic characteristic streams)
                                             ▼
                     RayBanMetaDeviceConnection (DeviceConnection contract)
                                             ▼
        CaptureController: audio frames → wss …/v4/listen?source=rayban_meta
                           photos      → image_chunk JSON frames (OpenGlass path)
```

### Key components

| Layer | File | Notes |
|---|---|---|
| Device type | `app/lib/backend/schema/bt_device/bt_device.dart` | `DeviceType.raybanMeta`; serialized by name; legacy index 9 |
| Locator | `app/lib/services/devices/discovery/device_locator.dart` | `TransportKind.metaDat` |
| Discoverer | `app/lib/services/devices/discovery/rayban_meta_discoverer.dart` | Self-gating (iOS + native availability); emits a setup placeholder before Meta AI registration |
| Transport | `app/lib/services/devices/transports/rayban_meta_transport.dart` | Maps native events to `rayban-meta-audio-*` / `rayban-meta-camera-*` streams |
| Connection | `app/lib/services/devices/connectors/rayban_meta_connection.dart` | `pcm16` codec; image listener emits `OrientedImage`; 30 s auto photo capture while active |
| Pigeon contract | `app/lib/pigeon_interfaces.dart` | `RayBanMetaHostAPI` / `RayBanMetaFlutterAPI` |
| iOS bridge | `app/ios/Runner/RayBanMeta/` | `RayBanMetaHostApiImpl.swift` (DAT under `#if canImport(MWDATCore)`), `RayBanMetaAudioCapture.swift` (HFP mic → PCM16/16 kHz) |
| Backend | `backend/models/conversation_enums.py`, `backend/routers/transcribe.py` | `ConversationSource.rayban_meta`; photo-source flip preserves `rayban_meta` |

### Audio path

The Meta Wearables Device Access Toolkit (DAT 0.8) has **no microphone API**.
Meta's documented input path is the Bluetooth Hands-Free Profile:
`AVAudioSession` with `.playAndRecord` + `.allowBluetoothHFP`, preferring the
glasses' `.bluetoothHFP` input port. `RayBanMetaAudioCapture` taps
`AVAudioEngine`'s input, converts to PCM16 mono 16 kHz with
`AVAudioConverter`, and streams frames over Pigeon. The Dart connection
reports `BleAudioCodec.pcm16`, so the live socket opens with
`codec=pcm16&sample_rate=16000&source=rayban_meta`.

Known properties of the HFP route:

- 8 kHz narrowband voice quality on many links (beamformed to the wearer).
- A2DP and HFP are mutually exclusive: music on the phone pauses while the
  glasses mic is in use. The UI says this in plain language.
- The route needs ~2 s to stabilize after the audio engine starts; the DAT
  camera stream must start **after** HFP is active or the route can fail
  silently (Meta's documented ordering constraint — sequenced in
  `RayBanMetaHostApiImpl`).

### Photo path

`startCamera()` opens a DAT stream session at the lowest frame rate (2 fps,
low resolution) purely to arm photo capture — the glasses' hardware capture
LED is on for the whole session, which is Meta's (and our) visible-capture
guarantee. `capturePhoto(format: .jpeg)` results arrive via
`photoDataPublisher` → Pigeon `onPhotoCaptured` → transport photo stream
(1 orientation byte + JPEG) → `OrientedImage` → CaptureController's existing
OmiGlass flow: base64, 8 KB `image_chunk` JSON frames over the same listen
WebSocket, server-side reassembly, vision-LLM description, and attachment to
the in-progress conversation.

While the photo controller is active the connection auto-captures every 30 s
(OmiGlass-equivalent ambient visual context); the connected-device screen also
offers a manual **Capture Photo** action.

### Backend

`source=rayban_meta` is a first-class `ConversationSource`. The listen
endpoint already accepted arbitrary source strings; without the enum member
the value would silently degrade to `unknown`
(`ConversationSource._missing_`). Storing photos historically relabeled the
conversation `openglass`; `resolve_photo_conversation_source()` now preserves
photo-capable sources (`openglass`, `rayban_meta`) and keeps the legacy flip
for everything else.

## Availability modes (the feature gate)

The repo has no runtime flag system; gating follows the discoverer-self-gating
idiom. `RayBanMetaHostAPI.getAvailabilityMode()` reports:

- **`full`** — the `meta-wearables-dat-ios` SPM package is linked
  (`#if canImport(MWDATCore)`). Audio + photos. Developer Mode deliberately
  runs without `MetaAppID` / `ClientToken`; those credentials are only for
  future beta/distribution builds.
- **`audio_only`** — no DAT in this build. Only the labeled
  "Ray-Ban Meta audio-only mode" via the system Bluetooth HFP route. All
  camera APIs honestly report unavailable; nothing is faked.
- **`none`** — non-iOS platforms (Android integration is future work; the
  discoverer yields nothing there).

The default repo build is `audio_only` and compiles everywhere with no Meta
credentials. See `docs/rayban-meta-dat-setup.md` for the `full` build.

## Privacy

- Audio capture starts only when the user has made Ray-Ban Meta the active
  device and capture is running — the same listening states as every Omi
  device; stopping capture stops the HFP engine.
- Photo capture requires the DAT camera permission granted through Meta's own
  consent flow, and the glasses' hardware LED is lit whenever the camera
  session is active.
- No Meta View/private APIs, no traffic interception — official SDK and
  platform audio routing only.

## Limitations (current, honest)

- **iOS only.** Android DAT exists but is not integrated yet.
- **No battery level** — DAT 0.8 does not expose it; the UI hides battery.
- **HFP voice quality** (≈8 kHz) is below Omi pendant audio; fine for
  transcription, noticeable on playback.
- **Music pauses** during capture (A2DP/HFP exclusivity).
- **App Store distribution of DAT builds is not yet supported by Meta** —
  developer/beta channel only (see Meta's toolkit terms).
- The DAT-enabled build requires Meta Wearables Developer Center access to
  fetch the SDK package and was written against the DAT 0.8 API reference;
  first compile against the real SDK may need minor symbol fixes. Developer
  Mode should not embed `MetaAppID` / `ClientToken`; those credentials are only
  for a future beta/distribution build configuration.
