# `@omi-core/dev-recall-stub`

**DEV ONLY. Never production authority.**

Tiny local HTTP fixture server that serves ratified synthesized-memory recall
pages so macOS / iOS shells and the integration harness have something real to
point at when the platform backend is not running.

It speaks the same page shape as `@omi-core/ratified-contracts` and asserts
every honest page with `isTrustedSynthesizedPageData` before writing the body.

## Start

From `core/`:

```bash
pnpm install
pnpm --filter @omi-core/dev-recall-stub build
pnpm --filter @omi-core/dev-recall-stub start
# or: node packages/dev-recall-stub/dist/create_dev_recall_stub_server.js
# or: node packages/dev-recall-stub/dist/create_dev_recall_stub_server.js 4821 --scenario=complete
```

Binds **`127.0.0.1` only** (hard rule 13). Default port **4821**, overridable:

```bash
pnpm --filter @omi-core/dev-recall-stub start -- --port=4821
pnpm --filter @omi-core/dev-recall-stub start -- 9123 --scenario=degraded
```

## Exact URL a shell should use

```
http://127.0.0.1:4821/v1/memories/recall?limit=2
```

Continuation (opaque cursor from the previous page's `window.nextCursor`):

```
http://127.0.0.1:4821/v1/memories/recall?limit=2&cursor=<opaque>
```

Scenario override on the request (takes precedence over the startup default):

```
http://127.0.0.1:4821/v1/memories/recall?limit=2&scenario=degraded
```

Any other path → **404** with an empty body.

## Scenarios

| Name | How to select | What you get |
|---|---|---|
| `complete` | default, or `?scenario=complete` / `--scenario=complete` | Multi-page keyset walk over a seeded 5-item corpus. Every page has `completeness.status: "complete"`. Non-final pages use `window.status: "more"` + `nextCursor`; the last page is the complete-terminal window. |
| `degraded` | `?scenario=degraded` / `--scenario=degraded` | Same corpus and pagination, but `completeness.status: "degraded"` and `reasons: ["projection_stale"]`. |
| `query_gap` | `?scenario=query_gap` / `--scenario=query_gap` | Zero items, `absence: { "kind": "query_gap" }`, complete recall, complete-terminal window. |
| `http_503` | `?scenario=http_503` / `--scenario=http_503` | HTTP **503**, empty body. Client must surface `http-error`, not invent a page. |
| `malformed` | `?scenario=malformed` / `--scenario=malformed` | HTTP **200** with a body that deliberately fails the ratified predicate (missing `contractVersion`). Client must report `unreadable` / UNKNOWN — never salvage an empty complete page. |

## Importable server (tests)

```ts
import { createDevRecallStubServer } from "@omi-core/dev-recall-stub";

const stub = await createDevRecallStubServer({ port: 0, scenario: "complete" });
// stub.origin === "http://127.0.0.1:<ephemeral>"
await stub.close();
```

## Determinism

Page generation uses a fixed seeded corpus and fixed frontier strings. No
`Math.random`, no `Date.now`, no wall clock. The same `(scenario, limit, cursor)`
request produces byte-identical response bodies every time.

## Supervisor note

Barrels are generated. Add this package to `core/scripts/gen-barrels.mjs`
(`packages/dev-recall-stub/src/index.ts`) and run `node scripts/gen-barrels.mjs`
before treating `./dist/index.js` as the public entry. Until then, the package
`main` / `exports` point at `create_dev_recall_stub_server.js` directly.
