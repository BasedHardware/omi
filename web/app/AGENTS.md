# web/app — Developer Guide

The signed-in Omi web client: React 19 on the `@tschk/moonshine` runtime, served
by Bun. Siblings: `web/admin`, `web/frontend`, `web/personas-open-source`.

## Setup

```bash
cd web/app
bun install     # the Dockerfile uses the same bun.lock
bun run dev     # full build, serve, rebuild on change (scripts/dev.ts)
```

`dev` runs the full build, not `moonshine dev`: `build:assets` injects
`NEXT_PUBLIC_*` and writes the real server, and the app boots blank without it.
Use Bun, never npm or pnpm — `Dockerfile` installs from `bun.lock`.

## Quality Gates

| Gate | Command | Status |
|---|---|---|
| Types | `bun run typecheck` | enforced |
| Tests | `bun run test` — `bun test` for the moonshine smoke suite, then vitest for `src/` | enforced |
| Both | `bun run check` — what `./test.sh` and CI run | enforced |
| Lint | `bun run lint` (`oxlint`) | not in `check` |

`./test.sh` (manifest: `web-app-checks`) installs deps if absent, then `bun run
check`. Vitest is scoped to `src/`; `scripts/` is `bun test` only, because the
moonshine smoke test imports `bun:test`.

## Destinations

`/home` is the hub *and* the chat, `/conversations` is conversations plus
recaps, `/connectors` is apps plus services. `/chat`, `/recaps`, `/my-apps` and
`/persona` were removed, not redirected — do not re-add aliases.
Route map, shared page chrome, shadcn, the moonshine >= 0.3.7 floor, and this
runtime's two motion traps:
[`.github/agent-docs/web-app-destinations.md`](../../.github/agent-docs/web-app-destinations.md).

## State & Tests

Home runs on `@tschk/moonshine` signals, not React state: `useAsyncResource` for
reads, a signal store for optimistically-written lists. Import only the kernel —
why and the pitfalls: [`.github/agent-docs/web-app-signals.md`](../../.github/agent-docs/web-app-signals.md).

Tests live in `__tests__/` beside the code (`vitest.config.mts`, jsdom, `@` →
`src/`). Prefer pure logic in `src/lib/` and `src/hooks/`; reserve component
rendering for behavior that only appears in the tree.

## Parity With Desktop

Not a port of `desktop/macos` and cannot be one — Rewind, Focus, Insights, the
floating bar, Bluetooth pairing and local indexing need macOS capture APIs with
no browser equivalent. Before porting a surface, check whether its data comes
from a `backend/routers/` endpoint (portable) or local Swift storage (not).
