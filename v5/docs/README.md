# Docs

Topic documents for the omi v5 monorepo. Area-level agent guides live next to
the code they describe (`AGENTS.md` files — see the root
[`AGENTS.md`](../AGENTS.md) router for the full map).

## Products and areas

| Doc | Covers |
|---|---|
| [desktop-app.md](desktop-app.md) | macOS desktop app: architecture, chrome/timeline contracts, capture, UX behavior, build and debug recipes |
| [mobile.md](mobile.md) | iOS/Android app surfaces, navigation, tasks and conversations behavior |
| [pwa.md](pwa.md) | Web/PWA build: shell caching, layout review preview, tests |
| [backend-worker.md](backend-worker.md) | `apps/backend-worker`: Cloudflare staging backend, D1/R2/DO contracts, delivery gate |
| [simulator.md](simulator.md) | `tools/OmiSimulator`: Rust Crepuscularity BLE peripheral simulator |

## Cross-cutting contracts

| Doc | Covers |
|---|---|
| [auth-and-sessions.md](auth-and-sessions.md) | Old/New backend selection, per-platform sign-in flows, native transport contract |
| [native-recording-journal.md](native-recording-journal.md) | Encrypted, ownership-bound capture journal (native keys never enter JS) |
| [provider-agnostic-parity.md](provider-agnostic-parity.md) | Parity gates between the Cloudflare Worker and the portable backend composition |
| [provider-agnostic-handoff.md](provider-agnostic-handoff.md) | Continuation state for the provider-independent backend work |
| [hardware-device-parity.md](hardware-device-parity.md) | Device/firmware characteristics coverage (Device Information service) |
| [production-readiness.md](production-readiness.md) | Ship-readiness evidence and remaining production requirements |

## Process

| Doc | Covers |
|---|---|
| [verification.md](verification.md) | What `bun run check` runs, per-area test commands, physical-device caveats |
| [workers-first-migration-evidence.md](workers-first-migration-evidence.md) | Evidence log from the workers-first backend migration |
