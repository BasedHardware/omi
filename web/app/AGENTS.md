# web/app — Developer Guide

The signed-in Omi web client (Next.js 16 App Router, React 19). Sibling web
surfaces live in `web/admin`, `web/frontend`, `web/personas-open-source`.

## Setup

```bash
cd web/app
npm ci          # the Dockerfile uses the same lockfile path
npm run dev     # generates the Firebase service worker, then next dev --turbopack
```

Use npm, not Bun or pnpm: `Dockerfile` runs `npm ci` against `package-lock.json`,
and a competing lockfile changes what the production image installs.

## Quality Gates

| Gate | Command | Status |
|---|---|---|
| Types | `npm run typecheck` | enforced |
| Tests | `npm test` (vitest + jsdom + testing-library) | enforced |
| Both | `npm run check` — what `./test.sh` and CI run | enforced |
| Lint | `npm run lint` (`eslint .`) | **not enforced — pre-existing failures** |

`./test.sh` is the component runner: installs deps if absent, then `npm run
check`. Registered in `.github/checks-manifest.yaml` as `web-app-checks`.

Lint is deliberately outside `check`: `eslint-config-next` 16 turned on the
React Compiler rules and the tree still reports 57 pre-existing errors, so
wiring it in would fail every PR on day one. 48 are
`react-hooks/set-state-in-effect` against the fetch-on-mount shape the older
data hooks use; signal-backed code does not hit it (see State below). Clear the
backlog before adding `npm run lint` to `check`.

## State

The Home hub runs on `@tschk/moonshine` signals, not React state:
`useAsyncResource` for reads, a signal store for optimistically-written lists.
Import only the kernel. Why, and the pitfalls:
[`docs/agents/web-app-signals.md`](../../docs/agents/web-app-signals.md).

## Tests

Tests live in `__tests__/` beside the code, discovered by `vitest.config.mts`
(jsdom, `@` → `src/`). Prefer pure logic in `src/lib/` and `src/hooks/`; reserve
component rendering for behavior that only appears in the tree.

## Parity With Desktop

`web/app` is not a port of `desktop/macos` and cannot be one — Rewind, Focus,
Insights, the floating bar, Bluetooth pairing, and local file indexing need
macOS capture APIs with no browser equivalent. Before porting a desktop surface,
check whether its data comes from a `backend/routers/` endpoint (portable) or
local Swift storage (not).
