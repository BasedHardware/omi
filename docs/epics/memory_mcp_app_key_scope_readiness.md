# memory MCP app/key/scope authorization readiness

**Date:** 2026-06-19
**Scope:** Oracle P0-1/P0-6 first MCP REST/SSE memory memory authorization context/readiness slice.

## Current MCP REST routes and dependencies

MCP REST routes in `backend/routers/mcp.py` still authenticate API keys with the uid-only dependency:

```python
uid: str = Depends(get_uid_from_mcp_api_key)
```

Memory surfaces observed:

| Surface | Route/tool | Current auth value | Current memory memory behavior | memory app/key/scope status |
|---|---|---|---|---|
| REST create | `POST /v1/mcp/memories` | uid only | Legacy write guarded by memory read/write convergence guard | Not app/key/scope-grant wired |
| REST delete | `DELETE /v1/mcp/memories/{memory_id}` | uid only | Legacy delete guarded by memory read/write convergence guard | Not app/key/scope-grant wired |
| REST edit | `PATCH /v1/mcp/memories/{memory_id}` | uid only | Legacy edit guarded by memory read/write convergence guard | Not app/key/scope-grant wired |
| REST search | `GET /v1/mcp/memories/search` | uid only | Existing memory vector adapter uses per-user MCP rollout decision, then explicit legacy-safe fallback | Missing app/key/scope context before memory vector read |
| REST list | `GET /v1/mcp/memories` | uid only | Legacy list/filter path only | If promoted to memory default-list, must use app/key/scope context first |

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

| Tool | Advertised security | Current execution value | Current memory memory behavior | memory app/key/scope status |
|---|---|---|---|---|
| `get_memories` | `memories.read` | `execute_tool(user_id, tool_name, arguments)` uid string only | Legacy list/filter path | Missing verified scopes/app/key execution context |
| `search_memories` | `memories.read` | uid string only | Existing memory vector adapter uses per-user MCP rollout decision, then explicit legacy-safe fallback | Missing app/key/scope context before memory vector read |
| `create_memory` | `memories.write` | uid string only | Legacy write guarded by memory read/write convergence guard | Missing app/key/scope write context |
| `delete_memory` | `memories.write` | uid string only | Legacy delete guarded by memory read/write convergence guard | Missing app/key/scope write context |
| `edit_memory` | `memories.write` | uid string only | Legacy edit guarded by memory read/write convergence guard | Missing app/key/scope write context |

## MCP API key model/storage contract

Current MCP API key storage/model files are `backend/database/mcp_api_key.py` and `backend/models/mcp_api_key.py`.

Current key document fields created for `mcp_api_keys/{key_id}` after the follow-up persisted-context contract slice:

```yaml
id: <uuid>
user_id: <uid>
name: <display name>
hashed_key: <hash>
key_prefix: <prefix>
created_at: <timestamp>
last_used_at: null
app_id: mcp-api | null
scopes: null | [memories.read, memories.write, ...]
```

The public `McpApiKey` model can now carry optional `app_id` and `scopes`. `database.mcp_api_key.get_user_and_scopes_by_api_key(...)` returns `user_id`, `app_id`, `key_id`, and persisted `scopes`. The Redis MCP key cache can store the same shape, while older uid-only cache entries decode as uid-only auth with `app_id=None`, `key_id=None`, and `scopes=None`. Existing `get_uid_from_mcp_api_key(...)` compatibility is preserved through `get_user_id_by_api_key(...)`.

Default behavior is fail-closed for memory authorization: old key docs have no `app_id`/`scopes`, new key creation writes stable server-owned `app_id: mcp-api` but `scopes: null` unless a server-side migration/admin path explicitly persists verified scopes. No client-supplied or advertised MCP tool scope is treated as verified execution authority.

There is still no OAuth token introspection result wired into MCP execution context. SSE sessions still pass only `user_id` into `execute_tool(...)`, so this is a persisted API-key auth-context contract, not route enforcement.

Therefore this slice does **not** invent MCP scopes or treat advertised OAuth scopes as verified execution scopes. Any memory route/tool wiring must wait until one of these exists:

1. MCP API keys persist server-owned `app_id`, `key_id`, and verified scopes, and the auth dependency returns them for the specific route/tool execution; or
2. MCP OAuth bearer tokens are introspected/verified and the execution context carries stable client/app/key identity plus verified scopes.

## Helper added in this slice

Added to `backend/utils/mcp_memories.py`:

```python
@dataclass(frozen=True)
class McpVerifiedAuth:
    uid: str
    app_id: Optional[str] = None
    key_id: Optional[str] = None
    scopes: tuple[str, ...] = ()

MCP_MEMORY_DEFAULT_MEMORY_READ_SURFACE = 'mcp_default_memory_read'

def build_mcp_default_memory_read_context(auth: McpVerifiedAuth) -> ProductAuthorizationContext: ...
```

The helper is deliberately fake-injectable. It carries `uid`, stable `app_id`, `key_id`, verified scopes, `consumer='mcp'`, and `surface='mcp_default_memory_read'` into the existing shared `ProductAuthorizationContext` / `authorize_memory_external_default_memory_read(...)` seam.

Missing `app_id`, `key_id`, or `memories.read` is not papered over; composing the resulting context with `authorize_memory_external_default_memory_read(...)` fails closed through deterministic existing reasons:

- `missing_app_or_key_identity`
- `missing_authenticated_scope_memories.read`
- `missing_app_key_memory_grants_state` / malformed state reason
- `missing_app_key_scope_grant`
- `app_key_scope_grant_disabled`
- `missing_persisted_scope_memories.read`
- `missing_default_read_grant`

Valid injected MCP context plus stored server-owned grant at:

```text
users/{uid}/memory_control/app_key_memory_grants
grants.mcp.apps.{app_id}.keys.{key_id}
```

allows default-read authorization with `archive_capability=false`. Archive remains unavailable by default and no Archive MCP route/tool was added.

## Required future route wiring point

When MCP auth can supply real verified scopes/app/key identity, the safe composition point for memory default reads is:

```python
auth_context = build_mcp_default_memory_read_context(verified_mcp_auth)
app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
if not app_key_grant.allowed:
    deny before read_mcp_default_memory_rollout(...)
```

This must occur before any memory vector query, repair/outbox side effect, or `users/{uid}/memory_items` hydration. For streamable HTTP/SSE, the JSON-RPC session/tool execution signature must carry a verified auth context rather than only `user_id: str` before tool execution can be safely memory-wired.

The REST dependency helper now exists as `get_mcp_memory_default_memory_read_context(...)`; it returns a `ProductAuthorizationContext` only when the persisted MCP API-key context has `memories.read`, `app_id`, and `key_id`. It is intentionally **not** wired to `/v1/mcp/memories/search` yet because most current keys have no persisted scopes/grants and SSE still lacks a verified execution-context carrier.

## RED tests still needed before route enforcement

- Route-level REST `GET /v1/mcp/memories/search` test proving `get_mcp_memory_default_memory_read_context(...)` plus `authorize_memory_external_default_memory_read(...)` denies before memory vector read and repair/outbox writer when app/key/scope/grant composition fails.
- SSE `search_memories` test proving the same deny-before-vector behavior with a verified execution context.
- SSE `get_memories` default-list test only if that tool is promoted to memory reads.
- Write-scope tests for create/edit/delete only when memory write convergence is designed; do not broaden writes through this default-read helper.

## MCP API-key scope readiness runner / server-owned assignment contract

Added `backend/scripts/mcp_api_key_scope_readiness.py` as the production-safe readiness runner for Oracle P0-1/P0-6 MCP key scope migration planning.

Default command:

```bash
python3 backend/scripts/mcp_api_key_scope_readiness.py
```

Default behavior is `status=NOT_RUN`, `read_only=true`, `mutation_allowed=false`, and no Firestore reads or writes. It is suitable for checked-in readiness evidence only; it is **not** production proof.

Inventory command, when a real backend runtime/project context is intentionally supplied:

```bash
python3 backend/scripts/mcp_api_key_scope_readiness.py --execute
```

`--execute` inventories `mcp_api_keys/{key_id}` documents and reports:

- total key count;
- keys missing `app_id`;
- keys missing `scopes`;
- keys with malformed `scopes`;
- keys with verified persisted `memories.read`;
- keys with unknown scopes.

The runner distinguishes missing scopes from verified `memories.read`. It does **not** infer scopes from advertised MCP tool metadata, OAuth security scheme advertisements, or client request fields; in operational review shorthand, do not infer scopes from advertised MCP tool metadata.

Optional assignment command, only for a deterministic server-owned input file:

```bash
python3 backend/scripts/mcp_api_key_scope_readiness.py \
  --execute \
  --allow-write \
  --assignment-file /secure/admin/mcp-key-scope-assignments.json
```

The compact form is `python3 backend/scripts/mcp_api_key_scope_readiness.py --execute --allow-write --assignment-file /secure/admin/mcp-key-scope-assignments.json`.

Assignment file shape:

```json
{
  "<existing-mcp-key-id>": {
    "app_id": "mcp-api",
    "scopes": ["memories.read"]
  }
}
```

Mutation contract:

- writes are unreachable unless **both** `--execute` and `--allow-write` are supplied;
- only existing key IDs are patched via `mcp_api_keys/{key_id}` update;
- user IDs, key IDs, hashes, prefixes, and creation timestamps are preserved;
- allowed server-owned scopes are limited to `memories.read`, `memories.write`, and `memories.archive.read`;
- unknown scopes such as `tool.search_memories` are denied/skipped before writes;
- assignment does not create app/key memory grants at `users/{uid}/memory_control/app_key_memory_grants`; that remains a separate server-owned product/admin decision.

This runner was not executed against production in this slice. It provides a safe inventory/plan and an explicit server-owned assignment contract only.

## Explicit non-claims

This artifact now covers a readiness/context helper, a backward-compatible persisted MCP API-key auth-context contract, REST/SSE `search_memories` app/key/scope enforcement, and a safe-by-default MCP key scope readiness runner. It does **not** grant scopes to existing keys by default, create a general admin UI, implement OAuth token introspection (no OAuth introspection), run deployed Firestore/IAM proof, call Pinecone, approve production rollout, expose Archive by default, or claim benchmarks/telemetry/cloud evidence. It was not executed against production.
