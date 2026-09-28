# native-core — Developer Guide

Four small C++20 static libraries forming the shared native boundary:
pure C-ABI functions with all platform machinery (TLS, keychain, filesystem,
sessions) deliberately kept in platform shims. Compiled directly into the
Android JNI lib (`react-native/android/app/src/main/cpp/CMakeLists.txt`) and
both Apple targets (`react-native/ios`, `react-native/macos` Xcode projects).
Root rules: [`../AGENTS.md`](../AGENTS.md).

## Layout

```
include/omi_native_boundary.h    src/omi_native_boundary.cpp
  # BLE audio packet codec: CRC32 checksum, 0xAA 0x55 framed-packet
  # normalization, native capabilities JSON
include/omi_backend_policy.h     src/omi_backend_policy.cpp
  # shared transport policy: capture-path allowlist, route stripping,
  # timeout table (transcribe POST 150 s, else 60 s), hostname classes
include/omi_backend_http.h       src/omi_backend_http.cpp
  # HTTP plan facade: plans timeout/capture/validity, platform shim injects
include/omi_backend_recording.h  src/omi_backend_recording.cpp
  # journal rules: timestamp bounds, 128 MiB / 64-file caps, retryable
  # statuses (408/429/5xx), login+origin context matching
tests/test_*.cpp                 # framework-free assertion suites, one per library
```

## Invariants

- Pure C ABI; no platform services here — credential-bearing HTTP and key
  storage stay in the per-platform shims (`OmiBackendModule.mm`,
  `OmiBackendTransport.java`).
- JS never re-derives this policy: capture-path allowlists, timeouts, and
  hostname classification come from here. The Android Java mirrors
  (`OmiBackendTransport.java`) must track changes to
  `omi_backend_policy.cpp`.
- `scripts/test-apple-auth` compiles several Apple host tests against the
  real `src/*.cpp`, so host tests and shims share semantics.

## Build and test

```sh
bun run native:test      # scripts/test-native-core: mktemp dir → cmake → build → ctest
```

Requires CMake ≥ 3.20 and a C++20 compiler. Suites cover invalid-argument
handling, sync-byte/CRC errors, route stripping, the allowlist, the timeout
table, hostname classification, and recording timestamp/retry/context rules.
No JDK needed here (JDK 17 is `scripts/test-android-http`'s requirement).
