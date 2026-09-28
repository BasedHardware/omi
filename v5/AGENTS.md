# Omi v5 — agent guide

Read the guide for the area you are changing. Start with the Routes table; each
area's guide carries its own map, commands, contracts, and gotchas. Topic docs
live in `docs/` (indexed in `docs/README.md`).

## Routes

| Working on | Read |
|---|---|
| React Native app (shared code, clients, UI kit) | `react-native/AGENTS.md` |
| macOS desktop app | `react-native/AGENTS.md` + `docs/desktop-app.md` |
| iOS / Android app | `react-native/AGENTS.md` + `docs/mobile.md` |
| PWA (web build) | `pwa/AGENTS.md` + `docs/pwa.md` |
| Cloudflare staging backend (Workers) | `apps/backend-worker/AGENTS.md` + `docs/backend-worker.md` |
| Provider-independent backend (example-platform) | `backends/example-platform/AGENTS.md` |
| Native C++ codec/policy boundary | `native-core/AGENTS.md` |
| Omi BLE simulator | `tools/OmiSimulator/AGENTS.md` + `docs/simulator.md` |
| Repo scripts and the `check` gate | `scripts/AGENTS.md` + `docs/verification.md` |
| CI workflows | `.github/AGENTS.md` |
| Auth flows, sessions, native transport contract | `docs/auth-and-sessions.md` |
| Encrypted capture journal | `docs/native-recording-journal.md` |
| Backend parity status | `docs/provider-agnostic-parity.md`, `docs/provider-agnostic-handoff.md` |
| Hardware/firmware parity | `docs/hardware-device-parity.md` |
| Ship-readiness evidence | `docs/production-readiness.md` |

## Repository conventions

- Use Bun for every JavaScript and TypeScript command.
- Keep product UI, routes, state, motion, and lifecycle orchestration in React
  Native. Objective-C++ is limited to platform bootstrap, real macOS material
  and window behavior, credential-bearing transport policy, desktop commands,
  and the C++ codec boundary. Swift sources, legacy product trees,
  compatibility aliases, and direct authenticated JavaScript networking are
  not allowed.
- The active Omi BLE simulator under `tools/OmiSimulator/` is a **Rust
  Crepuscularity (GPUI) desktop app** with a local CoreBluetooth GATT
  peripheral. Crepuscularity (`https://crepuscularity.tsc.hk` /
  `tschk/crepuscularity`) is the UI framework only — not an Omi API base.
- Run `bun run check` by hand before committing. CI runs it for v5 changes.
- Develop in `BasedHardware/omi` `main` through normal pull requests.
- Do not add secrets, generated dependencies, build output, or local Xcode
  environment files.

Keep this file a router. Area-specific facts belong in the owning guide above;
do not grow this file into a second docs set.
