# Omi v5

Rewrite-only Omi monorepo: the React Native product client (macOS, iOS,
Android, web/PWA), the native C++ codec and transport-policy boundary, typed
platform contracts, and the two backends the rewrite targets — the
Cloudflare-native staging Worker and the provider-independent
`backends/example-platform` reference implementation.

The standalone `main` branch is mirrored commit-for-commit to
`BasedHardware/omi:v5`. Only publish through the mirror gate:

```sh
bun run setup      # git hooks + frozen install (once per clone)
bun run check      # boundaries, format, lint, typecheck, tests, native, platform
bun run push:v5    # verify + mirror main to BasedHardware/omi:v5
```

Platform surfaces:

- **macOS desktop app** — React Native (`react-native-macos`) in a native
  glass window. See `docs/desktop-app.md`.
- **iOS / Android app** — same React Native tree with native transport and
  capture. See `docs/mobile.md`.
- **PWA** — the same app under React Native Web, with an offline app shell.
  See `docs/pwa.md`.
- **Backends** — `apps/backend-worker` (Cloudflare staging) and
  `backends/example-platform` (portable reference implementation).

## Documentation

- Topic index: [`docs/README.md`](docs/README.md)
- Per-area agent guides: [`react-native/AGENTS.md`](react-native/AGENTS.md),
  [`apps/backend-worker/AGENTS.md`](apps/backend-worker/AGENTS.md),
  [`backends/example-platform/AGENTS.md`](backends/example-platform/AGENTS.md),
  [`pwa/AGENTS.md`](pwa/AGENTS.md),
  [`native-core/AGENTS.md`](native-core/AGENTS.md),
  [`tools/OmiSimulator/AGENTS.md`](tools/OmiSimulator/AGENTS.md),
  [`scripts/AGENTS.md`](scripts/AGENTS.md)
- Repo conventions and area routing: [`AGENTS.md`](AGENTS.md)
