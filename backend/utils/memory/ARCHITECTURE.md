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

## Capture, terminal routing, and Long-term admission

Canonical writes enter through `MemoryService` (HTTP writes start in
`backend/routers/memories.py`). Every new conversation, explicit-user, import,
API, plugin, and integration intake is staged as Short-term.
`memory_service.py:create_external_memory` adds required-processing metadata,
then `canonical_memory_adapter.py:write_canonical_external_memory` /
`write_canonical_extraction_memory` persists evidence and submits an operation
to `backend/database/memory_apply_store.py:apply_long_term_patch_firestore`.
Conversation capture accepts a candidate only when every quote reference is
grounded in one transcript segment. Extraction completes before source
replacement: an extraction failure preserves prior canonical state, while a
successful empty reprocess fully retracts the prior conversation-sourced state.

`memory_apply_store.py` calls the pure transition in
`backend/models/memory_apply.py:apply_long_term_patch_transaction`. One
Firestore transaction advances the apply control and state head, writes the
commit and authoritative `memory_items`, and journals the operation. A
Short-term → Long-term transition additionally validates the server-authored
promotion admission receipt and writes
`memory_graph_assertions/{memory_id}` in that same transaction. Processed,
projection-eligible transitions also persist deterministic `projection_sync` /
`vector_sync` outbox events. This apply-store commit chain is the canonical
memory ledger.
`backend/database/memory_ledger.py` is the older fact ledger used by legacy
projections; do not use it as the canonical durability seam.

Scheduled maintenance runs:

```text
backend/modal/memory_maintenance_job.py
  canonical_short_term_maintenance_cron.py
  short_term_promotion.py:run_canonical_short_term_maintenance
    memory_outbox_worker.py              drain already-committed work before row parsing
    canonical_required_processing.py     process required user/import submissions
    short_term_promotion.py               audit TTL and reject expired indexed items
    canonical_consolidation.py            give every pending item one terminal route
      promote                             atomically admit Long-term + graph assertion
      archive / review / reject           settle outside default access
      memory_apply_store.py               commit item, ledger, operation, assertion, outbox
    memory_outbox_worker.py              drain events committed by this pass
```

`canonical_consolidation.py` is the sole L2 route owner. Its model response must
be an exact item-addressed partition of the pending batch into `promote`,
`archive`, `review`, or `reject` before the first mutation. There is no generic
promotion pass and no user-asserted/fast-track bypass. All routes mutate
authoritative state only through `memory_apply_store.py`. Captured
`subject_entity_id` and subject attribution are authoritative: promotion cannot
rewrite a known source subject or turn a third-party subject into the user.
Invalid model output, recurrence handoff failures, and apply conflicts record a
revision-scoped, leased attempt in `memory_runs` before the LLM call. Retried
sources are isolated from fresh items, and after three failed attempts the
canonical apply boundary settles the source as `review`. If the Archive review
route conflicts, that same boundary commits a blocked Short-term review plus
projection deletes, removing the quarantined revision from the eligible query;
if storage prevents both commits, later runs retry only those terminal routes
without another LLM call. A durable ordered scan cursor advances past any
still-blocked query page and resets after reaching later work, so even
store-level terminal failures cannot pin the oldest query window forever.
Either condition is reported as a cohort error, so the maintenance job cannot
claim success while work is blocked, and later selected items continue routing.

The shared knowledge-graph read overlays current version-fenced assertions on
retained legacy records with bounded Firestore scans (2,000 assertions/nodes
and 5,000 edges). Its edge page is referentially closed over the returned node
page, and any edge removed to preserve that closure sets `truncated=true`.
Because canonical assertions are graph authority, public delete and rebuild
routes (`DELETE /v1/knowledge-graph` and
`POST /v1/knowledge-graph/rebuild`) return HTTP 409 for canonical or
retained-assertion accounts; internal memory tombstones still remove their
assertion and derived graph state.

Automatic intake is cost-bounded by deterministic datastore query and per-LLM
batch caps. Every item selected for a pass receives a terminal route; overflow
remains immediately eligible on the next Scheduler run, so low-volume users,
explicit corrections, and bounded-query remainders cannot be stranded behind
a daily watermark.

The normal `projection_sync` and `vector_sync` events committed with canonical
state are the retry authority for keyword/compatibility and vector projections.
`backend/database/memory_outbox_worker.py` leases pending, retryable, and
expired-processing events; reloads the authoritative item; checks account,
revision, and content fences; applies an idempotent side effect; and
acknowledges only success. Failures use bounded backoff and then dead-letter.
When an expired processing lease is reclaimed, the worker repairs the provider
to current authoritative state before acknowledging, even when the original
event fences are stale. Restricted items are delete-only: their content never
reaches keyword, compatibility, embedding, or vector providers; only
UID-and-memory-fenced deletes contact those providers to purge prior state.
Typesense and Pinecone writes use a stable `memproj:` hash of
`(uid, memory_id)`. Before upsert or repair, the provider writer deletes every
row matching that UID and memory ID, including the retired bare-ID identity;
cleanup failure prevents acknowledgement. Rebuild and account deletion use
UID-only provider purges so orphaned rows do not depend on Firestore
enumeration.
This normal outbox is the sole delivery authority for keyword/compatibility and
vector projections; route/apply paths do not perform a regular synchronous
projection fast path. Privacy tombstones enqueue the same normal delete events
atomically with the item/evidence tombstone; immediate provider deletion is
only an exposure-reduction acceleration. The authoritative tombstone fences
graph reads immediately; its durable projection-delete event then removes the
derived per-memory graph assertion before pruning shared KG citations. This
keeps the released 100-item privacy request inside Firestore's transaction
limit without weakening read-time deletion. TTL expiry settles processed
Short-term items through the canonical reject/apply route so their stale
projections cannot accumulate.

Canonical review rows are revision-scoped derived projections, never a second
mutation authority. A resolution transaction reads the pending review and
validates its source commit, item revision, content hash, and `route=review`
against the authoritative item before writing both outcomes atomically.
`accept` and `correct` clear the settled route and return the item to pending
Short-term processing; `reject` and `drop` atomically redact the review while
privacy-tombstoning the item. A stale or competing command therefore cannot
change either side. Review reads also recheck the authoritative item and return
only a redacted tombstone when cleanup is delayed. Durable review cleanup uses
bounded indexed `fact_id` and `conflict_with` queries, including historical
rows that predate denormalized reference metadata.

Privacy deletion closes every non-tombstoned member of the requested canonical
lineage, including hidden and superseded aliases. Tombstones remove semantic
item content and embedded evidence payloads while retaining only the IDs,
revisions, generations, and timestamps needed for lineage and delete delivery.
A standalone evidence document remains active only while a non-deleted memory
still references it. Delete-all processes bounded transactions and then repeats
a control-fenced scan until it observes a stable empty set; sustained concurrent
writes fail the request instead of returning a partial success.

Conversation source replacement uses the denormalized `source_ids` projection
through a cursor-bounded indexed query. Withdrawing a source-owned canonical
survivor reactivates independently sourced superseded Long-term rows in that
same transaction, including a rebuilt graph assertion and projection upserts.
An emitted-but-invalid extraction batch fails before replacement; only a
genuinely empty provider result is allowed to retract the prior source cohort.

Account deletion installs its durable top-level wipe marker before provider
purge. Projection workers treat that marker as a delete-only fence, and the
purge refuses to erase its journal while any projection lease is active.

For enrolled `/v3` reads, `projection_sync` also updates the matching
`v3_compatibility_projection_items` row. The enrollment-created projection
state is a stable account-generation fence shared by every row; item deliveries
reuse that fence so one edit cannot invalidate unrelated rows. Each row
mutation transactionally reads the state fence and rejects a concurrent account
generation change. Upserts fail closed when the state is missing or malformed.
Deletes remove the compatibility row before retryable external cleanup so a
provider outage cannot keep retired or restricted content visible, while a
stale delete cannot remove a newly re-created account's row.

The authoritative per-memory graph is
`memory_graph_assertions/{memory_id}`. Shared KG nodes/edges are a read-side
merge/projection of current assertions and legacy graph data, never an
independent Long-term admission step.

The reviewed legacy-backfill remediation executor follows the same ledger and
normal-outbox path: it can only archive deterministic legacy artifacts and
retains evidence. Backfill never invokes keyword, vector, or legacy KG writers
directly; historical graph repair must use an explicit assertion migration or
normal promotion admission.

## Rollout and legacy sunset

`backend/config/memory_rollout.py` owns the runtime contract:

- `CANONICAL_MEMORY_USERS` in `config/canonical_memory_cohort.py` is the one product entitlement: it selects canonical memory, task intelligence, and Chat-first together.
- `MEMORY_MODE`, `MEMORY_ENABLED_USERS`, and `MEMORY_V3_GET_ENABLED` remain maintenance/readiness metadata only. Request routing must never use them to select or suppress a user.
- An enrolled account whose canonical projection is unavailable fails closed; it never falls back to legacy memory.
- `MEMORY_V3_CURSOR_SECRET`, `MEMORY_V3_CURSOR_TTL_SECONDS`, `MEMORY_V3_CURSOR_POLICY_VERSION`, and `MEMORY_V3_CURSOR_SECRET_VERSION` bind cursor behavior.
- Persisted control state additionally gates rollout stage, default-memory grant, global reads, write convergence, account/projection generations, and projection readiness.
- `MEMORY_CANONICAL_MAINTENANCE_ENABLED` gates scheduled maintenance; Cloud
  Scheduler owns cadence.
- `MEMORY_CANONICAL_CONSOLIDATION_ENABLED`, `MEMORY_CANONICAL_CONSOLIDATION_BATCH_THRESHOLD`, `MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP`, and `MEMORY_CANONICAL_CONSOLIDATION_CANDIDATES_PER_ITEM` tune consolidation. The batch cap bounds each LLM call, and one maintenance pass drains every batch in its deterministic datastore-bounded selection.
- Required processing queries only active pending required rows; a negative user review moves the row to terminal `processing_rejected`. TTL queries only active, processed, expired Short-term rows ordered by `expires_at, memory_id`, while consolidation queries active, processed, source-active Short-term rows ordered by `captured_at, memory_id`. Every query applies its server-owned limit after these eligibility filters, so unrelated rows cannot starve work beyond the cap.
- Vector repair persistence is a persisted rollout capability (`vector_repair_outbox_enabled` in `default_read_rollout.py`), not an environment switch.

Legacy has no date-based removal. `docs/memory/domain_model.md` requires all users to be migrated and verified plus explicit owner sign-off before legacy data is deleted. Until that gate, legacy records remain the durable rollback source; changing routing is reversible, deleting the stores is not.

## Where changes belong

- Add a public read/write/search surface through `MemoryService`; use `surface_routing.py` to pin one cohort decision per request. Do not call both stores defensively.
- Add a canonical list filter in `canonical_visibility_filter.py` for lifecycle semantics or `device_scope_filter.py` for capture-device semantics, then invoke it from `canonical_memory_adapter.py`.
- Add a composed filter end-to-end: request fields in `v3_composed_get_service.py`, cursor-bound `_filter_hash` in `v3_production_runtime.py`, typed fields in `v3_projection_reader_contract.py`, and the query in `database/memory_compatibility_projection.py`.
- Add a read mode in the runtime/control decision and bind it into `V3ComposedExecutionContext` plus `v3_cursor.py`; a mode must not reuse another mode's cursor.
- Add a projection by implementing the `ProjectionReader` (`V3ProjectionReadRequest` → `V3ProjectionPage`) contract and binding it in `v3_production_runtime.py`. Keep storage validation in `backend/database/`.
- Add canonical state transitions to `backend/models/memory_apply.py` and execute them with `memory_apply_store.py`; do not write authoritative items, commits, and outbox records independently.
- Add or change a Short-term terminal route in
  `canonical_consolidation.py`; do not add a second promotion loop or
  call-site bypass. Every new Long-term admission must carry the current
  receipt and graph plan through the atomic apply boundary.
