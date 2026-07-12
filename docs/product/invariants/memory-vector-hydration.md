# INV-MEM-2: Vector hydration fail-closed

**Status:** locked
**Statement:** Vector search hits are candidate memory IDs only. Every hit
must hydrate against an authoritative `memory_items` record and pass projection
freshness and access checks before it may appear in user-visible results.
Missing or stale hydration fails closed (empty or filtered results plus repair
candidates), never raw vector IDs.

## MUST NOT

- Return vector hits directly without authoritative hydration.
- Treat Pinecone/vector metadata as the source of truth for product memory content.
- Fail open when hydration rejects a hit (silent drop without repair telemetry is
  allowed only when access policy denies the item, not when the item is missing
  or stale).

## Surfaces

- `models.memory_search_gateway` hydration gateway
- `utils.memory.vector_search_service` vector search orchestration
- Vector repair outbox and metadata adapters under `database/memory_vector_*`

## Guard tests

- `backend/tests/unit/test_inv_mem_1_guard.py` — behavioral tests for
  `hydrate_and_filter_vector_hits` (missing authoritative items, stale projection,
  archive denied in default mode without repair candidates)
- `backend/tests/unit/test_memory_search_gateway.py` — extended hydration gateway cases

## Path globs

- `backend/models/memory_search_gateway.py`
- `backend/utils/memory/vector_search_service.py`
- `backend/database/memory_vector_*.py`

## PR rule

Name `INV-MEM-2` in the PR body if you touch the path globs above.

## Related

- [memory-tiers.md](./memory-tiers.md) — INV-MEM-1 default access policy
- [memory-canonical-fail-closed.md](./memory-canonical-fail-closed.md) — INV-MEM-3
  enrolled read routing
