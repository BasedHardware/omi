# Windows host (omi-v5)

**Status: source-only.** Nothing in this directory has ever been built —
there is no Windows SDK, swift-winrt, or Windows App SDK on this macOS
machine. Files are written and reviewed as source; expect import and codegen
fixes on the first real Windows build.

Context: upstream (`omi/main`) ships a `desktop/windows` desktop app written
in Rust/C++ — not Swift. This directory is the **Swift-first** host path for
branch `v5-swift`: the shared OmiKit/OmiUI Swift package reaches Windows via
Swift's Windows toolchain, with swift-winrt providing the WinRT surface
projections the host needs.

## Components

| File | What it is |
|---|---|
| `projections.yaml` | swift-winrt generator config naming the needed namespaces: `Windows.Devices.Bluetooth`, `Windows.Devices.Radios`, `Windows.Storage`, `Windows.Networking`, `Windows.Security.Credentials`, `Windows.UI.ViewManagement` |
| `generate-projections.ps1` | PowerShell script to run **on Windows** to emit the Swift projections into `Generated/` |
| `CMakeLists.txt` | Build skeleton: Swift static lib + WinUI 3 (C++/WinRT) host executable |
| `Sources/WindowsTransport.swift` | URLSession-backed transport plumbing (Foundation on Windows) + DPAPI credential store stub — source-complete but **unbuilt** |
| `host/App.cpp`, `host/MainWindow.{h,cpp}`, `host/pch.h` | WinUI 3 host skeleton (bootstrap only, never compiled) |

## swift-winrt status (honest)

`swift-winrt` is `thebrowsercompany/swift-winrt` on GitHub, which The Browser
Company **archived** (early 2025). The last release still works for these
namespaces and remains downloadable from GitHub Releases, but the project is
unmaintained. Before committing to this path, decide and document one of:
pin the last release, fork, or adopt a community continuation. The archived
status is also noted inline in `generate-projections.ps1`.

## Host pattern choice

WinUI 3 via **C++/WinRT** (not the pure-Swift "swift-winui" pattern, which is
too immature to pin). The C++/WinRT shell owns the window; Swift platform
sources (transport, credential store) build as a static library the shell
consumes through a small C ABI bridge once projections land.

## What a developer runs (on Windows)

```powershell
# 1. Swift for Windows toolchain installed (swift.org downloads).
swift --version

# 2. swift-winrt (last release of thebrowsercompany/swift-winrt).
#    Generates Swift projections per projections.yaml.
powershell -File .\generate-projections.ps1

# 3. Build (Visual Studio 2022 + Windows App SDK + CMake/Ninja).
cmake -S . -B build -G Ninja
cmake --build build
```

## Unbuilt / unverified

- All of it. The projections config format is written against the archived
  tool's documented YAML and may need adjustment for the pinned release.
- `WindowsCredentialStore` deliberately throws `Unavailable` — the DPAPI
  interop and blob layout need tests that only exist once the target builds.
- The full `OmiKit.BackendTransport` conformance (generation SSE resume,
  software-plane selection) is not implemented here; this file carries the
  request plumbing it plugs into.
