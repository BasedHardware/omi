# Windows portable-core and Swift/WinRT projection host

This is a **Windows-only developer build surface** for Context for Claude. It has two deliberately separate boundaries:

1. `../core` is the portable C++17 policy/audio/recall library. Native Windows hosts call its stable C ABI directly.
2. [swift-winrt](https://github.com/thebrowsercompany/swift-winrt) at pinned revision `79ffa65c` generates Swift bindings for **Windows SDK metadata** (`.winmd`). It is not a generator for this project's C ABI and does not make the core into a WinRT component.

The CMake target `generate_windows_foundation_projection` runs the actual upstream `swiftwinrt.exe` against the installed SDK's `Windows.winmd`, including the concrete `Windows.Foundation` namespace. It produces the real platform projection that the Swift host in `swift-host/` consumes.

The `swift-host/` directory is a SwiftPM package that imports the generated `WindowsFoundation` projection and links the portable C++ core through a module map (`CContextCore`). The CMake target `build_swift_host` generates the projection into `swift-host/projection/` and then runs `swift build` to compile the host executable.

## What this proves

- The portable core builds and its C++ host callers work on Windows.
- The pinned upstream Swift/WinRT generator can project a real Windows SDK namespace.
- A Swift host can import that projection and link the C++ core through a C ABI module map.
- The host boundary is honest: **Windows APIs use generated Swift/WinRT bindings; product policy/audio/recall use the Context core C ABI.**

## What this does not implement

This slice does not ship a Windows app, microphone/system-audio capture, screen capture, OCR, storage, MCP, or the macOS menu-bar UI. The Swift host in `swift-host/` proves the import/link boundary but does not implement capture or MCP. In particular, **SwiftUI is not provided by Swift/WinRT and is not claimed to be a supported Windows UI stack here.** A Windows UI must choose and validate its own native UI layer (for example WinUI) before this becomes an end-user host.

## Prerequisites

- Windows 10/11 on x64 or ARM64.
- Visual Studio 2022 with the Desktop development with C++ workload and a Windows SDK.
- A Windows Swift toolchain compatible with the pinned `swift-winrt` revision. Upstream recommends using the release selected by its Windows build workflow.
- CMake 3.24+ and Git.

Run configuration from a **Visual Studio Developer PowerShell** so `WindowsSdkDir` and `WindowsSDKVersion` resolve the SDK's `UnionMetadata/.../Windows.winmd` file. CMake validates this before downloading/building the generator.

## Validate on Windows

```powershell
# Configure native core host + the pinned upstream Swift/WinRT generator.
cmake -S desktop/context-for-claude/windows -B out/context-for-claude-windows `
  -G "Visual Studio 17 2022" -A x64

# Portable-core host checks.
cmake --build out/context-for-claude-windows --config Release
ctest --test-dir out/context-for-claude-windows -C Release --output-on-failure

# Real upstream Windows metadata -> Swift projection.
cmake --build out/context-for-claude-windows --config Release `
  --target generate_windows_foundation_projection

# Swift host: generates the WinRT projection and builds the SwiftPM package.
cmake --build out/context-for-claude-windows --config Release `
  --target build_swift_host

```

For ARM64, configure with `-A ARM64`. The projection command must run on Windows: this macOS development host cannot compile `swiftwinrt.exe` or exercise WinRT activation/UI runtime behavior.

## Validate on macOS

macOS can validate the portable C++ boundary:

```bash
cmake -S desktop/context-for-claude/core -B /tmp/context-core
cmake --build /tmp/context-core
ctest --test-dir /tmp/context-core --output-on-failure
```

The Windows CMake project intentionally stops immediately on non-Windows hosts and does not fetch or pretend to validate `swift-winrt` there. The Swift host's `Package.swift` and source files are visible on macOS but cannot be built here — `swift build` for the `x86_64-unknown-windows-msvc` / `aarch64-unknown-windows-msvc` triples requires a Windows Swift toolchain.

## Structure

```text
windows/
├── CMakeLists.txt        Windows C++ hosts, swift-winrt projection, and Swift host build
├── src/core_smoke.cpp    Session/recall C ABI smoke test
├── src/session_host.cpp  Session-boundary host test
├── src/pcm_host.cpp      PCM encode/decode/RMS/downmix host test
├── swift-host/           SwiftPM package: imports WinRT projection + links C++ core
│   ├── Package.swift
│   └── Sources/
│       ├── CContextCore/     C ABI module map wrapper (header → ../core/include)
│       └── ContextWindowsHost/  Swift main: calls core C ABI + WinRT Uri
└── README.md
```
