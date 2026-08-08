# Runnable framework shells

This directory is the **implementation spike**, not a production migration. Each shell exposes or displays the same contract marker:

```text
omi-relay-contract:v1|native-seam:<framework boundary>|payload:bounded|gap:explicit
```

## Verified locally

| Shell | Command | Evidence |
|---|---|---|
| Tauri 2 | `npm install && npm run build && npm run tauri build -- --debug` | TypeScript + Rust command + macOS bundle/DMG built |
| Dioxus | `cargo check --manifest-path src-tauri/Cargo.toml` | Official Dioxus/Tauri shell checks |
| Flutter | `flutter analyze`; `MACOSX_DEPLOYMENT_TARGET=12.0 flutter build macos --debug` | Analyzer and macOS shell build |
| Lynx | `npm install && npm run build` | ReactLynx shell bundle builds; native module remains next seam |
| Makepad | `cargo test --manifest-path .../makepad_shell/Cargo.toml` | Published Makepad widgets dependency compiles; contract test passes |
| SwiftUI | `swift build --package-path .../swift_native_shell -c debug` | SwiftUI macOS executable builds; Android intentionally skipped |
| Compose Multiplatform | `./gradlew jvmJar --no-daemon` in the official template | Desktop JVM target builds |

## Evidence that remains blocked or scoped

- **Valdi:** source checkout contains a native hello-world with C++/Objective-C/Kotlin examples. The isolated CLI resolved module targets successfully, but the full `agent-check --module hello_world --json` returned `success: false`: build failed, lint failed because files were not formatted, and tests failed because the requested test targets could not be built/found. Valdi is not marked built.
- **Electrobun:** package/arm64 CLI installed, but `electrobun init` returned no scaffold or diagnostic output. It is not marked built.
- **Crepuscularity:** remains source/research-only; no stable public scaffold command was found.
- **React Native:** existing Android shell and relay tests remain the primary native runtime baseline.
- **Swift:** this spike intentionally does not target Android.

The generated external repositories and dependency/build caches are ignored. Re-run the commands above after a fresh scaffold to reproduce the evidence; do not infer runtime support from the comparison manifest alone.
