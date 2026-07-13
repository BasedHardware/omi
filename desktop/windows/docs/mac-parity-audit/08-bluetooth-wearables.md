# Mac→Windows Parity Audit — Bluetooth / Wearables

> Scope: BLE wearable device support (device discovery, pairing, per-device protocol connections, BLE audio streaming/decode, storage/WiFi sync, sensors) and how device audio feeds transcription. Windows baseline checked: `desktop/windows/src/main/**`, `desktop/windows/src/renderer/**` (grep for bluetooth/ble/gatt/pendant/wearable/device-connection/codec terms — see per-section citations below).

Windows has no BLE/wearable stack at all (Phase 7 deferred per project baseline). This document exists to give a future Windows porter the full surface area the Mac app implements, so the port can be scoped accurately rather than discovered piecemeal.

## Summary table

| Capability / device | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| CoreBluetooth scanning/discovery | `Bluetooth/BluetoothManager.swift` | Absent | H |
| Device model + type detection | `Bluetooth/BtDevice.swift`, `Bluetooth/DeviceType.swift` | Absent | H |
| GATT service/characteristic UUID registry | `Bluetooth/DeviceUUIDs.swift` | Absent | H |
| Transport abstraction (BLE) | `Bluetooth/Transports/DeviceTransport.swift`, `Bluetooth/Transports/BleTransport.swift` | Absent | H |
| Device connection protocol + base impl | `Bluetooth/Connections/DeviceConnection.swift` | Absent | H |
| Connection factory (device type → connection) | `Bluetooth/Connections/DeviceConnectionFactory.swift` | Absent | H |
| Omi/OpenGlass device (audio, image, WiFi sync, settings) | `Bluetooth/Connections/OmiDeviceConnection.swift` | Absent | H |
| Friend Pendant (LC3 codec) | `Bluetooth/Connections/FriendPendantConnection.swift` | Absent | M |
| Bee (AAC/ADTS codec) | `Bluetooth/Connections/BeeDeviceConnection.swift` | Absent | M |
| Fieldy/Compass (Opus FS320) | `Bluetooth/Connections/FieldyDeviceConnection.swift` | Absent | M |
| Brilliant Labs Frame (partial — no Lua SDK) | `Bluetooth/Connections/FrameDeviceConnection.swift` | Absent | L |
| Limitless Pendant (protobuf-like + batch/realtime) | `Bluetooth/Connections/LimitlessDeviceConnection.swift` | Absent | M |
| PLAUD NotePin | `Bluetooth/Connections/PlaudDeviceConnection.swift` | Absent | M |
| WiFi sync (device-side offload sync) | `Bluetooth/WifiSyncTypes.swift`, `OmiDeviceConnection.setupWifiSync` | Absent | M |
| BLE audio frame reassembly + statistics | `Audio/BleAudioProcessor.swift` | Absent | H |
| BLE→transcription coordination service | `Audio/BleAudioService.swift` | Absent | H |
| Audio codec decoders (Opus/AAC/µ-law/PCM/LC3-stub) | `Audio/AudioCodecDecoder.swift` | Absent | H |
| Device state/lifecycle provider (scan/connect/reconnect/battery/firmware) | `Providers/DeviceProvider.swift` | Absent | H |
| System-audio-input Bluetooth-headset avoidance (unrelated, pre-existing) | — | Present | — |

## CoreBluetooth scanning/discovery

**What it is**: Central-role BLE scanner that discovers nearby supported wearables and surfaces them as connectable candidates.

**Where (Mac)**: `desktop/macos/Desktop/Sources/Bluetooth/BluetoothManager.swift`.

**How it works**: `BluetoothManager` is a `@MainActor` singleton wrapping a lazily-created `CBCentralManager` (lazy specifically to avoid triggering the macOS Bluetooth permission dialog at app startup). `startScanning(timeout:)` scans with `withServices: nil` (deliberately unfiltered — needed because PLAUD detection requires reading raw manufacturer advertisement data rather than a service UUID) and auto-stops via a `Timer` after the timeout. `CBCentralManagerDelegate` callbacks (`didDiscover`, `didConnect`, `didFailToConnect`, `didDisconnectPeripheral`) run `nonisolated` and hop to `@MainActor` via `Task`; connect/disconnect/fail events are additionally re-broadcast as `NotificationCenter` notifications (`bleDeviceConnected`/`bleDeviceDisconnected`/`bleDeviceFailedToConnect`) so `BleTransport` instances (which don't hold a delegate reference to the shared central manager) can observe connection outcomes for the peripheral they own. Exposes `triggerPermissionPrompt()` (issues a throwaway scan+immediate-stop specifically to force the macOS permission dialog) and a `DeviceBluetoothManaging` protocol used to inject a fake for tests.

**Windows status**: Absent. `grep -rliE "bluetooth|\bble\b|gatt|coreBluetooth|pendant|wearable|CBUUID|CBCentralManager" src/main src/renderer` returns only unrelated system-audio-input hits (see closing note).

**Value / notes**: macOS framework: `CoreBluetooth` (`CBCentralManager`/`CBPeripheral`). Windows equivalent: WinRT `Windows.Devices.Bluetooth.Advertisement.BluetoothLEAdvertisementWatcher` for scanning + `Windows.Devices.Bluetooth.BluetoothLEDevice`/`GattDeviceService` for GATT, accessed from Node either via a native N-API/WinRT projection addon or via `koffi` FFI calling the WinRT ABI (the project's existing `koffi` usage today is limited to Win32 `user32` calls for foreground-window/automation, not WinRT/BLE — this would be new ground). Electron itself has no built-in classic-BLE-central API beyond the `navigator.bluetooth` (Web Bluetooth) surface in the renderer, which is sandboxed and not suited to background scanning/reconnection.

## Device model, type detection, and codec enum

**What it is**: The `BtDevice` struct (identity/RSSI/info fields) plus `DeviceType` (9 supported hardware families) and `BleAudioCodec` (8 codec variants) that everything else keys off of.

**Where (Mac)**: `Bluetooth/BtDevice.swift`, `Bluetooth/DeviceType.swift`.

**How it works**: `DeviceType.detectDeviceType(peripheral:advertisementData:)` runs a priority-ordered match: advertised name substring (`"bee"`, `"plaud"`, `"compass"`/`"fieldy"`, `"friend_"` prefix, `"limitless"`/`"pendant"`) OR advertised service UUID match against `DeviceUUIDs`. PLAUD detection is special-cased: it reads `CBAdvertisementDataManufacturerDataKey`, checks manufacturer ID `93` (`0x5D`), and pattern-matches a known NotePin byte signature (`0456cf00`) — this is the reason scanning can't be service-UUID-filtered. OpenGlass is not detected at scan time; it's upgraded from `.omi` post-connection once GATT service discovery reveals an image-data-stream characteristic (`checkingForOpenGlass(services:)`). `BleAudioCodec` encodes codec id, sample rate (all 16kHz), bit depth, frame size/length, and FPS — this enum is the single source of truth threaded through the connection, processor, and decoder layers. `BtDevice` also owns pairing persistence (`saveAsPairedDevice()`/`loadPairedDevice()` via `UserDefaults` + `Codable`).

**Windows status**: Absent — no equivalent model, enum, or detection logic. `grep -rliE "device.?connection|device.?type|omi.?device|deviceprovider" src/main src/renderer` — no matches.

**Value / notes**: Pure Swift/data-model logic; trivially portable to TypeScript once a BLE transport exists — the detection rules and codec table are the actual reusable IP here, not the platform API calls.

## GATT service/characteristic UUID registry

**What it is**: Centralized enum of every BLE service and characteristic UUID for every supported device.

**Where (Mac)**: `Bluetooth/DeviceUUIDs.swift`.

**How it works**: Namespaced `enum`s per device/subsystem — `Omi` (main/settings/features services, audio+image+control characteristics), `Button`, `Storage` (data/read-control/wifi characteristics), `Accelerometer`, `Battery`/`DeviceInfo` (standard BLE SIG 16-bit UUIDs `180F`/`2A19`, `180A`/`2A24`/`2A26`/`2A27`/`2A29`), `Speaker`, `Frame`, `PLAUD` (128-bit UUIDs + manufacturer ID `93`), `Bee`, `Fieldy`, `FriendPendant`, `Limitless`. `allSupportedServiceUUIDs` aggregates the primary service UUIDs (unused for scanning today, since scanning is unfiltered, but available for a service-UUID-filtered scan mode).

**Windows status**: Absent.

**Value / notes**: Same UUIDs would carry over verbatim to a WinRT `GattDeviceService`/`GattCharacteristic` implementation — this file alone is most of the protocol contract a porter needs.

## Transport abstraction (BLE)

**What it is**: A `DeviceTransport` protocol (connect/disconnect/read/write/notify-stream/ping/dispose) with `BleTransport` as the CoreBluetooth-backed implementation, decoupling device-specific logic from the raw BLE API.

**Where (Mac)**: `Bluetooth/Transports/DeviceTransport.swift`, `Bluetooth/Transports/BleTransport.swift`.

**How it works**: `BleTransport` wraps one `CBPeripheral`, sets itself as `CBPeripheralDelegate`, and converts callback-based CoreBluetooth into Swift concurrency: `connect()` awaits a `CheckedContinuation` resolved by the `NotificationCenter` events `BluetoothManager` posts (not a delegate call, since `BluetoothManager` owns the single `CBCentralManagerDelegate`), then calls `discoverServices(nil)` awaiting another continuation, then `discoverCharacteristics(nil, for:)` per service, then sleeps 500ms as a crude "let characteristic discovery settle" barrier before marking `.connected`. `readCharacteristic`/`writeCharacteristic` use per-UUID continuation dictionaries keyed by characteristic UUID (note: not composite service+characteristic keys, so two different services sharing a characteristic UUID could collide — a latent bug, not exercised by current UUID set). `getCharacteristicStream` lazily enables notifications (`setNotifyValue(true, for:)`) and fans out `didUpdateValueFor` into a custom `CharacteristicStreamHandler` (`AsyncThrowingStream` wrapper), cached by `"service:characteristic"` key so repeated calls reuse one subscription. `ping()` issues `readRSSI()` but the async wrapper (`readRSSIAsync()`) is a documented placeholder that returns immediately without actually awaiting the RSSI delegate callback — connectivity-check-only, not a real RSSI value.

**Windows status**: Absent.

**Value / notes**: macOS framework: `CoreBluetooth` peripheral delegate model. Windows equivalent: WinRT `GattDeviceService.GetCharacteristicsAsync` / `GattCharacteristic.ValueChanged` event (real async APIs, no continuation-bridging hack needed) plus `WriteValueAsync`/`ReadValueAsync`. The `DeviceTransport` protocol boundary itself (service/characteristic UUID in, `Data` out, `AsyncThrowingStream` for notifications) is what a Windows port should replicate as a TS interface, backed by whatever WinRT bridge is chosen.

## Device connection protocol + base implementation

**What it is**: `DeviceConnection` — the full per-device API surface (battery, audio, button, storage, camera, accelerometer, speaker/haptic, features, LED/mic settings, WiFi sync) — with `BaseDeviceConnection` providing default implementations against the standard Omi GATT layout, which per-device subclasses override.

**Where (Mac)**: `Bluetooth/Connections/DeviceConnection.swift`.

**How it works**: `BaseDeviceConnection.connect()` calls `transport.connect()`, verifies with a ping (non-fatal if it fails), reads Device Information Service characteristics (model/firmware/hardware/manufacturer), then flips to `.connected` and emits on `connectionStatePublisher`. `getAccelerometerStream()` parses 12-byte little-endian 6×Int16 packets into `AccelerometerData` and computes a fall-detection magnitude (`> 30.0` threshold) that triggers `DeviceConnectionDelegate.deviceConnection(_:didDetectFall:)` — wired to a local notification in `DeviceProvider`. `getFeatures()` reads a 4-byte little-endian bitmask into `OmiFeatures` (`OptionSet`: speaker/accelerometer/button/battery/usb/haptic/offlineStorage/ledDimming/micGain/wifi) and caches it. Storage list parsing decodes 4-byte little-endian `Int32` file-length entries. WiFi sync default implementation validates SSID/password length constraints and returns "not supported" unless overridden.

**Windows status**: Absent.

**Value / notes**: This is the largest single porting surface — 20+ methods, each with byte-level wire format baked in (little-endian multi-byte fields throughout). A Windows port should keep this exact protocol/base-class split so per-device subclasses stay small.

## Connection factory (device type → connection)

**What it is**: Maps a detected `DeviceType` to the correct `DeviceConnection` subclass, constructing a fresh `BleTransport` per connection.

**Where (Mac)**: `Bluetooth/Connections/DeviceConnectionFactory.swift`.

**How it works**: Static `create(device:peripheral:centralManager:)` switches on `device.type`: `.omi`/`.openglass` → `OmiDeviceConnection`; `.plaud` → `PlaudDeviceConnection`; `.bee` → `BeeDeviceConnection`; `.fieldy` → `FieldyDeviceConnection`; `.friendPendant` → `FriendPendantConnection`; `.limitless` → `LimitlessDeviceConnection`; `.frame` → `FrameDeviceConnection` (partial); `.appleWatch` → `nil` (would use `WatchConnectivity`, not BLE — unimplemented). A convenience overload resolves the `CBPeripheral` via `BluetoothManager.shared.peripheral(for:)`.

**Windows status**: Absent.

**Value / notes**: Straightforward switch-based factory; low risk to port once the connection classes exist.

## Omi / OpenGlass device connection

**What it is**: The reference/primary device implementation — audio streaming, OpenGlass image streaming, LED dim + mic gain settings, and WiFi sync setup/start/stop with response-code handling.

**Where (Mac)**: `Bluetooth/Connections/OmiDeviceConnection.swift`.

**How it works**: On connect, probes `hasPhotoStreaming()` (a characteristic-read to `imageDataStream`) to auto-upgrade `.omi` → `.openglass`. Image streaming: reassembles frames from 2-byte little-endian frame-index-prefixed chunks, with `0xFFFF` as an end-of-image marker and `0` as start-of-image; firmware ≥ 2.1.1 embeds a 1-byte orientation code in frame 0, older firmware defaults to `orientation180`; has a 200KB buffer-overflow guard that discards and resets. WiFi sync: `setupWifiSync` validates credentials, races a 5-second timeout `Task` against a response-stream `Task` reading `WifiSyncErrorCode` from `Storage.wifi`, and returns a `WifiSyncSetupResult`; `startWifiSync`/`stopWifiSync` are single-byte command writes (`0x02`/`0x03`) to the same characteristic.

**Windows status**: Absent.

**Value / notes**: Highest-value single connection class to port first — it's Omi's own hardware protocol (not third-party reverse-engineered), and covers audio + image + WiFi sync + settings in one place.

## Friend Pendant connection (LC3 codec)

**What it is**: Connection for the "Friend" pendant, using LC3 audio at 16kHz/10ms frames.

**Where (Mac)**: `Bluetooth/Connections/FriendPendantConnection.swift`.

**How it works**: BLE notifications arrive as 95-byte packets (90 bytes LC3 payload = 3× 30-byte frames, + 5-byte footer); `processAudioPacket` strips the footer, then the payload is split into 30-byte frames and pushed individually into an `audioStreamSubject`. No real battery reporting — hardcodes 90% and republishes it every 30s. No button, photo, accelerometer, or features support (all stubbed to empty/false). Device info is hardcoded (no Device Information Service read).

**Windows status**: Absent.

**Value / notes**: LC3 decode itself is unimplemented even on Mac (see Audio Codec Decoders section) — porting this connection class doesn't unblock real audio without also sourcing/porting `liblc3`.

## Bee connection (AAC/ADTS codec)

**What it is**: Connection for "Bee" devices, using AAC audio with ADTS framing and a binary request/response command protocol.

**Where (Mac)**: `Bluetooth/Connections/BeeDeviceConnection.swift`.

**How it works**: Two characteristics on one service: a control characteristic (2-byte little-endian command IDs, e.g. mute/unmute `0xC006`, battery `0xC00F`) and an audio characteristic. Commands are sent then awaited via a `responseCompleters: [UInt16: CheckedContinuation]` dictionary keyed by command ID with a 5s timeout; responses can arrive either directly keyed by command ID or as an "echo" wrapper (`0x8000` response code containing the original command ID + payload) — `handleControlResponse` handles both shapes. Audio: raw notification bytes (minus a 2-byte prefix) accumulate in `audioBuffer`, then an ADTS-sync-word scanner (`0xFF`, top nibble `0xF`) extracts one AAC frame at a time using the ADTS header's embedded frame-length field. Recording is explicitly started/stopped via mute/unmute commands (mirrors the mic being physically gated by a device-side mute state, not just stream-open/close).

**Windows status**: Absent.

**Value / notes**: AAC decode is fully implemented on Mac via `AudioToolbox` (see Audio Codec Decoders) — this is one of the more "complete" third-party integrations.

## Fieldy / Compass connection (Opus FS320)

**What it is**: Connection for Fieldy/Compass devices using Opus at the FS320 (320-sample/20ms, 50fps) variant with fixed 40-byte frames.

**Where (Mac)**: `Bluetooth/Connections/FieldyDeviceConnection.swift`.

**How it works**: Single characteristic serves both control and audio. Each BLE notification packs 6× 40-byte Opus frames (240 bytes); the connection slices them and validates each frame's first byte against the Opus TOC value `0xb8` (logs but still forwards non-matching frames rather than dropping them). No button/photo/accelerometer/features support. Battery uses the standard BLE Battery Service directly (not command-based like Bee/PLAUD).

**Windows status**: Absent.

## Brilliant Labs Frame connection (partial — SDK-gated)

**What it is**: Connection stub for Brilliant Labs' Frame smart glasses; explicitly **not** a full implementation even on Mac.

**Where (Mac)**: `Bluetooth/Connections/FrameDeviceConnection.swift`.

**How it works**: Frame's real protocol requires Brilliant Labs' proprietary Lua-scripting SDK (text commands like `"MIC START"`/`"CAMERA START"`, response prefixes `0xEE`=audio/`0xCC`=battery/`0xE1`-`0xE4`=status, a heartbeat every 5s, and an echo-ack protocol) — none of which is implemented; the file's trailing comment block documents what a real implementation would need. What *is* implemented: standard BLE Battery Service reads/streaming, a hardcoded PCM8 codec declaration, and a base64-embedded JPEG header constant (`photoHeader`) intended to prepend Frame's headerless raw JPEG data (unused until real image streaming exists). `getAudioStream()`, `startPhotoCapture()`, `getImageStream()` all log a warning and return empty/no-op.

**Windows status**: Absent.

**Value / notes**: Lowest value to port as-is (it doesn't work on Mac either) — a Windows port would need the same upstream Frame SDK dependency regardless of platform.

## Limitless Pendant connection (protobuf-like + batch/realtime modes)

**What it is**: The most protocol-complex connection — a hand-rolled protobuf-wire-format encoder/decoder over BLE, supporting both live audio streaming and bulk download of on-device "flash page" recordings, plus button, LED, and storage-status queries.

**Where (Mac)**: `Bluetooth/Connections/LimitlessDeviceConnection.swift`.

**How it works**: Implements varint encode/decode and protobuf tag (field-number + wire-type) parsing by hand (no protobuf library). All outbound commands go through a common `encodeBleWrapper` (message-index/sequence/fragment-count/payload fields) + `encodeRequestData` (auto-incrementing request ID) envelope. Inbound BLE notifications are parsed as `BlePacket{index, seq, numFrags, payload}` and reassembled via a `fragmentBuffer: [Int: [Int: [UInt8]]]` (outer key = message index, inner = fragment sequence) until `numFrags` fragments are collected, then dispatched to either real-time audio handling (`handleRealTimePayload`, extracts Opus frames directly) or batch/"pendant message" handling (`handlePendantMessage`, recurses through nested protobuf fields to find storage buffers → flash pages → embedded Opus frames), selected by an `isBatchMode` flag toggled via `enableBatchMode()`/`disableBatchMode()`. Opus frame extraction (`extractOpusRecursive`) validates candidate frames by length range (10–200 bytes) and a TOC-byte whitelist (`0xb8, 0x78, 0xf8, 0xb0, 0x70, 0xf0`) — broader than the Fieldy check. Also parses button double-press events and device/storage status (oldest/newest flash page, current session, free/total capture pages) out of the same notification stream by scanning for specific protobuf field markers (magic bytes like `0x22`, `0x2a`, `0x62`, `0x12`, `0x08`/`0x10`/`0x18`/`0x20`/`0x28`) — clearly derived from Limitless's actual wire format via reverse engineering, not a public schema. Public methods expose storage status/flash-page-count queries, batch download control, processed-data acknowledgment, and unpair-without-factory-reset.

**Windows status**: Absent.

**Value / notes**: Would be the most expensive single connection class to port — it's a bespoke binary protocol implementation, not a thin GATT wrapper. A port needs either the Swift parsing logic transliterated line-for-line or a from-scratch re-derivation against Limitless hardware.

## PLAUD NotePin connection

**What it is**: Connection for PLAUD NotePin, using a request/response command protocol over one write + one notify characteristic, with an explicit device-side recording-session lifecycle (start record → start sync → stream → stop sync → stop record).

**Where (Mac)**: `Bluetooth/Connections/PlaudDeviceConnection.swift`.

**How it works**: Commands are `[0x01, cmdIdLow, cmdIdHigh] + payload`, sent on `writeCharacteristic` and awaited via a `commandQueues: [Int: PassthroughSubject]` per command ID with a 10s timeout. Audio arrives as notifications where byte 0 == `2` signals an audio-data packet; `parseAudioChunk` reads a 4-byte position field (bytes 4-7, little-endian; `0xFFFFFFFF` = end marker) and a 1-byte length (byte 8) to slice the actual Opus payload, which then gets re-chunked into fixed 80-byte pieces before forwarding (a second buffering layer beyond the BLE notification framing). `setupRecordingSession()` retries up to 3 times with backoff: stop any existing recording (session 0), `startRecord()` (returns session ID + device start-timestamp), then `startSync(sessionId:start:)` to open the data flow — only then does the audio stream actually begin flowing to the consumer's `AsyncThrowingStream`. Battery command response is `[isCharging, batteryLevel]`.

**Windows status**: Absent.

## WiFi sync (offload sync over the device's own WiFi radio)

**What it is**: A device-initiated bulk-sync path where the wearable connects to a WiFi network directly (bypassing BLE's low bandwidth) to upload buffered audio, orchestrated by a short BLE handshake for credentials/status.

**Where (Mac)**: `Bluetooth/WifiSyncTypes.swift` (error codes, validation, result types); implemented per-device in `OmiDeviceConnection` (others default to unsupported via `BaseDeviceConnection`); gated by `OmiFeatures.wifi` bit; consumer-side polling and low-priority "storage sync available" notification logic lives in `Providers/DeviceProvider.swift` (`checkPendingStorageSync`, `storageSyncAvailable` notification).

**How it works**: `WifiSyncErrorCode` maps 8 firmware response codes (success, invalid packet/setup length, SSID/password length invalid, session-already-running, hardware-not-available, unknown-command) to user-facing messages. `WifiCredentialsValidator` enforces SSID ≤32 bytes UTF-8, password 8–63 bytes UTF-8 (checks both `.count` and `.utf8.count` since multi-byte characters could pass a naive character-count check but fail the device's byte-length limit). `DeviceProvider.checkPendingStorageSync()` asks a `StorageDataChecker` (backend: `StorageSyncService.shared.checkForStorageData()`, not itself part of this Bluetooth read but a consumer) for total/current byte offsets, and only surfaces a "pending sync" system notification if the gap exceeds ~10 seconds of audio (80 bytes/frame × 100fps × 10s heuristic threshold).

**Windows status**: Absent.

**Value / notes**: Meaningful only in combination with a device connection that supports it (currently only Omi/OpenGlass). Self-contained validation/error-code logic — cheap to port once any BLE connection exists.

## BLE audio frame reassembly + processing pipeline

**What it is**: The shared layer that turns raw BLE notification bytes (packet-framed, pre-framed, or protobuf-wrapped depending on device) into individual codec frames, then into PCM samples, tracking loss/throughput statistics along the way.

**Where (Mac)**: `Audio/BleAudioProcessor.swift`.

**How it works**: Two entry paths depending on device: `processAudioData(_:)` for devices needing frame reassembly — branches by codec into `processFramedData` (Fieldy 40-byte / "LC3" 30-byte fixed-size slicing) or `processPacketData` (Omi's own scheme: `[indexLow, indexHigh, frameId, ...content]` headers, with `frameId == 0` starting a new frame, sequential `frameId` continuing it, and gap detection between `lastPacketIndex` values incrementing a `lostPackets` counter when the jump looks like real loss rather than an overflow/reset, capped at <100 to avoid false positives from wraparound). `processFrame(_:)` / `processFrames(_:)` is the entry path for devices that pre-extract frames themselves (Bee, Limitless) — goes straight to the codec decoder. Every completed frame is decoded via the codec's `AudioCodecDecoder` (falling back to `PCMPassthroughDecoder` if `decoder` is nil and codec `.isPCM`) and emitted on both a delegate callback and a Combine `pcmSamplesPublisher`/`pcmDataPublisher`. Tracks consecutive decode failures (logs once at failure #1, escalates to error at failure #10) and validates Opus TOC bytes on failure for diagnostics. Includes WAV-file helpers (`createWavHeader`/`createWavData`) used elsewhere for local audio export. `BleAudioProcessor.forDevice(_:)` maps each `DeviceType` to its default starting codec.

**Windows status**: Absent.

**Value / notes**: This is genuinely reusable, mostly-pure logic (byte-buffer parsing + a Combine publisher) — the least platform-coupled piece in the whole stack, and the highest-leverage file to port first since every device connection funnels through it.

## BLE→transcription coordination service

**What it is**: The `@MainActor` singleton that wires a live `DeviceConnection`'s audio stream through `BleAudioProcessor` into the app's transcription pipeline (or a raw-data/raw-frame callback for WAL recording), and computes a live audio-level meter.

**Where (Mac)**: `Audio/BleAudioService.swift`.

**How it works**: `startProcessing(from:transcriptionService:audioDataHandler:rawFrameHandler:)` reads the device's codec via `connection.getAudioCodec()`, refuses unsupported codecs (checks `AudioDecoderFactory.isSupported`), warns on partial-support codecs (`hasFullSupport` — currently only LC3), constructs a per-session `BleAudioProcessor`, and pumps `connection.getAudioStream()` through a device-type `switch` in `processDeviceAudio` that decides whether to call `processor.processAudioData` (needs reassembly: Fieldy/FriendPendant/PLAUD/Omi/OpenGlass) or `processor.processFrame` (pre-framed: Bee/Limitless) — this switch duplicates/depends on knowledge that's also implicit in each connection class, a coupling point a Windows port should probably collapse (e.g. have each connection self-report whether it emits raw or pre-framed data). Decoded PCM is forwarded to `transcriptionService?.sendAudio(_:)` (mono; diarization is server-side) and to an optional custom `audioDataHandler`; raw pre-decode bytes go to `rawFrameHandler` for WAL/local recording. Also computes a smoothed (70/30 exponential) RMS audio level for UI meters, and has an unused `convertToStereo` helper (duplicates mono samples to interleaved stereo — not currently called from this file).

**Windows status**: Absent.

## Audio codec decoders (Opus / AAC / µ-law / PCM / LC3-stub)

**What it is**: Per-codec decode implementations converting encoded frames to 16kHz mono Int16 PCM.

**Where (Mac)**: `Audio/AudioCodecDecoder.swift`.

**How it works**: `AudioDecoderFactory.createDecoder(for:)` dispatches by `BleAudioCodec`. `PCMPassthroughDecoder` handles pcm8 (unsigned→signed 16-bit expansion, ×256 scale) and pcm16 (direct little-endian reinterpret) with no real "decoding." `OpusAudioDecoder` uses `AudioToolbox`'s `AudioConverterNew`/`AudioConverterFillComplexBuffer` with `kAudioFormatOpus` as input format id and a manual C-callback-based data-supply closure (frame size 160 samples/10ms for standard Opus, 320/20ms for FS320); validates TOC byte but decodes even if invalid. `AACAudioDecoder` similarly uses `AudioToolbox` with `kAudioFormatMPEG4AAC`, validates the 7-byte ADTS sync word (`0xFF`, top nibble `0xF`) and extracts the embedded frame-length before decoding the raw (header-stripped) AAC payload to 1024 samples/frame. `MulawAudioDecoder` implements ITU-T G.711 µ-law expansion via a precomputed 256-entry lookup table (bit-invert → sign/exponent/mantissa extraction → linear reconstruction) — fully self-contained, no OS codec dependency. `LC3AudioDecoder` is an explicit placeholder: it does not decode LC3 at all, just logs a warning and returns silence sized to the expected sample count, specifically to avoid audio gaps rather than crashing; the file's doc comment specifies exactly what a real implementation needs (`liblc3`, `lc3_setup_decoder`/`lc3_decode`, 10ms frames, 30 bytes/frame, 160 samples/frame output). `AudioDecoderFactory.isSupported`/`hasFullSupport` distinguish "won't crash" from "actually produces audio" — only LC3 is in the gap between those two.

**Windows status**: Absent.

**Value / notes**: macOS framework: `AudioToolbox` (`AudioConverterRef`) for Opus/AAC. Windows has no built-in Opus/AAC BLE-oriented converter equivalent to `AudioConverterFillComplexBuffer`; a port would need either a portable Opus library (e.g. libopus via native binding — likely lower-risk than reimplementing `AudioToolbox`'s callback-based converter API) plus Windows Media Foundation or a userland AAC decoder for Bee, and µ-law/PCM ports trivially (pure math, already platform-agnostic in the Mac code). LC3 is unimplemented on **both** platforms today — porting Friend Pendant doesn't unblock real audio without sourcing `liblc3` regardless of OS.

## Device state/lifecycle provider (scan / connect / reconnect / battery / firmware)

**What it is**: The app-facing `ObservableObject` that owns overall device state — scanning, connecting, the active connection, paired-device persistence, auto-reconnection, battery monitoring + low-battery alerts, storage-support detection, firmware-update-check stub, and fall-detection/disconnect local notifications.

**Where (Mac)**: `Providers/DeviceProvider.swift`.

**How it works**: `@MainActor` singleton (`DeviceProvider.shared`) built on top of `BluetoothManager` (via a `DeviceBluetoothManaging` protocol for testability) with **lazy Bluetooth permission triggering** — `initializeBluetoothBindingsIfNeeded()` is only called from `startDiscovery`/`stopDiscovery`, not from `init`, so simply launching the app doesn't prompt for Bluetooth access. Persists the paired device to `UserDefaults` (id/name/type only, not RSSI) and auto-attempts reconnection whenever a `bleDeviceConnected` notification's peripheral ID matches the persisted paired device. `startReconnectionTimer()` polls every 15s (`connectionCheckInterval`): tries a direct `connect(to:)` first, and if that fails, kicks off a fresh 5s discovery scan and checks whether the paired device showed up in `discoveredDevices`. Battery: initial read + a `getBatteryLevelStream()` subscription; `checkLowBattery()` fires a local notification once when level crosses below 20% (latched via `hasLowBatteryAlerted` to avoid repeat spam, reset once back above 20%). Storage support: checks `connection.getStorageList()` is non-empty, then asks an injected `StorageDataChecker` closure (bridges to `StorageSyncService`, outside this file's scope) for pending-sync byte counts and posts a `storageSyncAvailable` notification if the gap is large enough. Firmware-update checking is an explicit **stub** — logs "would check" and never calls a real API (`TODO` in source). Also implements `DeviceConnectionDelegate` to turn unexpected disconnects into `handleDisconnection()` (which itself schedules a 30s-delayed "device disconnected" local notification, canceled if reconnection succeeds first) and fall-detection events into a local notification.

**Windows status**: Absent.

**Value / notes**: This is the orchestration layer a Windows port would eventually need to replicate in the Electron main process (or a renderer service, depending on where BLE access lives in the chosen bridge) — reconnection heuristics, low-battery/disconnect notification debouncing, and the paired-device persistence shape are all directly portable design decisions independent of the underlying BLE transport choice.

## Spotted outside my scope

- `desktop/windows/src/renderer/src/lib/audio.ts` and `src/renderer/src/lib/voice/echoGate.ts` already contain Bluetooth-*avoidance* logic (a `BLUETOOTH_RE = /bluetooth|hands-free/i` regex used to deprioritize Bluetooth/HFP mics when picking the Windows system audio-input device). This is unrelated to wearable BLE pairing — it's about not accidentally recording through a paired Bluetooth headset's low-quality HFP profile — but is worth flagging so a future BLE-wearable port doesn't confuse it with device-connection code.
- Windows already depends on `koffi` (native FFI to Win32 `user32`, foreground-window/automation helpers) per `desktop/windows/package.json:70` and `src/main/index.ts:613` — this is the most likely existing on-ramp for a native bridge, but it is not currently used for any WinRT/Bluetooth API, so BLE support would be genuinely new native-integration surface, not an extension of existing wiring.
