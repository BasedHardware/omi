# Canonical Memory Runtime Architecture

> Plain-English map of the canonical capture → terminal route → atomic
> Long-term admission → retrieval flow.
>
> - **Visual companion:** [canonical_memory_architecture.html](./canonical_memory_architecture.html)
> - **Domain vocabulary and schema SSOT:** [docs/memory/domain_model.md](../../../memory/domain_model.md)
> - **Product/storage decisions:** [docs/epics/memory_normative_architecture.md](../../../epics/memory_normative_architecture.md)

Canonical routing remains cohort-gated and fail-closed. This document describes
the canonical lane; non-canonical users remain on the legacy lane until their
explicit cutover.

## The lifecycle in one view

```text
Conversation, explicit user memory, import, API, plugin, integration
                              │
                              ▼
              broad Short-term capture (all new intake)
                              │
                              ▼
       required normalization → TTL audit/expiry settlement
                              │
                              ▼
      one total consolidation decision for each pending item
             ┌────────────────┼───────────────┐
             │                │               │
          promote       archive/review     reject
             │                │               │
             ▼                └──────┬────────┘
 atomic Long-term admission           ▼
 receipt + graph assertion       outside default access
 item + ledger + operation
 outbox, all in one commit
             │
             ├──────────────► outbox-retried projections
             │                 keyword/compatibility + vector
             ▼
 default retrieval = eligible Short-term + Long-term
                  → canonical-lineage dedupe
```

The important ownership rule is simple: broad capture creates Short-term;
consolidation owns the only terminal L2 route; the atomic apply transaction owns
Long-term admission; projections never own memory state.

## 1. Capture: all new intake is Short-term

All newly captured memory enters `users/{uid}/memory_items/{memory_id}` as
Short-term. That includes:

- processed Conversation extraction;
- first-party “remember this” submissions;
- imports;
- generic API and developer writes;
- plugins and integrations.

Explicit submissions may be immediately visible in the first-party memory list
as pending Short-term so the user receives a write receipt. Protected
agent/chat/developer/MCP/search consumers exclude pending raw text until
processing completes.

Conversation capture accepts a candidate only when every quote reference is
grounded in one transcript segment. Extraction and validation finish before
source replacement: an extraction failure preserves all prior canonical state,
while a successful empty reprocess is authoritative and fully retracts the
prior conversation-sourced state.

Historical migration/backfill is not new intake. Its explicit migration policy
may materialize retained historical tiers, but it must not expose a reusable
direct-to-Long-term writer.

| Concern | Behavior | Evidence |
|---------|----------|----------|
| Whitelist | Only UIDs in `CANONICAL_MEMORY_USERS` get canonical memory, task intelligence, and Chat-first | `backend/config/canonical_memory_cohort.py`, `resolve_memory_system` |
| Default | Absent from whitelist → `MemorySystem.LEGACY`, task intelligence off, Chat-first off | `canonical_memory_cohort.py` and `utils/task_intelligence/rollout.py` |
| Kill-switch | Removing a UID from the code whitelist overrides stale Firestore controls and hides canonical task routes | `canonical_memory_cohort.py` and `routers/canonical_task_access.py` |
| Operational controls | `MEMORY_MODE`, `MEMORY_ENABLED_USERS`, and `MEMORY_V3_GET_ENABLED` may govern maintenance readiness only; they never select or suppress a user's request path | `backend/.env.template` |
| Request pin | HTTP/MCP handlers pin cohort once per request to avoid mid-request flips | `backend/utils/memory/memory_system_pin.py:17-40` |
| Routing seam | `MemoryService._resolve_backend` picks `CanonicalMemoryBackend` vs `LegacyMemoryBackend`; an enrolled-but-unready account fails closed rather than falling back | `backend/utils/memory/memory_service.py` |
| Maintenance refusal | Consolidation/promotion return `skipped_reason="not_canonical_cohort"` for legacy users | `canonical_consolidation.py:784-785`, `short_term_promotion.py:361-362` |

Primary seams:

| Concern | Code |
|---|---|
| Public route selection | `backend/utils/memory/memory_service.py` |
| Canonical capture/write adapter | `backend/utils/memory/canonical_memory_adapter.py` |
| Explicit-submission envelope | `backend/utils/memory/required_promotion.py` |
| Canonical item model | `backend/models/product_memory.py` |
| Atomic persistence boundary | `backend/database/memory_apply_store.py` |

## 2. Maintenance: normalize, enforce TTL, route once

The enabled `memory-maintenance-job` runs
`run_canonical_short_term_maintenance` once per canonical cohort user:

1. `memory_outbox_worker.py` drains already-committed work before any
   Short-term row is parsed.
2. `canonical_required_processing.py` normalizes required explicit
   submissions and records their processing receipt.
3. `short_term_promotion.py` audits Short-term TTL lifecycle and settles an
   expired processed item as a canonical reject, atomically emitting projection
   deletes. It never promotes.
4. `canonical_consolidation.py` gives every item in the deterministic,
   server-bounded eligible set one terminal route.
5. `memory_outbox_worker.py` drains events committed by those phases.

There is no separate generic promotion step. A blocked or invalid consolidation
result cannot fall through to another promoter.
Consolidation failures are durable and revision-scoped: before invoking the
LLM, a leased attempt is recorded under `memory_runs`. A retrying source is
isolated from fresh items. Three failed attempts settle it through the
canonical `review` route. If the Archive review route conflicts, the same apply
boundary commits a blocked Short-term review and projection deletes, removing
the quarantined revision from the eligible query. If storage prevents both
terminal commits, later runs retry only those routes without another LLM call.
A durable cursor advances the stable ordered scan past a still-blocked page and
resets after reaching later work, so the oldest query window cannot remain
pinned. Retry and quarantine reports fail the cohort job while later selected
sources continue, preventing poison-row starvation, unbounded model cost, and
silent success.

Required processing queries active pending required rows, and negative user
review moves a row to terminal `processing_rejected`. TTL selects active,
processed, expired Short-term rows in `expires_at, memory_id` order;
consolidation selects active, processed, source-active Short-term rows in
`captured_at, memory_id` order. Eligibility filters precede server-owned query
limits, so unrelated rows cannot starve overflow. Each pass drains every batch
in its selected set; overflow remains immediately eligible on the next
Scheduler run, without a 24-hour watermark delay.

The cron is disabled unless
`MEMORY_CANONICAL_MAINTENANCE_ENABLED=true` and the code-reviewed canonical
cohort is non-empty. Cloud Scheduler owns cadence; the process has no second
interval gate.

## 3. Consolidation: an exact terminal partition

For every non-empty eligible pending set, consolidation:

1. loads active, processed, unexpired Short-term items;
2. gathers and hydrates candidate memories;
3. sends the batch and its evidence to one L2 planning call;
4. validates the complete response before the first mutation;
5. applies each item-addressed route through the atomic apply store.

The response must contain exactly one decision for every pending item and no
unknown or duplicate source IDs. Its terminal routes are:

| Route | Canonical result |
|---|---|
| `promote` | Atomically admit the same `memory_id` to active Long-term |
| `archive` | Settle as an active Archive item outside default access |
| `review` | Settle in Archive and create the review projection |
| `reject` | Settle as hidden Archive |

Incomplete partitions, duplicate routes, unowned evidence, unknown references,
cross-pending supersession, parse failures, or apply failures block the
watermark. They do not partially invent a replacement route.

Captured `subject_entity_id` and subject attribution are authoritative.
Promotion must conserve a known source subject and cannot rewrite a third-party
subject as the user; any contradiction blocks the batch before mutation.

Review rows are revision-scoped projections. Resolution validates the pending
row's source commit, item revision, content hash, and review route inside the
same Firestore transaction that updates the canonical item and redacts the
queue row. Accept/correct returns the item to pending Short-term processing
after clearing its settled route; reject/drop privacy-tombstones it. Stale and
competing commands fail closed, and review reads recheck authoritative item
state so delayed cleanup cannot expose a deleted candidate.

Privacy deletion closes the complete non-tombstoned canonical lineage,
including hidden and superseded aliases. Embedded evidence and semantic item
fields are scrubbed; a standalone evidence document is preserved only when a
surviving item still references it. Delete-all repeats bounded transactions
until a final control-fenced rescan observes no remaining item, or fails rather
than reporting a partial deletion.

Conversation replacement locates its exact source cohort through the
`source_ids array_contains` index and cursor-bounded pages, never an account-wide
item scan. If that source owns the active survivor of a merged lineage, the
same replacement transaction reactivates independently sourced superseded
Long-term rows, rebuilds their version-fenced graph assertions, and emits
projection upserts. A provider-returned empty candidate list is an authoritative
withdrawal; a non-empty batch containing an ungrounded quote fails before this
transaction so validation cannot masquerade as an empty replacement.

Account deletion uses the durable top-level wipe marker as a projection-write
fence before provider purge. Projection workers become delete-only while that
fence is active, and provider purge defers until no projection lease remains.

Primary guard surfaces:

- `backend/tests/unit/test_canonical_consolidation.py`
- `backend/tests/unit/test_canonical_consolidation_apply.py`
- `backend/tests/unit/test_canonical_maintenance_ordering.py`

## 4. Long-term admission: receipt and graph assertion are atomic

`promote` is the only route into Long-term. The consolidation plan must provide
a non-empty structured `PromotionGraphPlan`. Server code binds that plan to:

- the current Short-term `memory_id` and item revision;
- the output content hash;
- the exact evidence IDs;
- the superseded memory IDs;
- the graph-plan hash.

That binding becomes a server-authored `PromotionAdmissionReceipt`. The apply
boundary accepts the transition only for a `synthesis` operation with a current,
valid receipt.

One Firestore transaction then writes:

```text
memory_state/apply_control
memory_state/head
memory_operations/{operation_id}
memory_commits/{commit_id}
memory_items/{memory_id}
memory_graph_assertions/{memory_id}
memory_outbox/{event_id}
```

The promoted item, receipt, graph assertion, ledger head/commit, operation
result, supersession invalidations, and outbox events therefore succeed or
roll back together. An active newly admitted Long-term item cannot exist
without its version-fenced per-memory graph representation.

`memory_graph_assertions/{memory_id}` is graph authority for canonical memory.
The shared knowledge graph merges current assertions with retained legacy graph
data on read; it is a derived view, not a second LLM extraction or admission
authority. That overlay reads stable document-ID-ordered pages of at most 500
assertions plus the bounded legacy inputs, returns at most 500 nodes and 1,000
edges, and reports `truncated=true` whenever an input or merged result exceeds
its cap. `node_count` and `edge_count` report the records included in that
bounded snapshot. Returned edges are referentially closed over the returned
node page; filtering a dangling edge also marks the response truncated. Public
graph delete and rebuild return HTTP 409 for canonical or retained-assertion accounts at
`DELETE /v1/knowledge-graph` and `POST /v1/knowledge-graph/rebuild` because
those assertions, not the mutable shared projection, are authority.

Primary contracts:

| Concern | Code |
|---|---|
| Admission receipt and graph models | `backend/models/memory_promotion.py` |
| Pure transition validation | `backend/models/memory_apply.py` |
| Atomic Firestore transaction | `backend/database/memory_apply_store.py` |
| Read-side assertion merge | `backend/database/knowledge_graph.py` |

## 5. Projections: outbox retry is the authority

The canonical transaction commits deterministic `projection_sync` and
`vector_sync` events alongside each projection-eligible state change. This
normal outbox is the sole delivery authority for keyword/compatibility and
vector projections; capture, consolidation, and apply do not perform a regular
synchronous projection fast path.

`backend/database/memory_outbox_worker.py` owns normal projection convergence:

- leases pending, retryable, and expired-processing events with an ownership
  epoch;
- reloads the canonical item instead of trusting event content;
- checks account generation, item revision, and content hash;
- performs an idempotent keyword/compatibility or vector upsert/delete;
- acknowledges only an exact `True` success from the side-effect adapter;
- retries failures with deterministic bounded backoff, then dead-letters;
- leaves lost/failed acknowledgements replayable.

Restricted items are delete-only across keyword, compatibility, embedding, and
vector providers; their content is never submitted for indexing or embedding,
and only ID-scoped deletes contact providers to purge prior state.
When an expired processing lease is reclaimed, the worker repairs the provider
to current authoritative state before acknowledgement even if the original
event fences are stale. Ordinary stale events may still settle without replay.

Deletes, tombstones, superseded rows, and newer item versions outrank stale
upserts. Privacy/delete paths may attempt an immediate best-effort purge to
reduce exposure, but atomically committed normal projection/vector delete
events remain the retry authority. The authoritative tombstone makes graph
reads fail closed immediately; the durable projection-delete event removes
the per-memory graph assertion before pruning shared citations. Deferring that
derived delete keeps the released 100-item batch contract within Firestore's
transaction limit. Expired processed Short-term items use the same canonical
reject/apply path, preventing stale vectors from accumulating.
Legacy backfill and remediation never invoke projection or legacy KG writers
directly.

## 6. Default reads and search

`MemoryService.read`, `search`, and `search_mcp` route canonical consumers
through authoritative `memory_items` hydration and lifecycle policy.

Default retrieval:

- includes active, processed, eligible Short-term and Long-term;
- excludes Archive unless an explicit Archive operation is authorized;
- excludes expired, blocked, hidden, tombstoned, restricted, stale, or
  cross-user state;
- groups aliases by `canonical_memory_id` lineage;
- prefers the active Long-term canonical survivor for a duplicated lineage;
- retains fresh Short-term items that represent unique evidence.

The same lineage collapse is used for default lists and hybrid search, so a
Short-term alias and its Long-term survivor cannot both appear as separate
logical memories.

Search merges keyword and vector candidate IDs, hydrates authoritative items,
applies default visibility, collapses lineage, and then reranks. Neither
Typesense nor Pinecone content is trusted as the response source.

Primary guard:
`backend/tests/unit/test_ws_m_atom_keyword_index.py`.

## Canonical stores

| Store | Role |
|---|---|
| `users/{uid}/memory_items/{id}` | One tiered product-memory store |
| `users/{uid}/memory_evidence/{id}` | Immutable/source-state evidence |
| `users/{uid}/memory_operations/{id}` | Audited operation journal |
| `users/{uid}/memory_commits/{id}` + `memory_state/*` | Canonical ledger/head |
| `users/{uid}/memory_graph_assertions/{memory_id}` | Atomic per-memory graph authority |
| `users/{uid}/memory_outbox/{id}` | Retryable derived-projection intent |
| `users/{uid}/memory_lineage/*` / `canonical_memory_id` | Alias resolution and dedupe |
| `review_queue` | Derived human-review projection |
| Typesense / Pinecone / shared KG | Derived, rebuildable projections |

Legacy `users/{uid}/memories` remains for non-canonical users and as the
non-destructive rollback source until the separately approved decommission.

## Cohort and failure behavior

- `memory_system.py` requires code-reviewed cohort membership.
- `memory_system_pin.py` pins one cohort decision per request.
- `MemoryService` selects one backend; it does not dual-write defensively.
- Non-canonical maintenance is a no-op.
- Invalid consolidation output blocks before mutation.
- Invalid or stale promotion admission fails closed with no item, assertion, or
  outbox write.
- Projection failure does not roll back canonical memory; its durable event
  remains retryable.

## Quick file index

| Concern | Primary file |
|---|---|
| Cohort selection | `backend/utils/memory/memory_system.py` |
| Public read/write seam | `backend/utils/memory/memory_service.py` |
| Canonical CRUD/list/search | `backend/utils/memory/canonical_memory_adapter.py` |
| Required normalization | `backend/utils/memory/canonical_required_processing.py` |
| Maintenance ordering | `backend/utils/memory/short_term_promotion.py` |
| Total consolidation route | `backend/utils/memory/canonical_consolidation.py` |
| Promotion admission models | `backend/models/memory_promotion.py` |
| Pure atomic transition | `backend/models/memory_apply.py` |
| Firestore apply transaction | `backend/database/memory_apply_store.py` |
| Projection retry worker | `backend/database/memory_outbox_worker.py` |
| Graph assertion reads | `backend/database/knowledge_graph.py` |
| Domain vocabulary | `docs/memory/domain_model.md` |
