# omi local backend (`apps/service`)

## What this is

This is the canonical app-facing HTTP service, booted loopback-only for testing a real macOS or iOS app against the new omi backend rewrite. It starts from a cold checkout with deterministic QA seed data and exposes the same Hono app that tests exercise via `createLocalService` in `app-facing.ts` — `bin/dev-server.ts` adds only process concerns (config, socket, printing). The local composition uses in-memory and SQLite adapters; a deployed composition replaces those with production adapters and credentials.

## Run it

From the repo root:

```bash
bun run apps/service/bin/dev-server.ts
```

Zero environment variables are required. Supplying `OMI_QA_DB` switches the
entire registered service—not only Memories—to one file-backed SQLite
connection. Rebooting with the same file preserves service state; only the
explicit reset route restores the deterministic seed. On success the server
prints:

```
omi local backend is up

  base URL      http://127.0.0.1:4851
  bound to      127.0.0.1 (loopback only - not reachable from the LAN)
  seed identity local-dev-user, 12 memories, America/Los_Angeles
  time anchor   2026-08-07T12:00:00.000Z
  storage       :memory: (SQLite, QA fixture only - never production authority)

  dev token
    <token printed here>

  try it
    TOKEN='<same token>'
    curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:4851/v1/conversations?limit=5"
    curl -s http://127.0.0.1:4851/v1/qa/status
    curl -s -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:4851/v1/qa/reset

  served-request count prints below whenever it changes.
  if it stays at 0 while the app shows memories, the app is NOT talking to this backend.
```

After domain traffic arrives, a `[served]` heartbeat line prints whenever counts change (once per second at most):

```
[served] domain-reads=1 denied=0 failed=0 other=1
```

Stop with Ctrl-C (`omi dev-server: stopped`).

### Boot acceptance (for launchers)

`bin/boot-acceptance.ts` spawns the real dev server on port **4851**, drives it over HTTP, and prints one JSON verdict line to stdout. Exit 0 only when every check passes:

```bash
bun run apps/service/bin/boot-acceptance.ts
```

Example passing output:

```json
{"version":"boot-acceptance-v1","port":4851,"checks":[{"name":"boot","status":"pass","detail":"ready"},{"name":"health","status":"pass","detail":"status 200"},{"name":"memories-unauth","status":"pass","detail":"status 401"},{"name":"memories-page1","status":"pass","detail":"status 200 items 3"},{"name":"memories-pagination","status":"pass","detail":"pages 4 items 12"},{"name":"conversations-page1","status":"pass","detail":"status 200 items 1"},{"name":"qa-served-count","status":"pass","detail":"served count 5"},{"name":"qa-reset","status":"pass","detail":"reset total"},{"name":"loopback","status":"pass","detail":"loopback pass"}],"servedCount":5,"verdict":"pass"}
```

## Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/health` | none | Liveness (`{"status":"ok"}`) |
| `GET` | `/ready` | none | Readiness (`{"status":"ready"}`) |
| `GET` | `/v1/memories` | Bearer | Canonical paginated memory read (`limit`, `cursor`) |
| `GET` | `/v1/memories/recall` | Bearer | Transitional alias — same handler, byte-identical responses |
| `GET` | `/v1/conversations` | Bearer | Legacy-compatible conversation collection (`limit`, `offset`) |
| `PATCH` | `/v1/conversations/{id}/title` | Bearer | Set title from `?title=` |
| `PATCH` | `/v1/conversations/{id}/starred` | Bearer | Set starred from `?starred=true\|false` |
| `PATCH` | `/v1/conversations/{id}/visibility` | Bearer | Set visibility from `?value=public\|private\|shared` |
| `PATCH` | `/v1/conversations/{id}/folder` | Bearer | Set or clear folder with JSON `{folder_id}` |
| `DELETE` | `/v1/conversations/{id}` | Bearer | Delete only with explicit `?cascade=false` |
| `GET` | `/v1/chat-messages` | Bearer | Canonical Chat history and capabilities |
| `POST` | `/v1/chat-messages` | Bearer | Finite idempotent send admission; generation is read separately |
| `POST` | `/v1/chat-attachments` | Bearer | Stage exactly one sniffed multipart `file` for a Chat send |
| `GET` | `/v1/chat-generations/{generationId}/events` | Bearer | SSE reconnect from `Last-Event-ID` or a current snapshot |
| `DELETE` | `/v1/chat-generations/{generationId}` | Bearer | Durable, idempotent generation cancellation |
| `GET` | `/v1/qa/status` | none | Served-traffic counters and seed identity |
| `POST` | `/v1/qa/reset` | Bearer (dev token) | Total deterministic reseed |
| `GET` | `/v1/qa/evidence?run={run}` | Bearer (dev token) | Counts-only producer matrix for an exact host-owned run |

## curl examples

Copy `TOKEN` from the banner (it is stable across restarts unless `OMI_DEV_TOKEN_SECRET` changes):

```bash
TOKEN='dev1.dev-local.eyJleHBpcmVzX2F0X2Vwb2NoX3NlY29uZHMiOjE3ODYxOTA0MDAsImlzc3VlZF9hdF9lcG9jaF9zZWNvbmRzIjoxNzg2MTA0MDAwLCJ1aWQiOiJsb2NhbC1kZXYtdXNlciIsInZlcnNpb24iOjF9.6LwnfRr8CYxh4B--b2BF2hCn7B34BhfzOPcEgY_htO8'

# First page of memories
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:4851/v1/memories?limit=5"

# Transitional alias (identical bytes to /v1/memories)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:4851/v1/memories/recall?limit=5"

# Conversations use the adopted legacy limit/offset wire
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:4851/v1/conversations?limit=5&offset=0"

# QA observability (no auth)
curl -s http://127.0.0.1:4851/v1/qa/status

# Reset seed to initial state
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:4851/v1/qa/reset
```

Unauthenticated memory reads return `401` with body `{"error":"unauthorized"}`.

## Is the app really talking to this backend?

Poll `GET /v1/qa/status` (no auth). The `served` object tracks request outcomes:

```json
{
  "version": "qa-status-v1",
  "served": {
    "version": "served-count-v1",
    "domainReadsServed": 1,
    "domainReadsDenied": 0,
    "domainReadsFailed": 0,
    "nonDomainRequests": 1,
    "totalRequests": 2
  },
  "seed": { ... }
}
```

**`domainReadsServed` must be greater than zero** after the app loads a served collection. It increments only when a memory or conversation GET successfully returns a response body — not when auth fails or validation fails. **`GET /health`, `GET /ready`, and `GET /v1/qa/status` only increment `nonDomainRequests`; they never move `domainReadsServed`.**

The dev-server terminal also prints `[served] domain-reads=N ...` whenever `domainReadsServed` changes. This matters because a client can appear healthy while silently serving its own fixtures or hitting a different listener — health checks alone cannot distinguish that failure mode.

## Reset and reseed

`POST /v1/qa/reset` with the dev token clears and repopulates every supplied
store to the same deterministic state as a fresh boot: Memories,
Conversations/Folders, Tasks and write ids/stragglers, Settings and account
control/session/lifecycle, Listen sessions/segments, Chat messages,
attachments/content and generation events. It also clears all producer
evidence. The response includes the seed identity:

```json
{"version":"qa-reset-v1","status":"reset","seed":{"owner_account_id":"local-dev-user","memory_count":12,"account_timezone":"America/Los_Angeles","fixture_time_anchor_utc":"2026-08-07T12:00:00.000Z"}}
```

Seeded memories are placed one per local calendar day, stepping backward from the fixed anchor `2026-08-07T12:00:00.000Z`, so day-grouping in the client matches regardless of host clock.

## Verdict-grade producer evidence

Native hosts attribute requests with either the existing combined
`x-omi-client-id: <run>::<shell>` form or the explicit pair
`x-omi-run-id: <run>` plus `x-omi-client-id: <shell>`. Shell is exactly
`macos|ios`; run ids are bounded ASCII and reserved/normalized buckets are
rejected. The registered route, not request JSON or query input, resolves the
domain.

`GET /v1/qa/evidence?run=<run>` returns `omi.producer-evidence.v1` with exactly
the 14 `shell x domain` coordinates. Regular HTTP domains expose only a
successful response count. Chat adds `acceptedAdmission`, counted only after
the atomic human-message plus accepted-generation commit and never again for a
replay. Listen adds `protocolReady`, `acceptedBinary`, and
`acceptedBinaryBytes`; an upgrade or ready frame without non-empty audio leaves
the binary counts at zero. The document contains no token, account id, prompt,
transcript, attachment metadata, or other user/fixture content.

## Chat attachments

`POST /v1/chat-attachments` accepts one multipart field named `file`. The
service normalizes its basename, detects content from bytes, and returns an
opaque staged id; caller-provided account ids, metadata, paths, URLs and inline
message content are not accepted. Effective policy is four attachments per
message, 50 MiB per attachment, and the MIME list returned on every history
page: JPEG, PNG, GIF, WebP, PDF, UTF-8 plain text, and content-detected Markdown.

A message send carries only ordered `attachmentIds`. Admission binds each id
once to that account's main Chat message in the same transaction as the human
message, entitlement charge and durable dispatch record. Unbound staging lasts
24 hours. Bound content lasts 30 days from admission; its opaque
`contentReference` then becomes `null` while id, display name, media type and
byte size remain on history permanently. QA reset clears attachment metadata,
ownership and content together with Chat state.

## Chat generation lifecycle

The initiating Chat POST is finite JSON. The generation GET uses the ratified
SSE frame grammar. Advisory snapshots and deltas are durable only in the
generation event log; `done` always carries the complete canonical assistant
message also returned by history. A socket disconnect only stops that consumer
and never cancels model work.

Cancellation is a durable lifecycle transition. The supervisor stops its generation source, persists any non-empty partial assistant text as a canonical message, and emits `cancelled` with that same complete message. Cancelling a terminal generation returns `204` without adding another terminal.

Generation quota is reserved once, in the same admission transaction as the canonical human message and `accepted` event, through the shared Settings `readEntitlement` projection. Replaying the same client message id reuses that reservation and generation; terminal success or cancellation never decrements quota again.

On service construction, the supervisor scans durable non-terminal generations. A generation whose process disappeared without a cancellation request becomes `failed` with `generation_interrupted` and `retryable: true`; it is never resumed against a potentially non-deterministic provider and never remains `generating` indefinitely. A durable cancellation request discovered during recovery instead completes as `cancelled`, retaining its logged partial. Canonical assistant persistence and terminal event append share one SQLite transaction.

The local adapter emits a deterministic scripted answer with real timer delays.
Deployed LLM integration belongs behind `ChatGenerationSource`. Memory/context
consultation belongs behind `ChatGenerationContextSource`: the local adapter
returns an explicit `unavailable` envelope, while the opt-in PostgreSQL/Firebase
adapter reuses the canonical authorized memory page and preserves its citations,
window and completeness. No provider prompt or default consumes those bytes yet;
see `docs/memory-productionization/authorized-chat-memory-context-contract.md`.

The ratified Listen-to-memory semantic mapping is implemented as an inert
acceptance adapter; it is intentionally not called by the local socket
finalizer until an authoritative transcript seal and same-transaction outbox
exist. See
`docs/memory-productionization/listen-formation-ingestion-contract.md`.

## Environment variables

All are optional.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OMI_PORT` | `4851` | The one fixed app-facing listen port. |
| `OMI_SEED_OWNER` | `local-dev-user` | Owner account id written into the QA seed. |
| `OMI_SEED_MEMORIES` | `12` | Number of visible seeded memories. |
| `OMI_ACCOUNT_TIMEZONE` | `America/Los_Angeles` | IANA timezone for local-day grouping in the seed and read path. |
| `OMI_QA_DB` | `:memory:` | SQLite path, or `:memory:` for an ephemeral DB (recommended for cold checkout). |
| `OMI_DEV_TOKEN_SECRET` | `omi-local-dev-token-not-a-secret-v1` | Label hashed into the dev signing key. Change only if you need a different stable token across restarts. |
| `OMI_RUN_ID` | unset | Host-owned run id; requires `OMI_DEV_READY_RECORD`. |
| `OMI_DEV_READY_RECORD` | unset | Host-owned path for the versioned subprocess readiness record. |

## Troubleshooting

### Port already in use

If something else holds the port, boot may fail with:

```
omi dev-server: failed to bind 127.0.0.1:4851.
```

Find the listener:

```bash
lsof -nP -iTCP:4851 -sTCP:LISTEN
```

When Bun reports `EADDRINUSE`, the server instead prints:

```
omi dev-server: port 4851 is already in use. Something else is listening.
  Find it:  lsof -nP -iTCP:4851 -sTCP:LISTEN
  Stop the existing listener before booting the one service door.
```

### Invalid timezone

```
omi dev-server: OMI_ACCOUNT_TIMEZONE "Not/A/Timezone" is not a valid IANA timezone. Example: America/Los_Angeles. The zone is required because memories are grouped into days in LOCAL time, so a UTC-only fixture drifts by host.
```

### Unopenable database

```
omi dev-server: cannot open the QA database at "/nonexistent/path/qa.db". Check the directory exists and is writable, or unset OMI_QA_DB to use an in-memory database (the default, and what a cold checkout should use).
```

### Port out of registry range

```
omi dev-server: port 9999 is not allocated to this service. Use one bounded app-facing port.
```

### 401 on memory reads

Missing or invalid `Authorization: Bearer <token>` returns `401` with `{"error":"unauthorized"}`. Use the exact token from the boot banner. The dev token is not a production credential — it is fixed signing material for loopback fixture testing.

## Verifying the loopback bind

A loopback `curl` to `http://127.0.0.1:4851/health` succeeds even if the server is bound to all interfaces (`0.0.0.0`), which would expose it on the LAN. Verify binding with `lsof` **and** a LAN probe:

```bash
# 1. Confirm the listener is 127.0.0.1 only
lsof -nP -iTCP:4851 -sTCP:LISTEN
# Expect: TCP 127.0.0.1:4851 (LISTEN)

# 2. Automated check (used by boot-acceptance)
bun run apps/service/net/assert-loopback.ts 4851
```

Passing `assert-loopback` output looks like:

```json
{"version":"loopback-assertion-v1","port":4851,"lsof":{"status":"pass","listenerCount":1},"lanProbe":{"status":"pass","probedAddresses":["..."]},"verdict":"pass"}
```

If any non-loopback IPv4 address on the host can reach `/health`, `lanProbe.status` is `"fail"` with reason `"LAN address reached /health"`.

## Known limitations

- **The local binary deliberately remains SQLite QA.** The separately injected
  `createPostgresFirebaseAuthorizedMemoryServiceApp` composition now binds the
  authoritative PostgreSQL/Firebase memory reader to this same
  `/v1/memories` route and Hono `/mcp` root, but it chooses no listener,
  deployment credentials, MCP API-key adapter, or cohort. Conversations and the
  other local domains remain SQLite-only here.
- **No production Chat model adapter.** Local Chat generation uses the deterministic timed script; the production LLM remains a later source adapter.
- **Provisional served-memory selection.** The composition serves temporal **leaf** nodes (one synthesized memory per local day). That aligns with a timeline UI and the seeded fixture layout, but it is a QA composition choice, not a ratified product rule (`composition/memory-read.ts` documents this).
- **No field negotiation** for optional response fields such as citations or provenance — clients receive the full ratified wire shape.
- **Dev auth is a seam, not an auth system.** A fixed, committed signing label issues bearer tokens for loopback testing. A real deployment replaces this entire mechanism.
- **Records hidden by authorization are byte-identical on the wire, but NOT timing-identical.** A memory hidden by policy and a memory that never existed produce the same body, status, headers, item ids and cursors across the whole pagination walk — that is tested in `routes/hidden-vs-absent.test.ts`. They are still distinguishable by clock: hidden rows are loaded and policy-classified before being discarded, so the request costs work proportional to what exists rather than to what is visible. Measured at 8 visible vs 8 visible + 8 hidden: median 8.07 ms vs 10.46 ms, a 1.3x difference with non-overlapping p10/p90. This is a storage-layer concern (the authorization predicate should be applied in the query, not after load), not something the HTTP binding can fix. See `data/overnight-2026-08-08/blocked/BE-SURFACE-timing-side-channel.md`. Do not quote the byte-identity test as proof that hidden records are undetectable.
