# V17 Memory Product Integration Epic

**Created:** 2026-06-18T08:05:17Z  
**Owner:** David / Omi memory system  
**Status:** Draft after Wave 3 committee review + product terminology update  
**Repos:**
- Product: `/root/workspace/omi-memory-ingestion-pipeline`
- Benchmark: `/root/workspace/omi-ingestion-benchmark`

## Goal

Integrate the new V17 two-layer memory system into Omi product surfaces without losing user data, while preserving Base-Omi-like high-recall memory capture in L1 and progressively backfilling L2 durable memories under strict safety, review, and no-data-loss gates.

## Non-negotiables

1. **No silent data loss.** Every legacy memory, source row, and raw/source artifact must be either preserved, content-addressed, linked through lineage, or recorded with an explicit loss/skip/tombstone reason, user/account scope, timestamp, job ID, and remediation state. Known ephemeral/drop-prone paths (for example private-cloud raw queue drops or expiring sync temp blobs) must be reported as observable loss and excluded from preservation claims unless independently copied before expiry/drop.
2. **Keep raw/source artifacts by default.** Preserve raw artifacts for provenance, reprocessing, backfill, user trust, and rollback unless existing product deletion/account-purge conventions remove them.
3. **Use product vocabulary: Short-term, Long-term, Archive.** Do not expose “L1/L2” or “Durable” as primary user terms. “Context-only” should not be a major user-visible state; preserve useful non-long-term context as Short-term or Archive.
4. **Short-term memory is default-access memory.** Fresh source-backed memory is available to Omi/agent/default third-party access while it is short-term; it only becomes explicit-query Archive after L2/lifecycle processing.
5. **Long-term memory is stable synthesis.** Long-term uses existing-memory lookup, bounded replayable search, idempotent patches, review/reject routes, and append-only ledger semantics.
6. **Archive is explicit-query historical context.** Archive is preserved/searchable but not included in default Omi/chat/third-party memory access unless explicitly queried or opted in.
7. **Do not silently promote old memories.** Old Omi memories are migrated only for enabled/whitelisted accounts, enter Short-term/Archive candidates first, and become Long-term only through progressive backfill or explicit user/agent action.
8. **Roll out gradually without breaking old memory.** Old memory logic stays intact by default; V17 starts behind a user allowlist and simple mode config (`shadow`, `write`, `read`).
9. **Keep UI/config simple.** Avoid many user-facing states, many toggles, and heavy manual review. Users can manage memory by chatting with Omi; agent mode should have memory-management tools.
10. **Follow existing deletion conventions.** Extend existing memory/conversation/vector/account-purge flows to cover V17 tiers rather than inventing a separate deletion philosophy.
11. **Benchmark parity stays honest.** Use fair utility metrics and Base Omi historical/projection anchors; do not optimize by hiding useful records in Archive/reject/review.

---

# Product decision update — terminology, rollout, and defaults

This section supersedes earlier wording that framed product states as “Archive / Durable / Context only.” If later historical Wave 1/2/3 notes still say `L1`, `L2`, `Durable`, or user-visible `Context only`, read them as implementation-history context, not final product guidance. The final normative source of truth is `docs/epics/v17_memory_normative_architecture.md`; implementation-ticket amendments live in `docs/epics/v17_memory_implementation_tickets.md`.

Final policy decisions:

- Default reads for Omi/chat/agent/MCP/developer/third-party are **Short-term + Long-term**.
- **Archive** requires explicit archive query and opt-in/policy where applicable.
- Use the existing memory vector namespace `ns2` plus strict metadata filters first; a separate Archive namespace is only a fallback if metadata filtering proves unsafe or operationally confusing.

## Updated user-facing memory tiers

| Product term | Internal role | Default access |
|---|---|---|
| **Short-term memory** | Fresh source-backed memory before or during L2 processing. | Included in Omi/agent/default third-party memory access, subject to sensitivity/privacy policy. |
| **Long-term memory** | Clean, consolidated, stable memory after L2 processing. | Included in Omi/agent/default third-party memory access. |
| **Archive** | Older processed source-backed context preserved for history/search. | Explicit query/opt-in only; not included by default. |

Lifecycle:

```text
raw/source artifact → short-term memory → L2 processing → long-term memory or archive
```

## Context-only simplification

Do not make “Context only” a normal user-visible state unless implementation absolutely needs an internal route.

- Fresh useful context belongs in **Short-term**.
- Older useful-but-not-stable context belongs in **Archive**.
- Stable consolidated memory belongs in **Long-term**.
- Unsafe/useless items are rejected/hidden internally.

## Default access policy

| Consumer | Long-term | Short-term | Archive |
|---|---:|---:|---:|
| Omi chat | Yes | Yes | Explicit search only |
| Omi agent mode | Yes | Yes | Tool/explicit search only |
| Third-party integrations | Yes | Yes | Opt-in only |
| Admin/debug/eval | Configurable | Configurable | Configurable |

## Rollout/config simplification

Prefer a small configuration surface:

- `V17_MEMORY_ENABLED_USERS` or equivalent allowlist.
- `V17_MODE=shadow|write|read`.
- `V17_BACKFILL_ENABLED`.
- `V17_BACKFILL_DAILY_LIMIT`.
- `V17_ARCHIVE_OPT_IN_ENABLED`.

Avoid many independent product rollout toggles unless implementation requires hidden internal safety switches.

## Vector policy update

Prefer KISS: start with the existing memory vector namespace plus strict metadata filters instead of creating a separate Archive namespace by default.

Required metadata:

- `memory_tier=short_term|long_term|archive`
- `uid`
- `visibility`
- sensitivity/risk flags
- source-deleted/tombstone state

Default memory queries include Long-term + Short-term. Archive queries must explicitly filter for Archive.

A separate Archive namespace remains a fallback only if metadata filtering proves unsafe, leaky, or operationally confusing.

---

# Wave 1 — Seams Inventory

Wave 1 used three independent subagents:

1. Backend/product memory integration seams.
2. Client/product surfaces and UX seams.
3. Migration/backfill/data-safety/benchmark seams.

This section records the merged seam map. Wave 2 will turn this into a staged integration plan. Wave 3 will critique that plan.

## 1. Backend/product seams

### 1.1 Existing API entrypoints that must remain compatible

Primary mobile/app API: `backend/routers/memories.py`
- `POST /v3/memories`
- `POST /v3/memories/batch`
- `GET /v3/memories`
- `DELETE /v3/memories/{id}`
- `DELETE /v3/memories`
- `PATCH /v3/memories/{id}`
- `PATCH /v3/memories/{id}/visibility`
- `POST/PATCH review/read-style endpoints where present`

Developer API: `backend/routers/developer.py`
- `GET/POST/PATCH/DELETE /v1/dev/user/memories*`
- Current vector side effects differ from `/v3`; this must be reconciled before V17 read/write semantics become authoritative.

MCP API: `backend/routers/mcp.py`
- `POST /v1/mcp/memories`
- `GET /v1/mcp/memories`
- `GET /v1/mcp/memories/search`
- edit/delete routes
- External agents depend on this; L1/L2/review/private policy must be explicit.

Tools/router API: `backend/routers/tools.py`
- `GET /v1/tools/memories`
- `POST /v1/tools/memories/search`
- Used by product agent/chat tools; output format compatibility matters.

### 1.2 Persistence and source-of-truth seams

Legacy/current projection: `backend/database/memories.py`
- Collection: `users/{uid}/memories`
- Already appends to `database/memory_ledger.py` for creates/refines/retractions/evidence mutations.
- Handles encryption/decryption for `content` and `evidence`.
- Handles source deletion through `ripple_source_deletion(...)`.

Append-only durable ledger: `backend/database/memory_ledger.py`
- Collections:
  - `users/{uid}/memory_state/head`
  - `users/{uid}/memory_commits/{commit_id}`
- Existing primitives: `add_fact`, `add_evidence`, `supersede_fact`, `retract_fact`, `tombstone_evidence`, `fold_commits`, `HeadConflict`.
- Likely canonical L2 write target, with legacy projections rebuilt from ledger state.

Short-term/working memory store: `backend/database/short_term_memories.py`
- Collection: `users/{uid}/short_term`
- Already has `pending_review`, `consolidated`, tombstone-ish concepts.
- Useful precedent, but V17 L1 archive has a different contract and needs explicit storage/read semantics.

Review queue: `backend/database/review_queue.py`
- Collection: `users/{uid}/memory_review_queue`
- Corrections: `users/{uid}/memory_corrections`
- Existing review API exists but is not yet rich enough for V17 L1/L2/review UX.

### 1.3 V17 contracts and product logic already present

Contracts: `backend/models/v17_memory_contracts.py`
- `L1MemoryArchiveItem`
- `WorkingMemoryObservation`
- `DurableMemoryPatch`
- `L2SearchPlan`, `L2SearchResult`, `L2MemoryRoute`
- Lifecycle states: `working`, `active`, `context_only`, `review`, `superseded`, `rejected`, `hidden`

L1 product extractor: `backend/utils/llm/working_memory.py`
- `extract_l1_memory_archive_items_from_text(...)`
- Broad, source-aware, archive-oriented extraction.

L2 product synthesizer: `backend/utils/llm/durable_memory_patches.py`
- `synthesize_durable_memory_patches(...)`
- Uses product prompt/rubric and deterministic patch IDs/idempotency keys.

Patch adapter: `backend/utils/memory/v17_patch_adapter.py`
- Maps V17 patches to ledger-like mutations.

Read API: `backend/utils/memory/v17_read_api.py`
- `query_l1_archive(...)`
- `query_durable_memory(...)`
- `query_working_memory(...)`
- `query_memory_context(...)`
- Important labels: `l1_archive`, `agent_use = archived_evidence_not_stable_profile`.

### 1.4 Automatic memory creation seams

Conversation processing: `backend/utils/conversations/process_conversation.py`
- Current `_extract_memories_inner(...)` deletes/reprocesses conversation-tied memories, extracts using `utils.llm.memories`, dedups/conflict-resolves, writes `MemoryDB`, upserts vectors, triggers KG extraction.
- V17 must fit into this post-processing pipeline without breaking usage tracking, executor/threadpool behavior, vector writes, KG, or conversation reprocess behavior.

LLM legacy extraction: `backend/utils/llm/memories.py`
- Existing extraction/conflict/category functions still power product memory writes.
- Need transition strategy: shadow/dual-write first, not sudden replacement.

Listen/pusher/sync:
- `backend/routers/transcribe.py`
- `backend/routers/pusher.py`
- `backend/routers/sync.py`
- These create/process conversations and raw audio. They are high-risk for raw-data lineage and source deletion semantics.

### 1.5 Retrieval/search/chat seams

Prompt memory context: `backend/utils/llms/memory.py`
- `get_prompt_memories(uid)` currently feeds memories into prompts.

Agent/chat retrieval:
- `backend/utils/retrieval/tools/memory_tools.py`
- `backend/utils/retrieval/tool_services/memories.py`
- `backend/utils/retrieval/agentic.py`
- `backend/utils/retrieval/graph.py`
- `backend/routers/chat.py`

Open seam: normal chat should default to L2 active durable facts; L1 archive should be available for source-backed/contextual search with explicit labels and not used as stable profile truth.

### 1.6 Vector/index projection seams

Vector DB: `backend/database/vector_db.py`
- Current memory namespace: `ns2`
- Functions: upsert/delete/search memory vectors; projection repair/reconciliation.

Need decisions:
- Separate namespaces for L1 archive vs L2 durable facts?
- Metadata fields for lifecycle, layer, source commit, sensitive/review state?
- Projection repair for V17 ledger + L1 archive.

### 1.7 Raw data and deletion seams

Conversation/source deletion:
- `backend/routers/conversations.py:delete_conversation(...)`
- `backend/database/memories.py:ripple_source_deletion(...)`

Sync raw files:
- `backend/routers/sync.py`
- Raw paths/staged blobs can be ephemeral; L1/L2 evidence refs must not depend only on disappearing blobs.

Private-cloud pusher queue:
- `backend/routers/pusher.py`
- Queue can drop oldest raw chunks for health. This needs explicit telemetry and no-data-loss treatment.

Account deletion:
- `backend/routers/users.py:_purge_derived_user_data(...)`
- V17 collections/namespaces must be included.

### 1.8 Migration/backfill seams already present

Legacy ledger dry-run migration:
- `backend/migrations/007_genesis_ledger_backfill.py`
- `backend/utils/memory_ingestion/rollout.py`

Vector backfill:
- `backend/migrations/005_backfill_memory_vectors.py`
- Potential import bug noted by subagent: imports `LEGACY_TO_NEW_CATEGORY` from `models.memories`, but constant appears in `utils.llm.memories.py`.

Import precedent:
- `backend/routers/imports.py`
- Limitless import has job/status structure but uses temp files and has source-delete caveats.

---

## 2. Client/product surface seams

### 2.1 Mobile app

Core files:
- `app/lib/backend/schema/memory.dart`
- `app/lib/backend/http/api/memories.dart`
- `app/lib/providers/memories_provider.dart`
- `app/lib/pages/memories/page.dart`
- `app/lib/pages/memories/widgets/memory_item.dart`
- `app/lib/pages/memories/widgets/memory_dialog.dart`
- `app/lib/pages/memories/widgets/memory_edit_sheet.dart`
- `app/lib/pages/memories/widgets/memory_management_sheet.dart`
- `app/lib/pages/memories/widgets/memory_graph_page.dart`
- `app/lib/providers/message_provider.dart`
- `app/lib/pages/home/page.dart`

Important seams:
- Mobile model has `reviewed` and `userReview`, but UI does not meaningfully surface them.
- Mobile has no L1/L2 distinction.
- Search/filter is local over loaded memories; default load limit is low relative to migration/backfill scale.
- Source provenance is mostly just conversation link through `conversationId`.
- Delete all / delete memory copy does not distinguish memory projection from raw conversations/audio/source data.
- Public/private controls are partially hidden/commented in memory card UI.

### 2.2 macOS desktop

Core files:
- `desktop/macos/Desktop/Sources/MainWindow/SidebarView.swift`
- `desktop/macos/Desktop/Sources/MainWindow/DesktopHomeView.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/MemoryModels.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/MemoryStorage.swift`
- `desktop/macos/Desktop/Sources/APIClient.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoriesPage.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoryGraph/MemoryGraphPage.swift`
- `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift`
- `desktop/macos/Desktop/Sources/Chat/ChatPrompts.swift`
- `desktop/macos/Desktop/Sources/OnboardingPagedIntroCoordinator.swift`
- `desktop/macos/Desktop/Sources/OnboardingMemoryLogImportService.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/AppsPage.swift`
- `desktop/macos/Desktop/Sources/MemoryExportService.swift`
- `desktop/macos/Desktop/Sources/MemoryExportDestinationSheet.swift`
- `desktop/macos/Desktop/Sources/MemoryExportExecutor.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/SettingsPage.swift`

Important seams:
- Desktop has the richest provenance-ready model fields: confidence, reasoning, source app/window/device, context/activity, source conversation.
- Desktop has silent full sync/reconcile keys; migration/backfill needs visible status and versioned cache invalidation.
- Desktop chat loads local memories and prompts model with `<memories>`; this is a critical L1/L2 read-policy seam.
- MCP/export surfaces can expose memories to external agents; must decide include L1/L2/private/reviewed/source policy.
- Onboarding/import paths can import many memories and need idempotency/progress/review.

### 2.3 Windows desktop

Core files:
- `desktop/windows/src/renderer/src/pages/Memories.tsx`
- `desktop/windows/src/renderer/src/hooks/useMemories.ts`
- `desktop/windows/src/renderer/src/hooks/useMemoryGraph.ts`
- `desktop/windows/src/renderer/src/pages/Settings.tsx`

Important seams:
- Fetch cap is `limit=500`.
- Bulk delete / manage mode exists.
- Graph code already filters stale KG nodes against live memory IDs.
- No rich review/provenance/visibility affordances.

### 2.4 Web/frontend and admin

Public/shared frontend:
- `web/frontend/src/app/memories/page.tsx`
- `web/frontend/src/app/memories/[id]/page.tsx`
- `web/frontend/next.config.mjs`
- `web/frontend/src/components/memories/*`

Admin:
- `web/admin/app/(protected)/dashboard/apps/page.tsx`
- `web/admin/components/dashboard/app-detail-view.tsx`
- `web/admin/app/api/omi/apps/[app_id]/update/route.ts`
- `web/admin/app/(protected)/dashboard/summary-apps/page.tsx`
- `web/admin/components/dashboard/edit-summary-app-drawer.tsx`
- `web/admin/app/api/omi/summary-apps/route.ts`
- `web/admin/app/(protected)/dashboard/chat-lab/page.tsx`
- `web/admin/app/api/omi/chat-lab/questions/route.ts`
- metrics routes using `Memory Created`

Important seams:
- Web rewrites alias memories/conversations; naming must be careful.
- Admin app/summary-app memory prompts affect memory behavior but lack L1/L2/sensitive/review policy controls.
- Chat Lab is a good admin test surface for L1/L2 answer policy.
- Backfill must not inflate activation metrics that count `Memory Created`.

---

## 3. Benchmark and migration safety seams

### 3.1 Canonical benchmark docs/artifacts

Benchmark docs:
- `/root/workspace/omi-ingestion-benchmark/docs/v17_memory_system_architecture.md`
- `/root/workspace/omi-ingestion-benchmark/docs/v17_implementation_tickets.md`
- `/root/workspace/omi-ingestion-benchmark/docs/v17_llm_two_layer_memory_epic.md`
- `/root/workspace/omi-ingestion-benchmark/docs/base_omi_memory_behavior.md`

Benchmark scripts:
- `scripts/v17_4_e2e_pipeline.py`
- `scripts/v17_product_l1_runner.py`
- `scripts/v17_l2_packet_builder.py`
- `scripts/v17_l2_custom_search.py`
- `scripts/v17_l2_patch_runner.py`
- `scripts/v17_final_l2_bridge_export.py`
- `scripts/v10_judge.py`

Latest important report:
- `reports/v17/v17_9_product_l2_rubric_schema_guarded/`

Fair comparison report:
- `reports/v17/base_vs_v17_9_fair_utility/fair_utility_scorecard.md`
- `reports/v17/base_vs_v17_9_fair_utility/base_vs_v17_9_fair_utility.png`

### 3.2 Current benchmark signal

V17.9 product L2 is cleaner than Base Omi projection:
- Avg utility/card: `1.404` vs `0.386`
- Positive rate: `87.2%` vs `66.7%`
- Harmful/noisy per 100 contexts: `16.7` vs `45.2`
- Fabricated rate: `0%` vs `22.8%`

But Base Omi projection is still slightly higher useful-grounded-safe per 100 contexts:
- Base Omi projection: `76.2`
- V17.9 product L2: `73.8`

Implication: keep L1 broad/old-Omi-like and use L2 for precision, not yield collapse.

### 3.3 Needed migration inventories

Old Omi import inventory:
- total legacy memories
- skipped/deleted
- empty/missing content
- duplicate IDs/content hashes
- encryption/decryption failures
- category/review/manual distribution
- source/conversation linkage
- sensitive/secret scan counts
- per-memory outcome: imported_to_l1, skipped_deleted, failed_validation, quarantined_sensitive, needs_manual_review

L1 backfill inventory:
- original memory ID
- deterministic archive ID
- source type/ref
- archive class
- risk flags
- normal search allowed
- import batch/job ID
- idempotency key
- status and skip reason

Progressive L2 backfill inventory:
- per-user cursor/status
- batch size/rate limit
- input L1 IDs
- packet IDs
- search replay hash
- product L2 prompt/model version
- patch IDs/idempotency keys
- observed/applied commit IDs
- head conflicts/retries
- route distribution: active/review/context/reject/hidden and add/update/merge/add_evidence/skip

Raw-data preservation inventory:
- artifact path/size/sha256
- source table row count/schema fingerprint
- lineage: raw row → L1 archive item → L2 packet → search replay → L2 patch → ledger commit → projection/vector/card
- deletion/tombstone audit

---

## 4. Open questions after Wave 1

1. What is the exact persistent store for L1 archive in production? Existing contracts/read APIs exist, but a dedicated write/storage path was not clearly identified.
2. Should legacy `users/{uid}/memories` become L1 archive only first, or both L1 archive and low-confidence L2 genesis facts? Current user preference points to L1 first.
3. Is `database/memory_ledger.py` the canonical durable L2 store, with legacy memory docs as projection? If yes, product applier should target ledger first.
4. Should L1 archive have its own vector namespace, or share memory namespace with explicit metadata filters?
5. Where are Firestore indexes managed/deployed for new V17 collections/queries?
6. What is the rollout policy for chat/agents: L2 active by default, L1 only through explicit search/tool, review excluded unless asked?
7. How should private-cloud raw audio queue drops be represented in no-data-loss guarantees?
8. Should import/backfill generate user-visible review items immediately, or progressively cap review burden?
9. How should delete/export/account deletion copy distinguish memory facts, L1 archive, source conversations, audio, screenshots, KG, and external exports?
10. How do we avoid inflating product metrics like `Memory Created` during bulk import/backfill?

---

# Provisional Wave 1 synthesis

The codebase already has many pieces of the desired architecture: V17 contracts, product L1/L2 prompts, durable patch IDs, ledger primitives, review queue, vector projection repair, benchmark replay artifacts, and rich desktop provenance UI fields.

The missing integration layer is not one function; it is a set of seams:

1. **L1 persistence/import service** for old memories and new source-backed archive items.
2. **Production L2 applier/backfill orchestrator** that writes to the ledger idempotently and progressively.
3. **Unified read service** that serves L2 active durable memory by default and L1 archive as labeled source-backed context.
4. **Projection/vector repair and deletion semantics** for both L1 and L2.
5. **Review UX and API expansion** across mobile/desktop/web/admin.
6. **No-data-loss verifier** that proves raw artifacts and legacy memories survive migration with lineage or explicit skip reasons.
7. **Rollout/benchmark gates** that measure utility, coverage, review burden, harmful/noisy output, and replay/idempotency.

Wave 2 should now turn this into a staged plan with concrete epics/tickets, acceptance criteria, and file-level implementation paths.


---

# Wave 2 — Integration Plan

Wave 2 converted the Wave 1 seam inventory into an implementation plan. Two planning subagents completed backend/data and product-surface plans; the migration/ops subagent repeatedly hit a broken-pipe error after reading the repo, so its area is synthesized here from Wave 1 artifacts, benchmark docs, and existing product migration/import code.

## Plan principles

1. **Scaffold first, then dual-write/shadow, then read switch.** Do not make V17 authoritative until it can be observed, replayed, and rolled back.
2. **Old Omi memories land in L1 first.** L2 is a progressive promotion/backfill over L1 evidence, not a one-shot bulk durable import.
3. **The durable ledger is L2 source of truth.** `users/{uid}/memories` remains compatibility projection during rollout.
4. **Every bulk operation gets a job/run ID.** Imports, L1 writes, L2 backfills, review creation, projection repair, export, and deletion need traceability.
5. **Normal agents/chat get L2 active by default.** L1 archive is opt-in/explicit and labeled source context.
6. **Migration/backfill must not inflate product activation metrics.** Organic memory creation and migration-generated records must be separate event classes.

## User-visible memory lifecycle

Product UI should not primarily expose “L1” and “L2” to normal users. Engineering may use L1/L2 internally; user surfaces should use these labels:

| User label | Internal layer/state | Meaning | Default use | Required actions |
|---|---|---|---|---|
| **Archive** | L1 archive | Source-backed context captured from conversations/imports/old memories. Searchable, but not stable profile truth. | Explicit archive/source search only | View source, search, hide, delete archive item, request/promote to durable, exclude from AI use |
| **Durable memory** | L2 active | Stable memory Omi may use for personalization, chat, agents, and apps. | Normal personalization/read path | View provenance, edit/correct, delete, make private, demote to archive/context, mark wrong |
| **Needs review** | Review route | Omi is unsure whether this should become durable or how it should be used. | Excluded from personalization/actions by default | Accept, edit then accept, keep as archive/context, reject, hide, delete, view source |
| **Context only** | Context-only route | Useful supporting context, not a stable fact. | Explicit context/search only | View source, promote/request durable, hide, delete |
| **Not used** | Rejected/hidden | Retained only when needed for provenance/audit or explicitly excluded from normal use. | Not used | Export if requested, delete/purge where allowed |
| **Source deleted** | Source/evidence tombstoned | Original source was deleted or unavailable. | Requires policy decision | See evidence impact, delete remaining memory/provenance, keep or retract durable fact |

Required lifecycle transitions:

- Archive → Durable via L2 backfill or explicit user “remember this” action.
- Archive → Needs review when promotion is uncertain or sensitive.
- Needs review → Durable / Archive / Context only / Rejected.
- Durable → Edited / Hidden / Deleted / Demoted to Archive or Context.
- Source deleted → evidence tombstoned; durable fact is kept, reviewed, or retracted by policy.

Unreviewed items must have a safe default: they remain excluded from durable personalization and normal agent/chat use unless a later explicitly reviewed policy allows otherwise.

## Canonical source-of-truth and write-path rules

Before any V17 production write rollout, the architecture must enforce:

1. **No durable L2 write bypasses the ledger.** Creates, edits, reviews, visibility changes, retractions, source tombstones, deletes, MCP writes, developer API writes, and manual user writes must go through one memory write service that appends ledger mutations first and updates `users/{uid}/memories` only as a compatibility projection.
2. **L1 has its own persistent store.** L1 archive records live in `users/{uid}/memory_l1_archive/{archive_id}` and are not stable profile facts.
3. **Patch idempotency is transactionally claimed.** Do not rely on ledger commit hash alone because the commit hash includes parent head. A patch application record keyed by `(uid, idempotency_key)` must be claimed before or atomically with ledger append.
4. **Evidence schema is canonical.** V17 patch adapter, ledger fold, source tombstone, projection, read API, and export must agree on one evidence field shape.
5. **Encryption/redaction applies to every V17 store.** L1 archive, ledger commits, patch applications, lineage, search replay artifacts, review queue payloads, vectors metadata, and export snapshots must not store plaintext for enhanced-protection users unless the existing protection model explicitly permits it.
6. **Delete/account purge support precedes write pilots.** Staff/customer L1/L2 writes cannot be enabled until V17 collections, vectors, review records, patch records, lineage, and job metadata are covered by account purge and deletion/tombstone tests.

## Hard rollout blockers

Do not progress beyond dry-run/staff-local phases if any blocker is true:

- Any legacy/source record has unknown migration outcome.
- Any production write path can mutate durable memory without ledger entry.
- Any V17 collection/vector namespace is omitted from account purge.
- Any active credential/secret durable memory is produced.
- Normal chat/MCP/tools can receive L1 archive as stable profile truth.
- Hidden/context/reject/review missed-useful audit is absent.
- Idempotency rerun creates duplicate L1 records, duplicate review items, duplicate patches, duplicate ledger commits, or stale duplicate vectors.
- Firestore indexes for planned high-volume queries are absent or untested.
- Backfill/review budget dashboards and kill switches are absent.
- Benchmark report lacks useful-grounded-safe per 100 contexts, harmful/noisy per 100 contexts, active/review/context route distribution, and source-stratified metrics.

## Stage A — Product contracts, config, and rollout flags

### Create

- `backend/models/v17_product_memory.py`
  - `L1ArchiveStoredRecord`
  - `LegacyMemoryL1MigrationOutcome`
  - `L2BackfillRun`
  - `V17PatchApplicationRecord`
  - `ProductMemoryDTO`
  - `ProductMemoryProvenance`
  - `ProductMemoryReviewState`
  - `ProductMemoryUsePolicy`
- `backend/models/memory_read.py`
  - `MemoryLayer`
  - `MemoryUsePolicy`
  - `MemoryReadPolicy`
  - `MemoryReadItem`
  - `MemoryReadResult`
- `backend/config/v17_memory.py`
  - `V17_MEMORY_ENABLED`
  - `V17_L1_WRITE_ENABLED`
  - `V17_L1_READ_ENABLED`
  - `V17_OLD_OMI_TO_L1_MIGRATION_ENABLED`
  - `V17_L2_BACKFILL_ENABLED`
  - `V17_L2_PATCH_APPLY_ENABLED`
  - `V17_READ_SERVICE_ENABLED`
  - `V17_CHAT_USE_L2_DEFAULT`
  - `V17_ALLOW_L1_CONTEXT_SEARCH`
  - `V17_REVIEW_QUEUE_ENABLED`
  - `V17_VECTOR_L1_ENABLED`
  - `V17_BACKFILL_USER_ALLOWLIST`
  - `V17_BACKFILL_GLOBAL_RATE_LIMIT`
- `backend/database/v17_collections.py`
  - central collection refs for L1 archive, migration jobs, L2 backfill runs, patch applications, source lineage.

### Modify

- `backend/models/v17_memory_contracts.py`
- `backend/utils/memory_ingestion/rollout.py`

### Acceptance gates

- All V17 write/read/backfill flags default to off or shadow.
- Existing V17 tests still pass.
- New product DTO preserves existing `/v3/memories` response compatibility.

## Stage B — L1 persistent archive and import service

### Store

New collection:

```text
users/{uid}/memory_l1_archive/{archive_id}
```

Purpose: broad source-backed, queryable, Base-Omi-like archive memory. It is not stable profile truth.

### Create

- `backend/database/l1_memory_archive.py`
  - `put_l1_archive_item(...)`
  - `put_l1_archive_items_batch(...)`
  - `get_l1_archive_item(...)`
  - `list_l1_archive_items(...)`
  - `search_l1_archive_text_fallback(...)`
  - `mark_l1_source_tombstoned(...)`
  - `soft_delete_l1_archive_item(...)`
- `backend/utils/memory/l1_import_service.py`
  - `archive_items_from_conversation(...)`
  - `archive_items_from_legacy_memories(...)`
  - `import_l1_archive_items(...)`
- `backend/utils/memory/source_lineage.py`
  - content/artifact hashing and lineage recording.

### Modify

- `backend/utils/conversations/process_conversation.py`
  - shadow/dual-write L1 after source transcript/conversation data is available.
  - L1 failures must not block existing conversation processing.
- `backend/routers/imports.py`
- `backend/models/import_job.py`
- `backend/database/import_jobs.py`

### Acceptance gates

- L1 writes are idempotent by deterministic archive ID/idempotency key.
- Sensitive archive items default to `normal_search_allowed=false`.
- Every L1 item has source refs, evidence/quote or explicit source pointer, import/batch ID, and content hash.
- L1 shadow writes do not alter legacy memory output.

## Stage C — Old Omi memories to L1 migration

### Create

- `backend/migrations/008_old_omi_memories_to_l1_archive.py`
  - `--dry-run`
  - `--write`
  - `--uid`
  - `--all-users`
  - `--limit-users`
  - `--batch-size`
  - `--resume-job-id`
  - `--output-report`
  - `--quarantine-sensitive`
- `backend/utils/memory/old_omi_l1_migration.py`
  - `legacy_memory_to_l1_archive_item(...)`
  - `scan_legacy_memory_inventory(...)`
  - `classify_legacy_memory_for_l1(...)`
  - `run_old_omi_l1_migration(...)`
- `backend/database/old_omi_memory_inventory.py`

### Dry-run inventory must report

- total legacy memories
- skipped/deleted
- empty/missing content
- duplicate IDs/content hashes
- encrypted/decryption failures
- category/review/manual distribution
- source/conversation linkage
- sensitive/secret scan counts
- per-memory outcome:
  - `imported_to_l1`
  - `skipped_deleted`
  - `failed_validation`
  - `quarantined_sensitive`
  - `needs_manual_review`

### Acceptance gates

- 100% of non-deleted legacy memories map to exactly one L1 archive item or explicit skip/failure reason.
- No old-memory migration creates L2 active memories directly.
- No legacy memory is deleted.
- Re-run produces no duplicates.

## Stage D — Progressive L2 backfill orchestrator

### Create

- `backend/utils/memory/l2_backfill_orchestrator.py`
  - `plan_l2_backfill_batch(...)`
  - `build_l2_packets_from_l1(...)`
  - `run_l2_search_for_packet(...)`
  - `synthesize_patches_for_packet(...)`
  - `apply_patches_for_batch(...)`
  - `advance_l2_backfill_cursor(...)`
- `backend/database/l2_backfill_jobs.py`
- `backend/jobs/v17_l2_backfill_worker.py`
- `backend/routers/memory_backfill.py`

### Operational controls

Per-user:
- batch size, default small, e.g. 25–100 L1 archive items/run.
- max L2 calls/day.
- max review items/day.
- pause/resume.
- allowlist/denylist.
- high-review-burden auto-pause.

Global:
- max users/day.
- max L2 calls/day.
- max review items/day.
- max projection repairs/hour.
- kill switches by stage: L1 migration, L2 dry-run, patch apply, read switch, vector repair.

### Backfill run artifacts

Each batch records:
- input L1 archive IDs
- packet IDs
- bounded search plan/result replay hash
- prompt/model versions
- patch IDs and idempotency keys
- observed head commit ID
- applied/skipped/review/context/reject result
- head conflict/retry count
- projection repair status

### Acceptance gates

- Dry-run produces packets, replay hashes, patches, route distribution, and zero ledger writes.
- Write mode applies at most configured batch size.
- Cursor resumes after crash.
- Same patch cannot apply twice.
- Sensitive L1 excluded unless explicitly enabled.
- Review/context/reject routes are counted, not hidden.

## Stage E — Production patch applier and durable ledger

### Create

- `backend/utils/memory/v17_patch_applier.py`
- `backend/database/v17_patch_applications.py`

### Modify

- `backend/utils/memory/v17_patch_adapter.py`
- `backend/database/memory_ledger.py`
- `backend/database/review_queue.py`

### Required semantics

- `add`, `update`, `merge`, `add_evidence`, `keep_both` append ledger mutations when valid.
- `review`, `context_only`, `reject`, `hidden` do not create active durable facts.
- Every patch application is idempotent by `idempotency_key`.
- `HeadConflict` triggers re-read/replan, not blind apply.
- Projection repair is enqueued after successful active ledger writes.

### Acceptance gates

- Applying same patch twice yields one commit.
- Head conflict is detected and recorded.
- Review/context/reject do not leak into normal prompt memory.
- Ledger fold reconstructs active facts with evidence intact.

## Stage F — Unified read service and API compatibility

### Create

- `backend/services/memory_read_service.py`
- `backend/models/memory_read.py`

### Modify

- `backend/utils/memory/v17_read_api.py`
- `backend/database/memory_reads.py`
- `backend/routers/memories.py`
- `backend/routers/developer.py`
- `backend/routers/mcp.py`
- `backend/routers/tools.py`
- `backend/utils/llms/memory.py`
- `backend/utils/retrieval/tools/memory_tools.py`
- `backend/utils/retrieval/tool_services/memories.py`
- `backend/utils/retrieval/agentic.py`
- `backend/utils/retrieval/graph.py`
- `backend/routers/chat.py`

### Policies

- `legacy_compat`
- `l2_active_default`
- `l2_plus_explicit_l1`
- `review_admin`
- `export_all`
- `mcp_external_agent`

### API additions

`GET /v3/memories` keeps compatibility, adds optional params:

```text
layer=legacy|l1|l2|all
include_review=false
include_context=false
include_archived=false
include_source_refs=false
```

New or extended endpoints:
- `GET /v3/memories/context`
- `GET /v3/memories/{memory_id}/provenance`
- `GET /v3/memories/import-status`
- `GET /v3/memories/review-queue/summary`

### Acceptance gates

- Existing clients parse unchanged responses.
- Normal chat defaults to L2 active only.
- Explicit L1 search returns labeled archive results.
- Review/hidden/sensitive records excluded from normal read paths.

## Stage G — Vectors, projection repair, and drift reporting

### Create

- `backend/database/v17_projection_repair.py`
- `backend/jobs/v17_projection_repair_worker.py`
- `backend/migrations/009_repair_v17_memory_vectors.py`

### Modify

- `backend/database/vector_db.py`
- `backend/database/projection_repair.py`
- `backend/utils/memory/v17_projections.py`
- `backend/migrations/005_backfill_memory_vectors.py`

### Decisions

Preferred: separate namespace for L1 archive, e.g. `PINECONE_L1_MEMORY_NAMESPACE`. If delayed, same namespace requires mandatory metadata filters:
- `memory_layer`
- `lifecycle_status`
- `allowed_use`
- `normal_search_allowed`
- `archive_class`
- `source_commit_id`
- `projection_version`

### Acceptance gates

- L1/L2 vector repair can run independently.
- Hidden/review/source-tombstoned records are excluded from normal vector search.
- Drift reports list missing upserts, stale vectors, metadata mismatches, and failed repairs.

## Stage H — Deletion, export, source tombstones, account purge

### Create

- `backend/services/memory_deletion_service.py`
- `backend/services/memory_export_service.py`
- `backend/database/v17_account_purge.py`

### Modify

- `backend/routers/memories.py`
- `backend/routers/conversations.py`
- `backend/database/memories.py`
- `backend/routers/users.py`
- `backend/routers/sync.py`
- `backend/routers/pusher.py`

### Required behavior

- Deleting a memory is not the same as deleting raw source data.
- Deleting a source tombstones L1 source refs and L2 evidence refs.
- L2 facts with no active evidence are retracted or routed to review by policy.
- Account purge deletes V17 collections, vectors, review/correction records, patch applications, lineage, and import/backfill metadata.
- Export can include durable, archive, review, provenance, and deleted/tombstoned history with explicit options.

## Stage I — No-data-loss verifier and telemetry

### Create

- `backend/utils/memory/v17_telemetry.py`
- `backend/utils/memory/no_data_loss_verifier.py`
- `backend/routers/memory_admin.py`

### No-data-loss report must prove

```text
raw artifact / legacy memory / source row
→ L1 archive item or explicit skip reason
→ L2 packet if selected for backfill
→ search replay hash
→ durable patch
→ ledger commit or route outcome
→ projection/vector/card if active
```

### Telemetry events

- `v17_l1_archive_write`
- `v17_old_omi_l1_migration_started/completed`
- `v17_l2_backfill_started/batch_completed`
- `v17_l2_patch_applied/skipped/head_conflict`
- `v17_memory_review_item_created/resolved`
- `v17_projection_repair_completed/failed`
- `v17_source_tombstoned`
- `v17_raw_artifact_missing`
- `v17_private_queue_raw_drop`

### Metrics rule

Bulk imports/backfills must emit `operation_type=migration|backfill|repair` and `counts_as_user_memory_created=false`.

## Stage J — Product UI/UX integration

### Shared UX labels

- **Durable memory**: stable memory Omi may use for personalization.
- **Archive**: source-backed context; searchable, not stable profile truth.
- **Needs review**: not used for actions until reviewed.
- **Context only**: supporting context, not a stable fact.
- **Not used**: rejected/hidden.

### Mobile files

- `app/lib/backend/schema/memory.dart`
- `app/lib/backend/http/api/memories.dart`
- `app/lib/providers/memories_provider.dart`
- `app/lib/pages/memories/page.dart`
- `app/lib/pages/memories/widgets/memory_item.dart`
- `app/lib/pages/memories/widgets/memory_dialog.dart`
- `app/lib/pages/memories/widgets/memory_management_sheet.dart`
- new `review_queue_page.dart`, `review_queue_item.dart`, `review_resolution_sheet.dart`

Mobile MVP:
- badges for Durable/Archive/Needs review/Context only/Imported/Source deleted.
- filters: Durable, Archive, Needs Review, Imported, All.
- memory detail source/provenance section.
- delete copy distinguishing memory vs raw source.
- review queue entry point.

### macOS files

- `desktop/macos/Desktop/Sources/Rewind/Core/MemoryModels.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/MemoryStorage.swift`
- `desktop/macos/Desktop/Sources/APIClient.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoriesPage.swift`
- `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift`
- `desktop/macos/Desktop/Sources/Chat/ChatPrompts.swift`
- `desktop/macos/Desktop/Sources/MemoryExportService.swift`
- `desktop/macos/Desktop/Sources/MemoryExportDestinationSheet.swift`

macOS MVP:
- rich provenance panel using existing source app/window/device/context fields.
- review badge/count.
- import/backfill progress.
- export options for durable/archive/provenance/review.
- chat prompt separates `<stable_profile_memories>` from `<source_archive_context>`.

### Windows files

- `desktop/windows/src/renderer/src/hooks/useMemories.ts`
- `desktop/windows/src/renderer/src/hooks/useMemoryGraph.ts`
- `desktop/windows/src/renderer/src/pages/Memories.tsx`
- `desktop/windows/src/renderer/src/pages/Settings.tsx`

Windows MVP:
- layer badges and filters.
- review panel.
- provenance panel.
- paginated loading/server-side layer filters beyond current `limit=500`.
- graph defaults to L2 active; L1 overlay optional/dashed.

### Web/admin files

Web:
- `web/frontend/src/app/memories/page.tsx`
- `web/frontend/src/app/memories/[id]/page.tsx`
- `web/frontend/src/components/memories/*`

Admin:
- `web/admin/app/(protected)/dashboard/apps/page.tsx`
- `web/admin/components/dashboard/app-detail-view.tsx`
- `web/admin/app/(protected)/dashboard/summary-apps/page.tsx`
- `web/admin/components/dashboard/edit-summary-app-drawer.tsx`
- `web/admin/app/(protected)/dashboard/chat-lab/page.tsx`

Admin MVP:
- app memory policy controls: durable only, durable+archive, no memory.
- pending-review inclusion policy.
- sensitive/source-tombstoned exclusion policy.
- Chat Lab toggles to test durable vs archive retrieval.
- metrics distinguish organic from migration/backfill.

## Stage K — Migration operations and pilot phases

### Phase 1: local/dry-run only

- Run old-memory inventory on test export/fixture users.
- Generate no-data-loss report.
- Run L2 backfill dry-run with no ledger writes.
- Compare against benchmark V17.9 and Base Omi fair metrics.

Gate:
- 100% inventory accounted for.
- 0 duplicate L1 archive IDs on rerun.
- 0 active secrets.
- replay hashes stable.

### Phase 2: staff allowlist L1 write

- Enable L1 import/write for staff users only.
- No L2 writes yet.
- Verify UI labels/provenance/export/delete copy.

Gate:
- L1 write success ≥ 99%.
- no normal chat consumption of L1 as stable profile.
- no activation metric inflation.

### Phase 3: staff allowlist L2 dry-run → write

- Dry-run L2 backfill first.
- Cap review items/day.
- Enable patch apply for a small cohort.

Gate:
- no duplicate ledger commits.
- head conflicts handled.
- review burden under threshold.
- projection drift repairable.

### Phase 4: cohort rollout

- Expand by users/day and L1 items/day.
- Keep V17 read in shadow until diff gate passes.

Gate:
- support tickets/QA clear.
- no-data-loss reports green.
- harmful/noisy and review-burden dashboards green.

### Phase 5: read switch

- Enable `V17_READ_SERVICE_ENABLED` for allowlist.
- Chat/MCP/tools default to L2 active.
- L1 explicit search available.

Gate:
- rollback flag tested.
- legacy projection and V17 reads diff acceptable.
- user review UI ready.

## Stage L — Benchmark/eval gates

### Required recurring benchmark reports

Use product-compatible benchmark paths:
- `scripts/v17_4_e2e_pipeline.py`
- `scripts/v10_judge.py`
- `reports/v17/v17_9_product_l2_rubric_schema_guarded/`
- `reports/v17/base_vs_v17_9_fair_utility/`

Add migration/backfill benchmark mode:
- old Omi export → L1 import → L2 backfill dry-run/write simulation → judge.

### Gates

- **Base Omi leftmost** in graphs (historical/projection clearly labeled).
- L1 import completeness: 100% accounted for or skip reason.
- L2 active+review yield measured and not collapsed.
- Utility/card does not regress from current V17.9 without explicit tradeoff.
- Useful-grounded-safe per 100 contexts should remain Base-like; avoid yield collapse.
- Harmful/noisy per 100 contexts remains much lower than Base Omi projection.
- active secrets = 0.
- non-primary active without explicit identity = 0.
- review burden under configured threshold overall and per source type.
- fresh vs replay search drift explained.
- hidden/context/reject missed-useful audit included.
- idempotency rerun produces no extra L1 items, L2 patches, or commits.

## First implementation tickets

1. **V17 product DTO/config scaffolding**
2. **L1 archive Firestore store**
3. **Old Omi memory inventory dry-run**
4. **Old Omi memory → L1 archive dry-run + write**
5. **No-data-loss report v1**
6. **Product read DTO + `/v3/memories` optional layer/provenance fields**
7. **Mobile/macOS read-only labels/provenance MVP**
8. **L2 backfill dry-run orchestrator**
9. **Patch application idempotency record + ledger applier**
10. **Review queue expanded payload + review UI MVP**
11. **Vector/projection repair dry-run**
12. **Chat/MCP/tools read policy switch behind flag**
13. **Export/delete/account purge V17 coverage**
14. **Migration benchmark mode + rollout dashboard**

---

# Wave 2 open risks

1. L1 persistent store is not currently implemented; many downstream UI/API assumptions depend on it.
2. Existing `007_genesis_ledger_backfill.py` can be confused with the desired old-memory-to-L1 migration; it needs warning/docs or de-emphasis.
3. `/v3`, developer API, MCP, and tools have inconsistent vector side effects today; V17 read/write service should normalize them before read switch.
4. Private-cloud raw chunk drops conflict with absolute “no raw data loss”; Epic should define this as observable loss with explicit telemetry rather than pretend preservation.
5. Firestore index management path remains unclear and must be answered before adding new collection queries at scale.
6. Review burden can overwhelm users unless per-user daily caps and “keep as archive” defaults exist.
7. Default list limits on mobile/Windows/macOS can hide imported archive volume unless layer-aware pagination ships early.


---

# Wave 3 — Committee Critique and Required Amendments

Wave 3 ran three independent review panels:

1. Product/lifecycle UX.
2. Backend architecture/data model.
3. Migration/benchmark/safety.

All three returned **APPROVE_WITH_CHANGES**. The plan is directionally sound, but the committee identified required amendments before implementation at scale.

## Product/lifecycle UX review — APPROVE_WITH_CHANGES

Required amendments incorporated into the Epic:

- Use user-facing terms **Archive** and **Durable memory** instead of exposing “L1/L2” in normal UI.
- Add explicit user-visible lifecycle states and transitions.
- Define required actions per state: view source, hide, delete, promote/demote, accept/reject/correct review items.
- Add safe default for unreviewed items: excluded from durable personalization and normal actions.
- Make old memory migration visible:
  - “importing archive”
  - “backfilling durable memories”
  - “needs review”
  - “complete/paused/failed”
- Add review burden UX, not only backend caps:
  - counts by review type
  - bulk keep-as-archive/reject/accept where safe
  - “why am I seeing this?” copy
  - safe behavior when ignored
- Add delete/export user contract distinguishing memories, archive, source conversations/audio/screenshots/imported files, provenance/ledger, and account deletion.
- Add per-chat/app/agent memory-use policy: no memory, durable only, durable + explicit archive search, no pending/sensitive by default.
- Require server-side pagination and filters before large archive imports are user-visible.

## Backend architecture/data-model review — APPROVE_WITH_CHANGES

Required amendments incorporated into the Epic:

- Add hard rule: no L2 durable write path bypasses the ledger.
- Split L2 orchestrator sequencing:
  - D1 dry-run orchestrator can land before patch applier.
  - D2 write-mode orchestrator is blocked until production patch applier/idempotency gates pass.
- Require transactionally claimed idempotency record keyed by `(uid, idempotency_key)`; ledger commit hash is insufficient.
- Standardize evidence schema across patch adapter, ledger, tombstone logic, projections, read API, and export.
- Define encryption/redaction requirements for L1 archive, ledger commits, patch records, lineage, search replay, review payloads, vectors metadata, and export snapshots.
- Reconcile append-only ledger with delete/account purge/legal erasure semantics.
- Move minimum deletion/account purge coverage before any staff/customer L1/L2 write pilot.
- Make Firestore index deployment/load testing a blocking Stage A/B gate.
- Require per-user durable-memory writer serialization or lease/lock because live extraction, backfill, review, deletes, and user edits all contend for one ledger head.
- Make separate L1 vector namespace and layer-prefixed vector IDs the default, not merely preferred.
- Define POST/PATCH/DELETE semantics for `/v3`, developer API, MCP, and tools before V17 read/write switch.

## Migration/benchmark/safety review — APPROVE_WITH_CHANGES

Required amendments incorporated into the Epic:

- Replace absolute “no data loss” with auditable **no silent data loss**. Known ephemeral loss/drop paths must be observable and excluded from preservation claims.
- Add source snapshot/high-water-mark before migration writes so concurrent edits/deletes do not create duplicates, misses, or resurrected deleted records.
- Strengthen legacy accounting: every legacy doc, including deleted/empty/decryption-failed/duplicate/malformed/source-missing, must get exactly one terminal outcome.
- Add hard operational budget table and auto-pause thresholds for users/day, L1 imports/day, L2 calls/day, review items/day, global LLM calls/day, Firestore/vector throughput, cost/day, support tickets, queue age, and job latency.
- Add anti-reward-hacking gates for hidden/context/reject/review routes:
  - measure active-only, active+review, active+context, all non-rejected proposed memories, and L1 recall.
  - audit missed useful grounded safe memories in non-active routes.
- Make benchmark wording conservative: V17.9 is cleaner on the 42-context fair utility benchmark but has slightly lower useful-grounded-safe yield per 100 contexts than Base Omi projection; treat as directional, not launch proof.
- Add bootstrap/confidence intervals or equivalent uncertainty reporting for benchmark charts where feasible.
- Add full-pipeline idempotency matrix covering L1, vectors, L2 packets, search replay, patch synthesis, ledger apply, review queue, source tombstone, export/delete side effects.
- Add rollback mode for every stage, not just read switch.
- Move deletion/export/account purge minimum support before L1 migration writes.
- Add sensitive taxonomy and per-category policy for credentials, financial, health, intimate, minors, third-party data, workplace confidential, identity/auth, and safety risk.
- Prevent all migration/backfill/repair events from polluting not just activation metrics but also engagement, memory count, export, notification, search, and cohort dashboards unless user action makes them organic.

## Final reviewed sequencing

1. **Contracts/config/source-of-truth gates**
   - DTOs, flags, collection refs, Firestore indexes, write-path audit, purge/delete minimum coverage.
2. **L1 persistent archive in shadow**
   - conversation L1 writes and old-memory dry-run inventory only.
3. **No-data-loss verifier + account purge coverage**
   - before any customer/staff L1 write.
4. **Old Omi memory → L1 write for staff allowlist**
   - explicit import status and export/delete coverage.
5. **L2 dry-run orchestrator**
   - no ledger writes; route distribution, replay hashes, missed-useful audit.
6. **Patch applier/idempotency + ledger projection repair**
   - write-mode blocked until this passes.
7. **Limited L2 write backfill**
   - staff allowlist, review caps, kill switches, projection repair, shadow reads.
8. **Product read service and UI labels/review/provenance**
   - mobile/macOS first, Windows/web/admin parity after.
9. **Chat/MCP/tools policy switch**
   - L2 active default, L1 explicit labeled archive search only.
10. **Cohort rollout and benchmark gates**
    - source-stratified, Base-leftmost, active/review/context route audited, no metric pollution.

## Remaining open decisions for David/product

1. Should old manually created Omi memories get faster durable promotion or still go to L1 archive first with review/backfill?
2. Should normal users see “Context only,” or should it be an advanced/export-only state?
3. Can users manually promote Archive → Durable with a “Remember this” action in MVP?
4. What are initial review burden caps per user/day and backlog auto-pause thresholds?
5. What exact retention/erasure model is required for append-only ledger commits under account deletion/legal deletion?
6. Where are Firestore indexes deployed from in this repo/infrastructure?
7. Is separate Pinecone namespace for L1 acceptable operationally, or do we need a temporary metadata-filtered namespace migration path?
8. How much raw artifact preservation is expected for existing ephemeral sync/private-cloud paths where raw data may already have expired or dropped?

## Committee outcome

The Epic is ready for user review as a planning artifact after these amendments. It is **not** a green light to implement all stages immediately. The first safe implementation wave should stop at contracts, index plan, write-path audit, L1 dry-run inventory, no-data-loss verifier, and purge/delete coverage.
