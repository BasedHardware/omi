# Windows portable-core and Swift/WinRT projection host

This is a **Windows-only developer build surface** for Context for Claude. It has two deliberately separate boundaries:

1. `../core` is the portable C++17 policy/audio/recall library. Native Windows hosts call its stable C ABI directly.
2. [swift-winrt](https://github.com/thebrowsercompany/swift-winrt) at pinned revision `79ffa65c` generates Swift bindings for **Windows SDK metadata** (`.winmd`). It is not a generator for this project's C ABI and does not make the core into a WinRT component.

The CMake target `generate_windows_foundation_projection` runs the actual upstream `swiftwinrt.exe` against the installed SDK's `Windows.winmd`, including the concrete `Windows.Foundation` namespace. That gives a Windows Swift host the real platform projection it needs; its separate `ContextCoreBridge` system-library/module map should import and link `../core`'s C ABI.

## What this proves

- The portable core builds and its C++ host callers work on Windows.
- The pinned upstream Swift/WinRT generator can project a real Windows SDK namespace.
- The host boundary is honest: **Windows APIs use generated Swift/WinRT bindings; product policy/audio/recall use the Context core C ABI.**

## What this does not implement

This slice does not ship a Windows app, microphone/system-audio capture, screen capture, OCR, storage, MCP, or the macOS menu-bar UI. In particular, **SwiftUI is not provided by Swift/WinRT and is not claimed to be a supported Windows UI stack here.** A Windows UI must choose and validate its own native UI layer (for example WinUI) before this becomes an end-user host.

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

# Swift wrappers -> separately built Context core C ABI.
cmake --build out/context-for-claude-windows --config Release `
  --target context_for_claude_swift_host_tests
```

For ARM64, configure with `-A ARM64`. The projection command must run on Windows: this macOS development host cannot compile `swiftwinrt.exe` or exercise WinRT activation/UI runtime behavior.

## Validate on macOS

macOS can validate the portable C++ boundary and the platform-neutral Swift wrappers:

```bash
cmake -S desktop/context-for-claude/core -B /tmp/context-core
cmake --build /tmp/context-core
ctest --test-dir /tmp/context-core --output-on-failure
swift test --package-path desktop/context-for-claude/windows/swift-host \
  -Xlinker -L/tmp/context-core
```

The Windows CMake project intentionally stops immediately on non-Windows hosts and does not fetch or pretend to validate `swift-winrt` there. The macOS Swift test links the separately built portable library; it does not generate, compile, or run any WinRT projection.

## Structure

```text
windows/
├── CMakeLists.txt        Windows C++ hosts plus direct swift-winrt projection target
├── src/core_smoke.cpp    Session/recall C ABI smoke test
├── src/session_host.cpp  Session-boundary host test
├── src/pcm_host.cpp      PCM encode/decode/RMS/downmix host test
├── swift-host/           Swift system-library import, wrappers, and tests
└── README.md
```
