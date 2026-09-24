# Hosted MCP server utilities

LIFECYCLE: permanent

Owns the hosted Model Context Protocol server behind `POST /v1/mcp`
(canonical) and `POST /v1/mcp/sse` (permanent compatibility alias), bound by
the thin router `routers/mcp_sse.py`. `routers/mcp.py` (REST) delegates onto
the same tool surface — `spec_for_tool` handlers where the contract is
identical (people, goals, chat, daily summaries, memory search/edit/delete,
action-item writes/search) and shared domain cores
(`handlers/*_core`, `database/action_item_sync.py`,
`database/mcp_conversation_pages.py`) where REST needs wider caps, incremental
parameters, or its released projections — while keeping its own top-level
array bodies, status codes, and rate buckets.

| Module | Responsibility |
|--------|----------------|
| `transport.py` | Coordinates one MCP POST: JSON-RPC envelope validation, batch policy, protocol-version and `Mcp-*` header integrity, admission and write rate limiting, tool dispatch, per-request logging/analytics |
| `versions.py` | Pure compatibility constants and negotiation: supported/handshake/batch revisions, `_meta` declaration resolution, `-32020`/`-32022` errors. No I/O |
| `registry.py` | Sole declarative `ToolSpec` for every hosted tool: name, description, input/output schemas, annotations, scope, rate bucket, analytics operation, handler |
| `auth.py` | Resolves API-key / OAuth bearer credentials into `MCPAuthContext` + `ProductAuthorizationContext`. Scope checks live in `registry.py`/`transport.py`; product authorization is enforced inside `handlers/` |
| `oauth.py` | OAuth authorize/token/consent endpoints: RFC 9207 `iss` on code and validated-error redirects (unknown clients/mismatched redirects get JSON only), CIMD clients resolved via `database/mcp_client_metadata.py` and shown as `Unverified third-party app` + `Client ID host`, omitted-scope defaults to allowed `*.read`; `/token` maps token-store outage to `503 temporarily_unavailable`. Grant revoke lives in `routers/mcp.py` |
| `metadata.py` | Per-path OAuth protected-resource documents (canonical vs `/sse`) and authorization-server metadata (`client_id_metadata_document_supported`, `scopes_supported`); `server/discover` is answered in `transport.py` |
| `cursors.py` | Opaque cursor tokens for list tools: ≤4 KiB before base64, `(created_at, __name__)`/`(updated_at, __name__)` keyset positions, `DatetimeWithNanoseconds` round-trip |
| `payloads.py` | Single leaf for `_tool_result_payload`/`_complete_result` shared by transport and handlers, so the batch response budget measures the real serialized wire form (envelope + SSE frame) |
| `errors.py` | `ToolExecutionError` → stable model-visible `isError` code mapping (JSON-RPC error envelopes are built in `transport.py`) |
| `helpers.py` | Shared shaping: date parsing, conversation cards, transcript bounding (int parsing lives in `utils/mcp_memories.py`) |
| `constants.py` | Request bounds: batch cap 20, fetch/list/char limits (tools-list TTLs live in `versions.py`) |
| `handlers/memories.py` | Memory tools incl. ledger-aware `edit_memory` via `update_content` |
| `handlers/conversations.py` | Conversation list/get/search tools |
| `handlers/action_items.py` | Action-item read/write tools |
| `handlers/other.py` | Screen activity, people, goals, chat, X posts, daily summaries |
| `handlers/profile.py` | User-profile tool |

## Transport and protocol boundary

- Stateless core: each POST is self-contained; the 2026-07-28 revision is
  declared per message via `_meta`/header and never negotiated.
- Legacy-era batches (2025-03-26 / 2024-11-05 / undeclared) are capped at 20
  messages; modern revisions reject arrays.
- `GET` → 405, `HEAD` → auth probe, `DELETE` → 204 on both paths.
- `get_conversations_by_ids` budgets the whole serialized JSON-RPC response
  (≤120k chars), not just inner item JSON. List tools offer cursors;
  `get_action_items` also supports `updated_since`.
- Scope challenges stay protocol errors (`-32003` with `mcp/www_authenticate`);
  typed tool errors (`ToolExecutionError`) intentionally return safe,
  model-actionable messages. Unexpected exception text never reaches responses;
  server-side `logger.exception` retains stack traces for debugging.
- OAuth accepts canonical and legacy `/sse` resource audiences as equivalent
  but never matches cross-origin resources.
- Analytics (`utils/mcp_analytics.py`, sibling module) emit only normalized
  closed enums and bounded fields — no arguments, content, IDs, credentials,
  IP, or user-agent.
- No import-time I/O; storage is required at request time. The POST-level
  `mcp:sse` admission limiter fails open on Redis errors (HTTP 429 when
  exceeded) while the tool-write limiter fails closed: a `429` returns
  `isError` `rate_limited` with a retry hint, `403` returns
  `authorization_denied`, and `503`/unexpected returns `unavailable` — all with
  safe generic messages, never the raw limiter detail. PostHog telemetry fails
  open.
- `validate_access_token` is Redis-fronted (`database/mcp_token_cache.py`):
  positive-only cache (`TTL min(60s, expiry remaining)`, HMAC-signed payloads
  bound to their token key via `database/mcp_cache_integrity.py`), zero
  Firestore work on hits, revocation markers + grant token index with
  mandatory marker-first fail-closed revoke, `last_used_at` throttled on
  validated misses only. Redis outage → `503 + Retry-After`, never `401`.

## Companion leaves outside this directory

- `config/mcp_resource_urls.py` — canonical/legacy `/sse` audience
  equivalence shared by `database/mcp_oauth.py` and the token cache;
  cross-host resources never match.
- `database/mcp_client_metadata.py` — CIMD: URL-form `client_id` documents
  fetched with SSRF defenses (every DNS answer public, IP-pinned
  `HTTPSConnectionPool` with hostname verification, no redirects, ≤16 KiB),
  validated `client_id`/redirect URIs/public-client auth, sanitized
  `client_name`, HMAC-signed Redis cache honoring `Cache-Control`
  (`no-store`/`no-cache`/`private` bypass; `max-age` clamped to 3600).
- `database/mcp_conversation_pages.py` — `(created_at DESC, __name__ DESC)`
  keyset card pages that skip tombstones under a bounded scan budget.
- `database/action_item_sync.py` — the truthful `(updated_at ASC,
  __name__ ASC)` action-item sync query shared by the MCP tool and REST.
- `docs/mcp-rest-sync.md` — REST cursor/`X-Next-Cursor` contract and the
  `503 incremental_sync_unavailable` gates on conversations/memories.

## Non-goals

- No RFC 7591 Dynamic Client Registration — clients are either configured
  (`MCP_OAUTH_CLIENTS_JSON` etc.) or self-describing via CIMD; the server
  never mints client registrations.
- No MCP SDK transport; this is the custom FastAPI JSON-RPC implementation.
- No REST response-contract changes beyond additive fields/headers
  (`updated_at`/`deleted`, `truncated`, `X-Next-Cursor`, `X-Scan-Truncated`)
  — sharing is at the handler/core layer, not a merged schema.
- Server-initiated streaming: `/v1/mcp/sse` is an endpoint path alias. POST can
  return finite SSE frames when the client sends `Accept: text/event-stream`;
  GET opens no server-initiated stream.
