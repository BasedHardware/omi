# INV-MEM-4: Canonical promotion is the sole Long-term authority

**Status:** locked
**Proposed on:** 2026-07-27
**Statement:** All new canonical intake starts in Short-term, one consolidation
decision gives every pending item exactly one terminal route, and only an
atomically receipted, graph-backed promotion may admit an item to Long-term.
Default access collapses canonical lineage, while keyword, vector,
compatibility, and shared-graph projections remain retryable derived views.

This rule and its guards must remain unchanged for seven days before a separate
PR may promote it to `locked`.

## MUST NOT

- Admit newly captured conversation, explicit-user, import, API, plugin, or
  integration input directly to Long-term or Archive. Historical
  migration/backfill is not new intake and remains governed by its explicit
  migration policy.
- Leave a pending Short-term item without exactly one consolidation route, or
  apply more than one of `promote`, `archive`, `review`, and `reject` to it.
- Treat the Short-term TTL alone as a terminal route or hide an expired active
  item before canonical apply records its disposition.
- Add a generic, batch/daily, call-site, or user-asserted fast-track promotion
  pass alongside the consolidation route.
- Commit a new active Short-term → Long-term transition without validating a
  server-authored promotion admission receipt and atomically writing the
  version-fenced per-memory graph assertion with the item, ledger head/commit,
  operation result, and outbox events.
- Return both a Short-term alias and its Long-term canonical survivor in a
  default list or search result.
- Treat keyword, vector, compatibility, or shared-graph projections as
  authoritative state.
- Send restricted memory content to a search, embedding, or vector provider.
- Acknowledge an outbox-backed projection event before its idempotent write
  succeeds and its post-write authoritative fence is reconciled.

## Surfaces

- Canonical capture, maintenance, consolidation, and apply transactions
- Chat / agent / MCP memory retrieval
- Keyword, vector, compatibility, and graph projections

## Guard tests

> Coverage gap: `test_ws_i_write_convergence.py` (1,398 lines) was deleted by
> `5724a10084` "converge universal memory and task authority" and this list was
> never updated. It is removed here so the remaining guards can be verified
> continuously; whether its coverage was absorbed elsewhere is unconfirmed and
> belongs to the memory owner.

- `backend/tests/unit/test_canonical_extraction_subject_wiring.py` and
  `backend/tests/unit/test_working_observations_extractor.py` — conversation,
  observation, explicit, and external memory writes enter Short-term
- `backend/tests/unit/test_canonical_consolidation.py` — pending work receives
  an exact one-route partition with authoritative subject/evidence validation;
  owner-rejected sources and near-duplicate negative examples cannot promote
- `backend/tests/unit/test_rejected_memory_feedback.py` — negative examples are
  recent, bounded, sensitivity-safe, source-active, cached, and invalidatable
- `backend/tests/unit/test_canonical_maintenance_ordering.py` — maintenance has
  one L2 route owner and blocked consolidation cannot fall through to generic
  promotion
- `backend/tests/unit/test_canonical_short_term_maintenance_cron.py` and
  `backend/tests/unit/test_validate_memory_maintenance_scheduler.py` — the
  scheduled runtime invokes only the canonical maintenance owner, prioritizes
  expiry work independently of the registry/cooldown, and reports projection
  delivery and unadjudicated-expiry failures
- `backend/tests/unit/test_atomic_apply.py` and
  `backend/tests/unit/test_memory_apply_store.py` — promotion atomically writes
  the item, graph assertion, ledger state, operation result, and outbox;
  source replacement and privacy tombstones use the same journal boundary
- `backend/tests/unit/test_memory_replace_policy.py` and
  `backend/tests/unit/test_ws_j_delete_privacy.py` — conversation reprocessing
  replaces its complete source set atomically, and privacy deletion closes over
  the complete canonical lineage under a control fence
- `backend/tests/unit/test_ws_m_atom_keyword_index.py` — default retrieval
  collapses Short-term aliases into their Long-term canonical survivor
- `backend/tests/unit/test_memory_read_api.py` — product access policy excludes
  restricted or otherwise ineligible canonical items from default reads
- `backend/tests/unit/test_canonical_memory_vectors.py` — restricted canonical
  content is delete-only at the external vector boundary
- `backend/tests/unit/test_memory_graph_assertion_read.py` and
  `backend/tests/unit/test_knowledge_graph_canonical_mutation_routes.py` —
  shared graph reads enforce the authoritative item privacy fence and public
  legacy mutations cannot replace retained canonical assertions
- `backend/tests/unit/test_memory_outbox_worker.py` — projection delivery
  reloads authoritative state, repairs reclaimed deliveries, retries, and
  acknowledges only successful convergence
## Path globs

- `docs/epics/memory_normative_architecture.md`
- `docs/memory/**`
- `docs/doc/developer/backend/canonical_memory_architecture.*`
- `backend/database/memory_*.py`
- `backend/utils/memory/**`
- `backend/utils/memory_ingestion/**`
- `backend/utils/mcp_memories.py`
- `backend/utils/conversations/process_conversation.py`
- `backend/utils/llm/memories.py`
- `backend/utils/llm/working_observations.py`
- `backend/models/memory_*.py`
- `backend/models/product_memory.py`
- `backend/database/knowledge_graph.py`
- `backend/routers/memories.py`
- `backend/routers/memory_*.py`
- `backend/routers/knowledge_graph.py`
- `backend/modal/memory_maintenance_job.py`
- `backend/deploy/runtime_env.yaml`
- `backend/scripts/validate_memory_maintenance_scheduler.py`
- `.github/workflows/gcp_memory_maintenance_job*.yml`
- `scripts/dev-harness/run-canonical-maintenance.py`
- `backend/tests/unit/test_canonical_memory_vectors.py`
- `backend/tests/unit/test_memory_graph_assertion_read.py`
- `backend/tests/unit/test_knowledge_graph_canonical_mutation_routes.py`
- `backend/tests/unit/test_validate_memory_maintenance_scheduler.py`
- `scripts/dev-harness/tests/test_python_resolver.py`
- `firestore.rules`

## PR rule

Name `INV-MEM-4` in the PR body while this proposal is in scope. Proposed
invariants are design notes and are not CI-enforced until separately locked.

## Canonical docs (do not duplicate)

- [`docs/epics/memory_normative_architecture.md`](../../epics/memory_normative_architecture.md)
- [`docs/memory/domain_model.md`](../../memory/domain_model.md)
