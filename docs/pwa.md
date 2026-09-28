# PWA (web build)

The PWA is a Vite shell around the same React Native tree — there is no
separate app source. `pwa/src/main.ts` imports `App` from
`../../react-native/App` and boots it with `AppRegistry.runApplication`.
Guide-level rules: [`pwa/AGENTS.md`](../pwa/AGENTS.md).

## How web picks up the RN tree

- `pwa/vite.config.ts` aliases `react-native` → `react-native-web` and
  resolves `.web.ts(x)` first; `pwa/tsconfig.json` extends the RN tsconfig
  with `moduleSuffixes: [".web", ""]`. Platform selection is via `.web`
  suffixes, not duplicated code.
- Shared UI comes straight from `react-native/src/ui` and `react-native/src`
  (e.g. `ChatMessageContent.web.tsx` renders Markdown with Streamdown),
  while `react-native/src/omiNative.web.ts` and `browser-adapters.web.ts`
  provide browser implementations of the native boundary.

## App shell and scrolling

- `pwa/public/sw.js` keeps a versioned shell cache (`omi-v5-pwa-v1`):
  navigations are network-first with the fresh shell written back to cache,
  and offline falls back to the last cached shell; shell/asset GETs are
  cache-first with background refresh. `/v1/` and `/__omi/api/` requests are
  excluded. The service worker is a source file in `public/` (unit-tested),
  not a build artifact — bump the cache name when its contract changes.
- The document stays within the viewport (`root.css`: no document scroll, no
  overscroll); individual screens own scrolling so mobile navigation and the
  composer remain visible.
- The PWA uses the React Native Web animation runtime; its tests assert
  TimingAnimation cleanup without Node globals.

## Layout review preview

```sh
bun run pwa:dev          # then open /design-preview.html?surface=mobile&data=example
```

`pwa/src/design-preview.ts` renders the real mobile or desktop surfaces with
labelled simulated states (query params, one value at a time):
`surface=mobile|desktop`, `data=example|empty`, plus
`chat=empty|ready|waiting|loading|error`,
`device=connecting|waiting|listening|paused|error`, and
`conversations=ready|loading|error`. These are labelled simulated states: no
message, recording, or Bluetooth command is sent. Browser previews do not
verify native permissions, Bluetooth, safe areas, or the software keyboard.

## Commands and tests

Root passthroughs: `pwa:dev`, `pwa:build`, `pwa:preview`, `pwa:test`,
`pwa:lint`, `pwa:typecheck`, `pwa:format:check`. Inside `pwa/`:
`bun run build`, `dev`, `preview`, `test` (`bun test` +
`../scripts/test-metro-startup.ts`), `typecheck`.

Tests live in `pwa/tests/` (Bun test): service-worker caching contract,
web adapters, proxy boundary semantics, chat markdown, Pressable
accessibility, reduce motion, and the Metro startup test — the latter starts
a real Metro server via `scripts/start-metro.ts` and asserts `/status` plus
macOS/iOS/Android bundles that run their platform initializer first.

## Gotchas

- `pwa/dist/` is generated and git-ignored; a build wipes it.
- The dev/preview proxy needs `OMI_LOCAL_API_CLIENT_ID` +
  `OMI_LOCAL_API_TOKEN` to reach a real local backend; unset, it serves a
  503 `local_api_unavailable` fallback instead of failing to boot.
- `vite.config.ts` pins `preserveSymlinks` and a dedupe list — don't add
  duplicate React/RN dependency copies.
