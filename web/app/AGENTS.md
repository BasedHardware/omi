# web/app — Developer Guide

The signed-in Omi web client: React 19 on the `@tschk/moonshine` runtime, served
by Bun. Sibling web surfaces live in `web/admin`, `web/frontend`,
`web/personas-open-source`.

## Setup

```bash
cd web/app
bun install     # the Dockerfile uses the same bun.lock
bun run dev     # full build, serve, rebuild on change (scripts/dev.ts)
# dev runs the full build pipeline, not `moonshine dev`: build:assets injects
# NEXT_PUBLIC_* and writes the real server, and the app boots blank without it.
```

Use Bun, not npm or pnpm: `Dockerfile` installs from `bun.lock`.

## Quality Gates

| Gate | Command | Status |
|---|---|---|
| Types | `bun run typecheck` | enforced |
| Tests | `bun run test` — `bun test` for the moonshine smoke suite, then vitest for `src/` | enforced |
| Both | `bun run check` — what `./test.sh` and CI run | enforced |
| Lint | `bun run lint` (`oxlint`) | not in `check` |

`./test.sh` is the component runner: installs deps if absent, then `bun run
check`. Registered in `.github/checks-manifest.yaml` as `web-app-checks`.
Vitest is scoped to `src/`; `scripts/` is `bun test` only, because the moonshine
smoke test imports `bun:test`.

Lint moved from `eslint` to `oxlint` with the moonshine migration, so the
`eslint-config-next` React Compiler backlog no longer applies.

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
