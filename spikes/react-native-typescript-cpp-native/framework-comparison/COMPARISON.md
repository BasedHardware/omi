# Framework comparison

## Scope

This spike compares UI/runtime candidates against the same project constraint:

- TypeScript-first domain logic.
- A narrow native seam for bounded payloads.
- Explicit gaps instead of hidden parity claims.
- React Native Android remains the proven relay baseline.
- Swift is compared on iOS/macOS only; Swift Android is intentionally excluded.

The comparison is evidence-backed, not a feature checklist. A shell build does not prove a physical-device runtime, BLE behavior, background execution, or production parity.

## Shared contract

Every runnable shell uses this marker:

```text
omi-relay-contract:v1|native-seam:<framework boundary>|payload:bounded|gap:explicit
```

The dependency-free validator is:

```bash
python3 framework-comparison/run-probe.py
```

## Evidence matrix

| Candidate | Primary language | Mobile | Desktop | Native seam | Local evidence | Decision |
|---|---|---:|---:|---|---|---|
| React Native | TypeScript/JS + native modules | Yes | Limited | Android/iOS native module | Existing Android relay baseline and tests pass | Keep as baseline |
| Flutter | Dart + platform channels/plugins | Yes | Yes | Dart platform channel/plugin | `flutter analyze` and macOS debug build pass | Strong parity baseline |
| Valdi | TypeScript + generated native modules | Yes | Yes | C++/Swift/Kotlin/Objective-C bindings | Target resolution passes; repaired probe still needs the long Bazel build to finish | Highest-risk TS-native challenger; do not mark built |
| Lynx / ReactLynx | TypeScript/React-like | Yes | Host projects present | Native module boundary | Official shell bundle builds; native-module runtime not verified | Worth a focused mobile seam spike |
| Tauri 2 | TypeScript + Rust | No native mobile parity claim here | Yes | Rust commands/plugins | TS build, Rust contract command, and tests pass | Strong desktop candidate |
| Dioxus | Rust | Experimental mobile | Yes | Rust-owned UI/native host | Official Tauri shell `cargo check` passes | Rust alternative; mobile maturity remains a risk |
| Makepad | Rust | Target coverage exists | Yes | Rust/widgets/native target | Dependency compiles and contract test passes | Interesting Rust control; not TypeScript-first |
| Crepuscularity | Rust/Solid direction | No verified claim | Research | Rust/native host | Source-level inspection only | Research candidate, not decision-ready |
| Electrobun | TypeScript + Bun/native desktop | No mobile parity claim | Yes | Bun/native desktop APIs | CLI/arm64 package probe works; scaffold generation inconclusive | Revisit for desktop-only work |
| Compose Multiplatform | Kotlin | Yes | Yes | Kotlin/Swift/native interop | Official template JVM jar target builds | Best Kotlin-native comparison; no Swift Android claim |
| Swift native / SwiftUI | Swift | iOS/macOS only | macOS | Direct Apple APIs | Swift package builds | Apple control baseline |
| Web TypeScript + Moonshine | TypeScript/Web | Browser/PWA scope | Browser | Web/native host boundary | Existing web baseline; no mobile-native claim | Lowest native parity, useful portability control |

## What the evidence means

| Level | Meaning |
|---|---|
| `contract-probe` | Candidate metadata and the shared seam are validated. |
| `shell-built` | A generated or hand-built shell compiles locally. |
| `runtime-verified` | A real target runtime was launched and observed. |
| `research-only` | Source/docs were inspected without a runnable artifact. |

This repository currently has shell/build evidence for Tauri, Flutter, Lynx, Dioxus, Makepad, Swift, and Compose. It does **not** have uniform physical-device runtime evidence for those candidates.

## Local crate reuse: `rotary` and `zkr`

These are sibling projects under `~/projects`, not dependencies of this spike.

| Crate | Verified surface | Useful later | Boundary for this spike |
|---|---|---|---|
| `rotary` / `rx4` | `Cargo.toml` exposes feature-gated `mcp`, `ipc`, `providers`, sessions, permissions, and computer-use; `src/mcp.rs` implements JSON-RPC MCP transports and tool/resource metadata | Host-side MCP/tool orchestration, agent sessions, or a separate desktop host experiment | Not a UI framework and not proof of a React Native/Lynx/Valdi native seam; do not copy its production code into this spike |
| `zkr` | Rust 2024 crate with scoped evidence/claim/memory storage, SQLite persistence, embeddings, and strict `unsafe_code = forbid` linting | A separately versioned persistence adapter after the UI/native contract is proven | This spike explicitly avoids Omi-v4/production reuse; keep zkr out of the framework comparison build |

The practical conclusion is to reuse **interfaces and lessons**, not source:

1. Keep the TypeScript domain contract and bounded native seam independent of agent/MCP persistence.
2. If a later host spike needs MCP, evaluate `rotary` behind a separate Rust host adapter.
3. If a later host spike needs durable evidence, evaluate `zkr` behind a separate storage adapter.
4. Neither crate changes the current React Native recommendation or upgrades any framework's runtime evidence level.

## Valdi repair status

The first Valdi failure had two separate causes:

1. The hello-world `BUILD.bazel` glob passed `.bin` assets into the generated test target. The local probe removes that asset glob from `srcs` so the generated test target only receives TypeScript sources.
2. The host selects `/Applications/Xcode Beta.app/...`; Valdi's Bazel Apple wrapper loses the space in that path and invokes `env` with `Beta.app/...`. A space-free `DEVELOPER_DIR` symlink can remove that shell-path failure.

After the source fix and a clean Bazel invocation, target analysis proceeded, but the full `android.debug.valdimodule` build exceeded the available ten-minute execution window. Therefore Valdi remains **not build-verified**. The correct next gate is a completed clean Bazel build followed by the module tests; no parity claim should be made before both complete.

The Valdi checkout is an ignored external source tree. Its local changes are intentionally not treated as production code or as proof of upstream support.

## Recommendation for this spike

1. **Keep React Native** as the implementation baseline because its Android relay path is already proven and aligns with the TypeScript-first requirement.
2. **Use Flutter** as the strongest parity/control comparison when broad native platform coverage matters more than TypeScript ownership.
3. **Focus the next challenger experiment on Lynx and Valdi**, but require a real native-function binding and a completed Android build/test gate.
4. **Use Tauri/Electrobun for desktop-only options**, not as mobile replacements.
5. **Treat Makepad/Dioxus/Crepuscularity as Rust alternatives**, not direct TypeScript replacements.
6. **Keep Compose and Swift as language/platform controls**, with Swift Android explicitly out of scope.

## Verification commands

From this directory:

```bash
python3 framework-comparison/run-probe.py
python3 -m json.tool framework-comparison/frameworks.json >/dev/null
./run-tests.sh
git diff --check
```

For the committed runnable shells, see [`runtimes/README.md`](runtimes/README.md).