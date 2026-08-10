# Lynx Native Architecture

This spike uses Lynx as the UI/runtime owner and keeps Omi product logic in a shared native core.

## Boundary model

```text
Lynx TS UI
  -> typed Omi JS facade
  -> Lynx native-module contract
  -> platform adapter (Kotlin / Swift + ObjC++)
  -> narrow C ABI
  -> shared Omi C++ core
```

### Lynx owns

- template parsing, layout, rendering, and UI events;
- native-module dispatch from JavaScript;
- template/resource loading through the host-provided Lynx provider contract;
- generic resource fetching when enabled by the host.

### The platform shell owns

- app lifecycle and window/view creation;
- app bundle and asset packaging;
- supplying Lynx's template provider with bytes;
- OS permissions, Bluetooth/audio/background execution, and secure storage;
- registering the platform native module;
- JNI/Objective-C++ ABI adaptation.

### Shared C++ owns

- packet framing, validation, normalization, and checksums;
- transport-independent protocol state;
- deterministic data models and error codes;
- no UI, Lynx, JNI, Swift, or Objective-C dependencies.

## Native module domains

`OmiNativeModule` is the narrow relay boundary, not the whole application. Keep domains explicit as the spike grows:

1. **Core relay** — capabilities, packet normalization, protocol/session state.
2. **Device transport** — BLE discovery, connection, notifications, writes, reconnect policy.
3. **Capture** — microphone/system-audio permissions and frame ingestion.
4. **Persistence** — secure credentials, small local settings, migration state.
5. **Lifecycle** — foreground/background transitions and service ownership.
6. **Diagnostics** — structured status/events, never ad-hoc UI strings.

Each domain should expose a separate Lynx module or a clearly namespaced method group. Platform code adapts OS APIs; C++ remains the canonical protocol implementation.

## Data contracts

- JS-to-native binary payloads use base64 at the current Lynx boundary. Native adapters decode immediately and return base64 only at the boundary.
- Native methods return JSON-compatible objects until Lynx structured return behavior is proven on both platforms.
- Every response carries an explicit status/error code; unavailable capabilities are not represented as successful empty values.
- Event streams should use a single subscription surface with namespaced event names, for example `transport.state` and `capture.frame`, rather than polling UI state.
- Packet size limits are enforced before crossing into C++ and again by the C++ ABI.

## Runtime lifecycle

```text
Shell launch
  -> create Lynx view/config
  -> register modules/providers
  -> load bundled template
  -> restore native session state
  -> expose capability snapshot
  -> subscribe UI to native events

Shell background
  -> native transport/capture policy decides what continues
  -> Lynx view may be suspended
  -> state remains in native coordinator, not React component state

Shell resume
  -> reconcile native state
  -> emit one authoritative snapshot
  -> UI renders from snapshot/events
```

The UI must not own BLE/audio/session lifetimes. Those belong to a native coordinator with platform adapters.

## Current implementation status

- Bundled template loading is wired through Lynx providers on Android and iOS.
- Android and iOS register `OmiNativeModule`.
- Both adapters call the shared packet boundary.
- iOS device bundle ID is `hk.tsc.example` with automatic development signing team `LZ3NL5434Q`.
- Physical iOS installation succeeded; launch still requires the device to be unlocked.
- Packet success-path execution on physical hardware remains a validation gate.

## Next implementation order

1. Replace the UI's direct `NativeModules` reads with a typed `omiNative` facade and structured status parsing.
2. Add a shared native coordinator interface for lifecycle/session state.
3. Add a transport module contract with state snapshots plus event delivery.
4. Add secure credential storage behind the platform shells; never put secrets in Lynx storage.
5. Add adapter smoke tests and a device verification script for install, launch, capabilities, and packet success.

## Non-goals

- Do not move BLE/audio/permissions into TypeScript merely to reduce native files.
- Do not claim Android/iOS runtime parity from host C++ tests or simulator builds.
- Do not make Lynx responsible for app signing, provisioning, or OS background policy.
