# Memory architecture map

This package owns the universal memory repository and canonical processing
pipeline. Persistence contracts live in `backend/database/` and
`backend/models/`; HTTP entry points live in `backend/routers/`. The normative
data model is `backend/docs/memory/domain_model.md`, and the convergence record is
`backend/docs/epics/universal_memory_task_convergence.md`.

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
header, or client claim. `MEMORY_ENABLED` and the
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
projection/vector outbox fences together. `canonical_consolidation.py` now contains
the deterministic disposition primitive used by TTL and explicit required intake,
not an autonomous semantic planner. Required promotion keeps the server-authored
receipt defined by INV-MEM-4 and never considers existing facts as candidates.

Scheduled maintenance was retired on 2026-10-26 (`memory-maintenance-job` and
`canonical_short_term_maintenance_cron.py` are deleted; the job never served
production). The retired call tree, kept here as the contract its orphaned
duties held:

```text
canonical_short_term_maintenance_cron.py (async coordinator; RETIRED)
    bounded expiry + rotating registry inventory
    short_term_promotion.py
      memory_outbox_worker.py: deliver prior commits first
      canonical_required_processing.py: DB claim -> LLM normalize -> DB settle
      TTL audit (compatibility accounts; the retired daily sweep owned ledger lifecycle)
      canonical_consolidation.py: complete receipted required intake only
      memory_outbox_worker.py: deliver newly committed intents
    drain previously committed recurrence inbox receipts
```

The 400-account inventory retains expiry priority and generation-fenced registry
cursor advancement. Accounts with no active Short-term rows and ledger accounts
still drain their outboxes. No semantic cooldown, overflow dreaming, candidate
retrieval, consolidation call, or maintenance-host Dream invocation remains.
Ordinary facts are formed by the existing daily sweep; retrospective corrections
use the shared agent capabilities under Dream's verifier, journal and Undo policy.

Required intake uses the existing gateway-only Flex route, job time ceiling and
retry leases. Model waits borrow only the model executor; each database step is
offloaded independently. A resource deferral releases the processing lease and
stops the page without advancing past the unfinished account. Outbox/cursor
failures remain fatal even when provider capacity is deferred. The scheduled X
ingestion job retains its own optional Flex control and Standard user-sync path.

The required-completion scan is bounded to 100 ordered rows with a separate
capture/id cursor. Ordinary observations and invalid receipts cannot fill every
future window: the cursor advances and wraps. Only processed required submissions
with valid content-bound receipts can promote; current revision, evidence,
generation, source, head and graph-admission fences still apply.

Owner rejection closes the feedback loop through
`rejected_memory_feedback.py`. L1 extraction reads
at most eight newest active or terminally hidden owner rejections from active
sources in the last 30 days. Only non-restricted content is retained,
normalized to 180 characters per item and 1,600 characters total, then cached
in-process for five minutes; every memory mutation invalidates the owner's
entry. Conversation orchestration fetches the set through its injected
Firestore client and passes it into L1, which places the examples at
user-message priority after the conversation cache breakpoint. Consolidation
serializes the set once in its volatile batch JSON because rejected items are
deliberately absent from vector projection and therefore cannot be recovered
reliably as vector neighbors.

`decision_path_telemetry.py` emits the stable
`canonical_memory_decision_path.v1` event for persisted capture, applied or
blocked promotion routes, and daily-sweep candidate-gate decisions. Capture
events carry conversation source, resolved subject attribution, a non-PII
classification of model-authored `about`, disagreement, distinct speaker-ID count,
and `owner_trust`. Promotion events carry the route, stage status, and
structured reason fields. Sweep events carry per-day counters
(`dropped_subjectless`, `dropped_basis_proposed`, `demoted_owner_untrusted`,
`skipped_duplicate_lookup`) with no memory or transcript text.

## Owner attribution at capture and daily sweep

`utils/conversations/owner_attribution.py` is the typed evidence for whether a
source may mint an owner-attributed memory. Capture (`process_conversation.py`)
and the daily sweep share that policy:

- A unique owner speaker cluster is required before `about=user` (or an
  owner alias: the profile name, "the user", "primary user") or
  `subject_scope=primary_user` is admitted. Ambiguous or absent clustering
  demotes the claim (`demoted_owner_untrusted` on the sweep path) rather than
  rewriting it as a third-party fact.
- Owner attribution has no model override. A candidate without trusted unique
  owner-cluster evidence is not rewritten as an owner fact; correct attribution
  at the source before admitting it.
- Every sweep memory must name a subject in `about`. Subject-less, `unknown`,
  and `uncertain` rows are omitted (`dropped_subjectless`). An omitted `about`
  on the structured-output schema defaults to empty so one subjectless row
  cannot fail the day's parse.
- `basis` is `decided` only for a commitment or decision on tape by the owner,
  `proposed` for suggestions or plans without a decision (those are dropped,
  `dropped_basis_proposed`), and `observed` otherwise. Only `decided` may set a
  standing-attribute slot.
- A model mark `duplicate_of` citing a ledger lookup hit skips the candidate
  instead of staging a sibling (`skipped_duplicate_lookup`). Lookup rows
  prefix the canonical memory id so the model can cite it. A non-empty
  marker that is not one of those ids is ignored and the candidate is treated
  as new.
- Staged daily-sweep pages may remain in Firestore from the retired sweep. No
  current runtime reads or writes those pages; export, account deletion, and
  retention continue to handle the stored collections.

Clusters are `(speaker_id_scope, speaker_id)`. A `TranscriptSegment` that only
materialized `speaker_id` from the SPEAKER_00 default is not evidence; a
synthesized `0` that has already been persisted still looks real after reload
(stored provenance would need a schema field). L2 consolidation, the belief
model, and user-facing summary rendering are out of scope for this gate.

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
`backend/docs/runbooks/universal-memory-operations.md`.

- `MEMORY_ENABLED=on|off` is the one user-facing product flag. Unset fail-closes
  to off. `on` enables intake and list; it does not by itself enable ST→LT
  maintenance.
- `MEMORY_CANONICAL_MAINTENANCE_ENABLED` is job-only and stays a separate ops
  switch. Do not derive it from `MEMORY_ENABLED=on`. Both env overlays pin it
  on with `MEMORY_CANONICAL_MAINTENANCE_FLEX=true`.
- `MEMORY_CANONICAL_CONSOLIDATION_ENABLED` and its batch/candidate settings are
  global cost/incident controls.
- `GET /v3/memories` first page uses `read_page`, which raises
  `MemoryBackingStoreUnavailable` (503 `Memory cursor unavailable`) when
  `MEMORY_V3_CURSOR_SECRET` is missing. That is the list fence. First page
  falls back to offset `read()` for that typed failure — not by matching
  detail strings.

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
- Keep deterministic required-intake completion and TTL dispositions in `canonical_consolidation.py`; retrospective semantic edits use shared agent capabilities.
- Task packages must not import memory cohort/system-selection modules;
  recurrence is an optional evidence handoff, not task entitlement.
