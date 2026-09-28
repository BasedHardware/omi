# Platform hosts

Thin per-platform shells for the shared Swift app (`Package.swift` at the
repo root). Each host does **only** bootstrap, injection of platform
implementations, and window/permission plumbing — every product surface
comes from `OmiUI.RootView(model: OmiUI.AppModel)`, and all transport
policy comes from `OmiKit` (which binds the C++ `native-core/` middleware).

```
Platforms/
  ios/       xcodegen iOS app host (SwiftUI @main)
  macos/     xcodegen macOS app host (v5 glass window contract)
  android/   Gradle app module consuming the Skip skipstone Kotlin output
  windows/   swift-winrt + WinUI 3 host (source-only)
```

## The NativePolicyBridge injection contract

`OmiKit.Policy` fronts the shared C++ middleware (`native-core/`) and
exposes a process-wide `Policy.bridge: NativePolicyBridge`. Hosts must
guarantee the bridge binds the SAME C++ on every platform:

- **iOS / macOS** — nothing to do: `DefaultPolicyBridge` links `CNativeCore`
  (the real `native-core/src/*.cpp`) through the C ABI.
- **Android** — SwiftPM's C ABI does not exist on Kotlin, so the host
  replaces `Policy.bridge` at first launch with
  `app/Platforms/android/.../OmiPolicyJniBridge.kt`, which binds the same
  four `native-core/src/*.cpp` files through JNI (`externalNativeBuild`
  CMake + `omi_jni.c`). Policy is never re-derived in Kotlin
  (`native-core/AGENTS.md`).
- **Windows** — planned to link `CNativeCore` directly like Apple once the
  Windows Swift target exists (see `windows/README.md`).

## iOS (`ios/`)

```sh
cd app/Platforms/ios
xcodegen generate          # produces omi-v5-iOS.xcodeproj (gitignored)
open omi-v5-iOS.xcodeproj   # select the OmiHost scheme, run on a simulator
```

- `project.yml` + `Info.plist` + `OmiHost.entitlements` + `Sources/OmiHostApp.swift`.
- Bundle id: `org.reactjs.native.omi-v5-ios` (mirrors the RN tree's
  `org.reactjs.native.*` pattern). URL scheme `omi-rnruntime`
  (`omi-rnruntime://auth/callback` per `docs/auth-and-sessions.md`).
- Permission strings and background modes (`audio`, `bluetooth-central`)
  mirror `react-native/ios/RnRuntime/Info.plist`.
- Verified on macOS: `xcodegen generate` succeeds and the project builds
  against the root package. Not verified: on-device Bluetooth/auth runs.

## macOS (`macos/`)

```sh
cd app/Platforms/macos
xcodegen generate
open omi-v5-macOS.xcodeproj # run; grants needed: Screen Recording + Mic
```

- Implements the v5 window contract from `docs/desktop-app.md`: real
  behind-window `NSVisualEffectView` glass (`.hudWindow` dark /
  `.underWindowBackground` light, per upstream `desktop/macos` InkGlass and
  the RN `OmiGlassPanelView.mm` pattern), hidden titlebar material,
  titlebar accessory spacer of `OmiChromeRowHeight + OmiWindowInset`
  (44 + 12), traffic lights centered on the chrome row by shifting the
  titlebar container, `movableByWindowBackground` dragging.
- **Values are pinned to `OmiWindowInset = 12.0` / `OmiChromeRowHeight =
  44.0`** — they must change together with
  `react-native/src/desktop/desktopChrome.ts`
  (`desktopWindowInset` / `desktopOmnibarHeight`), which
  `react-native/__tests__/macOSNativeBoundary.test.ts` asserts. Where the
  full chrome contract (single window, presentation sizes, permission
  guide, capture toggle availability) is asserted is commented inline in
  `Sources/OmiHostApp.swift`; the host ships the availability probes
  (`CGPreflightScreenCaptureAccess`, AVFoundation mic) that feed the
  toggle-hides-when-unavailable rule. **Every rebuild resets the Screen
  Recording TCC grant** — re-grant before testing capture.
- Single-window policy: one `WindowGroup` scene, no secondary windows in
  `Info.plist`.

## Android (`android/`)

**Verified: Kotlin transpile output only.** `swift build --scratch-path
.build/scratch-platforms` from the repo root generates the skipstone
Kotlin (`omi.kit.NativePolicyBridge`, `omi.ui.RootView`, `omi.ui.AppModel`)
that this Gradle project wires as source sets; no Gradle/NDK build has run
(no Android SDK on this machine). See `android/README.md` for exact
developer steps (`swift build` → `gradlew :app:assembleDebug`), the
skipstone output paths, and the JNI wiring
(`externalNativeBuild` CMake → `omi_jni.c` → the same `native-core` C++).

## Windows (`windows/`)

**Source-only.** See `windows/README.md`: swift-winrt projections
(`projections.yaml` + `generate-projections.ps1`, run on Windows), a WinUI 3
(C++/WinRT) host skeleton, and Swift platform sources (URLSession transport +
DPAPI credential stub) marked source-complete-but-unbuilt. Upstream
`desktop/windows` is a Rust/C++ app — this directory is the Swift-first path.

## What each host must never grow

No product logic, no route state, no re-derived policy, no direct
authenticated networking outside the injected OmiKit seams. If a host needs
a behavior, it belongs in OmiKit/OmiUI or the native-core boundary.
