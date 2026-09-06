# Omi v5

This repository is the rewrite-only Omi monorepo. It contains the React Native product client, the native codec boundary, and the typed platform contracts required by the rewritten backend.

The standalone `main` branch is mirrored commit-for-commit to `BasedHardware/omi:v5`. Run `bun run setup` once, `bun run check` before committing, and `bun run push:v5` to publish the verified commit to the mirror branch.

Run `bun run platforms:test` for clean iOS Simulator and macOS Debug compiles after Pods are installed. The bounded pre-push gate remains focused on contracts, TypeScript, React Native tests, the native C++ boundary, and Android HTTP routing and redirect protection. `bun run native:test` requires CMake, a C++ compiler, and JDK 17 or newer; `scripts/test-android-http` runs the JVM transport regression independently without an Android SDK.

The example backend lives at `/Users/undivisible/projects/omi-platform-integration` on `codex/track3-backend-integration` and serves the ratified `/v1/*` contract locally on `127.0.0.1:4851`.

`apps/backend-worker` is the Cloudflare-native staging backend. D1 is authoritative for the migrated tasks projection and device-session metadata; capture bytes use the bound `ATTACHMENTS` R2 bucket. Durable Objects coordinate per-account admission and generation/event sequencing only. LLM traffic is fail-closed behind the Cloudflare AI Gateway/OpenRouter adapter when gateway mode is enabled; no direct provider credential or Google backend is part of this path. Workers Observability emits correlation-safe request events, and the delivery gate includes readiness verification, rollback guidance, focused tests, typecheck, format/diff checks, and `deploy:dry-run`. Secrets are provisioned only through Wrangler.

Mobile dashboard controls open the shared chat, memories, settings, and connector screens. Task rows remain read-only until the Worker implements the existing ratified task-mutation contract. The Conversations destination shows all records in the loaded projection; loading and failed reads do not claim an empty timeline. Failed recording uploads remain visible and require a new device connection instead of silently completing partial audio.

The PWA uses the React Native Web animation runtime, refreshes its application shell while online, and uses the last cached shell offline. Its document stays within the viewport; individual screens own scrolling so mobile navigation and the composer remain visible.

Start the native bundler with `bun run --cwd react-native start --port 8081`. Bun 1.3.14 and 1.4 do not invoke Metro's four-argument `net.Server.listen(port, host, undefined, callback)` readiness callback. The launcher uses Metro's existing middleware and platform resolution with the standard options-object listener, preserving bundle serving and HMR without changing global networking. The PWA test suite starts this real server and verifies its packager endpoint.

iOS and macOS share the native Firebase session implementation. iOS presents the system authentication session with the app-specific `omi-rnruntime://auth/callback` redirect and PKCE; macOS retains its browser and loopback callback. iOS stores only its own sandboxed keychain session. `scripts/test-apple-auth` validates mobile callback rejection rules using Foundation on macOS and runs in the existing CI workflow; live provider sign-in still requires device verification.

Production readiness still requires canonical memories, device-audio transcription, production identity/entitlement configuration, live provider and signed-attachment verification, and native device validation. Local Worker integration tests and deployment dry-runs do not certify those services. See `apps/backend-worker/RELEASE.md` before applying migration 0005 remotely.
