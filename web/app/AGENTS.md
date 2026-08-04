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

## Destinations

One rail entry per destination, and one place per idea:

| Route | Holds |
|---|---|
| `/home` | The hub **and** the chat. Chat is not a separate page: Home rests on the hub for an empty account and opens in the transcript once there is history (`src/lib/homeStage.ts`, ported from desktop's `restingMode`). Live capture starts here too. |
| `/timeline` | Conversations and daily recaps in one day-grouped gallery. |
| `/memories`, `/tasks` | As named. |
| `/connectors` | Installed apps **and** external services — the former Settings → Integrations. |
| `/settings` | Account (profile + plan merged), Privacy, Developer. |

Removed rather than redirected, so do not re-add aliases: `/chat`, `/conversations`,
`/recaps`, `/my-apps`, `/persona`.

Page chrome is shared: `components/layout/PageToolbar.tsx` gives every page its
left controls, right-aligned search and actions, and renders **no page title** —
the sidebar is the only thing that names the page. `PageHeader` is for detail
and sub pages that need a back button. shadcn/ui is set up (`components.json`);
its primitives are restyled onto the Omi tokens, because the generator emits
literal `oklch(...)` strings that are not valid classes here.

The accent is white and there are no purple tokens left to reach for — see
`docs/product/invariants/brand-ui.md` (INV-UI-1).

## Runtime

Needs `@tschk/moonshine` **>= 0.3.7**. Before it, the router's location signal
carried only the pathname, so a navigation that changed only the query wrote the
same value back and re-rendered nothing — every `useSearchParams` caller in an
already-mounted tree kept showing the previous query.

Two framer-motion traps this runtime sets, both already paid for:
- Every route registers its own copy of the authenticated layout, so navigating
  **remounts the shell**. `AnimatePresence initial={false}` therefore suppresses
  the enter animation on every navigation, not just the first.
- A hidden tab freezes rAF and CSS transitions, so animation measured through a
  backgrounded browser reads as permanently stuck at its initial frame. Check
  `document.visibilityState` before believing an animation is broken.

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
