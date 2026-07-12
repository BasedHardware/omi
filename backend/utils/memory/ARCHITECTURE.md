# Memory architecture map

This package owns the routing and orchestration seams for Omi's legacy and canonical memory systems. Persistence contracts live in `backend/database/` and `backend/models/`; HTTP entry points live in `backend/routers/`. This is a call-path map, not a data-model specification. See `docs/memory/domain_model.md` for the latter.

## `GET /v3/memories`

The entry point is `backend/routers/memories.py:get_memories`. Its live routing order matters:

1. `canonical_activation.py:canonical_read_enabled` selects the direct canonical lane. The router calls `memory_service.py:MemoryService.read`.
2. Otherwise, any production runtime decision other than `memory_read` selects `_legacy_get_memories` in the router.
3. Only a `memory_read` runtime decision that did not select the direct canonical lane enters `v3_composed_get_service.py:compose_v3_get`.

The runtime dependency is built lazily by `routers/memories.py:get_v3_get_runtime` → `v3_production_runtime.py:build_v3_production_runtime`. Legacy fallback happens in the router; the production composed adapter deliberately cannot fall back to legacy. `v3_request_adapter.py` and `v3_memory_read_service.py` describe planner/test contracts but are not in this live GET path.

### Direct canonical request

```text
backend/routers/memories.py:get_memories
  canonical_activation.py:canonical_read_enabled        choose the pinned, read-ready cohort
    memory_system_pin.py → memory_system.py              pin code + environment cohort membership
    backend/config/memory_rollout.py                     load mode and enabled users
    v3_control_state_adapter.py → default_read_rollout.py read persisted control and global gates
    memory_read_rollout_core.py                          evaluate shared grant/convergence gates
    v3_account_generation_source.py                     read the trusted account generation
    v3_control_reader_contract.py                       make the fail-closed route decision
  memory_service.py:MemoryService.read                   public routing seam
  memory_service.py:CanonicalMemoryBackend.read          canonical backend boundary
  canonical_memory_adapter.py:read_canonical_memories    assemble the product response
  product_memory_read_service.py                         read authoritative memory_items
  canonical_visibility_filter.py                         apply default lifecycle visibility
  device_scope_filter.py                                 apply all/current/specific-device scope
  canonical_memory_adapter.py:memory_item_to_memorydb    restore the released MemoryDB shape
```

The legacy lane is shorter: `routers/memories.py:_legacy_get_memories` → `database/memories.py:get_memories` → `memory_api_response.py:memory_list_response`. `memory_api_contract.py` removes canonical-only fields so legacy responses remain compatible.

### Composed projection request

```text
backend/routers/memories.py:get_memories
  v3_composed_get_service.py:compose_v3_get               stage budgets and fail-closed orchestration
  v3_production_runtime.py:_ProductionV3Adapters
    backend/config/memory_rollout.py                       load server-owned rollout configuration
    v3_control_state_adapter.py:read_v3_control            merge env rollout and persisted control state
      default_read_rollout.py → memory_read_rollout_core.py evaluate global/grant/convergence gates
    v3_account_generation_source.py                       read the trusted account generation
    v3_control_reader_contract.py:decide_v3_control_route enforce grant, convergence, generation, and mode
    v3_production_runtime.py:build_snapshot                attest projection state and bind the request
    v3_cursor.py                                           verify/create an HMAC keyset cursor
    v3_projection_reader_contract.py                      typed projection request/page boundary
    backend/database/memory_compatibility_projection.py   query and validate projection state/items
  v3_archive_visibility_readiness.py                      exclude archive/historical rows by default
  memory_api_response.py → memory_api_contract.py         serialize the released response shape
```

Every page is bound to the subject, account and projection generations, projection commit, filter hash, cursor policy, and read timestamp. A mismatched state, row fence, cursor, partial page, or exhausted budget fails closed; it does not bleed into legacy data.

## Capture, consolidation, and promotion

Canonical writes enter through `MemoryService` (HTTP writes start in `backend/routers/memories.py`). `memory_service.py:create_external_memory` adds required-processing metadata, then `canonical_memory_adapter.py:write_canonical_external_memory` / `write_canonical_extraction_memory` persists evidence and submits an operation to `backend/database/memory_apply_store.py:apply_long_term_patch_firestore`.

`memory_apply_store.py` calls the pure transition in `backend/models/memory_apply.py:apply_long_term_patch_transaction`. One Firestore transaction advances the apply control and state head, writes the commit and authoritative `memory_items`, and journals the operation. Processed, review-eligible transitions also persist deterministic `projection_sync` / `vector_sync` outbox events; an initial pending external capture does not. This apply-store commit chain is the canonical memory ledger. `backend/database/memory_ledger.py` is the older fact ledger used by legacy projections; do not use it as the canonical durability seam.

Scheduled maintenance runs:

```text
backend/modal/memory_maintenance_job.py
  canonical_short_term_maintenance_cron.py
  short_term_promotion.py:run_canonical_short_term_maintenance
    canonical_required_processing.py     process required user/import submissions
    short_term_promotion.py               evaluate and record short-term TTL lifecycle
    canonical_consolidation.py           batch candidates, decide, apply via memory_apply_store
    short_term_promotion.py               move accepted short-term items to long-term
      atom_keyword_index.py               refresh keyword projection
      canonical_vector_sync.py            refresh the normal vector projection
      canonical_kg_promotion.py            extract the knowledge-graph projection
```

Consolidation and promotion mutate authoritative state only through `memory_apply_store.py`. Separately, stale vector hits and tombstone/delete paths create deterministic `vector_repair_purge` records with `backend/database/memory_vector_repair_outbox.py`. `memory_vector_repair_outbox_worker.py` leases, retries, dead-letters, and acknowledges those repairs. Repair/purge records share `memory_outbox` storage with normal apply events but are a different event contract.

## Rollout and legacy sunset

`backend/config/memory_rollout.py` owns the runtime contract:

- `MEMORY_MODE` sets `off`, `shadow`, `write`, or `read`; composed GET requires `read`.
- `MEMORY_ENABLED_USERS` is the environment cohort. `memory_system.py` also requires membership in the code-reviewed `CANONICAL_MEMORY_USERS` cohort for direct canonical routing.
- `MEMORY_V3_GET_ENABLED` enables construction of the composed GET runtime.
- `MEMORY_V3_CURSOR_SECRET`, `MEMORY_V3_CURSOR_TTL_SECONDS`, `MEMORY_V3_CURSOR_POLICY_VERSION`, and `MEMORY_V3_CURSOR_SECRET_VERSION` bind cursor behavior.
- Persisted control state additionally gates rollout stage, default-memory grant, global reads, write convergence, account/projection generations, and projection readiness.
- `MEMORY_CANONICAL_PROMOTION_CRON_ENABLED` and `MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS` gate scheduled maintenance; `MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED` gates user-asserted fast promotion.
- `MEMORY_CANONICAL_CONSOLIDATION_ENABLED`, `MEMORY_CANONICAL_CONSOLIDATION_BATCH_THRESHOLD`, `MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP`, `MEMORY_CANONICAL_CONSOLIDATION_MAX_BATCHES_PER_PASS`, and `MEMORY_CANONICAL_CONSOLIDATION_CANDIDATES_PER_ITEM` tune consolidation.
- Vector repair persistence is a persisted rollout capability (`vector_repair_outbox_enabled` in `default_read_rollout.py`), not an environment switch.

Legacy has no date-based removal. `docs/memory/domain_model.md` requires all users to be migrated and verified plus explicit owner sign-off before legacy data is deleted. Until that gate, legacy records remain the durable rollback source; changing routing is reversible, deleting the stores is not.

## Where changes belong

- Add a public read/write/search surface through `MemoryService`; use `surface_routing.py` to pin one cohort decision per request. Do not call both stores defensively.
- Add a canonical list filter in `canonical_visibility_filter.py` for lifecycle semantics or `device_scope_filter.py` for capture-device semantics, then invoke it from `canonical_memory_adapter.py`.
- Add a composed filter end-to-end: request fields in `v3_composed_get_service.py`, cursor-bound `_filter_hash` in `v3_production_runtime.py`, typed fields in `v3_projection_reader_contract.py`, and the query in `database/memory_compatibility_projection.py`.
- Add a read mode in the runtime/control decision and bind it into `V3ComposedExecutionContext` plus `v3_cursor.py`; a mode must not reuse another mode's cursor.
- Add a projection by implementing the `ProjectionReader` (`V3ProjectionReadRequest` → `V3ProjectionPage`) contract and binding it in `v3_production_runtime.py`. Keep storage validation in `backend/database/`.
- Add canonical state transitions to `backend/models/memory_apply.py` and execute them with `memory_apply_store.py`; do not write authoritative items, commits, and outbox records independently.
