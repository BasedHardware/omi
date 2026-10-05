# Android host (omi-v5)

The Android app consumes the **same** Swift sources as iOS/macOS: the Skip
skipstone plugin transpiles `OmiKit` and `OmiUI` to Kotlin, and this Gradle
project builds that output into an APK. Product logic never appears here —
this module is bootstrap, injection, and intent plumbing only.

## Status

The debug APK builds on macOS and launches to the Welcome screen on an
emulator. `connectedDebugAndroidTest` covers SSE frame streaming and
redirect refusal on device. No auth, network, or BLE facade is injected yet,
so the app stays at the Welcome gate.

## Requirements

- Android SDK with an NDK and CMake 3.22.1.
- JDK 21 (`JAVA_HOME`), Gradle 9.
- Swift 6 toolchain; the Skip transpiler runs inside `swift build` through
  the SwiftPM plugin.

## Build steps

```sh
# 1. From the repo root: generate the Kotlin (skipstone output).
swift build --scratch-path .build/scratch-platforms

# 2. From this directory:
gradle :app:assembleDebug
gradle :app:installDebug                 # to a running emulator/device
gradle :app:connectedDebugAndroidTest    # on-device tests
```

Pass `-Pkotlin.incremental=false` after regenerating the skipstone output:
Kotlin incremental compilation reports spurious cross-file errors when Skip
rewrites every file. The skipstone output under `.build/` is generated and
never committed; regenerate after any OmiKit or OmiUI change.

## How the wiring works

- **Skipstone output** — `settings.gradle.kts` finds the OmiUI skipstone
  project under `<repo>/.build/scratch-platforms/plugins/outputs/` (or
  `.build/plugins/outputs/`), applies its settings for the `libs` and
  `testLibs` version catalogs, and includes it as a composite build. `:app`
  depends on `omi.ui:OmiUI`, which brings OmiKit and the Skip runtimes, on
  the AGP/Kotlin/Compose versions Skip generates.
- **OmiApplication / MainActivity** — the Application runs
  `ProcessInfo.launch` and installs the JNI policy bridge before any OmiKit
  call. MainActivity presents `RootView().environmentObject(store)` through
  Skip's `PresentationRoot` and routes `omi-rnruntime://auth/callback`
  (browser intent + PKCE per `docs/auth-and-sessions.md`) to the session
  seam.
- **native-core** — `src/main/cpp/CMakeLists.txt` builds the same C++
  sources the Apple hosts compile into `libomi_native_core_jni.so`, plus
  `omi_jni.c`, a pure marshalling shim. Strings cross JNI as UTF-8 byte
  arrays; inputs with embedded NULs are rejected.
- **Networking** — OmiKit sends backend requests through its own OkHttp
  client with redirects disabled and no response cache, rather than Skip's
  shared `URLSession` client.

## Injection contract

`omi.kit.Policy.bridge` is the process-wide policy object. On Apple it
defaults to `DefaultPolicyBridge` (direct C ABI). On Android it is unset
until `OmiPolicyJniBridge.installOnce()` installs the JNI-backed
implementation of `omi.kit.NativePolicyBridge`. No Kotlin code anywhere
re-derives capture-path allowlists, timeouts, hostname classes, text
decoding, or auth crypto — see `native-core/AGENTS.md`.
