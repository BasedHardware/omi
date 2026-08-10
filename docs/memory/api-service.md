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

## zkr replicas

zkr speaks the local evidence-backed replica side of the boundary. Keep its export high-water mark stable, apply only backend-acknowledged records, and rebuild local projections. A local zkr commit is not authoritative until it has passed backend ingestion and canonical apply.
