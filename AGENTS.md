# Omi v5 — agent guide

Read the guide for the area you are changing. Start with the Routes table; each
area's guide carries its own map, commands, contracts, and gotchas. Topic docs
live in `docs/` (indexed in `docs/README.md`).

## Routes

| Working on | Read |
|---|---|
| Swift cross-platform app (OmiKit, OmiUI, tests) | `app/AGENTS.md` |
| macOS desktop app | `app/AGENTS.md` + `docs/desktop-app.md` |
| iOS / Android app | `app/AGENTS.md` + `docs/mobile.md` |
| PWA (web build) | `pwa/AGENTS.md` + `docs/pwa.md` |
| Cloudflare staging backend (Workers) | `apps/backend-worker/AGENTS.md` + `docs/backend-worker.md` |
| Provider-independent backend (example-platform) | `backends/example-platform/AGENTS.md` |
| Native C++ codec/policy boundary | `native-core/AGENTS.md` |
| Omi BLE simulator | `tools/OmiSimulator/AGENTS.md` + `docs/simulator.md` |
| Repo scripts, the `check` gate, the `v5` mirror push | `scripts/AGENTS.md` + `docs/verification.md` |
| CI workflows | `.github/AGENTS.md` |
| Auth flows, sessions, native transport contract | `docs/auth-and-sessions.md` |
| Encrypted capture journal | `docs/native-recording-journal.md` |
| Backend parity status | `docs/provider-agnostic-parity.md`, `docs/provider-agnostic-handoff.md` |
| Hardware/firmware parity | `docs/hardware-device-parity.md` |
| Ship-readiness evidence | `docs/production-readiness.md` |

## Repository conventions

- Use Bun for every JavaScript and TypeScript command.
- This is the v5-swift rewrite branch: the native clients are one Swift
  package (`Package.swift`). Product UI, routes, state, motion, and
  lifecycle orchestration live in OmiKit + OmiUI under `app/` (SkipUI
  transpiles OmiUI to Kotlin for Android). Swift is allowed only inside
  `app/` and only in Package.swift-declared target paths.
- The C++ middleware stays C++: `native-core/` is compiled in place by the
  `CNativeCore` target and consumed through its C ABI behind OmiKit's
  Policy facade. Never re-derive or port the codec, transport policy, HTTP
  plan facade, or recording rules.
- Credentials live in the platform credential stores behind OmiKit's
  `CredentialStoring` — never in view models, never in JS.
- The active Omi BLE simulator under `tools/OmiSimulator/` is a **Rust
  Crepuscularity (GPUI) desktop app** with a local CoreBluetooth GATT
  peripheral. Crepuscularity (`https://crepuscularity.tsc.hk` /
  `tschk/crepuscularity`) is the UI framework only — not an Omi API base.
- Run `bun run check` before every commit and push. Push the standalone `main`
  branch only through `bun run push:v5`, which mirrors the identical commit to
  `BasedHardware/omi:v5`.
- Do not add secrets, generated dependencies, build output, or local Xcode
  environment files.

Keep this file a router. Area-specific facts belong in the owning guide above;
do not grow this file into a second docs set.
