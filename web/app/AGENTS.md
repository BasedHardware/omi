# web/app — Developer Guide

The signed-in Omi web client (Next.js 16 App Router, React 19). Sibling web
surfaces live in `web/admin`, `web/frontend`, `web/personas-open-source`.

## Setup

```bash
cd web/app
npm ci          # the Dockerfile uses the same lockfile path
npm run dev     # generates the Firebase service worker, then next dev --turbopack
```

Use npm here, not Bun or pnpm: `web/app/Dockerfile` runs `npm ci` against
`package-lock.json`, and a competing lockfile changes what the production image
installs.

## Quality Gates

| Gate | Command | Status |
|---|---|---|
| Types | `npm run typecheck` | enforced |
| Tests | `npm test` (vitest + jsdom + testing-library) | enforced |
| Both | `npm run check` — what `./test.sh` and CI run | enforced |
| Lint | `npm run lint` (`eslint .`) | **not enforced — pre-existing failures** |

`./test.sh` is the component runner; it installs dependencies when
`node_modules` is absent and then runs `npm run check`. It is registered in
`.github/checks-manifest.yaml` as `web-app-checks`, triggered by changes under
`web/app/`.

Lint is deliberately outside `check`: `eslint-config-next` 16 turned on the
React Compiler rules and the tree still reports 62 pre-existing errors, so
wiring it in would fail every PR on day one. 48 are
`react-hooks/set-state-in-effect`, which fires on the fetch-on-mount shape every
data hook here uses — the rule cannot see through the async boundary, so even an
effect that sets state only after an `await` is flagged. Clearing that is a
design decision (adopt a data-fetching library, or turn the rule off), not a
mechanical fix. Do it before adding `npm run lint` to `check`.

## Tests

Tests live in `__tests__/` next to the code they cover and are discovered by
`vitest.config.mts` (jsdom environment, `@` aliased to `src/`). Prefer testing
pure logic in `src/lib/` and `src/hooks/`; reserve component rendering for
behavior that only appears in the tree.

## Parity With Desktop

`web/app` is not a port of `desktop/macos` and cannot be one — Rewind, Focus,
Insights, the floating bar, Bluetooth pairing, and local file indexing all
depend on macOS capture APIs with no browser equivalent. When adding a surface
that desktop already has, check whether its data comes from a
`backend/routers/` endpoint (portable) or from local Swift storage (not).
