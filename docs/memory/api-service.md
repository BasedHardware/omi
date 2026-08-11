---
title: Memory Platform API
description: Build against Omi's backend-authoritative memory service.
---

Omi's backend is the authority for memory. API clients, MCP clients, local capture, and zkr replicas consume the canonical service; they do not write Firestore or commit records directly.

## Discover the contract

```bash
curl https://api.omi.me/v1/memory/platform \
  -H "Authorization: Bearer $OMI_SESSION"
```

The response identifies `omi_backend`, the canonical `memory_items` collection, the apply-control chain, the REST/MCP surfaces, and the zkr mirror boundary.

## Search

`GET /v1/memory/platform/search` accepts `query`, `limit`, and `offset`. The authenticated user session determines the tenant. Query strings are limited to 500 characters, `limit` to 500 results (default 100), and `offset` to 100,000.

```bash
curl "https://api.omi.me/v1/memory/platform/search?query=launch&limit=20" \
  -H "Authorization: Bearer $OMI_SESSION"
```

Search uses the same canonical visibility and rollout policy as Omi's product memory surface. Archive is not default-visible.

## Ingest

`POST /v1/memory/platform/ingest` accepts the existing memory payload and promotes it through `MemoryService`. If canonical writes are unavailable, the service returns `503` and does not fall back to an independent store.

```bash
curl -X POST https://api.omi.me/v1/memory/platform/ingest \
  -H "Authorization: Bearer $OMI_SESSION" \
  -H "Content-Type: application/json" \
  -d '{"content":"The next launch is Thursday","category":"manual"}'
```

## MCP

The hosted MCP server exposes a read-only `memory_platform` tool with `memories.read`. It reports the same contract without returning memory content or credentials. Use `get_memories`, `search_memories`, and the write tools for scoped memory operations.

```json
{
  "mcpServers": {
    "omi": {
      "url": "https://api.omi.me/v1/mcp/sse",
      "headers": { "Authorization": "Bearer ${OMI_MCP_KEY}" }
    }
  }
}
```

## Keys

Manage MCP keys at [`/memory-platform/keys`](https://h.omi.me/memory-platform/keys), or through the session-authenticated endpoints:

- `GET /v1/mcp/keys` — list keys. Returns `key_prefix`, `created_at`, and `last_used_at`; never the key.
- `POST /v1/mcp/keys` — create a key. The raw key is returned **once**, in the create response, and cannot be retrieved afterwards.
- `DELETE /v1/mcp/keys/{key_id}` — revoke a key.

Available MCP scopes are dot-form: `memories.read`, `memories.write`, `conversations.read`, `action_items.read`, `action_items.write`, `goals.read`, `chat.read`, `screen_activity.read`, `people.read`. Default to `memories.read` and grant a write scope only when the integration writes.

Store keys in a server-side secret store. Do not place them in source, browser storage, or a public environment variable. If a key may have leaked, revoke it — a revoked key stops working immediately.

## Plan and quota

Platform API access follows the Omi subscription. `GET /v1/memory/platform/quota` reports the platform allowance: `plan`, `plan_type`, `unit`, `used`, `limit`, `remaining`, `allowed`, and `reset_at`. `limit` and `remaining` are `null` on an uncapped plan. Over-quota requests get a `429` naming the plan, limit, usage, and reset instant.

`GET /v1/payments/overage-info` is a different meter — it reports chat-question usage and chat overage, not Memory Platform requests. Plan and usage are also shown at [`/memory-platform/billing`](https://h.omi.me/memory-platform/billing), alongside the upgrade path through Stripe checkout.

## zkr replicas

zkr speaks the local evidence-backed replica side of the boundary. Keep its export high-water mark stable, apply only backend-acknowledged records, and rebuild local projections. A local zkr commit is not authoritative until it has passed backend ingestion and canonical apply.
