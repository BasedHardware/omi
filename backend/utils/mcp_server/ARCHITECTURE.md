# Hosted MCP server utilities

LIFECYCLE: permanent

Owns the hosted Model Context Protocol server behind `POST /v1/mcp`
(canonical) and `POST /v1/mcp/sse` (permanent compatibility alias), bound by
the thin router `routers/mcp_sse.py`. `routers/mcp.py` (REST) reuses the
registry only for the response-equivalent `get_goals` and `get_people`
handlers; all other REST contracts stay separate.

| Module | Responsibility |
|--------|----------------|
| `transport.py` | Coordinates one MCP POST: JSON-RPC envelope validation, batch policy, protocol-version and `Mcp-*` header integrity, admission and write rate limiting, tool dispatch, per-request logging/analytics |
| `versions.py` | Pure compatibility constants and negotiation: supported/handshake/batch revisions, `_meta` declaration resolution, `-32020`/`-32022` errors. No I/O |
| `registry.py` | Sole declarative `ToolSpec` for every hosted tool: name, description, input/output schemas, annotations, scope, rate bucket, analytics operation, handler |
| `auth.py` | Resolves API-key / OAuth bearer credentials into `MCPAuthContext` + `ProductAuthorizationContext`. Scope checks live in `registry.py`/`transport.py`; product authorization is enforced inside `handlers/` |
| `oauth.py` | OAuth authorize/token/consent endpoints; canonical + legacy `/sse` resource-audience equivalence without cross-origin relaxation. Grant revoke lives in `routers/mcp.py` |
| `metadata.py` | OAuth protected-resource and authorization-server well-known documents (`server/discover` is answered in `transport.py`) |
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
- Scope challenges stay protocol errors (`-32003` with `mcp/www_authenticate`);
  typed tool errors (`ToolExecutionError`) intentionally return safe,
  model-actionable messages, while unexpected exception text and stack traces
  never reach responses or logs.
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

## Non-goals

- No CIMD/dynamic client registration — the authorization server keeps its
  existing configured-client model (`MCP_OAUTH_CLIENTS_JSON` etc.).
- No MCP SDK transport; this is the custom FastAPI JSON-RPC implementation.
- REST response contracts outside the two shared read handlers.
- Server-initiated streaming: `/v1/mcp/sse` is an endpoint path alias. POST can
  return finite SSE frames when the client sends `Accept: text/event-stream`;
  GET opens no server-initiated stream.
