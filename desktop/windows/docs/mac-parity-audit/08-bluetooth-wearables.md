# Mac→Windows Parity Audit — Bluetooth / Wearables

> Re-audited 2026-08-22 against current source (supersedes the 2026-08-20 pass). Scope:
> BLE wearable device support (device discovery, pairing, per-device protocol connections,
> BLE audio streaming/decode, storage/WiFi sync, sensors) and how device audio feeds
> transcription. Windows baseline checked: `desktop/windows/src/main/**`,
> `desktop/windows/src/renderer/**` (grep for bluetooth/ble/gatt/pendant/wearable/
> device-connection/codec terms — see per-section citations below).

Windows has no BLE/wearable stack at all (Phase 7 deferred per project baseline) — that
conclusion is unchanged and reconfirmed against current source. What changed in this pass
is the *Mac reference description*: the previous audit cited a version of the Mac
Bluetooth stack that had already been substantially rewritten (mostly on 2026-07-11 —
2026-07-19, over a month before the 2026-08-20 audit was written) into a much more
defensive session/reliability architecture, and got several structural details wrong as a
result. Fixed below. This document exists to give a future Windows porter the full,
currently-accurate surface area the Mac app implements, so the port can be scoped
accurately rather than discovered piecemeal.

## Changed since the 2026-08-20 audit

Nothing shipped on the Windows side (confirmed: no commits since 2026-08-20 touch
`desktop/windows/src/**` in any BLE-adjacent way, and no commits at all since 2026-08-20
touch the Mac Bluetooth/Audio/Provider files this doc depends on — see verification note
at the end). Every item below is a **correction to how the previous audit described
already-existing Mac code**, not a new Mac-side change and not a Windows-side status
change (everything Windows-side is still `Absent`).

1. **Transport layer was already rewritten, and the audit missed it.** The previous
   audit's "Transport abstraction (BLE)" section describes `BleTransport` as directly
   implementing `CBPeripheralDelegate`, coordinating via `NotificationCenter` broadcasts
   from `BluetoothManager`, using a 500ms sleep as a "let discovery settle" barrier, and
   having a latent same-UUID-collision bug in its continuation dictionaries. **All of that
   was already gone by 2026-07-19** — a `refactor(desktop): converge Bluetooth session
   ownership` pass (2026-07-12) plus a string of race/crash fixes (2026-07-11 – 2026-07-19:
   "three Bluetooth defects — double-resume crash, observer leak, audio wedge", "serialize
   BleTransport continuation maps to fix data race", "Extend BleTransport lock to
   connection/discovery continuations") replaced it with a `BLEPhysicalDriving` abstraction,
   session-generation fencing, connection leases, and a typed `DeviceOperationBroker` with
   composite (service+characteristic) keys — the exact collision the old audit flagged as
   "not exercised" is now structurally impossible. See the rewritten Transport and new
   Session/reliability sections below.
2. **A whole new reliability layer exists that the old audit never mentioned**:
   `Bluetooth/Session/DeviceSessionCoordinator.swift`, `DeviceOperationBroker.swift`,
   `BluetoothConnectionLease.swift`, `DeviceCommandQueue.swift`,
   `DeviceAudioStreamController.swift` (1,140 lines total). This is the actual owner of
   reconnection policy, generation fencing, and per-device command/audio-session
   lifecycles — DeviceProvider and the Bee/PLAUD connections now delegate to it rather than
   rolling their own dictionaries/timers as previously described.
3. **`DeviceProvider`'s reconnection logic moved.** The old audit describes
   `DeviceProvider.startReconnectionTimer()` polling every 15s and driving reconnect
   attempts directly. That method is gone; reconnection policy now lives in
   `DeviceSessionCoordinator` (`startReconnecting()`/`stopReconnecting()`/
   `scheduleReconnectIfNeeded`), and `DeviceProvider` is a thin caller that also gates
   every callback on `sessionCoordinator.isReady(generation:)` to reject stale events —
   this generation-fencing pattern wasn't in the old description at all.
4. **Bee and PLAUD no longer use bespoke response-correlation dictionaries.** The old audit
   describes Bee's `responseCompleters: [UInt16: CheckedContinuation]` and PLAUD's
   `commandQueues: [Int: PassthroughSubject]`. Both now go through the shared
   `DeviceCommandQueue` (serializes the request/response exchange) + `DeviceOperationBroker`
   + `UncorrelatedOperationGate` (poisons a command ID if its response arrives after the
   caller already gave up, rather than risking a stale response being read as the next
   command's answer). PLAUD's recording-session start/stop is now owned by a
   `DeviceAudioStreamController` (first-subscriber-starts/last-subscriber-stops semantics)
   rather than ad hoc retry logic in the connection class.
5. **Two Mac-side citations were simply wrong, independent of any timing question**: the
   device-type-detection function is `BtDevice.detectDeviceType(...)`, not
   `DeviceType.detectDeviceType(...)` (it lives in `BtDevice.swift`); and
   `src/renderer/src/lib/voice/echoGate.ts` does **not** contain a `BLUETOOTH_RE` regex or
   any Bluetooth-mic-avoidance logic — that regex (`BLUETOOTH_RE`) exists only in
   `src/renderer/src/lib/audio.ts`, and it's about **input** device selection. `echoGate.ts`
   has a differently-named `HEADSET_RE` for classifying the **output** device (to decide
   whether the echo-cancellation gate can relax during assistant playback) — a related but
   distinct piece of Bluetooth-adjacent logic that happens to reuse the substring
   `"hands-free"`. This file has been in this exact (non-Bluetooth-named) form since
   2026-07-10, six weeks before the old audit described it wrong — a clear case of the
   audit citing code without reading it.
6. **`koffi`'s footprint on Windows is far larger than the old audit implied.** The old
   audit characterized existing `koffi` usage as "limited to Win32 `user32` calls for
   foreground-window/automation." Current source shows `koffi` driving `user32.dll`,
   `kernel32.dll`, `advapi32.dll`, and `dwmapi.dll` across five files (global key-state
   sampling, process-snapshot enumeration, a registry-backed consent store with an
   async-wait pattern, foreground-window tracking with `WinEventProc` hooks, and a
   UserAssist registry reader) — all following the same "lazy-load the DLL, never throw,
   degrade to `null`/disabled" pattern. This doesn't change the "no WinRT/BLE usage today"
   conclusion, but it means a future BLE port has a much richer, battle-tested native-FFI
   pattern to extend rather than a single call site to generalize from.
7. Two small precision fixes with no status implications: Bee's ADTS extraction is
   explicitly documented in-source as draining **every** complete frame per notification
   (a `while` loop, doc comment: "Drains every complete ADTS frame the notification
   completed, not just the first") — the old audit's "extracts one AAC frame at a time"
   phrasing was ambiguous enough to misread as one-per-notification, which was true before
   a 2026-07-19 fix. And `BleTransport.ping()` no longer has a separately named
   `readRSSIAsync()` placeholder function — it's now inlined as a two-line fire-and-forget
   in `ping()` itself; the behavior (issue `readRSSI()`, don't actually await a value) is
   unchanged, just the old audit's specific function-name citation no longer resolves.

Net: **0 Windows-side status changes** (everything is still `Absent`, correctly), but **7
corrections to the Mac reference material**, two of which (transport rewrite, echoGate.ts
misattribution) are significant enough that a porter following the old doc verbatim would
have designed against an architecture that no longer exists and cited a file that doesn't
do what was claimed.

## Summary table

| Capability / device | Mac location(s) | Windows status | Value (H/M/L) |
|---|---|---|---|
| CoreBluetooth scanning/discovery | `Bluetooth/BluetoothManager.swift` | Absent | H |
| Device model + type detection | `Bluetooth/BtDevice.swift`, `Bluetooth/DeviceType.swift` | Absent | H |
| GATT service/characteristic UUID registry | `Bluetooth/DeviceUUIDs.swift` | Absent | H |
| Transport abstraction (BLE) | `Bluetooth/Transports/DeviceTransport.swift`, `Bluetooth/Transports/BleTransport.swift` | Absent | H |
| Session/connection-reliability layer | `Bluetooth/Session/*.swift` (5 files) | Absent | H |
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

**How it works**: `BluetoothManager` is a `@MainActor` singleton wrapping a lazily-created `CBCentralManager` (lazy specifically to avoid triggering the macOS Bluetooth permission dialog at app startup). `startScanning(timeout:)` scans with `withServices: nil` and `CBCentralManagerScanOptionAllowDuplicatesKey: false` (deliberately unfiltered on service UUID — needed because PLAUD detection requires reading raw manufacturer advertisement data rather than a service UUID) and auto-stops via a `Timer` after the timeout. `CBCentralManagerDelegate` callbacks (`didDiscover`, `didConnect`, `didFailToConnect`, `didDisconnectPeripheral`) run `nonisolated` and hop to `@MainActor` via `Task`. **Connection lifecycle no longer goes through `NotificationCenter`** (the old `bleDeviceConnected`/`bleDeviceDisconnected`/`bleDeviceFailedToConnect` notifications are gone): `BluetoothManager` now owns a `BluetoothConnectionLeaseRegistry` and issues a `BluetoothConnectionLease` per `beginConnection(to:sessionGeneration:)` call; the three terminal delegate callbacks resolve that lease and broadcast a typed `BluetoothCentralEvent` (`.connected`/`.failedToConnect`/`.disconnected`, each carrying the lease) over a `centralEventPublisher` (`PassthroughSubject`), which `BleTransport` subscribes to directly rather than observing global notifications — a callback whose peripheral has no active lease is logged and ignored (`"Ignoring unleased CoreBluetooth ... callback"`) instead of being misdelivered to a stale transport. Also exposes `triggerPermissionPrompt()` (issues a throwaway scan+immediate-stop specifically to force the macOS permission dialog) and a `DeviceBluetoothManaging` protocol used to inject a fake for tests.

**Windows status**: Absent. `grep -rliE "bluetooth|\bble\b|gatt|coreBluetooth|pendant|wearable|CBUUID|CBCentralManager" src/main src/renderer` returns no real hits — the handful of matches are false positives (`PendingAttachment` case-insensitively contains `...ngAtt...` which matches the `gatt` pattern) plus the unrelated system-audio-input Bluetooth-*avoidance* logic (see closing note, itself corrected below).

**Value / notes**: macOS framework: `CoreBluetooth` (`CBCentralManager`/`CBPeripheral`). Windows equivalent: WinRT `Windows.Devices.Bluetooth.Advertisement.BluetoothLEAdvertisementWatcher` for scanning + `Windows.Devices.Bluetooth.BluetoothLEDevice`/`GattDeviceService` for GATT, accessed from Node either via a native N-API/WinRT projection addon or via `koffi` FFI calling the WinRT ABI. Windows' existing `koffi` usage is now considerably broader than a single call site — see the corrected closing note — but it is still Win32 (`user32`/`kernel32`/`advapi32`/`dwmapi`), not WinRT/COM, so BLE support remains genuinely new native-integration surface. The lease/generation-fencing pattern the Mac side now uses for "don't let a stale async callback resurrect a dead connection" is a design worth replicating regardless of which native bridge is chosen — Windows will have the identical class of problem (a `BluetoothLEAdvertisementWatcher`/`GattDeviceService` callback arriving after the caller moved on).

## Device model, type detection, and codec enum

**What it is**: The `BtDevice` struct (identity/RSSI/info fields) plus `DeviceType` (9 supported hardware families) and `BleAudioCodec` (8 codec variants + `.unknown`) that everything else keys off of.

**Where (Mac)**: `Bluetooth/BtDevice.swift`, `Bluetooth/DeviceType.swift`.

**How it works**: `BtDevice.detectDeviceType(peripheral:advertisementData:)` **(note: this is a static method on `BtDevice`, not on `DeviceType` — the previous audit cited it as `DeviceType.detectDeviceType`, which does not exist)** runs a priority-ordered match: advertised name substring (`"bee"`, `"plaud"`, `"compass"`/`"fieldy"`, `"friend_"` prefix, `"limitless"`/`"pendant"`) OR advertised service UUID match against `DeviceUUIDs`. PLAUD detection is special-cased: it reads `CBAdvertisementDataManufacturerDataKey`, checks manufacturer ID `93` (`0x5D`), and pattern-matches a known NotePin byte signature (`0456cf00`) — this is the reason scanning can't be service-UUID-filtered. OpenGlass is not detected at scan time; it's upgraded from `.omi` post-connection once GATT service discovery reveals an image-data-stream characteristic (`BtDevice.checkingForOpenGlass(services:)`). `DeviceType` is a 9-case enum (`omi`, `openglass`, `frame`, `appleWatch`, `plaud`, `bee`, `fieldy`, `friendPendant`, `limitless`) — unchanged from the previous audit. `BleAudioCodec` encodes codec id, sample rate (all 16kHz), bit depth, frame size/length, and FPS — this enum is the single source of truth threaded through the connection, processor, and decoder layers. `BtDevice` also owns pairing persistence (`saveAsPairedDevice()`/`loadPairedDevice()` via `UserDefaults` + `Codable`).

**Windows status**: Absent — no equivalent model, enum, or detection logic. `grep -rliE "device.?connection|device.?type|omi.?device|deviceprovider" src/main src/renderer` — no matches.

**Value / notes**: Pure Swift/data-model logic; trivially portable to TypeScript once a BLE transport exists — the detection rules and codec table are the actual reusable IP here, not the platform API calls. This section is otherwise unchanged from the 2026-08-20 audit (these three files have had no functional edits since the June desktop-split; only the incorrect method-owner citation needed fixing).

## GATT service/characteristic UUID registry

**What it is**: Centralized enum of every BLE service and characteristic UUID for every supported device.

**Where (Mac)**: `Bluetooth/DeviceUUIDs.swift`.

**How it works**: Namespaced `enum`s per device/subsystem — `Omi` (main/settings/features services, audio+image+control characteristics), `Button`, `Storage` (data/read-control/wifi characteristics), `Accelerometer`, `Battery`/`DeviceInfo` (standard BLE SIG 16-bit UUIDs `180F`/`2A19`, `180A`/`2A24`/`2A26`/`2A27`/`2A29`), `Speaker`, `Frame`, `PLAUD` (128-bit UUIDs + manufacturer ID `93`), `Bee`, `Fieldy`, `FriendPendant`, `Limitless`. `allSupportedServiceUUIDs` aggregates the primary service UUIDs (unused for scanning today, since scanning is unfiltered, but available for a service-UUID-filtered scan mode).

**Windows status**: Absent.

**Value / notes**: Same UUIDs would carry over verbatim to a WinRT `GattDeviceService`/`GattCharacteristic` implementation — this file alone is most of the protocol contract a porter needs. Unchanged since the 2026-08-20 audit.

## Transport abstraction (BLE)

**What it is**: A `DeviceTransport` protocol (connect/disconnect/read/write/notify-stream/ping/dispose) with `BleTransport` as the CoreBluetooth-backed implementation, decoupling device-specific logic from the raw BLE API.

**Where (Mac)**: `Bluetooth/Transports/DeviceTransport.swift`, `Bluetooth/Transports/BleTransport.swift` (677 lines — nearly double the size implied by the previous audit's description, almost entirely the reliability machinery below).

**How it works — this section is substantially rewritten from the 2026-08-20 audit, which described a pre-refactor version of this file.** `BleTransport` no longer implements `CBPeripheralDelegate` directly or bridges via raw `CheckedContinuation` dictionaries. It now wraps a `physicalDriver: any BLEPhysicalDriving` (a `CoreBluetoothPhysicalDriver` in production, injectable for tests) and is constructed with a `sessionGeneration: UInt64` stamped by the caller (`DeviceConnectionFactory`/`DeviceSessionCoordinator`) plus an `AnyPublisher<BluetoothCentralEvent, Never>` subscription — no `NotificationCenter` involvement. `connect()` runs three sequential operations (connect → discover services → discover characteristics per service), each executed through a `DeviceOperationBroker` with a 10-second timeout and an `ensureConnectionIsValid()` check after every step; a failure at any step marks the transport `isConnectionInvalidated`, cancels all pending operations, and requests a physical disconnect — there is no 500ms "let discovery settle" sleep anymore. `readCharacteristic`/`writeCharacteristic(withResponse: true)` key their `DeviceOperationBroker<String, Data/Void>` entries by a **composite `"service:characteristic"` key** via `operationKey(serviceUUIDString:characteristicUUIDString:)`, plus an `UncorrelatedOperationGate` per operation type that refuses to start a new read/write if a prior one's callback is still "uncorrelated" (i.e., could still arrive and be mistaken for the new one) — this is the exact same-characteristic-UUID-across-services collision the previous audit flagged as a "latent bug, not exercised" in the old dictionary-keyed design; it no longer exists as a hazard. `getCharacteristicStream` still lazily enables notifications and fans out into a `CharacteristicStreamBroadcaster`, cached by the same `"service:characteristic"` key. `ping()` is now a two-line fire-and-forget (`guard physicalDriver.state == .connected else { return false }; physicalDriver.readRSSI(); return true`) — connectivity-check-only, same intent as before, but there's no longer a separately named `readRSSIAsync()` placeholder to cite. `handleCentralEvent(_:)` resolves the `BluetoothCentralEvent` into whichever `DeviceOperationBroker` handle is waiting, and ignores events whose lease doesn't match `connectionLease` (guards against a superseded session's stray callback).

**Windows status**: Absent.

**Value / notes**: macOS framework: `CoreBluetooth` peripheral delegate model, now wrapped behind `BLEPhysicalDriving` specifically so it's fakeable in tests. Windows equivalent: WinRT `GattDeviceService.GetCharacteristicsAsync` / `GattCharacteristic.ValueChanged` event (real async APIs) plus `WriteValueAsync`/`ReadValueAsync`. The `DeviceTransport` protocol boundary itself is still what a Windows port should replicate as a TS interface — but a porter should also replicate the *operation-broker + composite-key + uncorrelated-callback-gate* pattern underneath it, not just the old continuation-dictionary shape the previous audit described; WinRT's async APIs remove the need for continuation-bridging at all, but a Windows port will still need equivalent defense against a `ValueChanged`/connection-status callback arriving after the awaiting call already timed out or the session was superseded — the generation/lease pattern below is the reusable design, independent of transport choice.

## Session/connection-reliability layer (not covered by the previous audit)

**What it is**: A five-file subsystem (`Bluetooth/Session/*.swift`, ~1,140 lines) that owns connection-attempt identity, reconnection policy, and per-device command/audio-session serialization — factored out from what used to be ad hoc logic scattered across `BluetoothManager`, `BleTransport`, `DeviceProvider`, and individual connection classes. The 2026-08-20 audit didn't mention this layer at all because the description it was working from predated the refactor that introduced it (2026-07-11 – 2026-07-19).

**Where (Mac)**: `Bluetooth/Session/DeviceSessionCoordinator.swift` (406 lines), `Bluetooth/Session/DeviceOperationBroker.swift` (365 lines), `Bluetooth/Session/BluetoothConnectionLease.swift` (114 lines), `Bluetooth/Session/DeviceCommandQueue.swift` (70 lines), `Bluetooth/Session/DeviceAudioStreamController.swift` (185 lines).

**How it works**:
- `BluetoothConnectionLease` — a value type (`peripheralID`, `token`, `sessionGeneration`) minted by `BluetoothManager.beginConnection(to:sessionGeneration:)`. CoreBluetooth delegate callbacks carry only a peripheral, not a lease; the lease registry keeps one active per peripheral until a terminal callback (or a central-state reset) fires, so a *later* connection attempt on the same peripheral identity can't have an *earlier* attempt's stray callback misattributed to it.
- `DeviceOperationBroker<Key, Value>` — a generic "one pending async operation per key, with a timeout and explicit terminal reasons (`succeeded`/`timedOut`/`cancelled`/`disconnected`/`failed`)" primitive. Replaces the raw `CheckedContinuation` dictionaries the previous audit described throughout the transport and per-device connection classes.
- `UncorrelatedOperationGate<Key>` — tracks operations whose physical callback identifies only a key (not a broker-generated token). If such an operation times out or is cancelled before its real callback arrives, the key is **poisoned** (further operations on that key are refused) until session teardown, rather than risking a late callback being read as the response to a *new* operation on the same key.
- `DeviceSessionCoordinator` — a `@MainActor` state machine (`idle` → `connecting` → `ready` → `disconnecting` / `waitingToReconnect(attempt:)`) that is "the canonical owner for the logical lifecycle of one paired Bluetooth device" (source doc comment). Every connect attempt gets a monotonically increasing `generation`; `isReady(generation:)` is the guard every downstream consumer (battery monitoring, storage-sync check, firmware check, accelerometer/fall-detection) now checks before acting on a callback, so a callback from a session that has since been superseded is a no-op instead of corrupting current state. Owns the actual reconnect *policy* (`scheduleReconnectIfNeeded(after:)`: zero-delay direct-reconnect attempt first, escalating to a delayed attempt that also requests a fresh discovery scan) that `DeviceProvider.startReconnectionTimer()` used to own directly per the old audit.
- `DeviceCommandQueue` — serializes a device's request/response command exchanges end-to-end (not just the wait for one response), used by Bee and PLAUD (see their sections below) to close a race where a second command could be rejected locally after its response gate was already registered.
- `DeviceAudioStreamController` — owns "first subscriber starts the physical recording session, last subscriber leaving stops it" semantics for devices with an explicit device-side recording-session lifecycle (PLAUD), with generation-tagged start/stop actions so a subscriber that disappears mid-setup can't leave an orphaned recording session running.

**Windows status**: Absent.

**Value / notes**: This is the single most valuable file group for a Windows porter to study before writing any BLE code, independent of transport choice — WinRT's `GattCharacteristic.ValueChanged`/connection-status-changed events have the exact same "callback can arrive after I stopped caring" hazard class that this layer defends against, and getting that wrong is what produced the "double-resume crash, observer leak, audio wedge" class of bugs this layer was built to fix on Mac. A Windows port should design its own generation/lease equivalent from day one rather than discovering the same races empirically.

## Device connection protocol + base implementation

**What it is**: `DeviceConnection` — the full per-device API surface (battery, audio, button, storage, camera, accelerometer, speaker/haptic, features, LED/mic settings, WiFi sync) — with `BaseDeviceConnection` providing default implementations against the standard Omi GATT layout, which per-device subclasses override.

**Where (Mac)**: `Bluetooth/Connections/DeviceConnection.swift` (781 lines).

**How it works**: `BaseDeviceConnection.connect()` is now an explicit single-shot lifecycle guarded by `didStartLifecycle`/`teardownTask` (a second `connect()` call while one is in flight, or after teardown started, throws `.alreadyConnected` rather than silently racing): `transport.connect()` → `ensureLifecycleIsActive()` → `ping()` (non-fatal if it fails, still checked via `ensureLifecycleIsActive()` after) → `updateDeviceInfo()` (Device Information Service: model/firmware/hardware/manufacturer) → `prepareDeviceAfterConnect()` (device-specific hook) → flips `isReadyForCallbacks = true`. Any failure at any step routes through one `beginTeardown(...)` path shared with explicit `disconnect()`/`unpair()`, which is memoized as a single `Task` (`teardownTask`) so a second concurrent teardown request joins the first instead of running twice — the delegate's `didDisconnectUnexpectedly` callback fires only when teardown was triggered by an actual transport-state drop, not an explicit caller-initiated disconnect. `getAccelerometerStream()` parses 12-byte little-endian 6×Int16 packets into `AccelerometerData` and computes a fall-detection magnitude (`> 30.0` threshold) that triggers `DeviceConnectionDelegate.deviceConnection(_:didDetectFall:)` — wired through to `DeviceSessionCoordinator.onFallDetected` and from there to `DeviceProvider`'s local notification. `getFeatures()` reads a 4-byte little-endian bitmask into `OmiFeatures` (`OptionSet`: speaker/accelerometer/button/battery/usb/haptic/offlineStorage/ledDimming/micGain/wifi) and caches it. Storage list parsing decodes 4-byte little-endian `Int32` file-length entries. WiFi sync default implementation validates SSID/password length constraints and returns "not supported" unless overridden.

**Windows status**: Absent.

**Value / notes**: This is the largest single porting surface — 20+ methods, each with byte-level wire format baked in (little-endian multi-byte fields throughout). A Windows port should keep this exact protocol/base-class split so per-device subclasses stay small, and should keep the single-shared-teardown-path pattern (rather than letting explicit disconnect and unexpected-disconnect handling diverge) — that convergence is precisely what several of the pre-audit bugfix commits were about.

## Connection factory (device type → connection)

**What it is**: Maps a detected `DeviceType` to the correct `DeviceConnection` subclass, constructing a fresh `BleTransport` per connection.

**Where (Mac)**: `Bluetooth/Connections/DeviceConnectionFactory.swift`.

**How it works**: `create(device:peripheral:connectionController:centralEvents:sessionGeneration:operationClock:)` — the signature grew from the previous audit's `create(device:peripheral:centralManager:)`: it now threads through a `BluetoothCentralConnectionControlling` (the lease-issuing boundary, satisfied by `BluetoothManager`), the `centralEvents` publisher, the caller-assigned `sessionGeneration`, and an injectable `operationClock` (test seam for every internal timeout/sleep). It builds one `BleTransport` and switches on `device.type`: `.omi`/`.openglass` → `OmiDeviceConnection`; `.plaud` → `PlaudDeviceConnection`; `.bee` → `BeeDeviceConnection`; `.fieldy` → `FieldyDeviceConnection`; `.friendPendant` → `FriendPendantConnection`; `.limitless` → `LimitlessDeviceConnection`; `.frame` → `FrameDeviceConnection` (partial); `.appleWatch` → `nil` (would use `WatchConnectivity`, not BLE — unimplemented). A convenience overload resolves the `CBPeripheral` via `BluetoothManager.shared.peripheral(for:)` and supplies the manager itself as both the connection controller and the event source.

**Windows status**: Absent.

**Value / notes**: Straightforward switch-based factory; low risk to port once the connection classes and the session/reliability layer above exist. The signature growth (generation + operation clock threaded through construction) is itself informative — it's the concrete evidence that every connection class now participates in the generation-fencing scheme end to end, not just the transport.

## Omi / OpenGlass device connection

**What it is**: The reference/primary device implementation — audio streaming, OpenGlass image streaming, LED dim + mic gain settings, and WiFi sync setup/start/stop with response-code handling.

**Where (Mac)**: `Bluetooth/Connections/OmiDeviceConnection.swift`.

**How it works**: On connect, probes `hasPhotoStreaming()` (a characteristic-read to `imageDataStream`) to auto-upgrade `.omi` → `.openglass`. Image streaming: reassembles frames from 2-byte little-endian frame-index-prefixed chunks, with `0xFFFF` as an end-of-image marker and `0` as start-of-image; firmware ≥ 2.1.1 embeds a 1-byte orientation code in frame 0, older firmware defaults to `orientation180`; has a 200KB buffer-overflow guard that discards and resets. WiFi sync: `setupWifiSync` validates credentials, races a 5-second timeout `Task` against a response-stream `Task` reading `WifiSyncErrorCode` from `Storage.wifi`, and returns a `WifiSyncSetupResult`; `startWifiSync`/`stopWifiSync` are single-byte command writes (`0x02`/`0x03`) to the same characteristic. Unchanged in substance from the 2026-08-20 audit; only the constructor now also takes an `operationClock`.

**Windows status**: Absent.

**Value / notes**: Highest-value single connection class to port first — it's Omi's own hardware protocol (not third-party reverse-engineered), and covers audio + image + WiFi sync + settings in one place.

## Friend Pendant connection (LC3 codec)

**What it is**: Connection for the "Friend" pendant, using LC3 audio at 16kHz/10ms frames.

**Where (Mac)**: `Bluetooth/Connections/FriendPendantConnection.swift`.

**How it works**: BLE notifications arrive as 95-byte packets (90 bytes LC3 payload = 3× 30-byte frames, + 5-byte footer); `processAudioPacket` strips the footer, then the payload is split into 30-byte frames and pushed individually into an `audioStreamSubject`. No real battery reporting — hardcodes 90% and republishes it via a `operationClock.sleep(for: .seconds(30))` loop (previously described as "every 30s," same behavior, now explicitly driven by the injectable clock so it's test-controllable). No button, photo, accelerometer, or features support (all stubbed to empty/false). Device info is hardcoded (no Device Information Service read).

**Windows status**: Absent.

**Value / notes**: LC3 decode itself is unimplemented even on Mac (see Audio Codec Decoders section, confirmed still a placeholder) — porting this connection class doesn't unblock real audio without also sourcing/porting `liblc3`.

## Bee connection (AAC/ADTS codec)

**What it is**: Connection for "Bee" devices, using AAC audio with ADTS framing and a binary request/response command protocol.

**Where (Mac)**: `Bluetooth/Connections/BeeDeviceConnection.swift`.

**How it works**: Two characteristics on one service: a control characteristic (2-byte little-endian command IDs, e.g. mute/unmute `0xC006`, battery `0xC00F`) and an audio characteristic. **Command sending now goes through the shared session-layer primitives rather than a private `responseCompleters: [UInt16: CheckedContinuation]` dictionary as the previous audit described**: `sendCommand` runs the whole exchange through a `DeviceCommandQueue` (serializing overlapping calls), and the actual wait is a `DeviceOperationBroker<UInt16, Data>` entry guarded by a `responseGate: UncorrelatedOperationGate<UInt16>` (refuses to start a new command on a command ID whose previous response is still ambiguous). Responses can still arrive either directly keyed by command ID or as an "echo" wrapper (`0x8000` response code containing the original command ID + payload) — that dual-shape handling is unchanged. Audio: raw notification bytes (minus a 2-byte prefix) accumulate in `audioBuffer`, then an ADTS-sync-word scanner (`0xFF`, top nibble `0xF`) extracts frames one at a time in a `while` loop that **drains every complete frame the notification completed**, not just the first (source doc comment is explicit about this — a 2026-07-19 fix, `fix(desktop): drain all Bee ADTS frames per BLE notification`, closed a bug where only the first frame per notification was drained; a partial trailing frame correctly stays buffered for the next notification). Recording is explicitly started/stopped via mute/unmute commands, now via the shared `DeviceAudioStreamController` rather than bespoke state (mirrors the mic being physically gated by a device-side mute state, not just stream-open/close).

**Windows status**: Absent.

**Value / notes**: AAC decode is fully implemented on Mac via `AudioToolbox` (see Audio Codec Decoders) — this is one of the more "complete" third-party integrations.

## Fieldy / Compass connection (Opus FS320)

**What it is**: Connection for Fieldy/Compass devices using Opus at the FS320 (320-sample/20ms, 50fps) variant with fixed 40-byte frames.

**Where (Mac)**: `Bluetooth/Connections/FieldyDeviceConnection.swift`.

**How it works**: Single characteristic serves both control and audio. Each BLE notification packs 6× 40-byte Opus frames (240 bytes); the connection slices them and validates each frame's first byte against the Opus TOC value `0xb8` (logs but still forwards non-matching frames rather than dropping them). No button/photo/accelerometer/features support. Battery uses the standard BLE Battery Service directly (not command-based like Bee/PLAUD). Unchanged in substance from the 2026-08-20 audit (only the constructor gained an `operationClock` parameter, consistent with every other connection class).

**Windows status**: Absent.

## Brilliant Labs Frame connection (partial — SDK-gated)

**What it is**: Connection stub for Brilliant Labs' Frame smart glasses; explicitly **not** a full implementation even on Mac.

**Where (Mac)**: `Bluetooth/Connections/FrameDeviceConnection.swift`.

**How it works**: Frame's real protocol requires Brilliant Labs' proprietary Lua-scripting SDK (text commands like `"MIC START"`/`"CAMERA START"`, response prefixes `0xEE`=audio/`0xCC`=battery/`0xE1`-`0xE4`=status, a heartbeat every 5s, and an echo-ack protocol) — still none of it implemented; the file's trailing comment block still documents what a real implementation would need, confirmed unchanged. What *is* implemented: standard BLE Battery Service reads/streaming, a hardcoded PCM8 codec declaration, and a base64-embedded JPEG header constant (`photoHeader`) intended to prepend Frame's headerless raw JPEG data (unused until real image streaming exists). `getAudioStream()`, `startPhotoCapture()`, `getImageStream()` all still log a warning and return empty/no-op.

**Windows status**: Absent.

**Value / notes**: Lowest value to port as-is (it doesn't work on Mac either) — a Windows port would need the same upstream Frame SDK dependency regardless of platform.

## Limitless Pendant connection (protobuf-like + batch/realtime modes)

**What it is**: The most protocol-complex connection — a hand-rolled protobuf-wire-format encoder/decoder over BLE, supporting both live audio streaming and bulk download of on-device "flash page" recordings, plus button, LED, and storage-status queries.

**Where (Mac)**: `Bluetooth/Connections/LimitlessDeviceConnection.swift` (1,144 lines).

**How it works**: Implements varint encode/decode and protobuf tag (field-number + wire-type) parsing by hand (no protobuf library). All outbound commands go through a common `encodeBleWrapper` (message-index/sequence/fragment-count/payload fields) + `encodeRequestData` (auto-incrementing request ID) envelope. Inbound BLE notifications are parsed as `BlePacket{index, seq, numFrags, payload}` and reassembled via a `fragmentBuffer: [Int: [Int: [UInt8]]]` (outer key = message index, inner = fragment sequence) until `numFrags` fragments are collected, then dispatched to either real-time audio handling (`handleRealTimePayload`, extracts Opus frames directly) or batch/"pendant message" handling (`handlePendantMessage`, recurses through nested protobuf fields to find storage buffers → flash pages → embedded Opus frames), selected by an `isBatchMode` flag. Storage-status queries now run through a `DeviceOperationBroker<String, [String: Int]>` + `UncorrelatedOperationGate` pair (`storageStatusOperations`/`storageStatusGate`) rather than an ad hoc continuation — consistent with the session-layer convergence described above. Varint and embedded-length parsing throughout `extractOpusRecursive` and the flash-page/protobuf field walkers are explicitly clamped/bounds-checked (source comments: "A malformed varint can decode to a negative value ... or a length that overflows `Int` — cap the read ... and range-clamp before it indexes anything") — this hardening (three separate 2026-07-11/07-18 commits: "cap BLE varint length to protobuf max," "clamp malformed BLE protobuf field lengths to prevent parse crash," "clamp Limitless flash-page/opus varint lengths to stop OOB crash") predates the 2026-08-20 audit and was already reflected there in substance ("validates candidate frames by length range"), just not attributed to hostile/malformed input specifically. Opus frame extraction still validates candidate frames by length range (10–200 bytes) and a TOC-byte whitelist (`0xb8, 0x78, 0xf8, 0xb0, 0x70, 0xf0`) — broader than the Fieldy check. Also parses button double-press events and device/storage status out of the same notification stream by scanning for specific protobuf field markers — clearly derived from Limitless's actual wire format via reverse engineering, not a public schema.

**Windows status**: Absent.

**Value / notes**: Would be the most expensive single connection class to port — it's a bespoke binary protocol implementation, not a thin GATT wrapper, and one that has already needed three separate crash-hardening passes against malformed device input. A port needs either the Swift parsing logic (including its bounds-checking) transliterated line-for-line or a from-scratch re-derivation against Limitless hardware — transliterating without the clamps would reintroduce the exact OOB crashes Mac already fixed.

## PLAUD NotePin connection

**What it is**: Connection for PLAUD NotePin, using a request/response command protocol over one write + one notify characteristic, with an explicit device-side recording-session lifecycle (start record → start sync → stream → stop sync → stop record).

**Where (Mac)**: `Bluetooth/Connections/PlaudDeviceConnection.swift`.

**How it works**: Commands are `[0x01, cmdIdLow, cmdIdHigh] + payload`, sent on `writeCharacteristic`. **The previous audit's `commandQueues: [Int: PassthroughSubject]` description is stale**: commands now run through a `DeviceCommandQueue` (serializing the exchange) wrapping a `DeviceOperationBroker<Int, Data>` + `UncorrelatedOperationGate<Int>` (`commandOperations`/`commandGate`), same pattern as Bee. Audio arrives as notifications where byte 0 == `2` signals an audio-data packet; `parseAudioChunk` reads a 4-byte position field (bytes 4-7, little-endian; `0xFFFFFFFF` = end marker) and a 1-byte length (byte 8) to slice the actual Opus payload, which then gets re-chunked into fixed 80-byte pieces before forwarding. **The recording-session start/stop retry logic the previous audit described inline is now owned by a `DeviceAudioStreamController`**: `setupRecordingSession()` is the controller's `start` action (retries up to 3 times with backoff: stop any existing recording (session 0), `startRecord()` (returns session ID + device start-timestamp), then `startSync(sessionId:start:)`), and a corresponding `stopRecordingSession()` is the controller's `stop` action — the controller itself guarantees the audio stream doesn't start flowing until setup actually completes, and that a subscriber disappearing mid-setup can't leave a recording session orphaned. Battery command response is `[isCharging, batteryLevel]`.

**Windows status**: Absent.

## WiFi sync (offload sync over the device's own WiFi radio)

**What it is**: A device-initiated bulk-sync path where the wearable connects to a WiFi network directly (bypassing BLE's low bandwidth) to upload buffered audio, orchestrated by a short BLE handshake for credentials/status.

**Where (Mac)**: `Bluetooth/WifiSyncTypes.swift` (error codes, validation, result types); implemented per-device in `OmiDeviceConnection` (others default to unsupported via `BaseDeviceConnection`); gated by `OmiFeatures.wifi` bit; consumer-side polling and low-priority "storage sync available" notification logic lives in `Providers/DeviceProvider.swift` (`checkPendingStorageSync`, `storageSyncAvailable` notification).

**How it works**: `WifiSyncErrorCode` maps 8 firmware response codes (success, invalid packet/setup length, SSID/password length invalid, session-already-running, hardware-not-available, unknown-command) to user-facing messages. `WifiCredentialsValidator` enforces SSID ≤32 bytes UTF-8, password 8–63 bytes UTF-8. `DeviceProvider.checkPendingStorageSync()` (now gated by `sessionCoordinator.isReady(generation:)` like every other DeviceProvider callback) asks a `StorageDataChecker` closure for total/current byte offsets, and only surfaces a "pending sync" system notification if the gap exceeds ~10 seconds of audio (80 bytes/frame × 100fps × 10s heuristic threshold). Unchanged in substance from the 2026-08-20 audit.

**Windows status**: Absent.

**Value / notes**: Meaningful only in combination with a device connection that supports it (currently only Omi/OpenGlass). Self-contained validation/error-code logic — cheap to port once any BLE connection exists.

## BLE audio frame reassembly + processing pipeline

**What it is**: The shared layer that turns raw BLE notification bytes (packet-framed, pre-framed, or protobuf-wrapped depending on device) into individual codec frames, then into PCM samples, tracking loss/throughput statistics along the way.

**Where (Mac)**: `Audio/BleAudioProcessor.swift`.

**How it works**: Two entry paths depending on device: `processAudioData(_:)` for devices needing frame reassembly — branches by codec into `processFramedData` (Fieldy 40-byte / "LC3" 30-byte fixed-size slicing) or `processPacketData` (Omi's own scheme: `[indexLow, indexHigh, frameId, ...content]` headers, with `frameId == 0` starting a new frame, sequential `frameId` continuing it, and gap detection between `lastPacketIndex` values incrementing a `lostPackets` counter when the jump looks like real loss rather than an overflow/reset, capped at <100 to avoid false positives from wraparound). `processFrame(_:)` / `processFrames(_:)` is the entry path for devices that pre-extract frames themselves (Bee, Limitless) — goes straight to the codec decoder. Every completed frame is decoded via the codec's `AudioCodecDecoder` (falling back to `PCMPassthroughDecoder` if `decoder` is nil and codec `.isPCM`) and emitted on both a delegate callback and a Combine `pcmSamplesPublisher`/`pcmDataPublisher`. Tracks consecutive decode failures (logs once at failure #1, escalates to error at failure #10) and validates Opus TOC bytes on failure for diagnostics. Includes WAV-file helpers (`createWavHeader`/`createWavData`) used elsewhere for local audio export. `BleAudioProcessor.forDevice(_:)` maps each `DeviceType` to its default starting codec. Confirmed unchanged since 2026-08-20 (last functional edits to this file were four fixes on 2026-07-19: abort-on-supersede during codec read, dropped spurious await, stream-death recovery, dropped dead per-session buffer — all predating the audit).

**Windows status**: Absent.

**Value / notes**: This is genuinely reusable, mostly-pure logic (byte-buffer parsing + a Combine publisher) — the least platform-coupled piece in the whole stack, and the highest-leverage file to port first since every device connection funnels through it.

## BLE→transcription coordination service

**What it is**: The `@MainActor` singleton that wires a live `DeviceConnection`'s audio stream through `BleAudioProcessor` into the app's transcription pipeline (or a raw-data/raw-frame callback for WAL recording), and computes a live audio-level meter.

**Where (Mac)**: `Audio/BleAudioService.swift`.

**How it works**: `startProcessing(from:transcriptionService:audioDataHandler:rawFrameHandler:)` reads the device's codec via `connection.getAudioCodec()`, refuses unsupported codecs (checks `AudioDecoderFactory.isSupported`), warns on partial-support codecs (`hasFullSupport` — currently only LC3), constructs a per-session `BleAudioProcessor`, and pumps `connection.getAudioStream()` through a device-type `switch` in `processDeviceAudio` that decides whether to call `processor.processAudioData` (needs reassembly: Fieldy/FriendPendant/PLAUD/Omi/OpenGlass) or `processor.processFrame` (pre-framed: Bee/Limitless) — this switch still duplicates/depends on knowledge that's also implicit in each connection class, a coupling point a Windows port should probably collapse (e.g. have each connection self-report whether it emits raw or pre-framed data). Decoded PCM is forwarded to `transcriptionService?.sendAudio(_:)` (mono; diarization is server-side) and to an optional custom `audioDataHandler`; raw pre-decode bytes go to `rawFrameHandler` for WAL/local recording. Also computes a smoothed (70/30 exponential) RMS audio level for UI meters, and has an unused `convertToStereo` helper. Confirmed unchanged since 2026-08-20 (last edits: the same four 2026-07-19 fixes noted above, which touch this file's `BleAudioProcessor` interaction, not this file's own structure).

**Windows status**: Absent.

## Audio codec decoders (Opus / AAC / µ-law / PCM / LC3-stub)

**What it is**: Per-codec decode implementations converting encoded frames to 16kHz mono Int16 PCM.

**Where (Mac)**: `Audio/AudioCodecDecoder.swift`.

**How it works**: `AudioDecoderFactory.createDecoder(for:)` dispatches by `BleAudioCodec`. `PCMPassthroughDecoder` handles pcm8 (unsigned→signed 16-bit expansion, ×256 scale) and pcm16 (direct little-endian reinterpret) with no real "decoding." `OpusAudioDecoder` uses `AudioToolbox`'s `AudioConverterNew`/`AudioConverterFillComplexBuffer` with `kAudioFormatOpus` as input format id (frame size 160 samples/10ms for standard Opus, 320/20ms for FS320); validates TOC byte but decodes even if invalid — hardened 2026-07-13 (`fix(desktop): harden Opus decoder TOC read against non-zero-based Data slices`, before the audit) against a non-zero-based `Data` slice miscomputing the TOC offset. `AACAudioDecoder` similarly uses `AudioToolbox` with `kAudioFormatMPEG4AAC`, validates the 7-byte ADTS sync word and extracts the embedded frame-length before decoding — hardened 2026-07-12 against a malformed frame-length crash. `MulawAudioDecoder` implements ITU-T G.711 µ-law expansion via a precomputed 256-entry lookup table — fully self-contained, no OS codec dependency. `LC3AudioDecoder` is confirmed still an explicit placeholder: it does not decode LC3 at all, logs a warning, and returns silence sized to the expected sample count; the file's doc comment still specifies what a real implementation needs (`liblc3`, `lc3_setup_decoder`/`lc3_decode`, 10ms frames, 30 bytes/frame, 160 samples/frame output). `AudioDecoderFactory.isSupported`/`hasFullSupport` still distinguish "won't crash" from "actually produces audio" — only LC3 is in the gap between those two.

**Windows status**: Absent.

**Value / notes**: macOS framework: `AudioToolbox` (`AudioConverterRef`) for Opus/AAC. Windows has no built-in equivalent; a port would need either a portable Opus library (e.g. libopus via native binding) plus Windows Media Foundation or a userland AAC decoder for Bee, and µ-law/PCM port trivially (pure math). LC3 is unimplemented on **both** platforms today — porting Friend Pendant doesn't unblock real audio without sourcing `liblc3` regardless of OS. Note that two of the three decoder hardening fixes above (Opus TOC slice offset, AAC ADTS frame-length) are exactly the class of malformed-input crash a Windows port using different native codec libraries would need to re-derive defenses for independently — they aren't protocol facts that transfer, they're bugs in *this* implementation's use of `AudioToolbox`.

## Device state/lifecycle provider (scan / connect / reconnect / battery / firmware)

**What it is**: The app-facing `ObservableObject` that owns overall device state — scanning, connecting, the active connection, paired-device persistence, auto-reconnection, battery monitoring + low-battery alerts, storage-support detection, firmware-update-check stub, and fall-detection/disconnect local notifications.

**Where (Mac)**: `Providers/DeviceProvider.swift` (683 lines).

**How it works — reconnection ownership has moved since the previous audit.** `DeviceProvider` (`@MainActor` singleton, `DeviceProvider.shared`) now holds a `DeviceSessionCoordinator` (`sessionCoordinator`) and delegates connection-attempt identity, generation fencing, and reconnect *policy* to it: `startReconnecting()`/`stopReconnecting()` are one-line forwards to `sessionCoordinator.startReconnecting()`/`stopReconnecting()`, and `connect(to:)`/reconnect attempts go through `sessionCoordinator.connect(to:)`/`sessionCoordinator.reconnect(_:)` rather than a `DeviceProvider`-owned 15-second polling `Timer` as the previous audit described (`startReconnectionTimer()` no longer exists in this file). Every downstream side-effect method (`startBatteryMonitoring`, `checkLowBattery` via its caller, `checkStorageSupport`, `checkPendingStorageSync`, `checkFirmwareUpdates`) now takes the connection's `generation` and calls `sessionCoordinator.isReady(generation:)` before touching published state — a callback that resolves after the session has moved on (reconnected as a new generation, or torn down) is silently dropped instead of writing stale state, which is the actual mechanism replacing the ad hoc checks the previous audit didn't describe in this much detail. Behaviorally the observable surface is the same as previously documented: persists the paired device to `UserDefaults` (id/name/type only), unpair goes through `sessionCoordinator.unpair()` and is explicitly distinguished from an unexpected disconnect so the app doesn't prompt to reconnect a device the user just intentionally removed (2026-07-18 fix, predates the audit). Battery: initial read + a `getBatteryLevelStream()` subscription; `checkLowBattery()` fires a local notification once when level crosses below 20% (latched via `hasLowBatteryAlerted`). Storage support: checks `connection.getStorageList()` is non-empty, then asks an injected `StorageDataChecker` closure for pending-sync byte counts and posts a `storageSyncAvailable` notification if the gap is large enough. Firmware-update checking is still an explicit **stub** — logs "Would check firmware updates" and never calls a real API (tracked via #10240, same ticket referenced elsewhere in this repo's deferred-work markers). `handleDisconnection()` still schedules a 30s-delayed "device disconnected" local notification, cancelable if reconnection succeeds first, and fall-detection still routes to a local notification — both now arriving via `DeviceSessionCoordinator`'s `onSessionEnded`/`onFallDetected` callbacks rather than `DeviceConnectionDelegate` conformance directly on `DeviceProvider`.

**Windows status**: Absent.

**Value / notes**: This is the orchestration layer a Windows port would eventually need to replicate in the Electron main process (or a renderer service, depending on where BLE access lives in the chosen bridge). The reconnection *heuristics* (direct-reconnect-first, then rescan) are unchanged and still directly portable design decisions, but a porter should design the generation-fencing discipline in from the start — it's what turned an implicit "hope stale callbacks don't matter" system into an explicit one, and retrofitting it later (as Mac had to) means finding every one of these races by crash report first.

## Spotted outside my scope

- `desktop/windows/src/renderer/src/lib/audio.ts` (not `echoGate.ts` — **correcting the previous audit's citation**) contains the actual Bluetooth-*avoidance* logic for input-device selection: `const BLUETOOTH_RE = /bluetooth|hands-free/i` (line 18), used in `acquireMicStream()` to prefer a non-Bluetooth real microphone when the system default input is a virtual/loopback device. `src/renderer/src/lib/voice/echoGate.ts` is a *different* module with a *different* purpose: it classifies the **output** device (`HEADSET_RE = /headphone|headset|earbud|earphone|airpod|hands-free|\bbuds|in-ear/i`, line 33) to decide whether Omi's own voice can physically leak back into the mic, and therefore whether the always-on-transcription echo gate needs to stay active during assistant playback — it has no role in *picking* an input device at all. The previous audit's claim that `echoGate.ts` "already contain[s] Bluetooth-avoidance logic (a `BLUETOOTH_RE` regex ... used to deprioritize Bluetooth/HFP mics when picking the Windows system audio-input device)" is wrong on the variable name, the file's actual purpose, and which device role it inspects; `echoGate.ts` has existed in this exact form since 2026-07-10 (Phase 6 voice modules), five to six weeks before the audit that mis-described it. Both files remain unrelated to wearable BLE pairing and worth flagging so a future BLE-wearable port doesn't confuse either with device-connection code.
- Windows' `koffi` footprint is considerably larger than "foreground-window/automation helpers" — current source actually loads a DLL via `koffi` in exactly five files (a broader `grep -rl koffi` hits twelve files, but seven of those are comments or type-only references with no `koffi.load` call): `src/main/bar/keyState.ts` (global key-state sampling via `user32.dll`), `src/main/meeting/processSnapshot.ts` (process enumeration via `kernel32.dll`'s `CreateToolhelp32Snapshot`), `src/main/meeting/micConsentStore.ts` (a registry-backed consent store via `advapi32.dll`/`kernel32.dll`, including koffi's async/worker-thread FFI mode for a blocking wait), `src/main/usage/nativeForeground.ts` (foreground-window tracking via `user32.dll`/`dwmapi.dll` plus `WinEventProc` hooks), and `src/main/usage/userAssistRegistry.ts` (`advapi32.dll` UserAssist registry reads). `koffi` itself is declared at `desktop/windows/package.json:109` (not `:70` as previously cited — the file has grown since). All five follow the same "lazy-load the DLL inside a function, never throw, log-and-degrade to `null`/disabled on any failure" pattern — a real, repeatedly-validated template for a future WinRT/BLE native bridge, even though none of it touches WinRT or Bluetooth today.

---

**Verification note (2026-08-22)**: `git log --since=2026-08-20` across every Mac Bluetooth/Audio/Provider file this document cites, and across all of `desktop/windows/`, returns only this parity-audit doc series' own commits — nothing in the underlying implementation changed in the two days between the previous audit and this one. Every correction above is a fix to how the 2026-08-20 audit described pre-existing code (most of it 4-6 weeks stale at the time it was written), not a new landing.
