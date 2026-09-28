# scripts/ — Developer Guide

Repo-level automation. All JS/TS here runs under Bun; shell scripts are
POSIX `sh` executables referenced bare from the root `package.json`. The
gate chain and per-area test coverage are documented in
[`../docs/verification.md`](../docs/verification.md).

## Layout

| Script | Invoked by | Purpose |
|---|---|---|
| `check-boundaries.ts` | `bun run boundaries` (first `check` step) | Fails on `*.swift` outside Package.swift target paths, generated dirs (node_modules, Pods, DerivedData, `.build`, dist), foreign lockfiles (`tools/OmiSimulator` exempt), and forbidden legacy imports in sources |
| `setup` | `bun run setup` | `git config core.hooksPath .githooks` + `bun install --frozen-lockfile` |
| `push-v5` | `bun run push:v5` | Requires branch `main` + clean worktree, runs full `bun run check`, then `OMI_V5_CHECKED=1 git push omi HEAD:refs/heads/v5` (mirror to `BasedHardware/omi:v5`) |
| `start-metro.ts` | PWA metro test, ad hoc | Programmatic Metro dev server (options-object `listen` — Bun 1.3.14/1.4 never fire the four-argument callback form); `--port` when run directly |
| `test-metro-startup.ts` | `pwa` `bun run test` | Boots Metro, asserts `/status` and that each platform bundle (macos/ios/android) runs its runtime initializer first |
| `test-native-core` | `bun run native:test` | mktemp dir → `cmake` → build → `ctest --output-on-failure` for `native-core/` |

`swift:test` is plain `swift test` from the root (no script here); it needs
a macOS host with the Swift 6 toolchain (Xcode stable).

## Conventions

- The only git hook is `.githooks/pre-push` = `bun run check` unless
  `OMI_V5_CHECKED=1` (set only by `push-v5`, to avoid a double check).
- Not in the gate (ad hoc): `test-metro-startup` (runs via the PWA test).
  Everything else — boundaries, format, lint, typecheck, tests,
  `swift:test`, `native:test`, `platform:check` — runs in `bun run check`.
- Adding a script: wire it into `package.json`, keep it Bun-first, and add
  it to the right column above plus `docs/verification.md` if it belongs to
  the gate.
