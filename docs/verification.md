# Verification

The repo gate is `bun run check` (run before every commit and push; the
pre-push hook runs it again unless `OMI_V5_CHECKED=1`, which only
`scripts/push-v5` sets). It chains:

| Step | Script | What it proves |
|---|---|---|
| `boundaries` | `scripts/check-boundaries.ts` | No legacy-tree files, no `*.swift`, no generated dirs, no forbidden imports |
| `format:check` | prettier | Formatting over apps, pwa, react-native, scripts |
| `lint` | per-package eslint | react-native, backend-worker, pwa |
| `typecheck` | `bun run build` + per-package tsc | Builds ratified contracts + PWA, then typechecks each package |
| `test` | per-package test runners | JS suites (below) |
| `native:test` | `scripts/test-native-core` | C++ boundary suites via CMake/CTest |
| `platform:check` | `backends/example-platform check:deployed` | Portable backend contract + production-server purity |

Publishing: `bun run push:v5` requires branch `main`, a clean worktree, a
full `bun run check`, then mirrors the identical commit to
`BasedHardware/omi:v5`.

## Per-area test commands

- **React Native**: from `react-native/`, `bunx jest src/desktop` (desktop
  shell), `bunx jest __tests__` (native boundary + clients), or the full
  `bun run test` (also wired into the gate with `--runInBand`). Typecheck:
  `bun run typecheck`. Contracts must be built first (`bun run build` from
  the root) or the `@omi-core/ratified-contracts` mapping fails.
- **Backend Worker**: from `apps/backend-worker/`, `bun run test` — a
  Bun-test contract/policy layer plus `@cloudflare/vitest-pool-workers`
  integration tests over real miniflare D1/R2/DO with all migrations
  applied. Also `typecheck` (verifies generated wrangler types are fresh),
  `lint`, `deploy:dry-run`.
- **example-platform**: `bun test` (keep green); Postgres/Firebase runtimes
  via `bun run test:postgres`; full deployed-composition check via
  `bun run check:deployed`.
- **PWA**: `bun run pwa:test` — Bun tests plus the Metro startup test (real
  Metro server, `/status`, per-platform bundles).
- **native-core**: `bun run native:test` — needs CMake ≥ 3.20 and a C++20
  compiler; four self-contained suites (BLE packet codec, backend policy,
  HTTP plan facade, recording rules).
- **Android transport** (not in the gate): `scripts/test-android-http` —
  compiles and runs the JVM transport, OAuth callback, PKCE, authenticated
  encryption, SSE reconnect/cancellation, and BLE Device Information
  regressions with plain `java`; needs JDK 17+ and no Android SDK.
- **Apple host tests**: `scripts/test-apple-auth` (macOS only) — compiles
  ~14 Obj-C++ suites, several against the real `native-core` sources.
- **Clean platform compiles** (not in the gate): `bun run platforms:test` —
  iOS Simulator and macOS Debug `xcodebuild` smoke builds after Pods are
  installed.

Toolchain: Bun for everything JS/TS, Xcode for Apple, JDK 17 for the
Android JVM tests, CMake + C++20 for the native boundary.

## What checks cannot prove

- These checks do not replace authenticated app or physical-device
  verification. Live provider sign-in, AndroidKeyStore persistence, end-to-end
  capture, and BLE flows need a real device or the Mac app.
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
  options-object form. See [desktop-app.md](desktop-app.md) for the run
  recipes.
