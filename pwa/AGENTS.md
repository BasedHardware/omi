# PWA — Developer Guide

The PWA is a Vite shell around the shared React Native tree — no separate
app source. `src/main.ts` boots `../../react-native/App` via
`AppRegistry.runApplication`; `vite.config.ts` aliases `react-native` →
`react-native-web` and resolves `.web.ts(x)` first. Behavior docs:
[`../docs/pwa.md`](../docs/pwa.md). Root rules: [`../AGENTS.md`](../AGENTS.md).

## File map

```
index.html               # Vite entry; viewport-fit=cover
src/main.ts              # bootstrap + service-worker registration (best-effort)
src/design-preview.ts    # labelled layout-review states over real surfaces
src/root.css             # document pinned (no scroll/overscroll); screens own scrolling
public/sw.js             # service worker: shell cache omi-v5-pwa-v1 (source, unit-tested)
public/manifest.webmanifest, omi-mark.svg
tests/                   # bun tests (service worker, adapters, proxy, markdown, a11y)
vite.config.ts           # aliases, dedupe, localProxy (dev/preview API proxy)
```

## Commands

Root passthroughs `pwa:dev|build|preview|test|lint|typecheck|format:check`;
inside `pwa/`: `bun run dev` (`--host 127.0.0.1`), `build`, `test` (bun
tests + `../scripts/test-metro-startup.ts`), `typecheck`.

## Contracts

- Shell: network-first navigations that refresh the cached shell, cached
  shell offline; `/v1/` and `/__omi/api/` excluded. Bump the cache name in
  `public/sw.js` when the caching contract changes.
- The document never scrolls; screens own scrolling (mobile nav and the
  composer must stay visible).
- Dev/preview proxy: needs `OMI_LOCAL_API_CLIENT_ID` + `OMI_LOCAL_API_TOKEN`
  to reach a real local backend; otherwise it serves a 503
  `local_api_unavailable` fallback (never crashes the dev server).
- `vite.config.ts` dedupes react/react-native-web/svg/safe-area-context and
  sets `preserveSymlinks` — don't add duplicate copies.

## Testing

`tests/` covers the service-worker contract (executed in a sandbox), web
adapters, proxy rewrite semantics (imports the real `vite.config`), chat
markdown, Pressable a11y, reduce motion, and the Metro startup test, which
boots a real Metro server via `../scripts/start-metro.ts` and asserts
`/status` plus platform-initializer-first bundles for macos/ios/android.

## Gotchas

- `dist/` is generated, git-ignored, and wiped by each build — never commit
  it.
- The tsconfig maps `react-native` to the real package for types while Vite
  aliases it to react-native-web at runtime; keep `.web` suffix resolution
  aligned between the two configs.
- The service worker is a source file, not a build artifact — edit and test
  it directly.
