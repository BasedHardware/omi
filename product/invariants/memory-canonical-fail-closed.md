# INV-MEM-3: Universal memory authority fails closed

**Status:** locked
**Statement:** Every authenticated account uses the universal memory authority.
Canonical state, historical suppression, generation, authorization, and global
readiness failures must fail closed. The historical adapter is a read-only input
to that authority, never a recovery route around a failed canonical check.

## MUST NOT

- Return a historical row when its canonical item, override, tombstone,
  generation fence, product grant, or global readiness state cannot be checked.
- Bypass `MemoryService` through a direct legacy reader when canonical or
  provider hydration is unavailable.
- Turn a global intake pause into permission to write historical memory.
- Let a global intake pause block privacy tombstones or account deletion.

## Surfaces

- `utils.memory.memory_service` universal reads, mutations, and historical suppression
- `utils.memory.default_read_rollout` global readiness and product grants
- `utils.memory.product_memory_read_service` and search/tool hydration
- memory REST, chat, MCP, developer, integration, export, and deletion surfaces

## Guard tests

- `backend/tests/unit/test_universal_memory_service.py` — mixed-origin reads,
  suppression, canonical failure, global intake pause, and privacy deletion
- `backend/tests/unit/test_universal_memory_task_authority.py` — static route
  and retired-selector guards
- `backend/tests/unit/test_ws_l_surface_routing.py` — all released surfaces use
  universal authority
- `backend/tests/unit/test_inv_mem_1_guard.py` — lifecycle and access fail-closed guards

## Path globs

- `backend/utils/memory/memory_service.py`
- `backend/utils/memory/default_read_rollout.py`
- `backend/utils/memory/product_memory_read_service.py`
- `backend/routers/memories.py`
- `backend/services/users/data_export.py`
- `backend/services/users/account_deletion.py`

## PR rule

Name `INV-MEM-3` in the PR body if you touch the path globs above.

## Related

- [memory-tiers.md](./memory-tiers.md) — INV-MEM-1 tier vocabulary
- [memory-vector-hydration.md](./memory-vector-hydration.md) — INV-MEM-2 vector
  hydration fail-closed
- [universal-memory-task-authority.md](./universal-memory-task-authority.md) —
  INV-MEM-5 universal product authority
