# Verification

> This is the v5-swift rewrite branch: the clients are the Swift package in
> `app/` (OmiKit + OmiUI, Skip-transpiled to Kotlin for Android); the React
> Native tree is gone.

The repo gate is `bun run check` (run before every commit and push; the
pre-push hook runs it again unless `OMI_V5_CHECKED=1`, which only
`scripts/push-v5` sets). It chains:

| Step | Script | What it proves |
|---|---|---|
| `boundaries` | `scripts/check-boundaries.ts` | Swift files only under Package.swift target paths, no generated dirs (node_modules, Pods, DerivedData, `.build`, dist), no foreign lockfiles (`tools/OmiSimulator` exempt), no legacy imports |
| `format:check` | prettier | Formatting over apps, pwa, scripts |
| `lint` | per-package eslint | backend-worker, pwa |
| `typecheck` | `bun run build` + per-package tsc | Builds ratified contracts + PWA, then typechecks each package |
| `test` | per-package test runners | backend-worker suites, ratified contract verify, PWA tests |
| `swift:test` | `swift test` | Swift package unit tests (`app/Tests`); needs a macOS host with the Swift 6 toolchain |
| `native:test` | `scripts/test-native-core` | C++ boundary suites via CMake/CTest |
| `platform:check` | `backends/example-platform check:deployed` | Portable backend contract + production-server purity |

Publishing: `bun run push:v5` requires branch `main`, a clean worktree, a
full `bun run check`, then mirrors the identical commit to
`BasedHardware/omi:v5`.

## Swift package (`swift build` / `swift test`)

- Targets: `CNativeCore` (the C++ `native-core/` middleware compiled in
  place), `OmiKit` (platform-neutral core: Wire/Backend/Session/Devices/
  Timeline plus foundation models, transport, and the Policy facade over
  the C ABI), `OmiUI` (shared SwiftUI surfaces). Tests live in
  `app/Tests/OmiKitTests` and `app/Tests/OmiUITests` — `swift test` runs
  both. Tree map and Skip-transpiler coding rules: [`../app/AGENTS.md`](../app/AGENTS.md).
- `swift build` runs the Skip `skipstone` plugin, transpiling OmiKit/OmiUI
  to Kotlin. A green build is the transpilation proof; Kotlin output lands
  under `.build/plugins/outputs/` (generated, never committed).
- `swift test` needs a macOS host with the Swift 6 toolchain (Xcode
  stable). There is no Android SDK or Windows step in the gate: Skip's
  Kotlin output and the Windows host are verified ad hoc, not in CI.

## Per-area test commands

- **Backend Worker**: from `apps/backend-worker/`, `bun run test` — a
  Bun-test contract/policy layer plus `@cloudflare/vitest-pool-workers`
  integration tests over real miniflare D1/R2/DO with all migrations
  applied. Also `typecheck` (verifies generated wrangler types are fresh),
  `lint`, `deploy:dry-run`.
- **example-platform**: `bun test` (keep green); Postgres/Firebase runtimes
  via `bun run test:postgres`; full deployed-composition check via
  `bun run check:deployed`.
- **PWA**: `bun run pwa:test` — Bun tests plus the Metro startup test
  (`scripts/test-metro-startup.ts`: real Metro server, `/status`,
  per-platform bundles).
- **native-core**: `bun run native:test` — needs CMake ≥ 3.20 and a C++20
  compiler; four self-contained suites (BLE packet codec, backend policy,
  HTTP plan facade, recording rules).

Toolchain: Bun for everything JS/TS, Swift 6 (Xcode stable, macOS) for the
app package, CMake + C++20 for the native boundary.

## What checks cannot prove

- These checks do not replace authenticated app or physical-device
  verification. Live provider sign-in, platform credential stores,
  end-to-end capture, and BLE flows need a real device or the Mac app.
- Browser/PWA previews do not verify native permissions, Bluetooth, safe
  areas, or the software keyboard.
- Every macOS rebuild resets the Screen Recording TCC grant — re-grant and
  relaunch before testing capture (a newly granted permission requires
  relaunch).
- Smoke-test rendered behavior in the real app or a real browser before and
  after deploys; bundle checks and passing unit tests are not verification
  of the user-visible result.
- Metro on Bun: Bun 1.3.14/1.4 don't fire Metro's four-argument
  `net.Server.listen` readiness callback; `scripts/start-metro.ts` uses the
  options-object form.
