# Universal memory and task convergence

**Status:** implementation in progress

**Decision date:** 2026-08-11

**Applies to:** the existing Python backend and released Flutter/macOS clients in this repository. The separate clean-slate frontend/backend rewrite is outside this epic.

**Proposed invariant:** [`INV-MEM-5`](../product/invariants/universal-memory-task-authority.md)

## Outcome

Omi has one memory policy and one task-intelligence policy for every authenticated user. Account identity, generation fences, user privacy choices, and global operational kill switches remain authoritative. A UID allowlist, cohort membership, or a per-account legacy/canonical selection must not change product behavior.

Memory has one canonical domain service and state machine. All new intake enters canonical Short-term memory and follows the canonical evidence, consolidation, ledger, graph, privacy, and outbox contracts. Historical `users/{uid}/memories` documents remain physically readable without a bulk backfill, but only through a read-only storage adapter. They are not a second mutation authority.

Tasks keep `action_items` as the accepted-task authority and use one universal Candidate, goal, workstream, recommendation, and Chat-first flow. Task availability no longer derives from memory enrollment.

## Product invariants

1. **One logical authority.** Product policy is identical for all authenticated users and all memory origins. Store origin is an internal persistence fact, not a product mode.
2. **No general-population backfill.** Reading historical memory causes no writes, LLM calls, embeddings, graph admission, or migration checkpoint. Cold data may remain in the legacy collection indefinitely.
3. **No new legacy memory writes.** New capture, API, import, plugin, integration, and explicit-user intake goes through canonical apply.
4. **Historical rows are read-only.** A mutation of a historical row first creates its canonical successor through the canonical journal. A durable canonical override/tombstone suppresses the historical row before asynchronous provider cleanup.
5. **No dual write or best-effort mirror.** One logical mutation commits to one authority. Legacy cleanup is an idempotent consequence, never the correctness boundary.
6. **Canonical privacy wins.** Reads, search, graph, export, and tools honor canonical tombstones and account-deletion fences before exposing historical content. Canonical unavailability must not resurrect an old row.
7. **Stable identity.** Public IDs stay stable across adaptation and lazy materialization. Origin-qualified internal locators prevent ambiguous physical lookup. Text similarity is never identity or deletion precedence.
8. **One task flow.** Authenticated ownership plus `account_generation` and idempotency fences authorize task operations. Memory cohort membership does not.
9. **Released clients remain decodable.** `/v3/memories`, action-item, goal, task-intelligence, and Chat-first requests accepted by released clients remain accepted. Response changes are additive and preserve the existing `id`/`memory_id` and `layer`/`tier`/`memory_tier` compatibility contract.
10. **Operational controls are global or integrity-related.** Cost/incident switches, Scheduler cadence, generation fences, and provider readiness may stop a feature globally or fail a request safely. They must not silently recreate per-user product systems.

## Explicit non-goals

- Bulk-copying or re-embedding every historical memory.
- Reprocessing historical memory with an LLM solely to make it canonical.
- Treating legacy vectors, the compatibility projection, or shared knowledge graph as memory authority.
- Keeping legacy mutations as a fallback when canonical mutation fails.
- Making proactive interruption ignore user opt-in, quiet hours, budgets, focus state, or device binding.
- Deleting existing Firestore collections or provider data as part of code convergence. Physical data retirement requires separate measured evidence and explicit authorization.

## Target architecture

```text
authenticated surface
        |
        v
Universal MemoryService  <-------------------->  Universal Task Intelligence
        |                                             |
        | one policy/state machine                    | Candidate -> action_items
        |                                             | goals/workstreams/recommendations
        +----------------------+----------------------+
                               |
               +---------------+----------------+
               |                                |
      canonical memory repository       historical storage adapter
      users/{uid}/memory_items           users/{uid}/memories
      read + write authority             read-only physical compatibility
      ledger/evidence/graph/outbox       no new writes or business policy
```

### Historical read adaptation

The adapter converts a legacy document into the released `MemoryDB` boundary and a neutral internal record:

- origin locator: `(uid, "legacy", legacy_id)`;
- stable public ID: the existing legacy ID;
- lifecycle admission: `grandfathered_long_term`, an explicit historical exception rather than a fabricated promotion receipt;
- missing visibility: handled by one ratified compatibility policy, not separately by each caller;
- missing device identity: device-neutral historical data, included consistently according to the universal device-scope contract;
- malformed/encrypted rows: use the existing protected legacy reader and one shared malformed-row policy;
- no graph assertion or canonical evidence is fabricated at read time.

Canonical rows and all canonical override/tombstone records suppress a legacy row with the same stable identity before pagination or exposure. An ambiguous collision fails closed and emits content-free telemetry; it is never resolved through content comparison.

### Lazy mutation

Editing, reviewing, recategorizing, changing visibility, or otherwise mutating a historical record performs a bounded per-item conversion:

1. Read and validate the owned legacy document through the protected adapter.
2. Submit a deterministic historical-materialization operation to canonical apply, preserving stable public identity and original timestamps/provenance where available.
3. Atomically establish the canonical override/suppression record with canonical state.
4. Apply the requested mutation using canonical mutation logic.
5. Enqueue provider/graph cleanup through the canonical outbox.
6. Delete or redact the physical legacy document only as idempotent cleanup. A cleanup failure cannot make it visible again.

Deleting a historical record follows the same ordering but commits a canonical privacy tombstone. Delete-all and account deletion repeat bounded, generation-fenced scans until both origins are logically empty.

### Unified reads and pagination

List/read/search callers use one repository. Mixed accounts are read as two bounded indexed streams and merged under one deterministic public order. Cursor-capable calls use a signed composite cursor containing both source positions plus applicable generation/head fences. Released offset calls are retained as a bounded compatibility boundary and must have property coverage for interleaved writes, equal timestamps, malformed legacy rows, and no skip/duplicate behavior.

Search queries existing canonical and historical provider identities only while historical rows remain. One gateway rank-fuses candidates, hydrates every result through the unified repository, applies privacy/device/lifecycle policy, and deduplicates by stable identity or explicit lineage. Raw provider metadata is never returned.

## Task convergence

The task rollout selector becomes universal for authenticated accounts:

- remove memory-system/cohort checks from task rollout, route dependencies, database guards, conversation capture, workstream association/indexing, recommendations, goals, Chat-first intents, and recurrence inbox;
- retain and lazily provision `task_intelligence_control/state` as the generation and concurrency fence;
- keep generation mismatch, cross-owner, device binding, evidence, idempotency, resolution-claim, and outbox checks;
- always use the Candidate capture policy, with an explicit no-drop decision when extraction emits an item that Candidate policy rejects;
- retain conversation evidence as sufficient workstream evidence; memory evidence is optional;
- keep canonical-consolidation recurrence signals as an optional input, not a task entitlement dependency;
- preserve proactive interruption user opt-in, shipped-surface, quiet-hour, frequency, focus, and notification-budget gates;
- keep released action-item and goal routes as compatibility APIs backed by the same task authority, not separate business logic;
- retire staged/local task authorities only after their released clients have migrated and no-drop/no-duplicate evidence is green.

## Implementation ledger

Every checkbox is part of this convergence. A checked phase must include its code, tests, documentation, and operational contract in the same PR.

### Owned surface inventory

This inventory is intentionally path-level. Update it when discovery adds or removes scope; do not silently leave a listed surface on cohort behavior.

| Area | Primary paths |
| --- | --- |
| Entitlement and activation | `backend/config/canonical_memory_cohort.py`, `backend/config/memory_rollout.py`, `backend/utils/memory/{memory_system.py,memory_system_pin.py,canonical_activation.py,default_read_rollout.py}`, `backend/utils/memory/v3/**` |
| Memory service and canonical domain | `backend/utils/memory/{memory_service.py,canonical_memory_adapter.py,product_memory_read_service.py,canonical_lineage.py,canonical_visibility_filter.py,device_scope_filter.py}`, `backend/models/{memories.py,memory_domain.py,product_memory.py,memory_apply.py}`, `backend/database/{memories.py,memory_collections.py,memory_apply_store.py,memory_ledger.py,product_memory_items.py}` |
| Capture and maintenance | `backend/utils/conversations/{memories.py,merge_conversations.py,process_conversation.py}`, `backend/utils/llm/{memories.py,working_observations.py}`, `backend/utils/memory/{canonical_required_processing.py,canonical_consolidation.py,short_term_promotion.py,canonical_short_term_maintenance_cron.py,canonical_kg_promotion.py,memory_outbox_worker.py}`, `backend/modal/memory_maintenance_job.py` |
| Historical migration machinery | `backend/utils/memory/{legacy_backfill.py,canonical_legacy_backfill.py,bulk_legacy_backfill.py,legacy_backfill_inventory.py,legacy_backfill_bulk_support.py,canonical_cohort_lifecycle.py,canonical_memory_onboarding.py}`, `backend/scripts/{enroll_canonical_memory_user.py,backfill_legacy_memories.py,bulk_backfill_legacy_memories.py,backfill_canonical_memory_schema.py,plan_legacy_backfill_remediation.py,apply_legacy_backfill_remediation.py}` |
| Memory API and tools | `backend/routers/{memories.py,developer.py,integration.py,conversations.py,knowledge_graph.py,mcp.py,mcp_sse.py}`, `backend/utils/{mcp_memories.py,x_connector.py,apps.py}`, `backend/utils/retrieval/tool_services/memories.py`, `backend/utils/retrieval/tools/{memory_tools.py,preference_tools.py}` |
| Search, graph, and projections | `backend/utils/memory/{atom_keyword_index.py,vector_search_service.py,canonical_graph.py,kg_graph_traversal.py}`, `backend/database/{knowledge_graph.py,memory_compatibility_projection.py,memory_vector_metadata.py,memory_vector_repair_outbox.py,memory_outbox_worker.py,vector_db.py}`, `backend/models/memory_search_gateway.py` |
| Privacy and account lifecycle | `backend/services/users/{data_export.py,account_deletion.py}`, `backend/database/{users.py,account_deletion_policy.py,account_deletion_wipe.py}`, canonical tombstone/purge functions in `canonical_memory_adapter.py` and `memory_apply_store.py` |
| Task entitlement and capture | `backend/routers/canonical_task_access.py`, `backend/utils/task_intelligence/{rollout.py,conversation_capture.py,backend_capture.py,capture_policy.py,candidate_service.py,workstream_association.py,workstream_index.py}`, `backend/models/task_intelligence.py` |
| Task stores and APIs | `backend/database/{action_items.py,candidates.py,goals.py,workstreams.py,task_recommendations.py,task_intelligence_control.py,chat_first_intents.py,recurrence_inbox.py,staged_tasks.py}`, `backend/routers/{action_items.py,candidates.py,goals.py,workstreams.py,task_recommendations.py,chat_first.py,staged_tasks.py,task_integrations.py}` |
| Flutter clients | `app/lib/backend/http/api/{memories.dart,action_items.dart,goals.dart,shared.dart}`, `app/lib/backend/schema/memory.dart`, `app/lib/backend/schema/gen/**`, `app/lib/providers/{memories_provider.dart,action_items_provider.dart,goals_provider.dart}`, memory/task UI and tests |
| macOS clients | `desktop/macos/Desktop/Sources/Services/APIClient/{APIClient+Memories.swift,APIClient+TaskCatalog.swift}`, `CanonicalGoalsStore.swift`, `SuggestedTasksStore.swift`, `TasksStore.swift`, Chat-first shell/capability/tool-manifest files, `DesktopAutomationBridge*.swift`, `MemoryGraph/**`, `OnboardingImportEvidenceService.swift`, `Generated/OmiApi.generated.swift`, related tests/e2e flows |
| Windows/web clients | `desktop/windows/src/renderer/src/{hooks/useMemories.ts,lib/memoriesCache.ts,lib/memoryFilters.ts,components/memories/**,pages/Memories.tsx}`, generated TypeScript API clients and memory tests; web memory surfaces named by `INV-MEM-1` |
| OpenAPI/contracts | `docs/api-reference/{app-client-openapi.json,openapi.json,integration-public-openapi.json}`, `backend/scripts/{export_openapi.py,generate_dart_models.py,generate_swift_openapi_types.py,generate_ts_openapi_types.py,check_app_client_openapi_compatibility.py}`, `.github/workflows/openapi-contract.yml` |
| Runtime and deployment | `backend/deploy/runtime_env.yaml`, `backend/deploy/runtime_env/**`, `backend/.env*.template`, `backend/scripts/runtime_env_validation/**`, render/validate/pre-deploy scripts, `.github/workflows/{gcp_backend*.yml,gcp_memory_maintenance_job*.yml,gcp_notifications_job.yml,task-recommendation-live-eval.yml}`, `backend/testing/workflow_contracts.json` |
| Indexes, rules, monitoring | `backend/database/firestore_index_registry.py`, `firestore.indexes.json`, `firestore.rules`, `backend/utils/metrics.py`, `backend/charts/monitoring/**`, runtime-image and workflow source-closure contracts |
| Product and developer documentation | `PRODUCT.md`, `docs/product/invariants/**`, `docs/epics/{memory_normative_architecture.md,universal_memory_task_convergence.md}`, `docs/memory/domain_model.md`, `backend/utils/memory/ARCHITECTURE.md`, `backend/utils/task_intelligence/ARCHITECTURE.md`, `backend/docs/task_intelligence_baseline.md`, `docs/doc/developer/backend/{canonical_memory_architecture.md,canonical_memory_architecture.html,task_candidate_lifecycle.mdx,goal_workstream_lifecycle.mdx}` |
| Runbooks and proof documents | `docs/runbooks/{canonical-memory-rollout-flags.md,canonical-legacy-backfill.md,memory-v3-dev-cloud-proof.md,memory-v3-production-activation.md,account-cohort-cutover.md}`, `docs/rollout/memory-v3-proof-order.md`, memory IAM/readiness epics and operational evidence-marker docs |

Historical changelog releases remain historical. Add a new release fragment; do not rewrite old release records merely because they mention the former cohort.

### Required guard and test families

- Memory product guards: `test_inv_mem_1_guard.py`, canonical apply/consolidation/maintenance/vector/search/graph/outbox/privacy/source-replacement tests, and `backend/testing/e2e/test_canonical_memory_pipeline.py`.
- Former cohort/rollout tests: memory-system, activation, default-read, v3 runtime/composed projection, onboarding, backfill, runtime-env, maintenance Scheduler, and proof-contract suites must become universal-readiness tests or be deleted with their retired production owner.
- Task tests: rollout, Candidate lifecycle/router/capture, recommendation/What Matters, Chat-first eligibility/blocks/intents, goal/workstream/association/index/recurrence, staged migration/review, generation/malformed-control tests.
- Privacy and portability: data export, account-deletion Cloud Tasks, provider purge, generation reset/recreation, cross-UID ownership, and restricted/archive/tombstone exclusion.
- Client contracts: Flutter memory alias/device-scope/provider and action-item/goal tests; macOS memory lifecycle/header/filter/graph tests, Candidate/SuggestedTasks/Chat-first/goal/staged/recurrence tests; Windows memory header/filter/edit/delete/focus/graph tests.
- Generated contracts: directional OpenAPI compatibility plus regenerated Dart, Swift, and TypeScript fixtures.
- New static ratchets: task code cannot import memory cohort/system selection; production code cannot create or mutate historical memory; production routing cannot branch on UID cohort.

### Phase 0 - Ratify compatibility behavior

- [ ] Add golden fixtures for legacy-only, canonical-only, and mixed-memory accounts.
- [ ] Ratify grandfathered lifecycle, missing visibility, missing device identity, encryption, malformed-row, locked-memory, timestamp, ID-collision, and Archive-export behavior.
- [ ] Ratify the Candidate no-admission behavior so universal capture cannot silently lose tasks.
- [ ] Define content-free telemetry for origin counts, suppressions, collisions, malformed rows, cursor failures, outbox lag, and legacy cleanup failures.

### Phase 1 - Universal task authority

- [ ] Replace canonical-memory task access with authenticated ownership plus task control/generation.
- [ ] Remove repeated whitelist validation from Candidate, goal, workstream, recommendation, Chat-first intent, recurrence, and index stores.
- [ ] Make conversation Candidate capture universal and prove no dropped or duplicated tasks against the legacy writer corpus.
- [ ] Make workstream indexing/association universal and neutralize `canonical_*` task naming.
- [ ] Preserve recurrence handoff without making memory readiness a task gate.
- [ ] Make Chat-first capability/control available to all authenticated users while retaining stale/missing-generation failure behavior.
- [ ] Update macOS shell/tool-manifest wording and capability projections.
- [ ] Keep Flutter action-item/goal compatibility routes on the universal authority.

### Phase 2 - Universal memory repository

- [ ] Introduce the read-only protected legacy storage adapter.
- [ ] Introduce origin-qualified internal locators and stable public identity mapping.
- [ ] Merge canonical and historical rows under one access, lifecycle, device, and locked-memory policy.
- [ ] Add deterministic mixed-source ordering and composite cursor support; preserve bounded offset compatibility.
- [ ] Route `/v3/memories`, chat, agent, MCP, tools, developer APIs, and memory links through the repository.
- [ ] Remove client-visible behavior that depends on account/store origin.

### Phase 3 - Universal canonical writes and lazy mutation

- [ ] Lazily provision canonical apply/control state without a UID enrollment ceremony.
- [ ] Route all new memory intake and conversation replacement through canonical apply.
- [ ] Implement deterministic historical materialization for mutation without LLM processing or bulk backfill.
- [ ] Commit durable override/tombstone suppression before legacy cleanup.
- [ ] Move edit, review, visibility, category/tags, single delete, batch delete, default delete, and delete-all to the universal service.
- [ ] Prove canonical failure never falls back to a legacy writer.

### Phase 4 - Search, graph, privacy, export, and account lifecycle

- [ ] Unify keyword/vector candidate ranking and authoritative hydration across origins.
- [ ] Keep canonical graph assertions authoritative; expose historical graph only as bounded read compatibility.
- [ ] Route source deletion and conversation replacement through both-origin closure rules.
- [ ] Route user data export through the unified iterator and include canonical task sidecars according to the export policy.
- [ ] Make account deletion close over legacy memories/vectors and canonical items/evidence/operations/reviews/assertions/outbox/projections/task sidecars.
- [ ] Prove delete/read races, retries, reclaimed leases, and account recreation cannot resurrect content.

### Phase 5 - Remove rollout and duplicate authority machinery

- [ ] Delete `CANONICAL_MEMORY_USERS` and its fixture/dogfood scripts.
- [ ] Delete `MemorySystem` account selection, system pins, per-user enrollment, cohort lifecycle, and cohort backfill gates.
- [ ] Delete router/backend branches that choose legacy versus canonical business behavior.
- [ ] Delete best-effort legacy mirror writes/deletes and their recovery assumptions.
- [ ] Retire the v3 compatibility projection/control machinery that exists only for per-user cutover after the universal repository serves all released surfaces.
- [ ] Remove `MEMORY_ENABLED_USERS` and per-user rollout inventory from runtime manifests/workflows; retain only global incident/cost/readiness and cursor-integrity bindings that still have an owner.
- [ ] Remove obsolete backfill, activation, proof, and dogfood scripts and workflow checks.
- [ ] Delete or neutralize legacy task writers only after released-client compatibility is proven.
- [ ] Add static guards forbidding task packages from importing memory cohort/system selection and forbidding new legacy memory writes.

### Phase 6 - Documentation and operational closure

- [ ] Update `PRODUCT.md` from proposed cohort lifecycle to universal memory lifecycle.
- [ ] Update `docs/memory/domain_model.md`, memory architecture maps, Mintlify developer architecture, and task-intelligence architecture/baseline.
- [ ] Replace cohort rollout, production-activation, schema-migration, and proof-order runbooks with universal deploy/rollback/incident guidance; delete documents that no longer describe a supported operation.
- [ ] Update root/backend component guides and service maps, env templates, runtime manifests, Firestore index registry/rules, monitoring, Scheduler/job workflows, and source manifests.
- [ ] Update Flutter/macOS comments, capability copy, generated contracts, compatibility fixtures, and user-facing changelog entries where behavior changes.
- [ ] Rename `canonical_*` product vocabulary after the system is universal; retain physical collection names where renaming would create data migration risk.
- [ ] Ensure searches for retired cohort/whitelist/enrollment terminology return only historical decision context or explicit forbidden-pattern tests.

## Verification gates

1. **Cross-surface equivalence:** old-only, new-only, and mixed users return the same logical IDs/order/policy across `/v3`, chat, agent, MCP, tools, developer API, Flutter, and macOS.
2. **State-machine properties:** create, source replace, edit, review, visibility, category/tags, archive, supersede, delete, and account recreation preserve legal states and canonical precedence.
3. **Adversarial pagination:** thousands of rows, identical timestamps, invalid/encrypted documents, collisions, and interleaved writes produce bounded reads with no duplicates or omissions.
4. **Privacy gauntlet:** deletion disappears immediately from every read/search/graph surface; outbox/provider cleanup survives crash, retry, and lease reclaim.
5. **Export oracle:** every live logical memory is exported once, tombstoned content is absent, and task-derived records follow the ratified export policy.
6. **Task no-drop/no-duplicate:** a formerly non-cohort account completes extraction -> Candidate -> acceptance -> action item/workstream -> recommendation -> feedback/outcome -> Chat-first without consulting memory cohort or graph.
7. **Recurrence handoff:** canonical consolidation recurrence may create a workstream Candidate, but its absence never disables tasks.
8. **Compatibility:** directional OpenAPI checks and released Flutter/macOS decoding fixtures pass.
9. **Cost/latency:** Firestore reads per returned item, p95/p99 latency, cursor size, vector/LLM calls, outbox lag, and dead letters stay within the recorded pre-cutover budget.
10. **Rollback rehearsal:** a release with the universal dual-format reader can stop new canonical writes globally without hiding either historical or newly canonical data.

## Removal proof

Before declaring convergence complete, repository-wide searches must prove:

- no production UID allowlist grants memory, task intelligence, or Chat-first;
- no task production module imports the retired memory cohort/system selector;
- no production path creates or mutates `users/{uid}/memories` except bounded cleanup owned by historical materialization/account deletion;
- no route selects legacy versus canonical behavior by account;
- no best-effort mirror is required for correctness;
- no current runbook instructs operators to enroll, backfill, or activate a UID;
- no client copy or telemetry describes general availability as a canonical cohort;
- exports and deletion enumerate both physical formats through the universal authority.

## Rollback and data retention

The first universal-reader release is the rollback floor. After canonical writes are global, rolling back to a legacy-only reader would hide new data and is forbidden. A safe rollback stops new canonical intake globally while keeping the universal reader and historical adapter deployed.

This epic authorizes code and documentation convergence, not physical data destruction. Legacy and canonical collections remain retained until separate production evidence demonstrates that deletion is safe and an owner explicitly authorizes it.
