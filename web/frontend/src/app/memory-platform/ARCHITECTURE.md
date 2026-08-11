# `/memory-platform` package

The public developer surface for Omi's backend-authoritative memory service.

## Routes

| Route                      | Rendering               | Purpose                                                                                                         |
| -------------------------- | ----------------------- | --------------------------------------------------------------------------------------------------------------- |
| `/memory-platform`         | Server                  | Landing page. Positioning, surfaces, JSON-LD.                                                                   |
| `/memory-platform/docs`    | Server                  | REST + MCP reference. Bounds are read from `MEMORY_PLATFORM_LIMITS`, never hardcoded in prose.                  |
| `/memory-platform/embed`   | Server (client preview) | Integration guide plus a live, sandboxed render of the widget.                                                  |
| `/memory-platform/keys`    | Server shell + client   | MCP key list / create / rotate / revoke.                                                                        |
| `/memory-platform/billing` | Server shell + client   | Plan, platform-API quota, upgrade path.                                                                         |
| `/memory-platform/widget`  | Server shell + client   | The embeddable surface itself. `noIndex`. Pinned over the viewport so host iframes never show marketing chrome. |

## Layout

- `components/` — kebab-case route-local components. `platform-shell.tsx` owns the dark chrome and applies the `dark` class the shadcn primitives key off (the app's root layout is light).
- `utils/metadata.ts` — `generateMetadata()` builder plus JSON-LD helpers, mirroring `app/apps/utils/metadata.ts`.
- `utils/snippets.ts` — every published code snippet, single-sourced so docs and pages cannot drift.
- `hooks/use-session-token.ts` — Firebase session + a stable `getToken()` that mints a fresh ID token per request. Tokens are never persisted. `getToken` is memoized: consumers use it as an effect dependency, so an unstable identity re-triggers every load.
- `hooks/use-embed-session.ts` — how a framed widget gets a credential. The sandboxed frame has an opaque origin and no storage, so Firebase cannot work inside it; the host page mints a short-lived token server-side and hands it over by `postMessage`. Messages are validated by `event.source`, never by origin, because an opaque-origin sender always reports `"null"`.

## Backend seams

All network calls live in `src/lib/api/`, one function per endpoint:

- `memory-platform.ts` — `GET /v1/memory/platform`, `/search`, `POST /ingest`. `MEMORY_PLATFORM_LIMITS` mirrors the bounds the backend enforces (`MAX_PRODUCT_MEMORY_READ_LIMIT`, query length, offset ceiling).
- `mcp-keys.ts` — list, create (with per-key `scopes`), rotate (`POST /v1/mcp/keys/{key_id}/rotate`), and revoke are all live against real routes. Nothing here is pending.
- `billing.ts` — plans, checkout, portal, overage, and `getPlatformApiQuota` (`GET /v1/memory/platform/quota`) are all live. `getAvailablePlans` must send `X-App-Platform: web`, or the backend serves the legacy catalog.
- `browser-base.ts` — the one base-URL helper every browser client uses. It reads `NEXT_PUBLIC_API_BASE_URL`; the server-only `API_URL` is undefined in the client bundle and collapses requests to the web origin.

## Invariants

- **INV-UI-1**: no purple anywhere. Accents are white/neutral plus lime `#b9f36b` and coral `#ff806a` for destructive/warning text.
- **Key handling**: a raw key exists only in React state, only for the lifetime of the reveal dialog. No `localStorage`, no cookies, no `NEXT_PUBLIC_*`.
- **Sandbox**: published and rendered iframes use `allow-scripts` without `allow-same-origin`. `backend/tests/unit/test_memory_platform_docs_guards.py` enforces this for `docs/memory/*.md`; `src/__tests__/memory-platform-surface.test.mjs` enforces it for this package.
- **Authority**: the UI never presents a local cache as canonical. Ingest failures surface as failures.

## Tests

`web/frontend/src/__tests__/memory-platform-surface.test.mjs`, run by `npm test`
(`node --test src/__tests__/*.test.mjs`). These are **static tripwires** — they read
source text and assert on it. They are not behavioral coverage of the rendered UI.
