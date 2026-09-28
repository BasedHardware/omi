# Android host (omi-v5)

The Android app consumes the **same** Swift sources as iOS/macOS: the Skip
skipstone plugin transpiles `OmiKit` and `OmiUI` to Kotlin, and this Gradle
project compiles that output into an APK. Product logic never appears here —
this module is bootstrap, injection, and intent plumbing only.

## Status on this machine

**Not buildable here.** There is no Android SDK, NDK, or JDK configured in
this environment, and the `skip` transpiler wrapper expects a macOS/Linux
host with the Skip toolchain. Everything in this directory is **statically
reviewed only**: the Gradle/Kotlin/CMake sources are written and linted by
eye against the real generated output (see below), but no Gradle build has
ever run against them.

What *is* verified on macOS:

- `swift build --scratch-path .build/scratch-platforms` succeeds, producing
  the exact Kotlin trees this project wires as source sets
  (`omi.kit.NativePolicyBridge`, `omi.ui.RootView`, `omi.ui.AppModel`).
- The JNI bridge's method set matches the transpiled
  `omi.kit.NativePolicyBridge` interface one-for-one.
- The C ABI symbols called in `omi_jni.c` exist in
  `native-core/include/*.h`.

## What a developer needs

1. **Android Studio** (or plain SDK/NDK): compile SDK 35, min SDK 26, NDK
   with CMake ≥ 3.22.1 and a C++20 toolchain.
2. **JDK 17.**
3. **Swift 6 toolchain + Skip** (`brew install swiftpkg/formulae/skip` or per
   skiptools docs) — the `skip` tool is not available on this machine; the
   skipstone run itself happens inside `swift build` via the SwiftPM plugin.

## Build steps

```sh
# 1. From the repo root: generate the Kotlin (skipstone output).
swift build --scratch-path .build/scratch-platforms

# 2. From this directory:
./gradlew :app:assembleDebug        # or open in Android Studio and Run
./gradlew :app:installDebug         # to a connected device/emulator
```

A Gradle wrapper (`gradlew`) is not committed yet — install Gradle 8.7+ or
generate one with `gradle wrapper`. The skipstone output under
`.build/` is generated and never committed; regenerate after any OmiKit or
OmiUI change.

## How the wiring works

- **Skipstone output** — `app/build.gradle.kts` adds the transpiled
  `src/main` Kotlin trees (OmiKit, OmiUI, SkipModel, SkipLib, SkipFoundation,
  SkipUI) to the `main` source set. The outputs live under
  `<repo>/.build/scratch-platforms/plugins/outputs/`.
- **MainActivity** — a Compose `ComponentActivity` that installs the JNI
  policy bridge and presents the transpiled `omi.ui.RootView` over
  `omi.ui.AppModel`. It routes `omi-rnruntime://auth/callback` (browser
  intent + PKCE per `docs/auth-and-sessions.md`) to the session seam.
- **native-core** — `src/main/cpp/CMakeLists.txt` builds the SAME four C++
  sources the Apple hosts compile into `libomi_native_core_jni.so`, plus
  `omi_jni.c`, a pure marshalling shim. Relative path from the CMake dir to
  `native-core/` is `../../../../../../native-core`.

## Injection contract

`omi.kit.Policy.bridge` is the process-wide policy object. On Apple it
defaults to `DefaultPolicyBridge` (direct C ABI). On Android the default is
unusable, so `OmiPolicyJniBridge.installOnce()` replaces it at first
`onCreate` with a JNI-backed implementation of `omi.kit.NativePolicyBridge`.
No Kotlin code anywhere re-derives capture-path allowlists, timeouts, or
hostname classes — see `native-core/AGENTS.md`.
