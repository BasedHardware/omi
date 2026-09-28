# scripts/ — Developer Guide

Repo-level automation. All JS/TS here runs under Bun; shell scripts are
POSIX `sh` executables referenced bare from the root `package.json`. The
gate chain and per-area test coverage are documented in
[`../docs/verification.md`](../docs/verification.md).

## Layout

| Script | Invoked by | Purpose |
|---|---|---|
| `check-boundaries.ts` | `bun run boundaries` (first `check` step) | Fails on tracked legacy-tree files (`app|backend|desktop|spikes|web/`), any `*.swift`, generated dirs (node_modules, Pods, DerivedData, dist), foreign lockfiles (`tools/OmiSimulator` exempt), and forbidden legacy imports in sources |
| `setup` | `bun run setup` | `bun install --frozen-lockfile`; monorepo `make setup` owns hooks |
| `start-metro.ts` | `react-native` `bun start`, PWA metro test, ad hoc | Programmatic Metro dev server for `react-native/` (options-object `listen` — Bun 1.3.14/1.4 never fire the four-argument callback form); `--port` when run directly |
| `test-metro-startup.ts` | `pwa` `bun run test` | Boots Metro, asserts `/status` and that each platform bundle (macos/ios/android) runs its runtime initializer first |
| `test-android-http` | CI, ad hoc | Compiles and runs the JVM transport suite with `javac --release 17` + `java -ea`; needs JDK 17+, no Android SDK |
| `test-apple-auth` | CI (macOS), ad hoc | Compiles ~14 Obj-C++ host suites with `xcrun clang++`, several against real `native-core/src/*.cpp`; macOS only |
| `test-apple-platforms` | `bun run platforms:test` | Clean Debug `xcodebuild` smoke builds: iOS Simulator + macOS workspaces, signing off |
| `test-native-core` | `bun run native:test` | mktemp dir → `cmake` → build → `ctest --output-on-failure` for `native-core/` |

## Conventions

- The monorepo owns hooks. Run `bun run check` by hand; the root
  `v5-checks.yml` workflow runs v5 checks in CI.
- `test-apple-platforms` and `test-metro-startup` are ad hoc. Everything else —
  boundaries, format, lint, typecheck, tests, `native:test`,
  `platform:check` — runs in `bun run check`.
- Adding a script: wire it into `package.json`, keep it Bun-first, and add
  it to the right column above plus `../docs/verification.md` if it belongs to
  the gate.
