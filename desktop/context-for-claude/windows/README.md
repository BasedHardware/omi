# Windows portable-core host

This is a Windows-only developer build surface. It builds the portable `../core` C++17 library,
builds swift-winrt at the fixed `79ffa65c` revision, and runs a native C++ CLI that calls the core
C ABI for a session-boundary decision and a ranking score.

It deliberately does not generate a Swift/WinRT projection yet: this host calls no WinRT API, and
generating bindings without a Windows API consumer would be unused output. The pinned `swiftwinrt`
tool is built so a future Windows host can generate its bindings from the same reproducible build.

## Prerequisites

- Windows 10 or later with a Windows SDK and the Visual Studio Desktop development with C++ workload.
- A Visual Studio Developer PowerShell, or another environment where MSVC is available to CMake.
- A Windows Swift toolchain with `swiftc` on `PATH`. Use the toolchain recommended by
  [swift-winrt](https://github.com/thebrowsercompany/swift-winrt).
- CMake 3.24 or later and Git. CMake obtains swift-winrt and its upstream submodules outside this
  repository; this repository contains no swift-winrt submodule.

## Validate on Windows

```powershell
cmake -S desktop/context-for-claude/windows -B out/context-for-claude-windows -G "Visual Studio 17 2022" -A x64
cmake --build out/context-for-claude-windows --config Release
ctest --test-dir out/context-for-claude-windows -C Release --output-on-failure
.\out\context-for-claude-windows\Release\context_for_claude_windows_core_smoke.exe
```

The configuration stops before downloading swift-winrt when it is not running on Windows. On
Windows, it stops with a prerequisite-specific message if MSVC, `swiftc`, or the Windows SDK headers
are unavailable.

## Scope

This slice proves the portable rules are callable from a Windows host. It does not implement
microphone capture, system-audio capture, screen capture, OCR, storage, MCP, or the macOS menu-bar
UI on Windows.
