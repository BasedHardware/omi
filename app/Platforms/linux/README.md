# Linux desktop host (omi-v5)

**Status: bootstrap-real, rendering-pending.** The host bootstrap (service
assembly, credential store, store lifecycle) is written and type-checked
against the shared package plus OpenSwiftUI on macOS (see "Verified" below).
No Linux build has run — there is no Linux toolchain on the dev machine, and
upstream OpenSwiftUI does not yet ship a Linux windowing layer.

Per the platform decision, the desktop UI layer for **Linux and Windows** is
[OpenSwiftUI](https://github.com/OpenSwiftUIProject/OpenSwiftUI) (MIT,
OpenSwiftUIProject). macOS stays on Apple SwiftUI (`../macos`); Android stays
on Skip/SkipUI (`../android`).

## What upstream OpenSwiftUI actually supports today (researched 2026-09)

From the project README platform table and `Renderer/Stdout/README.md`:

| Platform | Status |
|---|---|
| macOS / iOS Simulator | Best supported; partial AppKit/UIKit integration; binary XCFrameworks via [OpenSwiftUI-spm](https://github.com/OpenSwiftUIProject/OpenSwiftUI-spm) (macOS 15.5–26.0) |
| Ubuntu 22.04 | Builds and tests in CI, but deployment is the **stdout renderer only** — one terminal frame, **no window, no event loop, no text layout** (README suggests Pango as the future text provider) |
| Windows | **Not supported yet** (build ❌ / deploy ❌ in the upstream table) |
| Android | Not supported |

Implication, stated plainly: **OpenSwiftUI does not currently provide a GUI
window on Linux, and has no Windows support at all.** The directive to
standardize on it resolves *which UI framework* the Linux/Windows hosts build
toward; it does not by itself make a native window possible today. Reaching a
real Linux window requires either upstream GTK/Wayland/X11 integration work
(they request platform owners) or a host-side renderer integration. Windows
additionally needs upstream to ship Windows support, likely via swift-winrt
crossings — the same projections this tree already carries in `../windows`.

## Architecture

Same contract as every host (`../README.md`): this directory owns **only
bootstrap**. All product behavior lives in OmiKit + OmiUI; `RootView` renders
the injected `AppStore`.

```
linux/
  Package.swift                  standalone host package (NOT in the repo-root manifest)
  Sources/LinuxBootstrap.swift   FileCredentialStore, UserDefaults settings, service assembly
  Sources/OmiLinuxMain.swift     @main: builds AppStore, start(), arms the UI shell
  Sources/OmiOpenSwiftUIShell.swift  #if canImport(OpenSwiftUI) shell view (OpenSwiftUI's View protocol)
  Sources/OmiUIAdapter.swift     documents the RootView→OpenSwiftUI adapter decision
```

### Wired

- `FileCredentialStore: CredentialStoring` — 0600 JSON under
  `$XDG_DATA_HOME/omi-v5/session.json`. **Interim, not a secure store**: the
  Linux platform credential store is the Secret Service
  (gnome-keyring/libsecret, KWallet on KDE); swapping it in is pending.
- `UserDefaultsKeyValueStore: KeyValueStoring` — corelibs-Foundation
  `UserDefaults` is file-backed on Linux; no CoreFoundation type sniffing.
- The real `HTTPBackendTransport`, `ChatService`, `ReadsService`,
  `TasksService`, `CloudService`, `SettingsStore` — identical assembly to the
  macOS host minus the legs below.
- Store lifecycle: `AppStore(services:)` + `start()`/`stop()`.

### Pending (absent → degrades honestly in OmiUI)

- **`auth`** — needs a `BrowserAuthControlling` browser + loopback portal.
  `Network.NWListener` does not exist on Linux; the portal needs a different
  loopback server (GLib main loop, SwiftNIO, or raw sockets). Firebase API
  key comes from `OMI_FIREBASE_API_KEY` (no Info.plist convention).
- **`devices`** — CoreBluetooth is Apple-only; BlueZ transport is a separate
  platform seam to design.
- **`rewindCapture` / `rewindTimeline` / `rewindFrameImage`** — the rewind
  engine is ScreenCaptureKit; no Linux counterpart.
- **The product surface.** `OmiUI.RootView` conforms to Apple's
  `SwiftUI.View`. OpenSwiftUI defines its own `View` protocol — a SwiftUI view
  tree is not automatically an OpenSwiftUI view tree. Bridging is the
  `OmiUIAdapter` seam and needs a decision (see that file): a
  conditional-import shim module inside a fork of OmiUI, or an adapter that
  re-expresses `DesktopSurface` against OpenSwiftUI. Blocked on upstream
  coverage (windowing, text layout, materials, transitions) either way.
- **Native-core policy.** `OmiKit.Policy` binds the C++ `native-core` through
  `CNativeCore`'s C ABI; on Linux the C ABI compiles with the Swift toolchain
  like anywhere else — first Linux build will confirm nothing platform-specific
  leaked into the C++ (no reason to expect it; the Android JNI bridge binds
  the same files).

## What a developer runs (on Linux)

```sh
# Swift 6.3.3+ toolchain (swiftly or swift.org), plus upstream's deps:
sudo apt-get update && sudo apt-get install -y libssl-dev uuid-dev

cd app/Platforms/linux
# OpenSwiftUI on Linux must build from source — swap the binary dependency in
# Package.swift for https://github.com/OpenSwiftUIProject/OpenSwiftUI (source),
# per Renderer/Stdout/README.md, then:
swift run omi-linux-host          # today: bootstrap + status line; no window
OMI_FIREBASE_API_KEY=… swift run omi-linux-host
```

## Verified vs documented

**Verified on macOS (throwaway scratch project, /tmp, not committed):** the
host sources compile and the executable **runs** against this repo's OmiKit +
OmiUI (path dependency) and OpenSwiftUI-spm **0.22.0** (resolved from
`from: "0.19.1"`) on arm64, Swift 6.4 / Xcode 27: `swift build` clean, binary
prints the shell-armed status line. This proves the bootstrap is type-correct
and the OpenSwiftUI API surface used (`VStack(spacing:)`, `Text`, `.padding()`,
`View.body`) exists upstream.

**Not verified:** anything on actual Linux or Windows (no toolchain here);
no Linux/Windows binary was produced; the `FileCredentialStore` round-trip is
source-reviewed only; Swift 6 language-mode behavior on corelibs-Foundation.
