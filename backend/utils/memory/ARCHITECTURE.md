# Memory architecture map

This package owns the universal memory repository and canonical processing
pipeline. Persistence contracts live in `backend/database/` and
`backend/models/`; HTTP entry points live in `backend/routers/`. The normative
data model is `docs/memory/domain_model.md`, and the convergence record is
`docs/epics/universal_memory_task_convergence.md`.

## One logical authority, two retained formats

Every authenticated account uses `memory_service.py:MemoryService`. New writes
always enter canonical `memory_items`. Existing
`users/{uid}/memories` documents remain readable through
`HistoricalMemoryAdapter`, which is deliberately read-only.

```text
released memory surface
  -> MemoryService
     -> CanonicalMemoryBackend                 authoritative reads and writes
     -> HistoricalMemoryAdapter                bounded compatibility reads only
     -> memory_historical_overrides            durable suppression/materialization fence
  -> one MemoryDB response contract
```

Canonical wins a stable-ID collision. An active override suppresses the
historical copy after materialization; a tombstone suppresses it after delete.
Sorting, visibility, device, locked-memory, and lifecycle policy are applied by
the service rather than selected by physical origin.

No request chooses a memory system from a UID list, user enrollment document,
header, or client claim. `MEMORY_MODE`, `MEMORY_V3_GET_ENABLED`, and the
canonical maintenance/consolidation flags are deployment-wide safety controls.
There is no runtime user inventory.

## Released read surfaces

`backend/routers/memories.py` and the chat, agent, MCP, developer, integration,
tool, and X-connector adapters call `MemoryService` directly. The normal list
path merges canonical and historical rows with stable ordering and duplicate
suppression. The retired cutover projection cannot represent that mixed view,
so `cursor` requests fail explicitly with HTTP 400 instead of selecting a
second authority. Released clients continue to use bounded offset paging.

The authoritative canonical read path is:

```text
MemoryService.read/search/get
  canonical_memory_adapter.py
  product_memory_read_service.py
  canonical_visibility_filter.py
  device_scope_filter.py
  memory_item_to_memorydb
```

Historical rows are adapted to the same released model without inventing
promotion receipts or changing public IDs. Missing historical visibility keeps
the released public default; missing device identity is device-neutral.

## Writes and lazy historical mutation

Explicit, import, conversation, API, plugin, integration, and X-connector
intake all stage canonical Short-term items. Canonical apply state is created
lazily on first write and is fenced by UID, account generation, source
generation, idempotency, and content hash.

Mutating a historical-only item is deterministic and local:

1. read and validate the historical row;
2. write the canonical representation with the same public ID;
3. durably write its active override or tombstone;
4. best-effort remove the historical row and obsolete vector entry.

The override is committed before cleanup so a retry or cleanup outage cannot
resurrect or duplicate content. This path does not call an LLM, create an
embedding, or require a bulk account backfill. Batch mutations prevalidate the
whole request before the first write.

## Canonical processing and Long-term admission

`memory_apply_store.py` is the canonical transaction boundary. It advances the
apply control/head, item, commit, operation journal, graph assertion, and
projection/vector outbox fences together. `canonical_consolidation.py` is the
sole new Short-term -> Long-term admission authority and requires the
server-authored promotion receipt defined by INV-MEM-4.

Scheduled maintenance runs:

```text
backend/modal/memory_maintenance_job.py
  canonical_short_term_maintenance_cron.py
  short_term_promotion.py
    memory_outbox_worker.py
    TTL audit
    canonical_consolidation.py
      pending required submissions + processed Short-term
      one Luna call: normalize if needed, then promote | archive | review | reject
    memory_outbox_worker.py
```

The job inventories accounts from a content-free universal maintenance
registry. First canonical apply-state provisioning idempotently registers the
UID; each job run advances a persisted bounded cursor and wraps at the end.
This is neither a rollout allowlist nor an unbounded users scan. Scheduler owns
cadence; the job is the sole host of
`MEMORY_CANONICAL_MAINTENANCE_ENABLED`.

The scheduled final planner and six-hour X memory
extractor share one optional OpenAI Flex switch and use dedicated gateway lanes.
Manual and post-OAuth X syncs remain Standard. Ordinary `memory_conflict`,
`memory_l2`, and `memories` traffic keeps its Standard timeout and cannot
request Flex. `OMI_BACKGROUND_FLEX_CAPABLE` is present only on the two owning
jobs. The live Firestore control is stage-scoped because dev and prod can share
the customer Firestore project: dev uses
`llm_runtime_controls/background_flex_dev`, and prod uses
`llm_runtime_controls/background_flex_prod`. Each document must contain
exactly:

```json
{"enabled":false,"generation":1}
```

Set `enabled` to `true` to route eligible scheduled workloads through
Flex, and increment `generation` with every control change. Setting it back to
`false` restores their legacy Standard paths without a redeploy. An in-flight
response from an older generation is discarded before durable apply. Flex
resource deferrals release promotion leases for the next scheduled run and
do not consume model-output quality retry budgets; X raw posts remain pending.
Flex-mode memory maintenance scans a bounded registry page (up to 400 UIDs),
skips accounts with no active Short-term row, and skips accounts dreamed in
the last 20 hours unless they already have more than 10 active Short-term
rows (hourly overflow drain). Remaining users run until the 15-minute Flex
reservation no longer fits in the one-hour job budget. A Flex deferral leaves
the durable cursor on the unfinished UID so later accounts are not skipped.
The job does not run a separate required-processing LLM: explicit submissions
enter the consolidation batch with `requires_normalization=true`, and apply
stamps the L2 receipt then the route from that one decision. Promote
`memory_text` is always rebound to the stored L2 content when
`promotion.required` is set, including retries after L2 already committed.
Consolidation
keeps 20 Short-term items per Luna call and splits the planner rules onto a
cached prefix so later batches of the same hour reuse that prefix; one pass
can issue up to 25 such calls (500 items). Both owning
jobs use verified private gateway endpoints, zero SDK retries, and a one-hour
Cloud Run task budget.

## Search, graph, and derived providers

Canonical item state is authoritative. Keyword/vector results are candidates
only and must hydrate against the universal repository before return. Restricted,
archived, superseded, or tombstoned items stay excluded according to the
surface policy even when a provider row lags.

The normal `projection_sync` and `vector_sync` outbox is the retry authority for
Typesense, compatibility, Pinecone, and derived graph delivery. Restricted
items are delete-only. Provider identity is the stable `memproj:` hash of
`(uid, memory_id)`; cleanup also removes the retired bare-ID identity.

`memory_graph_assertions/{memory_id}` is graph authority. Retained historical
graph data is a bounded read overlay only and cannot admit, mutate, or delete a
memory. Public graph mutation routes therefore preserve canonical assertion
semantics for every account.

## Privacy, export, and account lifecycle

Edit, review, visibility, category/tags, baseline, single delete, batch delete,
delete-default, delete-all, source replacement, export, and account deletion
all enter through the universal authority. Canonical tombstones and historical
override tombstones suppress reads immediately; outbox/provider cleanup may
complete asynchronously without changing that authority.

Data export iterates the merged logical set once. Account deletion closes over
historical rows/vectors and canonical items, evidence, operations, reviews,
assertions, outbox/projections, overrides, and task sidecars. Account-generation
fences prevent an old lease or retry from resurrecting a recreated account.

## Operational controls and rollback

The supported controls and rollback floor are documented in
`docs/runbooks/universal-memory-operations.md`.

- `MEMORY_ENABLED=on|off` is the one user-facing product flag. Unset fail-closes
  to off. `on` enables intake and list; it does not by itself enable ST→LT
  maintenance. `MEMORY_MODE` and `MEMORY_V3_GET_ENABLED` are one-deploy aliases
  only (`write|read` → on, `off|shadow` → off) and are not written in overlays.
- `MEMORY_CANONICAL_MAINTENANCE_ENABLED` is job-only and stays a separate ops
  switch. Do not derive it from `MEMORY_ENABLED=on`. Both env overlays pin it
  on with `MEMORY_CANONICAL_MAINTENANCE_FLEX=true`.
- `MEMORY_CANONICAL_CONSOLIDATION_ENABLED` and its batch/candidate settings are
  global cost/incident controls.
- `GET /v3/memories` first page uses `read_page`, which 503s
  `Memory cursor unavailable` when `MEMORY_V3_CURSOR_SECRET` is missing. That is
  the list fence, not `MEMORY_V3_GET_ENABLED` (unused on the route). First page
  falls back to offset `read()` for that 503.

The universal dual-format reader is the rollback floor. A rollback may stop new
canonical intake or L2 maintenance globally, but must keep the universal reader
and historical adapter deployed. Physical legacy deletion is a separate,
explicitly approved operation after production evidence.

## Change rules

- Add public reads or mutations through `MemoryService`, never by selecting a
  physical store in a router.
- Historical storage may only be read or idempotently cleaned by lazy
  materialization/account deletion.
- Add canonical state transitions to `models/memory_apply.py` and execute them
  through `database/memory_apply_store.py`.
- Add Long-term terminal routing only in `canonical_consolidation.py`.
- Task packages must not import memory cohort/system-selection modules;
  recurrence is an optional evidence handoff, not task entitlement.
