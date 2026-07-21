# Canonical Memory Runtime Architecture

> **Runtime flow companion (WS-O era).** Plain-English map of how capture → consolidation → promotion → long-term/KG → read/search works in code today on branch `memory-canonical-rollout`.
>
> - **Visual companion:** [canonical_memory_architecture.html](./canonical_memory_architecture.html) — open in a browser for boxes-and-arrows.
> - **Domain vocabulary & schema SSOT:** [docs/memory/domain_model.md](../../../memory/domain_model.md) — layers, record fields, state matrix (do not duplicate here).
> - **Product/storage decisions:** [docs/epics/memory_normative_architecture.md](../../../epics/memory_normative_architecture.md).

**Status:** Local on `memory-canonical-rollout` (not merged to `main`). Canonical cohort is code-whitelisted; everyone else stays on legacy routing.

---

## Top-level flow

```
Raw inputs (conversation, chat, OCR, explicit API/plugin memory)
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  LAYER 1 — Short-term capture (extract liberally)         │
│  Evidence/extractions are processed; explicit text pending│
└───────────────────────────────────────────────────────────┘
        │
        ▼  explicit text: required normalization + receipt
┌───────────────────────────────────────────────────────────┐
│  LAYER 2 — Maintenance pass                               │
│  Required processing → TTL → consolidation → promotion    │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  Long-term + derived indexes                              │
│  same memory_items row (layer flip) + Pinecone + KG       │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  Reads / search / agent tools                             │
│  MemoryService read/search → visibility + hybrid retrieval│
└───────────────────────────────────────────────────────────┘
```

---

## Two-layer principle

| Layer | Job | Philosophy | Where in code |
|-------|-----|------------|---------------|
| **Layer 1 (Short-term)** | Capture structured extractions from any source | **Extract liberally** — recall over precision; noise is expected | `write_canonical_extraction_memory` in `backend/utils/memory/canonical_memory_adapter.py` |
| **Layer 2 (Long-term)** | Consolidate, dedupe, promote durable facts | **Filter/consolidate in code + LLM** — merge, supersede, corroborate before promotion | `run_canonical_consolidation`, `run_canonical_short_term_promotion` in `backend/utils/memory/` |

Benchmark repo AGENTS.md Rule #12.5 states the same invariant for the ingestion pipeline: Layer 1 maximizes recall; Layer 2 owns dedup, entity resolution, and contradiction handling. The canonical memory path implements Layer 2 as the maintenance cron (consolidation → promotion gate → vector/KG side effects).

---

## Cohort gating (fail-closed)

Every read/write/maintenance path resolves the user's cohort first.

| Concern | Behavior | Evidence |
|---------|----------|----------|
| Whitelist | Only UIDs in `CANONICAL_MEMORY_USERS` get canonical memory, task intelligence, and Chat-first | `backend/config/canonical_memory_cohort.py`, `resolve_memory_system` |
| Default | Absent from whitelist → `MemorySystem.LEGACY`, task intelligence off, Chat-first off | `canonical_memory_cohort.py` and `utils/task_intelligence/rollout.py` |
| Kill-switch | Removing a UID from the code whitelist overrides stale Firestore controls and hides canonical task routes | `canonical_memory_cohort.py` and `routers/canonical_task_access.py` |
| Operational controls | `MEMORY_MODE`, `MEMORY_ENABLED_USERS`, and `MEMORY_V3_GET_ENABLED` may govern maintenance readiness only; they never select or suppress a user's request path | `backend/.env.template` |
| Request pin | HTTP/MCP handlers pin cohort once per request to avoid mid-request flips | `backend/utils/memory/memory_system_pin.py:17-40` |
| Routing seam | `MemoryService._resolve_backend` picks `CanonicalMemoryBackend` vs `LegacyMemoryBackend`; an enrolled-but-unready account fails closed rather than falling back | `backend/utils/memory/memory_service.py` |
| Maintenance refusal | Consolidation/promotion return `skipped_reason="not_canonical_cohort"` for legacy users | `canonical_consolidation.py:784-785`, `short_term_promotion.py:361-362` |

---

## Stage-by-stage

### 1. Capture → Short-term write (Layer 1)

**What happens:** Processed conversation extraction uses `MemoryService.write` / `write_batch`. Explicit user, MCP, developer API, plugin, and integration submissions use the same public create APIs as before, but the compatibility seam stores them as `tier=short_term`, `processing_state=pending`, with immutable submission provenance and a 30-day TTL. Filesystem, mail, calendar, and notes imports use `/v3/memory-imports/batch` and create evidence only, never product memories.

**Plain English:** Raw external text never enters Long-term or its derived indexes. An explicit memory is immediately visible in the first-party `/v3/memories` list as Short-term, while agent/chat, developer, MCP, search-index, and KG reads ignore it until processing completes.

| Piece | Evidence |
|-------|----------|
| Conversation extraction seam | `backend/utils/conversations/process_conversation.py:460-461` (`MemoryService`) |
| Canonical extraction write | `write_canonical_extraction_memory` — `canonical_memory_adapter.py:476` |
| Structured fields on write | `canonical_memory_adapter.py:534-535` (`subject_entity_id` in patch) |
| Record shape | `MemoryItem` — `backend/models/product_memory.py:93-129` |
| Subject inference (voice) | `process_conversation.py:478`, `:496` (`infer_subject_from_segments`) |
| Explicit submission envelope | `required_processing_payload` in `backend/utils/memory/required_promotion.py` |
| Evidence-only imports | `create_memory_import_batch` in `backend/routers/memories.py` |

### 2. Required processing for explicit memories

**What happens:** `canonical_required_processing.py` normalizes every explicit canonical submission into one self-contained memory plus structured `subject_entity_id`, `predicate`, and `arguments`. User-requested memories have a required durable outcome: processing may retry, but it cannot silently reject or downgrade them. A successful pass attaches a versioned processing receipt containing processor identity, input/output hashes, source submission ID, and timestamp. Only a required memory with that receipt is promotion-eligible.

**Plain English:** “Remember this” is guaranteed to remain a durable intent, but the raw sentence is not itself trusted as a graph atom. The processor makes it fit the memory model first and leaves an auditable receipt.

Failures remain pending/retryable Short-term. Edits to an admitted memory invalidate its KG citation and search projections, create a new pending revision, and go through the same processor again.

Legacy migration is deliberately stricter: manually added and positively reviewed rows enter this required-processing path, while unreviewed bulk/profile rows are stored as hidden `pending_admission` candidates. Those candidates are provenance-preserving quarantine records, not processor input or promotion candidates; a separate future admission decision is required before they can become product memory.

### 3. Scheduled maintenance orchestration

**What happens:** Hourly `memory-maintenance-job` may run `run_canonical_short_term_maintenance_cron` when `MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=true` and the whitelist is non-empty. Per user: **required processing → TTL audit → consolidation → promotion** (in that order). The maintenance job is the durable processor and retry owner; request handlers only stage the submission and return it as pending Short-term.

**Plain English:** A background job ages out expired short-term rows, asks the LLM to reconcile duplicates/contradictions, then promotes survivors to long-term — but only if consolidation did not fail mid-flight.

| Piece | Evidence |
|-------|----------|
| Cron entry + env gate | `canonical_short_term_maintenance_cron.py:31-52`, `run_canonical_short_term_maintenance_cron` at `:150` |
| Orchestration order | `run_canonical_short_term_maintenance` — `short_term_promotion.py:480-509` |
| Promotion gate semantics | Docstring at `short_term_promotion.py:352-357`; gate logic `:365-374`, `:496-501` |

### 4. Batched LLM consolidation (Layer 2 decider)

**What happens:**

1. List pending short-term items (`list_pending_consolidation_items`).
2. Trigger when batch count ≥ threshold **or** ≥24h since `last_consolidation_run_at` (first run is batch-only).
3. For each batch: gather vector/Firestore candidates → format context → **single batched LLM call** (`invoke_consolidation_agent`).
4. Apply decisions through `apply_long_term_patch_firestore` (merge, update, supersede, corroborate).
5. Escalate ambiguous conflicts to `review_queue`.
6. Advance `last_consolidation_run_at` watermark only on clean completion (fail-closed on parse failure or partial supersede).

**Plain English:** Before anything becomes long-term, an LLM batch decides whether items duplicate, contradict, corroborate, or coexist. Code enforces atomicity: if a supersede step fails after the survivor commits, the watermark blocks and promotion defers.

| Piece | Evidence |
|-------|----------|
| Module purpose | `canonical_consolidation.py:1-6` |
| Pending + trigger | `list_pending_consolidation_items` `:134-149`, `consolidation_trigger_reason` `:152+` |
| Candidate gather + context | `gather_consolidation_candidates` `:217`, `format_consolidation_llm_context` `:261` |
| Sole LLM decider | `invoke_consolidation_agent` `:360-383` |
| Apply + supersede atomicity | `apply_consolidation_decision` `:618`, `ConsolidationPartialApply` `:403-408` |
| Watermark fail-closed | `_should_advance_consolidation_watermark` `:411-427`, persist at `:888-895` |
| Review escalation | `_escalate_to_review_queue` `:546`, `create_review_conflict` — `backend/database/review_queue.py:57` |
| KG citation prune on supersede | `invalidate_kg_for_memory_retraction` — `canonical_memory_adapter.py:61-73` → `knowledge_graph.py:244` |
| Corroboration fields | `MemoryItem.corroboration_count` — `product_memory.py:122-123`; increment in apply `:705-708` |

### 5. Promotion gate → Long-term

**What happens:** After consolidation, promotion runs only for items allowed by the gate:

- `consolidation_batched_ids is None` — consolidation did not fire this pass → normal batch/daily promotion.
- `consolidation_batched_ids == {}` — consolidation fired but watermark blocked → **defer all promotion**.
- `consolidation_batched_ids == {ids…}` — only batched survivors may promote this pass.

Promotion flips `tier` short_term → long_term on the **same** `memory_id` via `apply_long_term_patch_firestore`, then syncs keyword index, Pinecone vector, and KG extraction.

For required explicit memories, promotion additionally fails closed unless `processing_status=processed` and a valid `processing_receipt` are present.

**Plain English:** Long-term is not a copy — it's a audited layer transition on one row. Vector and KG are derived indexes built at promotion time.

| Piece | Evidence |
|-------|----------|
| Batch-or-daily trigger | `promotion_trigger_reason` — `short_term_promotion.py:134-156` |
| First-run batch-only guard | Docstring at `short_term_promotion.py:6-9` |
| Promotion apply | `promote_short_term_item_via_apply` `:206-288` |
| Fast-track bypass (default off) | `is_fast_track_promotable` `:114-116`, env `MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED` |
| Post-promotion side effects | `sync_atom_keyword_index_for_item` `:279`, `sync_canonical_memory_vector` `:286`, `extract_kg_for_promoted_memory` `:287` |

### 6. KG write on promotion

**What happens:** When a row becomes `tier=long_term`, `extract_kg_for_promoted_memory` calls `extract_knowledge_from_memory` (LLM) and upserts nodes/edges into the Firestore KG (`users/{uid}/knowledge_graph/...`). Retractions prune citations via `prune_memory_citations_from_kg`.

| Piece | Evidence |
|-------|----------|
| Extraction on promotion | `canonical_kg_promotion.py:25-66` |
| Predicate/subject-aware content | `canonical_kg_promotion.py:44-48` |
| KG store | `backend/database/knowledge_graph.py` — `upsert_knowledge_node` `:112`, `upsert_knowledge_edge` `:189` |
| Idempotent flag | `kg_extracted` on `MemoryItem` — `product_memory.py:129` |

### 7. Reads and search

**What happens:** All product reads go through `MemoryService.read` / `search` / `search_mcp`. The first-party `/v3/memories` list opts into required pending submissions so users see their write immediately as Short-term. Agent/chat, developer, MCP, plugin, and search consumers use the protected default and see only processed memories. Search combines Typesense keyword hits + Pinecone vectors with RRF reranking (processed rows only).

**Plain English:** The memory-management screen can show a pending Short-term receipt without allowing that raw text to influence an agent. Once processed, normal Short-term and Long-term reads work as before; archive remains explicit.

| Piece | Evidence |
|-------|----------|
| Read routing | `MemoryService.read` — `memory_service.py:396-409` |
| Canonical list | `read_canonical_memories` — `canonical_memory_adapter.py:167` |
| Hybrid search | `search_canonical_memories` — `canonical_memory_adapter.py:192-275` |
| Keyword index | `atom_keyword_index.py` (sync on promotion) |
| Graph traversal tool (read-only) | `backend/utils/memory/kg_graph_traversal.py` |

---

## Data stores (canonical cohort)

| Store | Role | Evidence |
|-------|------|----------|
| `users/{uid}/memory_items/{id}` | Single product store; `tier` = short_term / long_term / archive | `domain_model.md`, `product_memory.py` |
| `users/{uid}/memory_evidence/` | Immutable evidence artifacts | `canonical_memory_adapter.py:370` |
| `users/{uid}/memory_operations/` + ledger apply | Audited mutations | `apply_long_term_patch_firestore` — `database/memory_apply_store.py` |
| `memory_items.promotion.submission` / `processing_receipt` | Source provenance and durable-admission proof | `required_promotion.py`, `canonical_required_processing.py` |
| Pinecone ns2 | Neutral `mem_*` vector ids | `neutral_vector_id_for_memory` — `canonical_memory_adapter.py:56-58` |
| Firestore KG | Nodes/edges with memory citations | `knowledge_graph.py` |
| `review_queue` | Human escalation for ambiguous conflicts | `review_queue.py:57` |

Legacy `users/{uid}/memories` remains for non-canonical users and as a non-destructive fallback for migrated users (see `domain_model.md` backfill directive).

---

## Known gaps / nits (honest)

Items below are intentional deferrals or edge cases worth reviewing — not hidden behind optimistic docs.

| Gap | Why it matters | Evidence |
|-----|----------------|----------|
| **Fast-track promotion bypass** | When `MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED=true`, `user_asserted` short-term items promote on `user_asserted_fast_track` even if batch/daily gate is not met — skips consolidation ordering for those rows | `short_term_promotion.py:70-72`, `:383-385` |
| **LLM invoke exceptions uncaught** | Parse failures become `parse_failed:*` and block watermark; raw LLM/network exceptions from `_invoke_consolidation_llm` propagate uncaught through `submit_with_context(...).result()` | `canonical_consolidation.py:355-357`, `:374`, `:828` (no try/except around invoke) |
| **Corroboration re-bump on re-consolidation** | Operation-level idempotency is tested (`test_consolidation_apply_is_idempotent_on_operation_retry`), but a later consolidation pass on the same still-short-term duplicate could increment `corroboration_count` again if the agent re-issues `corroboration_increment` — no per-pair dedupe key | `canonical_consolidation.py:705-708`; test at `test_canonical_consolidation_apply.py:300` |
| **`review_queue` cascade purge** | Conversation delete / account purge paths do not fully cascade-review-queue cleanup for canonical cohort | `domain_model.md` delete matrix row `review_queue` 🔜 |
| **Cron default off** | Maintenance requires explicit `MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=true` + non-empty whitelist | `canonical_short_term_maintenance_cron.py:31-33` |
| **Legacy stack retained** | `database/memories.py` and legacy paths still exist until WS-H decommission | Plan §WS-H; `LegacyMemoryBackend` in `memory_service.py:239` |
| **Partial `subject_entity_id` coverage** | Voice extraction infers subject; not all external writers may populate predicate/subject triples — KG promotion degrades to plain content | `process_conversation.py:478`; `canonical_kg_promotion.py:44-48` |

---

## Quick file index (agents)

| Concern | Primary file |
|---------|----------------|
| Cohort whitelist | `backend/utils/memory/memory_system.py` |
| Read/write seam | `backend/utils/memory/memory_service.py` |
| Canonical CRUD + search | `backend/utils/memory/canonical_memory_adapter.py` |
| Consolidation agent | `backend/utils/memory/canonical_consolidation.py` |
| Promotion + maintenance | `backend/utils/memory/short_term_promotion.py` |
| Explicit required processing | `backend/utils/memory/canonical_required_processing.py` |
| Cron wiring | `backend/utils/memory/canonical_short_term_maintenance_cron.py` |
| KG on promotion | `backend/utils/memory/canonical_kg_promotion.py` |
| Record model | `backend/models/product_memory.py` |
| KG persistence | `backend/database/knowledge_graph.py` |
| Review conflicts | `backend/database/review_queue.py` |
| Domain vocabulary | `docs/memory/domain_model.md` |
