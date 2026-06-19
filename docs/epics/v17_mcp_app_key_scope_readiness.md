# V17 MCP app/key/scope authorization readiness

**Date:** 2026-06-19  
**Scope:** Oracle P0-1/P0-6 first MCP REST/SSE V17 memory authorization context/readiness slice.

## Current MCP REST routes and dependencies

MCP REST routes in `backend/routers/mcp.py` still authenticate API keys with the uid-only dependency:

```python
uid: str = Depends(get_uid_from_mcp_api_key)
```

Memory surfaces observed:

| Surface | Route/tool | Current auth value | Current V17 memory behavior | V17 app/key/scope status |
|---|---|---|---|---|
| REST create | `POST /v1/mcp/memories` | uid only | Legacy write guarded by V17 read/write convergence guard | Not app/key/scope-grant wired |
| REST delete | `DELETE /v1/mcp/memories/{memory_id}` | uid only | Legacy delete guarded by V17 read/write convergence guard | Not app/key/scope-grant wired |
| REST edit | `PATCH /v1/mcp/memories/{memory_id}` | uid only | Legacy edit guarded by V17 read/write convergence guard | Not app/key/scope-grant wired |
| REST search | `GET /v1/mcp/memories/search` | uid only | Existing V17 vector adapter uses per-user MCP rollout decision, then explicit legacy-safe fallback | Missing app/key/scope context before V17 vector read |
| REST list | `GET /v1/mcp/memories` | uid only | Legacy list/filter path only | If promoted to V17 default-list, must use app/key/scope context first |

Compatibility requirement preserved by this slice: `get_uid_from_mcp_api_key(...)` remains available and existing uid-only MCP routes are not rewired.

## Current MCP streamable HTTP/SSE tools

`backend/routers/mcp_sse.py` advertises OAuth-style scopes through tool `securitySchemes` and metadata:

- `memories.read`
- `memories.write`
- `conversations.read`
- `action_items.read`
- `goals.read`
- `chat.read`
- `screen_activity.read`
- `people.read`

Memory tools observed:

| Tool | Advertised security | Current execution value | Current V17 memory behavior | V17 app/key/scope status |
|---|---|---|---|---|
| `get_memories` | `memories.read` | `execute_tool(user_id, tool_name, arguments)` uid string only | Legacy list/filter path | Missing verified scopes/app/key execution context |
| `search_memories` | `memories.read` | uid string only | Existing V17 vector adapter uses per-user MCP rollout decision, then explicit legacy-safe fallback | Missing app/key/scope context before V17 vector read |
| `create_memory` | `memories.write` | uid string only | Legacy write guarded by V17 read/write convergence guard | Missing app/key/scope write context |
| `delete_memory` | `memories.write` | uid string only | Legacy delete guarded by V17 read/write convergence guard | Missing app/key/scope write context |
| `edit_memory` | `memories.write` | uid string only | Legacy edit guarded by V17 read/write convergence guard | Missing app/key/scope write context |

## MCP API key model/storage gap

Current MCP API key storage/model files are `backend/database/mcp_api_key.py` and `backend/models/mcp_api_key.py`.

Current key document fields created for `mcp_api_keys/{key_id}`:

```yaml
id: <uuid>
user_id: <uid>
name: <display name>
hashed_key: <hash>
key_prefix: <prefix>
created_at: <timestamp>
last_used_at: null
```

The public `McpApiKey` model returns only `id`, `name`, `key_prefix`, `created_at`, and `last_used_at`. There is no persisted `app_id`, no persisted key scopes, no OAuth token introspection result, and the Redis MCP key cache stores only `user_id`.

Therefore this slice does **not** invent MCP scopes or treat advertised OAuth scopes as verified execution scopes. Any V17 route/tool wiring must wait until one of these exists:

1. MCP API keys persist server-owned `app_id`, `key_id`, and verified scopes, and the auth dependency returns them; or
2. MCP OAuth bearer tokens are introspected/verified and the execution context carries stable client/app/key identity plus verified scopes.

## Helper added in this slice

Added to `backend/utils/mcp_memories.py`:

```python
@dataclass(frozen=True)
class McpV17VerifiedAuth:
    uid: str
    app_id: Optional[str] = None
    key_id: Optional[str] = None
    scopes: tuple[str, ...] = ()

MCP_V17_DEFAULT_MEMORY_READ_SURFACE = 'mcp_default_memory_read'

def build_mcp_v17_default_memory_read_context(auth: McpV17VerifiedAuth) -> V17ProductAuthorizationContext: ...
```

The helper is deliberately fake-injectable. It carries `uid`, stable `app_id`, `key_id`, verified scopes, `consumer='mcp'`, and `surface='mcp_default_memory_read'` into the existing shared `V17ProductAuthorizationContext` / `authorize_v17_external_default_memory_read(...)` seam.

Missing `app_id`, `key_id`, or `memories.read` is not papered over; composing the resulting context with `authorize_v17_external_default_memory_read(...)` fails closed through deterministic existing reasons:

- `missing_app_or_key_identity`
- `missing_authenticated_scope_memories.read`
- `missing_v17_app_key_memory_grants_state` / malformed state reason
- `missing_app_key_scope_grant`
- `app_key_scope_grant_disabled`
- `missing_persisted_scope_memories.read`
- `missing_default_read_grant`

Valid injected MCP context plus stored server-owned grant at:

```text
users/{uid}/memory_control/v17_app_key_memory_grants
grants.mcp.apps.{app_id}.keys.{key_id}
```

allows default-read authorization with `archive_capability=false`. Archive remains unavailable by default and no Archive MCP route/tool was added.

## Required future route wiring point

When MCP auth can supply real verified scopes/app/key identity, the safe composition point for V17 default reads is:

```python
auth_context = build_mcp_v17_default_memory_read_context(verified_mcp_auth)
v17_app_key_grant = authorize_v17_external_default_memory_read(auth_context, db_client=db)
if not v17_app_key_grant.allowed:
    deny before read_v17_mcp_default_memory_rollout(...)
```

This must occur before any V17 vector query, repair/outbox side effect, or `users/{uid}/memory_items` hydration. For streamable HTTP/SSE, the JSON-RPC session/tool execution signature must carry a verified auth context rather than only `user_id: str` before tool execution can be safely V17-wired.

## RED tests still needed before route enforcement

- MCP API key persistence test proving server-owned scopes are written/read and client-requested scopes are ignored.
- Auth dependency test proving REST `get_mcp_v17_default_memory_read_context` returns uid/app_id/key_id/verified scopes and preserves uid-only compatibility.
- REST `GET /v1/mcp/memories/search` test proving missing app/key/scope/grant denies before V17 vector read and repair/outbox writer.
- SSE `search_memories` test proving the same deny-before-vector behavior with a verified execution context.
- SSE `get_memories` default-list test only if that tool is promoted to V17 reads.
- Write-scope tests for create/edit/delete only when V17 write convergence is designed; do not broaden writes through this default-read helper.

## Explicit non-claims

This slice is a readiness/context helper only. It does **not** wire MCP REST/SSE V17 reads to app/key/scope enforcement, persist MCP key scopes, introspect OAuth tokens, run deployed Firestore/IAM proof, call Pinecone, approve production rollout, expose Archive by default, or claim benchmarks/telemetry/cloud evidence.
