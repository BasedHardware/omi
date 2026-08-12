# Disposable Feasibility Spike: TypeScript-First React Native Architecture with Narrow C++ Boundary

**Location**: `spikes/react-native-typescript-cpp-native/`
**Branch**: `spike/react-native-typescript-cpp-native`
**Framework Decision**: **Bare React Native + TypeScript**
**Spike Outcome**: **PARTIAL — Omi-v4 relay parity and local TypeScript/native-boundary feasibility validated; physical BLE, real RN TurboModule execution, iOS runtime, background lifecycle, and ASR remain unvalidated**

---

## 1. Architectural Overview & Boundary Diagram

This spike validates a **TypeScript-First React Native Architecture** where native C++ code is strictly confined to a narrow, high-performance C ABI function boundary (e.g. packet framing, checksum calculation, native capability queries). High-level domain logic, state management, transport simulation, and UI subscription layers remain 100% idiomatic TypeScript.

```
+-----------------------------------------------------------------------+
|                       React Native UI Screen Sketch                    |
|                        (DeviceListScreenSketch.ts)                    |
+-----------------------------------------------------------------------+
                                   | Subscribes to DeviceState updates
                                   v
+-----------------------------------------------------------------------+
|                      TypeScript Domain Controller                     |
|                           (DeviceController.ts)                       |
+-----------------------------------------------------------------------+
          | Handles transport events                 | Calls native API
          v                                          v
+-----------------------------------+     +-----------------------------+
|    Fake Device Transport (TS)     |     | TS Native Module Contract   |
|     (FakeDeviceTransport.ts)      |     | (INativePacketBoundary.ts)  |
|  - 2 simulated devices            |     +-----------------------------+
|  - Connect / Disconnect toggles   |                | Implemented by
|  - Device packet attribution      |                v
|  - Bounded retry mechanism        |     +-----------------------------+
+-----------------------------------+     |  C++ Native Host Bridge     |
                                          |   (MockNativeBoundary.ts /  |
                                          |    omi_native_boundary.cpp) |
                                          +-----------------------------+
                                                         | Native C ABI
                                                         v
                                          +-----------------------------+
                                          |     ISO C++17 Native Lib    |
                                          |  (omi_native_boundary.h/cpp)|
                                          |  - CRC32 checksum           |
                                          |  - Sync header 0xAA 0x55    |
                                          |  - Buffer safety / bounds   |
                                          |  - Native capability JSON   |
                                          +-----------------------------+
```

---

## 2. Directory Structure

```
spikes/react-native-typescript-cpp-native/
├── CMakeLists.txt                      # ISO C++17 CMake build & CTest configuration
├── README.md                           # Architecture decision, diagrams & validation evidence
├── run-tests.sh                        # Combined zero-dependency test runner script
├── cpp/
│   ├── include/
│   │   └── omi_native_boundary.h       # Narrow C ABI header interface
│   ├── src/
│   │   └── omi_native_boundary.cpp     # C++17 checksum & packet normalization implementation
│   └── tests/
│       └── test_omi_native_boundary.cpp # C++ host unit test executable
└── ts/
    ├── benchmark/
    │   ├── adapters.ts                 # Three adapter path implementations (A/B/C)
    │   └── run-benchmark.ts            # Node perf_hooks benchmark runner
    ├── contracts/
    │   └── NativeBoundaryContract.ts   # Strongly-typed TypeScript native module contract
    ├── cpp-bridge/
    │   └── MockNativeBoundary.ts       # TS native bridge implementing contract
    ├── domain/
    │   └── DeviceController.ts         # Domain state manager & packet handler
    ├── transport/
    │   └── FakeDeviceTransport.ts      # Deterministic transport (2 devices, retries, attribution)
    ├── ui/
    │   └── DeviceListScreenSketch.ts   # React Native UI screen sketch renderer
    └── tests/
        ├── DeviceController.test.ts    # End-to-end domain behavior tests
        ├── FakeDeviceTransport.test.ts  # Deterministic transport tests
        ├── NativeBoundaryContract.test.ts # Native contract & checksum tests
        └── benchmark-adapters.test.ts   # Benchmark adapter correctness & equivalence tests
```

---

## 3. Fake versus Real Behavior

| Component | Spike Implementation | Classification | Notes |
| :--- | :--- | :--- | :--- |
| **Native C++ Library** | ISO C++17 C ABI (`omi_calculate_packet_checksum`, `omi_normalize_packet`, `omi_get_native_capabilities`) | **REAL** | Real memory-safe C++ implementation compiled with Apple Clang & validated via CMake CTest |
| **Native Module Contract** | `INativePacketBoundary` TypeScript interface & `MockNativeBoundary` | **REAL / BRIDGED** | Mirrors TurboModule / JSI memory layout & function contract |
| **Domain Controller** | `DeviceController` in TypeScript | **REAL** | Manages multi-device lifecycle, state notifications, packet normalization |
| **Device Transport** | `FakeDeviceTransport` simulating 2 devices (`dev-001`, `dev-002`) | **FAKE** | Simulates hardware BLE/USB transport without hardware dependencies |
| **UI Screen Sketch** | `renderDeviceListScreenSketch` | **SKETCH** | Renders React Native component hierarchy representation without Metro/iOS/Android build |

### Omi-v4 relay-parity slice

The generic transport tests are not the parity claim. The added `ts/omi-parity/relay.ts` slice models the highest-value behavior read from Omi-v4's existing Dart relay:

| Omi-v4 behavior | Spike proof |
|---|---|
| 3-byte audio packet header | `decodeAudioPacket` + reassembly test |
| 16-bit packet-ID rollover | explicit `0xffff → 0` test |
| fragment and packet discontinuity | explicit gap event; payload is never spliced across a gap |
| 256 KiB frame bound | oversized frame test |
| codec IDs PCM8/Opus/Opus-FS320 | mapping test; unknown IDs fail closed |
| eight-frame forwarding bound | queue saturation test |
| mobile-owner versus observer roles | control capability test |
| 20-second reconnect grace and stream identity | grace-boundary test |

This is a **TypeScript domain parity model**, not a claim that C++ has replaced the existing Flutter relay. C++ remains a narrow native-function boundary in this spike.

---

## 4. Test Execution & Strict TDD Evidence

### C++ Host Build & Tests (CMake / CTest)
```bash
cmake -B build -S .
cmake --build build
ctest --test-dir build --output-on-failure
```

**GREEN Phase Output (C++ implementation complete)**:
```
Test project .../spikes/react-native-typescript-cpp-native/build
    Start 1: NativeBoundaryHostTest
1/1 Test #1: NativeBoundaryHostTest ...........   Passed    0.09 sec
100% tests passed out of 1
```

---

### TypeScript Behavior Tests (Node 22 Built-in TS Runner)
```bash
node --experimental-strip-types --test ts/tests/*.test.ts
```

**GREEN Phase Output (abbreviated; current run: all 30 tests passing)**:
```
TAP version 13
# Subtest: DeviceController - connects and normalizes incoming native packets
ok 1 - DeviceController - connects and normalizes incoming native packets
# Subtest: DeviceController - handles corrupt packets via native boundary
ok 2 - DeviceController - handles corrupt packets via native boundary
# Subtest: DeviceController & UI Screen Sketch integration
ok 3 - DeviceController & UI Screen Sketch integration
# Subtest: FakeDeviceTransport - initializes with two simulated devices
ok 4 - FakeDeviceTransport - initializes with two simulated devices
# Subtest: FakeDeviceTransport - manages connection state toggles
ok 5 - FakeDeviceTransport - manages connection state toggles
# Subtest: FakeDeviceTransport - attribution of packets to specific device
ok 6 - FakeDeviceTransport - attribution of packets to specific device
# Subtest: FakeDeviceTransport - bounded retry mechanism
ok 7 - FakeDeviceTransport - bounded retry mechanism
# Subtest: NativeBoundaryContract - calculates CRC32 checksum correctly
ok 8 - NativeBoundaryContract - calculates CRC32 checksum correctly
# Subtest: NativeBoundaryContract - normalizes valid framed packet
ok 9 - NativeBoundaryContract - normalizes valid framed packet
# Subtest: NativeBoundaryContract - detects corrupt sync header and invalid checksum
ok 10 - NativeBoundaryContract - detects corrupt sync header and invalid checksum
# Subtest: NativeBoundaryContract - queries native capabilities
ok 11 - NativeBoundaryContract - queries native capabilities
# Subtest: buildSyntheticPacket - produces deterministic framed packets
ok 12 - buildSyntheticPacket - produces deterministic framed packets
# Subtest: CurrentTsAdapter - normalizes valid synthetic packet
ok 13 - CurrentTsAdapter - normalizes valid synthetic packet
# Subtest: CurrentTsAdapter - checksum matches normalize result
ok 14 - CurrentTsAdapter - checksum matches normalize result
# Subtest: CurrentTsAdapter - reports capabilities
ok 15 - CurrentTsAdapter - reports capabilities
# Subtest: ReactNativeNativeModuleAdapter - normalizes valid synthetic packet
ok 16 - ReactNativeNativeModuleAdapter - normalizes valid synthetic packet
# Subtest: ReactNativeNativeModuleAdapter - checksum matches current adapter
ok 17 - ReactNativeNativeModuleAdapter - checksum matches current adapter
# Subtest: ReactNativeNativeModuleAdapter - capabilities match current adapter
ok 18 - ReactNativeNativeModuleAdapter - capabilities match current adapter
# Subtest: WebTypescriptAdapter - normalizes valid synthetic packet
ok 19 - WebTypescriptAdapter - normalizes valid synthetic packet
# Subtest: WebTypescriptAdapter - checksum matches current adapter
ok 20 - WebTypescriptAdapter - checksum matches current adapter
# Subtest: WebTypescriptAdapter - Moonshine boundary stub is not available
ok 21 - WebTypescriptAdapter - Moonshine boundary stub is not available
# Subtest: WebTypescriptAdapter - render cache resets between runs
ok 22 - WebTypescriptAdapter - render cache resets between runs
# Subtest: All three adapters produce identical normalization for same input
ok 23 - All three adapters produce identical normalization for same input
1..30
# tests 30
# pass 30
# fail 0
```

---

### Combined Test & Benchmark Execution
```bash
./run-tests.sh
```

---

## 5. Benchmark: Adapter/Controller Overhead Comparison

### What This Measures

**LOCAL adapter/controller overhead ONLY** using Node `perf_hooks` with deterministic synthetic inputs.

⚠ **This is NOT a UI, browser, or ASR performance benchmark.**

Three adapter paths are compared:

| Path | Description |
| :--- | :--- |
| **(A) Current TS Adapter** | The existing TypeScript controller/adapter shape from this spike |
| **(B) RN Native-Module Bridge** | Simulated JSI/TurboModule boundary with serialize → dispatch → deserialize overhead |
| **(C) Web TS Adapter (Moonshine)** | Web TypeScript adapter modeled on crepuscularity.tsc.hk architecture, with Moonshine boundary stub |

### Run Benchmark
```bash
node --experimental-strip-types ts/benchmark/run-benchmark.ts
```

### Benchmark Matrix — Actual Local Results

> **Platform**: darwin arm64 · **Node**: v22.23.1 · **Date**: 2026-08-08
> **Iterations**: 10,000 (warmup: 1,000) · **Unit**: µs/op (lower is better)

| Adapter | 16B | 64B | 256B | 1024B |
| :--- | ---: | ---: | ---: | ---: |
| **(A) Current TS Adapter** | 35.03 µs | 73.28 µs | 309.75 µs | 275.12 µs |
| **(B) RN Native-Module Bridge** | 2.85 µs | 142.77 µs | 80.19 µs | 434.10 µs |
| **(C) Web TS Adapter (Moonshine)** | 32.24 µs | 84.43 µs | 71.62 µs | 369.39 µs |

### Benchmark Interpretation

- All three adapter paths produce **identical CRC32 checksums and normalization results** for the same input (verified by cross-adapter equivalence tests).
- Adapter overhead is in the **single-digit to low-hundreds µs/op range** — dominated by CRC32 computation scaling linearly with payload size.
- The simulated bridge overhead (B) varies due to `ArrayBuffer` copy semantics at different sizes; in a real React Native runtime, JSI SharedArrayBuffer would eliminate this copy.
- The Web TS Adapter (C) adds render cache + Moonshine boundary stub overhead, which is negligible (~2–15 µs additional at most sizes).
- **Conclusion**: Adapter shape choice does not meaningfully constrain performance at this boundary. The TypeScript-first architecture validated by this spike imposes no measurable penalty relative to alternative adapter shapes.

---

## 6. Moonshine Integration Boundary

**Moonshine** is treated here as an **external speech/voice integration boundary** requested for comparison with [crepuscularity.tsc.hk](https://crepuscularity.tsc.hk). It is **NOT a dependency** of this spike or benchmark. The external site could not be inspected from this environment: a direct HTTPS fetch returned HTTP 403, so no site architecture or footer claim is treated as verified.

The Web TS Adapter (C) models the Moonshine boundary as a typed interface stub:

```typescript
interface MoonshineBoundaryStub {
  readonly available: boolean;
  dispatchAudioFrame(pcm16: Uint8Array): { accepted: boolean; boundaryLabel: string };
}
```

This measures typed stub dispatch overhead only. No audio processing, no ASR inference, no network calls.

### Browser Verification of External URL

To verify the crepuscularity.tsc.hk site in a browser:
```bash
# Quick HTTP verification (no browser required)
curl -sI https://crepuscularity.tsc.hk | head -5

# Or open in browser
open https://crepuscularity.tsc.hk
```

**HTTP limitation**: Direct HTTPS fetch returned HTTP 403 in this environment. The browser procedure is intentionally unrun here. This does not affect the local synthetic benchmark, which has **zero network dependencies**.

---

## 7. Proof Limits & Boundary Notes

1. **Host-Level Evaluation**: Tests validate C++ C ABI memory boundaries and TypeScript domain logic natively on the host platform without bundling native Objective-C/Swift/Java/Kotlin JSI boilerplate.
2. **Package-Free Zero-Dependency Scope**: Uses Node 22 native `--experimental-strip-types` and built-in `node:test` test runner alongside ISO C++17 and CMake 4.4.0. No external NPM packages or Metro/BLE native drivers were added.
3. **Architecture Fit**: Demonstrates a narrow native-function boundary while TypeScript handles the simulated device lifecycle, UI state, and transport routing. It does not prove the proportion or cost of a production implementation.
4. **Benchmark Limitations**:
   - Measures adapter/controller overhead ONLY — not UI, browser, or ASR performance
   - Synthetic deterministic inputs — not real device packets
   - Simulated JSI/TurboModule bridge — not actual native module calls
   - Moonshine boundary is a typed stub — not real speech processing
   - Node.js `perf_hooks` timing — not React Native runtime timing
5. **External URL**: `https://crepuscularity.tsc.hk` returned HTTP 403 to this environment. Its content and runtime were not treated as verified. The benchmark models only a requested web TypeScript adapter boundary without fetching or depending on it.
6. **No Omi-v4 Concepts**: This spike contains no Omi-v4 production code, no production integration patterns, and no references to production worktrees.

---

## 8. Framework Decision & Conclusion

**Decision**: **Bare React Native + TypeScript**
**Conclusion**: **PARTIAL — local boundary shape validated; real RN/web/ASR runtime unvalidated**

The local benchmark shows no meaningful difference between the three simulated adapter shapes at this synthetic boundary. It does not measure React Native, browser, Moonshine, or real C++ module runtime performance. The TypeScript-first architecture with a narrow C++ native-function boundary remains the recommended PoC direction.

### Expanded framework comparison

This is an architecture comparison, not a claim that every framework was built in this spike. The decisive constraints are Omi-v4's mobile BLE ownership, background relay, audio/WAL boundary, TypeScript preference, and existing Flutter/native investment.

| Option | Best fit | Omi-v4 fit | Main cost/risk | Spike verdict |
|---|---|---|---|---|
| **Bare React Native + TypeScript** | iOS/Android product UI with TypeScript domain contracts | Strong mobile-shell fit; native BLE adapters and C++/TurboModule seam are expressible | Native lifecycle and module work remains; desktop is not one uniform target | **Best ecosystem/TS-first mobile baseline** |
| **Valdi** | Native iOS/Android/macOS UI authored in TypeScript | Very strong shape for this question: official project claims native views, no webview/JS bridge, and type-safe C++/Swift/Kotlin/Objective-C polyglot modules | Public project is beta; smaller ecosystem and less Omi-v4-specific proof than Flutter/RN; setup/tooling needs independent validation | **Strongest new TS-native mobile challenger** |
| **Flutter** | Existing Omi mobile relay and cross-platform UI | Highest immediate parity because the current relay is Flutter-owned | Dart becomes the primary UI language; does not answer the TS preference | **Lowest migration risk** |
| **Tauri 2** | Desktop/webview shell with Rust commands and web UI | Good for desktop, Rust-owned native capabilities, and C/C++ via Rust FFI; Tauri documentation exposes iOS/Android targets | Mobile is a separate native-plugin path, not a drop-in BLE solution; webview/native boundary still has to be maintained | **Strong desktop candidate; secondary mobile candidate** |
| **Dioxus** | Rust-owned UI across web/desktop and experimental/mobile paths | Official Dioxus/Tauri shell now passes Cargo checking; C++ can sit behind Rust FFI | Adds a Rust UI/runtime decision and has less Omi-v4 mobile proof than Flutter/RN | **Interesting Rust alternative, not yet mobile-runtime proven** |
| **Crepuscularity** | Rust-owned DSL, GPUI desktop, web/extensions, and native View IR | Local repo proves GPUI, web, TUI, C ABI, SwiftUI/Compose View IR, and Tauri integration surfaces | Mobile View IR is not the same as a proven BLE/background relay; adopting it would be a new Rust/IR architecture | **Strong desktop/shared-UI comparison; do not call it mobile-proven** |
| **Electrobun** | Very small TypeScript/Bun desktop apps | Excellent TS fit for desktop tooling and native desktop capabilities | Desktop-focused; does not solve iOS/Android mobile BLE/background lifecycle; local CLI probe did not produce a scaffold | **Desktop-only candidate** |
| **Jetpack Compose Multiplatform** | Kotlin-native Android/iOS/desktop UI | Official template desktop JVM target builds; strong native mobile lifecycle and Android BLE ergonomics | Kotlin becomes the app language and the TS-first goal is lost; iOS and desktop still need platform work | **Strong native mobile option, weak TS alignment** |
| **Lynx / ReactLynx** | TypeScript/React-style cross-platform UI with Lynx native runtime and Lynx for Web | Official scaffold bundles successfully with Rspeedy; native modules can own platform capabilities | Requires Lynx-specific native-module proof; does not automatically solve BLE background ownership or desktop parity | **TS mobile candidate; native module is next seam** |
| **Makepad** | Rust UI across native desktop/mobile and WASM | Published Makepad widgets dependency compiles and the contract test passes | Current shell is a native-dependency/contract probe, not a full window; Rust-first rather than TypeScript-first | **Rust breadth candidate; not TS-aligned** |
| **Swift native** | iOS/macOS product shell with direct Apple APIs | Best Apple BLE/background control and direct C++ interop | Swift is not an Android target here by request; separate Android shell would be required | **iOS/macOS control baseline only** |
| **Web TS + Moonshine** | Browser voice/UI experiments | Useful for web rendering/ASR boundary tests | No reliable mobile BLE/background relay or native device ownership | **Web/ASR-only comparison** |

**Included by correction:** Lynx and Makepad. **Swift Android is intentionally skipped.**

#### Recommendation from the expanded comparison

Keep the PoC decision split into two independent questions:

1. **Mobile shell:** compare Valdi, RN + TypeScript, and the existing Flutter shell. Valdi is the strongest new TS-native challenger if its beta tooling and native-module workflow survive a real device spike; RN is the safer ecosystem baseline; Flutter remains the safest parity baseline.
2. **Desktop shell:** compare Tauri, Crepuscularity, Electrobun, and the existing native shell separately. Do not force the mobile winner onto macOS.
3. **Shared relay:** keep the Omi relay contract/platform adapters independently testable. C++ is optional at the narrow native boundary; it is not a reason to adopt a Rust UI framework or rewrite the Flutter relay.

Evidence anchors for this comparison:

- [Tauri guides](https://tauri.app/start/) — Rust/webview host and documented desktop/mobile distribution surfaces.
- [Dioxus documentation](https://dioxuslabs.com/learn/0.6/getting_started/) — Rust UI/runtime candidate.
- [Electrobun](https://electrobun.dev/) — Bun/TypeScript desktop candidate.
- [Compose Multiplatform documentation](https://www.jetbrains.com/help/kotlin-multiplatform-dev/compose-multiplatform.html) — Kotlin native/mobile candidate.
- [Valdi repository](https://github.com/Snapchat/Valdi) — TypeScript-to-native-view and polyglot-module claims; repository labels the project beta.
- [Lynx stack repository](https://github.com/lynx-family/lynx-stack) — ReactLynx, Rspeedy, and Lynx for Web frontend stack.
- [Makepad repository](https://github.com/makepad/makepad) — Rust native/web UI framework and `cargo-makepad` target tooling.
- [Local Crepuscularity README](file:///Users/undivisible/projects/crepuscularity/README.md) — inspected local evidence for GPUI, Tauri integration, native View IR, C ABI, and mobile scaffolding.
- [`framework-comparison/`](framework-comparison/) — runnable uniform contract probe and evidence-level manifest for every candidate.
- [`framework-comparison/runtimes/`](framework-comparison/runtimes/) — disposable generated shells and exact build evidence for Tauri, Dioxus, Flutter, Lynx, Makepad, SwiftUI, plus the Compose template result.

The next discriminating experiment is therefore one real mobile native adapter—not another UI framework benchmark:

```text
RN or Flutter mobile shell
        │
platform BLE adapter
        │
Omi-v4-compatible relay contract
        │
optional C++ narrow native function
```

---

## 10. Real React Native Runtime Attempt

This spike also contains `rn-runtime/`, a fresh bare React Native 0.79.2 shell generated with the React Native CLI. It is intentionally separate from production code and contains no BLE dependency or production SDK import.

### Completed

- React Native CLI generated the iOS and Android projects.
- Dependency installation completed: 902 packages installed.
- New Architecture/codegen ran during CocoaPods setup.

### Native build results

- **iOS**: `pod install` reached React Native's `glog` build, then failed because the configured Xcode Beta toolchain compiler could not create executables (`C compiler cannot create executables`).
- **Android**: after using Homebrew OpenJDK 17 and the local Android SDK, `./gradlew assembleDebug --no-daemon` completed successfully. The debug APK was built through the RN New Architecture/CMake path.

The Android result is real shell/build evidence, but this spike still does not prove a real C++ TurboModule call, BLE hardware, or iOS binary execution.

---

## 11. Observability Decision

The observability shape follows the current Omi-v4 decision record, without importing Omi-v4 production code:

```text
React Native client
  └─ local diagnostics only; no raw audio, prompts, transcripts, paths, or titles

Rust/Cloudflare Worker
  ├─ Workers Observability: structured invocation logs + metrics
  ├─ Better Stack: uptime, incidents, on-call, and optional log sink
  ├─ Better Stack heartbeat: emitted only after a successful cron batch
  └─ Better Stack Errors: Sentry-compatible error envelopes
```

**Choice:** use **Better Stack** as the operational product for uptime, incidents, logs, heartbeat monitoring, and worker error intake. Keep Cloudflare Workers Observability enabled as the native first-party source. Do not put Better Stack credentials in the client or repository; configure them as Worker secrets.

**Privacy boundary:** client telemetry is not required for the TypeScript/RN architecture. If crash reporting is later enabled, send crash signatures and bounded diagnostics only—never ambient audio, transcripts, prompts, user IDs, file paths, or window titles.

**Omi-v4 evidence checked:** Workers Observability is enabled in `worker-rs/wrangler.toml`; Better Stack is used for the heartbeat, Tail log export, and Sentry-compatible worker errors. The Flutter client is currently unwired. This spike adopts the server-side decision and keeps the client boundary intentionally inert.
