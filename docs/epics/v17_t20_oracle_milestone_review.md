# V17 T19/T20/T21 Oracle Milestone Review

**Date:** 2026-06-19T10:20:49Z  
**Oracle session:** `v17-t20-vector-review`  
**Oracle CLI:** `/usr/local/bin/consult-oracle` (`oracle 0.14.0`)  
**Requested model:** `gpt-5.5-pro`  
**Execution mode:** browser foreground  
**Run summary:** 10m51s, `files=15`, `↑103.84k ↓4.2k ↻0 Δ108.03k`  
**Model selection caveat:** Oracle reported `requested=Pro; resolved=(unavailable); status=unavailable; strategy=select; verified=no`, but returned an answer under `gpt-5.5-pro[browser]`. Treat this as a real Oracle/browser milestone review with model-selection caveat, not as production approval.

## Prompt summary

Review the V17 memory T19/T20/T21 default-read and vector integration milestone for production readiness, focusing on hidden safety/product/architecture risks: stale Short-term default visibility, Archive default exposure, rollout fail-closed behavior, legacy vector fallback interactions, vector metadata vs authoritative hydration, MCP/developer/chat caller surfaces, observability/metrics cardinality, production cutover gates, and missing tests. Return verdict, P0/P1 issues, required fixes before rollout, and product-owner decisions. Do not assume Oracle/cloud/benchmark validation was run unless shown.

## Files reviewed

- `docs/epics/v17_t20_vector_readiness_remaining_gates.md`
- `docs/epics/v17_memory_implementation_tickets.md`
- `backend/utils/memory/v17_vector_search_service.py`
- `backend/database/v17_vector_metadata.py`
- `backend/routers/v17_memory_product.py`
- `backend/utils/memory/v17_chat_memory_adapter.py`
- `backend/utils/mcp_memories.py`
- `backend/routers/mcp.py`
- `backend/routers/mcp_sse.py`
- `backend/utils/memory/v17_developer_memory_adapter.py`
- `backend/routers/developer.py`
- `backend/utils/memory/v17_default_read_rollout.py`
- `backend/tests/unit/test_v17_developer_memory_adapter.py`
- `backend/tests/unit/test_v17_vector_search_service.py`
- `backend/tests/unit/test_v17_default_read_rollout_decision.py`

## Oracle verdict

**BLOCK production rollout.** Oracle says this milestone is ready for architecture/milestone review, but a production read/vector cutover is **NO-GO**. Shadow tests that cannot affect returned results may continue.

Oracle affirmed the foundation that vector candidates hydrate through authoritative `memory_items` and that tested stale Short-term/Archive exclusion is useful, but concluded the system is not yet safe for production because authorization, downgrade behavior, write/read convergence, vector fencing, shared-namespace coexistence, and real operational validation remain unresolved.

## P0 issues from Oracle

1. **Product default read is not rollout-gated; Archive capability is client-self-granted.** Every V17 product route must call one shared server-side authorization decision before any `memory_items` access. Archive must require both persisted capability and explicit Archive query.
2. **“Fail closed” is conflated with unsafe legacy downgrade.** Replace Boolean/`None` rollout contracts with an explicit decision such as `USE_V17`, `USE_LEGACY_SAFE`, `DENY_MEMORY`, and optionally `SHADOW_ONLY`; legacy downgrade must require proven reconciliation/generation/epoch safety and explicit policy.
3. **Reads are V17 while MCP/developer writes and deletes remain legacy.** Before authoritative read cutover, route applicable create/edit/delete through V17, disable those writes for pilots and prove reconciliation, or implement tested durable dual-write/outbox; deletion must update authoritative state and compatibility/vector projections before success.
4. **Vector freshness and purge fences are optional in production callers.** Make expected account generation, uid, item revision, content hash, source commit/version, projection commit/version, and source/tombstone state mandatory; missing fence metadata rejects the hit; projection workers must delete prior tier/revision IDs and repair must prove no stale/duplicate IDs remain.
5. **Shared `ns2` isolation from legacy search is unproven.** Prove with real Pinecone/`ns2` data that legacy queries exclude V17 schema records and retain baseline recall, or add a legacy schema filter / separate namespace before production V17 inserts.
6. **Third-party authorization is not shown at app/key granularity.** Carry authenticated key/app identity and verified scopes into `MemoryAccessPolicy`; enforce `memories.read` at execution time on every MCP transport; store grants per app/key if product requires differentiated access.
7. **Vector search algorithm is not production-shaped.** Replace full-collection hydration with candidate-ID batch hydration, measured overfetch/refill, strict budgets, timeouts, rate limits, and high-volume load tests.
8. **Required cutover evidence is absent.** Real Pinecone, Firestore/cloud, benchmarks, production metrics aggregation, projection/repair consistency, `/v3` compatibility, and T22/T23 write/caller coverage remain gates.

## P1 issues from Oracle

1. Rollout document parsing is too permissive: missing uid accepted, alias/revocation precedence ambiguous, top-level grants may override nested state, Firestore transport exceptions not handled by policy.
2. Sensitive-data policy is duplicated/incomplete in vector metadata; restricted vectors can pollute top-k before hydration.
3. Caller/API behavior is inconsistent across product, MCP REST, MCP SSE, chat, developer list, developer category filtering, and fallback semantics.
4. Current metrics are admin-derived local renderings, not central monotonic production counters.
5. Chat concatenates memory content directly into LLM-facing text without visible quoting/escaping/size-budget/prompt-injection tests.
6. Test coverage is mostly fake/static wiring coverage and does not exercise real FastAPI dependencies, response filtering, Pinecone filters, Firestore exceptions, scope enforcement, or cross-store behavior.

## Required fixes/gates before rollout

1. Gate every V17 route with the same versioned rollout decision and add a global emergency kill switch independent of per-user Firestore reads.
2. Implement server-authorized Archive capability, separate from explicit query flag, with audit logging and revocation tests.
3. Introduce explicit read decisions and prohibit legacy downgrade unless reconciliation proves it safe.
4. Complete T22/T23 across applicable surfaces, especially MCP/developer create, edit, delete, list, tools, agent paths, and existing `/v3` compatibility.
5. Make vector consistency fences mandatory, including current account generation, and complete outbox/stale-ID deletion/repair/tombstone precedence.
6. Prove shared-namespace isolation against real Pinecone data for V17 and legacy callers.
7. Replace full-collection hydration with candidate-ID batch hydration and measured overfetch/refill.
8. Enforce scopes and app/key-specific grants on MCP REST, MCP streamable HTTP/SSE, and developer keys.
9. Add central, monotonic, low-cardinality telemetry and alerts for path selection, vector errors/latency, candidate/parse/hydration/returned counts, empty-after-hydration, stale mismatch, fallback reason, Firestore reads, and per-surface errors.
10. Run real cloud validation and benchmarks with malformed metadata, cross-user hits, expired Short-term, Archive, deleted/tombstoned sources, duplicate revisions, partial outages, and high-volume accounts.
11. Close all P0 findings before production rollout.
12. Cut over only through shadow comparison and canaries with abort thresholds and tested rollback that cannot lose or resurrect data.

## Product-owner decisions required

1. Archive authorization: whether first-party `include_archive=true` is enough, or persisted opt-in/capability is required; whether Archive vector search exists now or remains non-vector.
2. Fallback semantics: deny, error, last-known-safe, merge, or legacy only when reconciliation is proven for missing/malformed control state, grant revocation, vector outage, or empty V17 results.
3. Meaning of default-memory grant: rollout eligibility vs privacy/consent; if consent, legacy fallback after grant removal is unacceptable.
4. Third-party scope: broad per-user consumer grant vs per app/key/OAuth client/installation.
5. Short-term exposure: whether fresh source-backed Short-term is default-visible to MCP/developer apps or first-party chat only without stronger scope.
6. Read/write sequencing: whether T22 V17 writes/deletes must land before read cutover or pilot external writes are disabled.
7. API strategy: additive switch on existing `/v3`, MCP, developer endpoints vs private/experimental `/v17` until compatibility is complete.
8. Launch thresholds: acceptable recall regression, p95/p99 latency, empty-after-hydration rate, stale-vector rate, error rate, and observation period before expanding allowlist.


## Follow-up implementation slices after Oracle review

### 2026-06-19 — first narrow P0-1/P0-2 fix slice

Implemented a small local code slice after this review, without changing the production rollout verdict:

- Added shared explicit `V17ReadDecision` semantics in `backend/utils/memory/v17_default_read_rollout.py`: `USE_V17`, `USE_LEGACY_SAFE`, `DENY_MEMORY`, and `SHADOW_ONLY`.
- Classified missing, malformed, uid-mismatched, disabled, unsupported, and no-default-memory-grant control states as `DENY_MEMORY` for default V17 reads instead of silently implying legacy fallback.
- Added an explicit `legacy_safe_v17_default_read_rollout_decision(...)` constructor for callers that are intentionally legacy-safe by policy, so safe legacy behavior is opt-in rather than derived from bad V17 control state.
- Classified shadow-enabled/read-disabled granted state as `SHADOW_ONLY`.
- Applied the explicit decision to product `/v17/memory/search` and `/v17/memory/vector/search`: both require persisted server-owned Omi-chat rollout/grant state to return `USE_V17` before any `users/{uid}/memory_items` or vector read; non-`USE_V17` returns 403 with rollout observability.
- Kept Archive default-unavailable. The existing Archive product route remains explicit-query-only and is **not** yet persisted/server-authorized; that part of P0-1 remains open.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED import failure for missing explicit decision type, GREEN focused tests, full `pytest tests/unit/test_v17_*.py -q` (`175 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

Remaining P0-1/P0-2 work:

- Add persisted/server-authorized Archive capability plus explicit Archive query before Archive reads; do not treat client `include_archive=true` as sufficient.
- Continue converting legacy-fallback callers to explicit `USE_LEGACY_SAFE` only where reconciliation/projection/generation policy proves it safe; otherwise deny or shadow.
- Add the global emergency kill switch independent of per-user Firestore reads.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — persisted/server-authorized Archive product-route slice

Implemented the next narrow P0-1 Archive authorization slice after the explicit read-decision product-route work, without changing the production rollout verdict:

- Added shared persisted Archive capability parsing in `backend/utils/memory/v17_default_read_rollout.py` through `read_v17_archive_read_rollout(...)` / `normalize_v17_archive_read_rollout_decision(...)`.
- Archive reads now require the same persisted Omi-chat V17 default-read authorization (`USE_V17`) plus default-memory grant and a distinct server-owned Archive capability (`grants.omi_chat.archive=true`, `grants.chat.archive=true`, or boolean top-level Omi-chat aliases). Non-boolean Archive capability values fail closed as malformed.
- Applied the decision to the explicit product `/v17/memory/archive/search` route: it still requires explicit `include_archive=true`, but that flag alone no longer grants Archive access. Missing control state, disabled reads, no default grant, missing Archive grant, or malformed Archive capability all return 403 before `users/{uid}/memory_items` reads.
- Default `/v17/memory/search` and `/v17/memory/vector/search` remain Archive-default-unavailable (`archive_capability=false`), and no Archive vector route/exposure was added.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED import failure for missing `read_v17_archive_read_rollout`, first GREEN attempt exposing fallback reason precedence (`2 failed, 18 passed`), focused GREEN (`20 passed`), full `pytest tests/unit/test_v17_*.py -q` (`178 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes the narrow Oracle P0-1 subpoint for the explicit Archive product route's persisted/server-authorized capability. Remaining P0-1/P0-2 work:

- Continue rolling explicit `USE_V17` / `USE_LEGACY_SAFE` / `DENY_MEMORY` / `SHADOW_ONLY` semantics across fallback callers and deny unsafe downgrades.
- Add the global emergency kill switch independent of per-user Firestore reads.
- Expand shared route authorization to any remaining V17 product/caller surfaces before production rollout.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — global V17 product-read gate / emergency kill switch slice

Implemented the next narrow P0-1 global-gate slice after persisted Archive authorization, without changing the production rollout verdict:

- Added `V17_GLOBAL_READ_GATE_PATH = memory_control/v17_global_read_gate` plus `read_v17_global_read_gate(...)` / `normalize_v17_global_read_gate(...)` in `backend/utils/memory/v17_default_read_rollout.py`.
- The global gate is independent of per-user `users/{uid}/memory_control/state`; product routes read it first and require boolean `v17_reads_enabled=true` and boolean `kill_switch_active=false`.
- Missing global config, malformed config, disabled global reads, and active kill switch all return explicit `DENY_MEMORY` reasons (`missing_global_read_gate`, `malformed_global_read_gate`, `global_v17_reads_disabled`, `global_v17_read_kill_switch_active`). This intentionally fails safe/closed under the Oracle-risk posture.
- Applied the gate before per-user rollout reads, vector calls, or `users/{uid}/memory_items` reads on product `/v17/memory/search`, `/v17/memory/vector/search`, and explicit `/v17/memory/archive/search?include_archive=true`.
- Enabled global gate preserves existing per-user `USE_V17` default and Archive decisions; Archive remains default-unavailable and still requires explicit intent plus persisted Archive capability.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED import failure for missing `V17_GLOBAL_READ_GATE_PATH`, GREEN focused tests (`24 passed`), formatted/focused regression (`26 passed`), full `pytest tests/unit/test_v17_*.py -q` (`182 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes the narrow Oracle P0-1 subpoint for the product default/vector/Archive routes' global emergency read gate. Remaining P0 work:

- Continue P0-2 by rolling explicit `USE_V17` / `USE_LEGACY_SAFE` / `DENY_MEMORY` / `SHADOW_ONLY` semantics across remaining fallback callers and denying unsafe legacy downgrades.
- Address P0-3 write/read split-brain before authoritative read cutover.
- Make P0-4 vector freshness/purge fences mandatory and complete repair/stale-ID proof.
- Complete shared `ns2`, third-party app/key/scope authorization, vector overfetch/budgets, central telemetry, and real cloud/Pinecone/Firestore/benchmark evidence.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — Omi chat vector fallback explicit read-decision slice

Implemented one narrow Oracle P0-2 fallback-caller-family slice after the global product-read gate, without changing the production rollout verdict:

- Added `V17ChatMemorySearchResult` in `backend/utils/memory/v17_chat_memory_adapter.py` so the Omi chat vector adapter returns explicit `V17ReadDecision` semantics plus fallback reason instead of using `None` as an ambiguous downgrade signal.
- Wired the mature Omi chat `search_memories_tool` in `backend/utils/retrieval/tools/memory_tools.py` to call the explicit decision adapter and to preserve legacy vector fallback only when the decision is explicitly `USE_LEGACY_SAFE`.
- Missing, malformed, no-grant, disabled, or shadow-only Omi-chat rollout decisions now avoid V17 vector search and `users/{uid}/memory_items` reads and return a safe no-memory response instead of silently calling legacy `vector_db.find_similar_memories(...)`.
- Enabled/granted Omi-chat rollout continues using hydrated V17 vector search with default Archive unavailable; no Archive exposure was broadened.
- The old text wrapper is retained only as an explicit compatibility/legacy-safe opt-in path; it is not used by the production chat tool.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED import failure for missing `V17ChatMemorySearchResult`, GREEN chat adapter tests (`8 passed`), focused regression (`20 passed`), full `pytest tests/unit/test_v17_*.py -q` (`183 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes one Oracle P0-2 subpoint for the Omi chat vector fallback caller family. Remaining P0-2/P0 work:

- Continue converting any remaining fallback callers (chat default/list path if promoted, MCP REST/SSE list/default paths, developer list/category paths) so only explicit `USE_LEGACY_SAFE` can downgrade to legacy.
- Address P0-3 write/read split-brain before authoritative read cutover.
- Make P0-4 vector freshness/purge fences mandatory and complete repair/stale-ID proof.
- Complete shared `ns2`, third-party app/key/scope authorization, vector overfetch/budgets, central telemetry, and real cloud/Pinecone/Firestore/benchmark evidence.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — MCP REST/SSE vector fallback explicit read-decision slice

Implemented the next narrow Oracle P0-2 MCP fallback-caller slice after the Omi chat vector caller work, without changing the production rollout verdict:

- Added `V17McpMemorySearchResult` in `backend/utils/mcp_memories.py` so the MCP hydrated vector adapter returns explicit `V17ReadDecision` semantics plus fallback reason instead of using `None` as an ambiguous downgrade signal.
- Wired MCP REST `/v1/mcp/memories/search` and streamable HTTP/SSE `search_memories` to pass the persisted MCP rollout decision into the adapter and branch on `USE_V17` / `USE_LEGACY_SAFE` / `DENY_MEMORY` / `SHADOW_ONLY` before any legacy vector/default fallback.
- Missing, malformed, no-grant, disabled, or shadow-only MCP rollout decisions now avoid V17 vector search and `users/{uid}/memory_items` reads and return an empty safe memory response instead of silently calling legacy `vector_db.find_similar_memories(...)` or the legacy default read fallback.
- Enabled/granted MCP rollout continues using hydrated V17 vector search with default Archive unavailable; no Archive exposure was broadened.
- Intentional legacy fallback is preserved only for an explicit `USE_LEGACY_SAFE` adapter classification.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED import failure for missing `V17McpMemorySearchResult`, GREEN MCP adapter tests (`11 passed`), focused regression (`23 passed`), full `pytest tests/unit/test_v17_*.py -q` (`186 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only. An additional attempted legacy MCP route test collection is blocked in this local environment by missing `fastapi`.

This closes the Oracle P0-2 subpoint for MCP REST/SSE vector search fallback downgrade semantics. Remaining P0-2/P0 work:

- MCP list (`GET /v1/mcp/memories`) is still legacy-only/not V17-default-read-wired; if it becomes a V17 default/list path, convert it through explicit decisions before rollout.
- Continue converting developer list/category fallback semantics and any other fallback callers so only explicit `USE_LEGACY_SAFE` can downgrade to legacy.
- Address P0-3 write/read split-brain before authoritative read cutover.
- Make P0-4 vector freshness/purge fences mandatory and complete repair/stale-ID proof.
- Complete shared `ns2`, third-party app/key/scope authorization, vector overfetch/budgets, central telemetry, and real cloud/Pinecone/Firestore/benchmark evidence.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — developer API fallback explicit read-decision slice

Implemented the next narrow Oracle P0-2 developer API fallback-caller slice after the MCP vector caller work, without changing the production rollout verdict:

- Added `V17DeveloperMemorySearchResult` in `backend/utils/memory/v17_developer_memory_adapter.py` so developer default-list and vector adapters return explicit `V17ReadDecision` semantics plus fallback reason instead of using `None` as an ambiguous downgrade signal.
- Wired developer default list (`GET /v1/dev/user/memories` with no category filter) and developer vector search (`GET /v1/dev/user/memories/vector/search`) to pass the persisted developer rollout decision into the adapter and branch on `USE_V17` / `USE_LEGACY_SAFE` / `DENY_MEMORY` / `SHADOW_ONLY` before any legacy fallback.
- Missing, malformed, no-grant, disabled, or shadow-only developer rollout decisions now avoid V17 vector search and `users/{uid}/memory_items` reads and return 403 instead of silently calling legacy `memories_db.get_memories(...)` on the V17-enabled list path.
- Category-filtered developer list remains a legacy-only compatibility path until T22/T23 resolves category/read/write split-brain, but that fallback is now explicitly classified as `USE_LEGACY_SAFE` (`developer_category_legacy_safe_fallback_explicit`) rather than implicit `None`.
- Enabled/granted developer rollout continues using hydrated V17 default/vector reads with default Archive unavailable; no Archive exposure was broadened.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED import failure for missing `V17DeveloperMemorySearchResult`, GREEN developer adapter tests (`11 passed`), focused regression (`23 passed`), full `pytest tests/unit/test_v17_*.py -q` (`189 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes the Oracle P0-2 subpoint for developer default-list/vector fallback downgrade semantics. Remaining P0-2/P0 work:

- MCP list (`GET /v1/mcp/memories`) remains legacy-only/not V17-default-read-wired; if it becomes a V17 default/list path, convert it through explicit decisions before rollout.
- Developer category filtering still has external read/write/category split-brain risk and remains a T22/T23 compatibility follow-up before any authoritative external read cutover.
- Address P0-3 write/read split-brain before authoritative read cutover.
- Make P0-4 vector freshness/purge fences mandatory and complete repair/stale-ID proof.
- Complete shared `ns2`, third-party app/key/scope authorization, vector overfetch/budgets, central telemetry, and real cloud/Pinecone/Firestore/benchmark evidence.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — first P0-3 developer create write/read split-brain guard slice

Implemented the first narrow Oracle P0-3 write/read split-brain guard after the P0-2 developer read-decision work, without changing the production rollout verdict:

- Added `V17LegacyMemoryWriteGuardDecision` and `assert_legacy_memory_write_allowed_for_default_read_decision(...)` in `backend/utils/memory/v17_default_read_rollout.py`.
- Applied the guard to external developer `POST /v1/dev/user/memories` before auto-categorization or `memories_db.create_memory(...)`.
- The guard uses the same persisted `developer_api` default-read rollout decision as developer V17 reads and blocks legacy `memories` mutation with HTTP 409 for `USE_V17`, `SHADOW_ONLY`, missing, malformed, or uid-mismatched control state unless an explicit server-owned `allow_write_convergence=True` policy is passed.
- V17-disabled reads and explicit convergence preserve the legacy create path; Archive remains default-unavailable and no read surface was broadened.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing guard import, RED fail-safe coverage catch, GREEN developer adapter tests (`15 passed`), focused regression (`27 passed`), full `pytest tests/unit/test_v17_*.py -q` (`193 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the first narrow Oracle P0-3 subpoint for developer single-create. Remaining P0-3 work:

- Extend the same guard/policy to developer batch create, edit, delete.
- Add equivalent MCP REST and streamable HTTP/SSE create/edit/delete protection.
- Decide and implement durable V17 write convergence / dual-write outbox before any authoritative external read cutover.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — second P0-3 developer batch-create write/read split-brain guard slice

Implemented the next narrow Oracle P0-3 write/read split-brain guard after the developer single-create guard, without changing the production rollout verdict:

- Applied `assert_legacy_memory_write_allowed_for_default_read_decision(...)` to external developer `POST /v1/dev/user/memories/batch` after shape/limit validation but before auto-categorization, `memories_db.save_memories(...)`, vector upsert, or persona updates.
- The guard uses the same persisted `developer_api` default-read rollout decision as developer V17 reads and blocks legacy batch mutation with HTTP 409 for `USE_V17`, `SHADOW_ONLY`, missing, malformed, or uid-mismatched control state unless an explicit server-owned convergence policy is passed through the shared guard.
- V17-disabled reads preserve existing developer batch-create behavior; Archive remains default-unavailable and no read surface was broadened.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED batch-route guard-order failure (`1 failed, 16 passed`), GREEN developer adapter tests (`17 passed`), focused regression (`29 passed`), full `pytest tests/unit/test_v17_*.py -q` (`195 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the narrow Oracle P0-3 subpoint for developer batch-create. Remaining P0-3 work:

- Extend the same guard/policy to developer edit and delete.
- Add equivalent MCP REST and streamable HTTP/SSE create/edit/delete protection.
- Decide and implement durable V17 write convergence / dual-write outbox before any authoritative external read cutover.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — third P0-3 developer edit/delete write/read split-brain guard slice

Implemented the next narrow Oracle P0-3 write/read split-brain guard after the developer batch-create guard, without changing the production rollout verdict:

- Applied `assert_legacy_memory_write_allowed_for_default_read_decision(...)` to external developer `DELETE /v1/dev/user/memories/{memory_id}` before legacy `memories_db.get_memory(...)` or `memories_db.delete_memory(...)`.
- Applied the same guard to external developer `PATCH /v1/dev/user/memories/{memory_id}` before legacy `memories_db.get_memory(...)`, `edit_memory(...)`, `change_memory_visibility(...)`, or `update_memory_fields(...)`.
- The guard uses the same persisted `developer_api` default-read rollout decision as developer V17 reads and blocks legacy mutation/delete with HTTP 409 for `USE_V17`, `SHADOW_ONLY`, missing, malformed, or uid-mismatched control state unless an explicit server-owned convergence policy is passed through the shared guard.
- V17-disabled reads preserve existing developer edit/delete behavior; Archive remains default-unavailable and no read surface was broadened.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED edit/delete guard-order failures (`2 failed, 18 passed`), GREEN developer adapter tests (`20 passed`), focused regression (`32 passed`), full `pytest tests/unit/test_v17_*.py -q` (`198 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the narrow Oracle P0-3 subpoints for developer edit and delete. Remaining P0-3 work:

- Add equivalent MCP REST and streamable HTTP/SSE create/edit/delete protection.
- Decide and implement durable V17 write convergence / dual-write outbox before any authoritative external read cutover.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — MCP REST/SSE create/edit/delete write/read split-brain guard slice

Implemented the next narrow Oracle P0-3 write/read split-brain guard after the developer edit/delete guard, without changing the production rollout verdict:

- Inspected MCP REST and streamable HTTP/SSE tool write surfaces and found six legacy mutation surfaces: REST `POST /v1/mcp/memories`, `DELETE /v1/mcp/memories/{memory_id}`, `PATCH /v1/mcp/memories/{memory_id}`, and SSE tools `create_memory`, `delete_memory`, `edit_memory`.
- Applied `assert_legacy_memory_write_allowed_for_default_read_decision(...)` to all six surfaces before legacy mutation/delete and before expensive side effects such as auto-categorization, vector updates, persona updates, and legacy `memories_db.get_memory(...)` validation.
- The guard uses the same persisted `mcp` default-read rollout decision as MCP V17 reads and blocks legacy mutation/delete for `USE_V17`, `SHADOW_ONLY`, missing, malformed, or uid-mismatched control state unless a server-owned convergence policy explicitly allows the write.
- REST surfaces return HTTP 409 with the shared guard detail; SSE tools return a safe MCP tool error (`code=-32009`) with the same guard detail. V17-disabled reads preserve existing behavior.
- Archive remains default-unavailable and no read surface was broadened.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED MCP write-surface guard-order failures (`2 failed, 12 passed`), GREEN MCP adapter/source tests (`14 passed`), focused regression (`26 passed`), full `pytest tests/unit/test_v17_*.py -q` (`201 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes the narrow Oracle P0-3 subpoints for MCP REST/SSE create/edit/delete legacy write protection. Remaining P0-3/P0 work:

- Decide and implement durable V17 write convergence / dual-write outbox before any authoritative external read cutover.
- Make P0-4 vector freshness/purge fences mandatory and complete repair/stale-ID proof.
- Complete shared `ns2`, third-party app/key/scope authorization, vector overfetch/budgets, central telemetry, and real cloud/Pinecone/Firestore/benchmark evidence.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-3 durable write convergence/outbox readiness gate seam

Concretized the remaining Oracle P0-3 durable write convergence gate as a narrow fail-closed backend seam, without claiming full external V17 write convergence or changing the production rollout verdict:

- Added server-owned convergence gate path `memory_control/v17_write_convergence_gate`, `V17WriteConvergencePolicy`, and `read_v17_write_convergence_gate(...)` in `backend/utils/memory/v17_default_read_rollout.py`.
- Updated `assert_legacy_memory_write_allowed_for_default_read_decision(...)` so `USE_V17`, `SHADOW_ONLY`, and fail-safe read-decision states still block legacy external writes unless the convergence gate is explicitly ready.
- Gate readiness requires all four booleans to be true: `durable_outbox_enabled`, `dual_write_projection_ready`, `delete_convergence_ready`, and `idempotency_contract_ready`.
- Missing, malformed, or partial convergence config fails safe; the old legacy boolean override is not sufficient for V17/shadow read consumers.
- Wired the gate into the external write surfaces already protected by the P0-3 guard: developer create/batch/edit/delete, MCP REST create/edit/delete, and MCP streamable HTTP/SSE `create_memory`/`delete_memory`/`edit_memory`.
- Archive remains default-unavailable and no read surface was broadened.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing convergence gate import, focused GREEN across MCP/developer/default-read tests (`47 passed`), focused regression (`49 passed`), full `pytest tests/unit/test_v17_*.py -q` (`204 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the fail-closed convergence readiness seam. Remaining P0-3/P0 work:

- Implement the actual durable external V17 write service / dual-write outbox worker and transaction contract.
- Prove idempotent create/edit/delete replay, delete convergence, and projection consistency under provider/emulator tests.
- Make P0-4 vector freshness/purge fences mandatory and complete repair/stale-ID proof.
- Complete shared `ns2`, third-party app/key/scope authorization, vector overfetch/budgets, central telemetry, and real cloud/Pinecone/Firestore/benchmark evidence.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 mandatory vector freshness/account-generation fence seam

Started Oracle P0-4 with a narrow mandatory vector freshness fence, without changing the production rollout verdict:

- V17 vector hydration now requires a server-owned `vector_projection_commit_id` from persisted default-read rollout state plus the current account generation.
- `fetch_default_v17_vector_memory_search(...)` requires `required_projection_commit_id` and `required_account_generation`; missing or malformed values fail fast.
- `hydrate_and_filter_vector_hits(...)` now rejects candidates missing mandatory vector metadata (`uid`, `account_generation`, `item_revision`, `source_commit_id`, `content_hash`) and rejects stale projection/account-generation/item-revision/source/content mismatches before returning results.
- Product vector route, Omi chat vector adapter, MCP vector adapter, and developer vector adapter deny with `missing_vector_projection_commit_id` before vector/memory reads when the rollout lacks the fence.
- Archive remains default-unavailable and no read surface was broadened.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED vector-service tests (`2 failed, 2 passed`), focused fixture failure while adapting mandatory fences (`5 failed, 68 passed`), GREEN focused suite (`76 passed`), full `pytest tests/unit/test_v17_*.py -q` (`206 passed, 1 warning`), and formatting (`14 files left unchanged`).

This closes only the first narrow P0-4 freshness/account-generation seam. Remaining P0-4/P0 work:

- Implement/validate real vector purge/repair worker behavior and stale-ID deletion against Pinecone/Firestore.
- Prove shared `ns2` isolation.
- Add app/key/scope third-party authorization and vector overfetch/refill/budgets/telemetry.
- Produce real cloud/Pinecone/Firestore/benchmark evidence before production read/vector cutover.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 stale vector repair/purge candidate seam

Continued Oracle P0-4 with a narrow fake-injectable repair/purge seam for hydration-rejected vector IDs, without claiming real Pinecone/Firestore deletion or changing the production rollout verdict:

- Added `VectorRepairPurgeReason` taxonomy and `SearchVectorHit.vector_id` plumbing so Pinecone match IDs can be carried through candidate hydration.
- `hydrate_and_filter_vector_hits(...)` now returns `repair_purge_candidates` for stale-ID conditions found after authoritative hydration: missing authoritative item, stale projection commit, missing vector freshness metadata, stale account generation, cross-user metadata, stale item revision, stale source commit, stale content hash, and stale vector timestamp.
- `fetch_default_v17_vector_memory_search(...)` accepts an optional fake-injectable `repair_purge_callback` and dispatches one batch after hydration only when repair/purge candidates exist. Returned memory results are still only hydrated valid `memory_items`; access-policy rejects such as stale Short-term or Archive default denial are not purge candidates.
- Missing freshness-fence paths still fail before vector query, `memory_items` reads, or repair callbacks.
- This is an outbox/worker contract seam only. No real Pinecone delete, Firestore repair collection write, tombstone-precedence worker, shared-`ns2` proof, benchmark, or production approval is claimed.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED import failure for missing `VectorRepairPurgeReason`, GREEN vector-service seam tests (`6 passed`), focused V17 vector/caller regression (`78 passed`), full `pytest tests/unit/test_v17_*.py -q` (`208 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the fake-injectable stale-ID repair/purge candidate dispatch seam. Remaining P0-4/P0 work:

- Wire candidates to a durable Firestore outbox and real Pinecone delete/repair worker with idempotency, tombstone precedence, and retry/error telemetry.
- Prove actual stale IDs are deleted or repaired against Pinecone/Firestore/emulator or cloud fixtures, including missing authoritative items, stale projection/revision/content/source, old account generation, and duplicate physical vector IDs.
- Prove shared `ns2` isolation; add vector overfetch/refill/budgets/central telemetry and app/key/scope authorization.
- Produce real cloud/Pinecone/Firestore/benchmark evidence before production read/vector cutover.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 durable fake-injectable repair/purge outbox record seam

Continued Oracle P0-4 by transforming hydration repair/purge candidates into deterministic durable outbox records, without calling Pinecone or changing the production rollout verdict:

- Added `backend/database/v17_vector_repair_outbox.py` with `build_v17_vector_repair_purge_outbox_records(...)` and fake-friendly `write_v17_vector_repair_purge_outbox_records(...)`.
- Outbox records target `users/{uid}/memory_outbox/{record_id}` with `event_type="vector_repair_purge"`, `status="pending"`, `attempt_count=0`, and `last_error=None`.
- `record_id` / `idempotency_key` is deterministic from `uid`, `vector_id`, `memory_id`, `reason`, `required_projection_commit_id`, and `required_account_generation` so retrying the same stale-vector observation is idempotent.
- Records carry observed/authoritative account generation, item revision, source commit, content hash, and projection commit fields for a later worker to decide delete-vs-repair under tombstone precedence.
- `fetch_default_v17_vector_memory_search(...)` now builds outbox records after authoritative hydration and calls an injected `repair_purge_outbox_writer` exactly once only when records exist. Missing/no candidates writes nothing.
- Missing freshness-fence paths still fail before vector query, `memory_items` reads, candidate callbacks, or outbox writer calls.
- Access-policy rejects remain non-candidates; returned results remain hydrated valid `memory_items`; Archive remains default-unavailable.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing outbox module (`ModuleNotFoundError`), GREEN vector-service tests (`8 passed`), focused V17 vector/caller regression (`80 passed`), full `pytest tests/unit/test_v17_*.py -q` (`210 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the durable fake-injectable outbox record seam. Remaining P0-4/P0 work:

- Wire the injected writer only after Firestore emulator/cloud validation of `users/{uid}/memory_outbox/{record_id}` semantics.
- Implement a real idempotent Pinecone delete/repair worker with tombstone precedence, duplicate stale-ID proof, retries, dead-lettering, and low-cardinality error telemetry.
- Prove shared `ns2` isolation; add vector overfetch/refill/budgets/central telemetry and app/key/scope authorization.
- Produce real cloud/Pinecone/Firestore/benchmark evidence before production read/vector cutover.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 server-flagged repair/purge outbox writer wiring seam

Continued Oracle P0-4 with a narrow fake-backed Firestore persistence and route-wiring seam, without changing the production rollout verdict:

- Validated `write_v17_vector_repair_purge_outbox_records(...)` against a fake Firestore document seam: repeated writes set the same stable `users/{uid}/memory_outbox/{record_id}` document with the same `record_id`/`idempotency_key`.
- Added a server-owned persisted control bit, `users/{uid}/memory_control/state.vector_repair_outbox_enabled`, parsed as boolean-true only. Missing, false, or malformed values do not enable persistence.
- Wired only the product `/v17/memory/vector/search` surface to pass the real Firestore outbox writer into `fetch_default_v17_vector_memory_search(...)`, and only when that server flag is true.
- Disabled/no-flag paths still build response outbox records for observability but do not persist `users/{uid}/memory_outbox/*`; enabled paths persist after vector query and authoritative hydration only when stale-vector records exist.
- Missing global/per-user rollout gates and missing vector freshness fences still fail before vector query, `memory_items` reads, callbacks, or outbox writes.
- Returned memory results remain hydrated valid `memory_items`; access-policy rejects remain non-outbox candidates; Archive remains default-unavailable.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED flag/wiring tests (`2 failed, 23 passed` with missing `vector_repair_outbox_enabled`), GREEN focused tests (`25 passed`), focused V17 vector/caller regression (`83 passed`), full `pytest tests/unit/test_v17_*.py -q` (`213 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the fake-backed/server-flagged writer wiring seam for one product vector surface. Remaining P0-4/P0 work:

- Run real Firestore emulator/cloud validation for `users/{uid}/memory_outbox/{record_id}` semantics, IAM/rules assumptions, and write failure behavior.
- Implement the real idempotent Pinecone delete/repair worker with tombstone precedence, duplicate stale-ID proof, retries, dead-lettering, and low-cardinality error telemetry.
- Prove shared `ns2` isolation; add vector overfetch/refill/budgets/central telemetry and app/key/scope authorization.
- Produce real cloud/Pinecone/Firestore/benchmark evidence before production read/vector cutover.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 Firestore emulator validation gate for vector repair outbox

Continued Oracle P0-4 by adding and running a local Firebase emulator validation gate for V17 vector repair outbox persistence, without changing the production rollout verdict:

- Added `backend/scripts/v17_vector_repair_outbox_emulator_test.py` and `npm run test:v17-vector-repair-outbox:emulator`.
- The emulator harness uses the real Python Firestore client against `FIRESTORE_EMULATOR_HOST`, builds a deterministic `vector_repair_purge` outbox record, writes it twice through `write_v17_vector_repair_purge_outbox_records(...)`, and verifies the stable `users/{uid}/memory_outbox/{record_id}` document with unchanged `record_id`/`idempotency_key`.
- The harness verifies the initial retry contract (`status="pending"`, `attempt_count=0`, `last_error=None`) and proves writer failure is explicit by asserting a failing document `.set(...)` exception propagates.
- Added `npm run test:v17-vector-repair-outbox-rules:emulator` as the explicit rules-side companion command for the existing Security Rules emulator harness, which denies signed-in client direct read/create/update/delete on `memory_outbox` and other protected V17 collections. Backend/Admin context remains required; direct client writes are not assumed.
- Updated `docs/epics/v17_firestore_iam_deployment.md` with exact commands, prerequisites, pass/fail criteria, IAM/rules assumptions, non-claims, and remaining worker/Pinecone/shared-namespace gates.
- This is local emulator evidence only. It is **not** production cloud IAM validation, not deployed Security Rules validation, not a Pinecone delete/repair worker, not tombstone precedence proof, not shared-`ns2` proof, and not production approval.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED harness test (`1 failed`), GREEN harness test (`1 passed`), real Firestore emulator outbox persistence command exit 0 with idempotent path `users/v17-vector-repair-outbox-emulator-user/memory_outbox/v17vrp_a9f8abf2b6c7f8409d23f3bc63de76cf`, real rules emulator command exit 0 with client-denial PASS, plus focused/regression/async outputs from this commit.

This closes only the local emulator validation subpoint for outbox persistence semantics and client-rule denial. Remaining P0-4/P0 work:

- Validate production cloud IAM/service-account bindings and deployed Security Rules against the real Firebase project before rollout.
- Implement the real idempotent Pinecone delete/repair worker with tombstone precedence, duplicate stale-ID proof, retries, dead-lettering, and low-cardinality error telemetry.
- Prove shared `ns2` isolation; add vector overfetch/refill/budgets/central telemetry and app/key/scope authorization.
- Produce real cloud/Pinecone/Firestore/benchmark evidence before production read/vector cutover.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 first idempotent vector repair/purge outbox worker seam

Continued Oracle P0-4 with the first narrow pure worker seam for prepared `vector_repair_purge` outbox records, without changing the production rollout verdict:

- Added `backend/database/v17_vector_repair_outbox_worker.py` with `process_v17_vector_repair_purge_outbox_records(...)`.
- The seam is fake-injectable: it accepts an authoritative item loader, vector deleter, vector repairer, and outbox updater, and does not import/call Pinecone directly.
- Idempotency semantics are explicit for this seam: terminal/leased statuses (`completed`, `dead_letter`, `in_progress`) and duplicate same-batch `idempotency_key` records are skipped before side effects; pending records are patched to `in_progress` before the injected vector action and `completed` after success.
- Tombstone/delete precedence is explicit: missing authoritative items, `reason=missing_authoritative_item`, deleted/tombstoned/purged authoritative items, and missing/tombstoned/purged source state choose vector delete; live authoritative stale projection/revision/source/content records choose repair.
- Failure handling is deterministic: injected delete/repair exceptions are converted to retry/dead-letter patches with incremented `attempt_count`, `last_error`, and `status=pending|dead_letter` based on `max_attempts`.
- Added `backend/tests/unit/test_v17_vector_repair_outbox_worker.py` covering missing item delete, live item repair, tombstone precedence delete, terminal/in-progress/duplicate idempotency skips, and retry/dead-letter failure handling; added the test file to `backend/test.sh`.
- This remains a worker seam only. It does **not** start production background execution, claim real Pinecone delete/upsert, prove duplicate physical stale-ID removal in Pinecone, validate production cloud IAM/deployed rules, prove shared `ns2`, or approve rollout.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing worker module (`ModuleNotFoundError`), GREEN worker tests (`5 passed`), focused vector/outbox/product regression (`31 passed`), full `pytest tests/unit/test_v17_*.py -q` (`219 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the first fake-injectable worker decision/idempotency/retry seam. Remaining P0-4/P0 work:

- Validate production cloud IAM/service-account bindings and deployed Security Rules against the real Firebase project before rollout.
- Add a real leased Firestore reader/ack writer for `users/{uid}/memory_outbox/*` and Cloud Run/Tasks scheduling semantics.
- Implement injected real Pinecone delete/upsert repair functions and prove duplicate stale-ID removal with Pinecone data, including tombstoned/deleted/missing authoritative items.
- Add central low-cardinality telemetry/alerts for worker attempts, action counts, retry/dead-letter reasons, latency, and stale-vector rates.
- Prove shared `ns2` isolation; add overfetch/refill/budgets, app/key/scope auth, and real benchmark/cloud evidence.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 leased Firestore reader/ack writer seam for vector repair outbox

Continued Oracle P0-4 with a narrow fake-backed Firestore lease/read/ack seam for prepared `vector_repair_purge` records, without changing the production rollout verdict:

- Added `lease_v17_vector_repair_purge_outbox_records(...)` in `backend/database/v17_vector_repair_outbox_worker.py` for `users/{uid}/memory_outbox/*` records.
- The reader selects only `event_type="vector_repair_purge"`, `status="pending"`, and `available_at <= now` records under the target user outbox, then re-reads each document before claiming it.
- Claiming marks the stored document `in_progress` with `lease_owner`, `leased_at`, `locked_at`, `lease_expires_at`, and `updated_at`; returned records preserve the original pending status so they can be passed to the existing pure processor.
- Added `ack_v17_vector_repair_purge_outbox_record(...)` to apply the worker's ack/retry/dead-letter patches (`in_progress`, `completed`, `pending`, `dead_letter`, `attempt_count`, `last_error`, `action`) to the deterministic outbox document path.
- Tests prove pending/available selection, terminal/in-progress/future/wrong-event skip behavior, ack path updates, duplicate lease prevention when paired with the existing idempotent worker seam, and ack write-failure propagation.
- The seam documents its fake-backed concurrency contract. It is **not** a production scheduler and does **not** claim real Firestore transaction contention validation, Cloud Run/Tasks leasing, production IAM/deployed rules validation, real Pinecone delete/upsert, duplicate physical stale-ID proof, shared `ns2` isolation, central telemetry, benchmark evidence, or production approval.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing lease/ack imports (`ImportError`), GREEN worker seam tests (`8 passed`), focused vector/outbox/product regression (`34 passed`), full `pytest tests/unit/test_v17_*.py -q` (`222 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the narrow fake-backed Firestore reader/ack writer seam. Remaining P0-4/P0 work:

- Validate the lease/ack contract under real Firestore emulator transaction contention and then production cloud IAM/deployed Security Rules before rollout.
- Add Cloud Run/Tasks or another explicit scheduler/lease-owner execution contract; do not start background production processing from this seam alone.
- Implement injected real Pinecone delete/upsert repair functions and prove duplicate stale-ID removal with Pinecone data, including tombstoned/deleted/missing authoritative items.
- Add central low-cardinality telemetry/alerts for lease attempts, action counts, retry/dead-letter reasons, latency, stale-vector rates, and ack failures.
- Prove shared `ns2` isolation; add overfetch/refill/budgets, app/key/scope auth, and real benchmark/cloud evidence.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 Firestore emulator transaction contention validation for vector repair outbox lease

Continued Oracle P0-4 by hardening the leased Firestore reader seam and validating the claim contract under real local Firestore emulator contention, without changing the production rollout verdict:

- Updated `lease_v17_vector_repair_purge_outbox_records(...)` so each pending document claim uses a Firestore transaction when the injected client supports `transaction()`: the claim re-reads the document inside the transaction, verifies it is still `event_type="vector_repair_purge"`, `status="pending"`, and due, then updates the same document to `in_progress` with lease metadata in the transaction.
- Kept the existing fake/no-transaction fallback for unit seams, but documented and tested the transactional path separately so production-capable clients do not depend only on in-memory fake behavior.
- Added `backend/scripts/v17_vector_repair_outbox_lease_emulator_test.py` and `npm run test:v17-vector-repair-outbox-lease:emulator`, which starts the Firebase Firestore emulator, writes one deterministic pending `users/{uid}/memory_outbox/{record_id}` record, launches eight competing worker lease attempts, and asserts exactly one returned claim and one stored `in_progress` lease owner/timestamp set.
- The ack writer remains explicit and failure-propagating; no Pinecone delete/upsert or production scheduler was added.
- This is local emulator evidence only. It does **not** validate production cloud IAM/service-account bindings, deployed Security Rules, Cloud Run/Tasks scheduling, real Pinecone deletion/repair, duplicate physical stale-ID removal, shared `ns2` isolation, central telemetry/alerts, benchmarks, or production approval.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED transactional unit expectation (`1 failed, 8 passed`), RED missing emulator lease harness/package script (`2 failed`), GREEN focused outbox tests (`11 passed`), real Firestore emulator contention command (`npm run test:v17-vector-repair-outbox-lease:emulator` → PASS, `claimed=1`), focused vector/outbox/product regression (`36 passed`), full `pytest tests/unit/test_v17_*.py -q` (`224 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the local Firestore emulator transaction-contention validation subpoint for the lease seam. Remaining P0-4/P0 work:

- Validate production cloud IAM/service-account bindings and deployed Security Rules against the real Firebase project before rollout.
- Add Cloud Run/Tasks or another explicit scheduler/lease-owner execution contract; do not start background production processing from this seam alone.
- Implement injected real Pinecone delete/upsert repair functions and prove duplicate stale-ID removal with Pinecone data, including tombstoned/deleted/missing authoritative items.
- Add central low-cardinality telemetry/alerts for lease attempts, action counts, retry/dead-letter reasons, latency, stale-vector rates, and ack failures.
- Prove shared `ns2` isolation; add overfetch/refill/budgets, app/key/scope auth, and real benchmark/cloud evidence.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 fake-first Pinecone delete/repair adapter seam for vector repair outbox actions

Continued Oracle P0-4 with a narrow Pinecone-compatible adapter seam for the existing fake-injectable outbox worker, without changing the production rollout verdict:

- Added `backend/database/v17_vector_repair_pinecone_adapter.py` with worker-compatible `make_v17_pinecone_vector_deleter(...)` and `make_v17_pinecone_vector_repairer(...)` factories.
- The delete adapter calls only an injected Pinecone-shaped `delete_vectors(ids=[vector_id], namespace="ns2")` function and returns deterministic action metadata. Unit tests use fakes only; no real Pinecone client is imported or called.
- The repair adapter calls injected `embed_text(content)` and `upsert_vectors(vectors=[...], namespace="ns2")` functions, builds the deterministic V17 vector id and V17 metadata from the live authoritative `V17MemoryItem` plus the outbox `required_projection_commit_id`, and raises `V17VectorRepairNotReady` before embedding/upsert if content, source commit, content hash, or required projection fence is missing.
- Namespace isolation is explicit at the seam (`V17_VECTOR_REPAIR_PINECONE_NAMESPACE = "ns2"`), matching the existing memory-vector namespace in `backend/database/vector_db.py`; real shared-`ns2` coexistence proof is still not claimed.
- Added tests covering delete namespace/id mapping, repair metadata/upsert mapping, not-ready repair with no side effects, injected Pinecone failure propagation through the worker retry path, and duplicate same-batch idempotency with at most one adapter side effect.
- This is still not production execution. It does **not** start Cloud Run/Tasks or a scheduler, validate production Firestore IAM/deployed rules, call real Pinecone, prove duplicate physical stale-ID removal, prove shared `ns2` isolation, add central telemetry/alerts, run benchmarks, or approve rollout.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing Pinecone adapter module (`ModuleNotFoundError`), GREEN worker/adapter tests (`13 passed`), focused vector/outbox/product regression (`40 passed`), full `pytest tests/unit/test_v17_*.py -q` (`228 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the fake-first Pinecone delete/upsert adapter mapping seam. Remaining P0-4/P0 work:

- Wire an explicit Cloud Run/Tasks or scheduler/lease-owner execution contract; do not start background production processing from this seam alone.
- Validate production cloud IAM/service-account bindings and deployed Security Rules against the real Firebase project before rollout.
- Run real Pinecone delete/upsert validation with duplicate stale physical IDs, tombstoned/deleted/missing authoritative items, failure/retry/dead-letter behavior, and shared-`ns2` legacy isolation evidence.
- Add central low-cardinality telemetry/alerts for adapter attempts, action counts, retry/dead-letter reasons, latency, stale-vector rates, and ack failures.
- Add overfetch/refill/budgets, app/key/scope auth, real benchmark/cloud evidence, and explicit production rollout gates.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 explicit scheduler/lease-owner worker tick contract

Continued Oracle P0-4 by adding the first explicit Cloud Run/Tasks-or-scheduler execution contract seam for V17 vector repair outbox processing, without registering a production scheduler or changing the production rollout verdict:

- Added `V17VectorRepairOutboxWorkerTickConfig` and `run_v17_vector_repair_outbox_worker_tick(...)` in `backend/database/v17_vector_repair_outbox_worker.py`.
- The tick contract is disabled/fail-closed by default (`enabled=false`) and requires server-owned config/lease owner identity before it leases anything.
- An enabled tick leases due pending `vector_repair_purge` records for one uid, processes them through the existing fake-injectable worker with injected authoritative item loader plus delete/repair adapter functions, and applies ack/retry/dead-letter patches through `ack_v17_vector_repair_purge_outbox_record(...)`.
- The seam returns deterministic summary counts (`leased_count`, `processed_count`, `skipped_count`, `failed_count`, `ack_failed_count`) plus actions/errors so a later Cloud Run/Tasks wrapper can emit central low-cardinality telemetry.
- Tests prove disabled config performs no lease or side effect, enabled fake ticks lease/process/ack delete and repair records, lease failures return deterministic errors before adapter calls, ack failures are counted, and duplicate same-batch idempotency still produces at most one adapter side effect.
- Updated `docs/epics/v17_firestore_iam_deployment.md` with the explicit proposed Cloud Run/Tasks contract, service identity/config/env vars, enablement flag, telemetry/alert needs, remaining IAM/Pinecone/shared-`ns2` gates, and non-claims.
- This still does **not** deploy Cloud Run/Tasks, create a scheduler, validate production Firestore IAM/deployed rules, call real Pinecone, prove duplicate physical stale-ID cleanup, prove shared `ns2` isolation, add central alerts, run benchmarks, or approve rollout.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing worker tick imports (`ImportError`), GREEN worker/adapter tests (`17 passed`), focused vector/outbox/product/docs regression (`45 passed`), full `pytest tests/unit/test_v17_*.py -q` (`232 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the explicit scheduler/lease-owner one-tick contract seam. Remaining P0-4/P0 work:

- Build/validate a real Cloud Run/Tasks wrapper and disabled-by-default deployment config, including OIDC/IAM proof and uid sharding/backlog ownership.
- Validate production cloud IAM/service-account bindings and deployed Security Rules against the real Firebase project before rollout.
- Run real Pinecone delete/upsert validation with duplicate stale physical IDs, tombstoned/deleted/missing authoritative items, retry/dead-letter behavior, and shared-`ns2` legacy isolation evidence.
- Add central low-cardinality telemetry/alerts for lease/adapter/ack attempts, action counts, retry/dead-letter reasons, latency, stale-vector rates, and backlog age.
- Add overfetch/refill/budgets, app/key/scope auth, real benchmark/cloud evidence, and explicit production rollout gates.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 disabled-by-default Cloud Run/Tasks wrapper contract

Continued Oracle P0-4 by adding a checked-in disabled-by-default wrapper contract around the existing one-tick seam, without deploying Cloud Run/Tasks, creating a scheduler, or changing the production rollout verdict:

- Added `backend/scripts/v17_vector_repair_outbox_worker_entrypoint.py`, a small fake-injectable entrypoint that reads explicit env/config and prints one deterministic JSON summary suitable for Cloud Run/Tasks logs.
- The wrapper fails closed/no-ops when `V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED` is absent, empty, or `false`; malformed enablement, missing enabled uid, missing enabled stable worker/lease-owner ID, or invalid numeric bounds exit nonzero before any tick/lease call.
- Enabled execution requires injected Firestore client, authoritative item loader, vector deleter, vector repairer, and invokes exactly one `run_v17_vector_repair_outbox_worker_tick(...)` for one explicit uid. There is no unbounded scan and no scheduler enqueue side effect.
- Added `backend/tests/unit/test_v17_vector_repair_outbox_worker_entrypoint.py` and registered it in `backend/test.sh`. Tests cover disabled no-op, malformed config denial, required uid/lease-owner denial, enabled fake tick summary, dependency/action failure summary, and source-level no scheduler enqueue side effects.
- Updated `docs/epics/v17_firestore_iam_deployment.md` with the proposed command, env vars, OIDC/IAM assumptions, uid-shard/backlog ownership rule, telemetry/alert needs, failure modes, and explicit non-claims.
- This is still a wrapper contract/readiness artifact, not production execution. It does **not** deploy Cloud Run/Tasks, create a Cloud Scheduler job, validate production Firestore IAM/deployed rules, call real Pinecone, prove duplicate physical stale-ID cleanup, prove shared `ns2` isolation, add central alerts, run benchmarks, or approve rollout.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing entrypoint import (`ImportError`), GREEN entrypoint tests (`6 passed`), disabled CLI JSON smoke output, focused vector/outbox/docs regression (`26 passed`), full `pytest tests/unit/test_v17_*.py -q` (`238 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the first disabled-by-default wrapper/config parser contract. Remaining P0-4/P0 work:

### 2026-06-19 — P0-4 production-safe dependency resolver behind disabled wrapper

Continued Oracle P0-4 by wiring a narrow production dependency resolver behind the disabled wrapper, without enabling production execution or changing the production rollout verdict:

- Added `V17VectorRepairOutboxProductionDependencies` and `build_v17_vector_repair_outbox_production_dependencies(...)` to `backend/scripts/v17_vector_repair_outbox_worker_entrypoint.py`.
- `main(...)` now parses wrapper config first; when disabled it prints the same no-op JSON without initializing Pinecone, the embedding provider, or the Firestore client singleton. Enabled mode invokes the resolver exactly once after explicit `uid`/`worker_id` config validation.
- Enabled dependency resolution fails deterministically before lease/tick when `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, or `OPENAI_API_KEY` is absent. It does not silently skip Pinecone/embedding work.
- When dependency env is present, the resolver lazily constructs Admin Firestore via `database._client.db`, an authoritative `users/{uid}/memory_items/{memory_id}` loader returning `V17MemoryItem`, and Pinecone `delete`/`upsert` repair adapters using `utils.llm.clients.embeddings.embed_query` with explicit namespace `ns2`.
- Tests use monkeypatch/fakes only; no real Pinecone, OpenAI, Firestore cloud, Cloud Run/Tasks, Scheduler, IAM, deployed rules, duplicate stale physical-ID cleanup, shared-`ns2` proof, central alerts, benchmarks, or production approval is claimed.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED dependency-factory tests (`4 failed, 6 passed`), GREEN entrypoint tests (`10 passed`), focused wrapper/outbox/doc regression (`30 passed`), disabled CLI smoke JSON, full `pytest tests/unit/test_v17_*.py -q` (`242 passed, 1 warning`), and async scan exit 0 with pre-existing findings only.

This closes only the narrow production dependency factory behind the disabled wrapper. Remaining P0-4/P0 work:

- Add real Cloud Run/Tasks/Scheduler deployment config and OIDC/IAM proof for the worker identity and trigger principal.
- Validate production Firestore IAM/service-account bindings and deployed Security Rules against the real Firebase project before rollout.
- Run real Pinecone delete/upsert validation with duplicate stale physical IDs, tombstoned/deleted/missing authoritative items, retry/dead-letter behavior, and shared-`ns2` legacy isolation evidence.
- Add central low-cardinality telemetry/alerts for lease/adapter/ack attempts, action counts, retry/dead-letter reasons, latency, stale-vector rates, and backlog age.
- Add overfetch/refill/budgets, app/key/scope auth, real benchmark/cloud evidence, and explicit production rollout gates.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 disabled Cloud Run/Tasks/Scheduler contract and OIDC/IAM proof artifact

Continued Oracle P0-4 by adding a checked-in disabled-by-default deployment/proof contract artifact, without applying cloud resources or changing the production rollout verdict:

- Added `docs/epics/v17_vector_repair_outbox_cloud_deployment_contract.yaml`, a static Cloud Run/Cloud Tasks/Cloud Scheduler contract with explicit command/image shape, env/secrets, dedicated worker/scheduler service accounts, OIDC `serviceAccountEmail`/`audience`, IAM proof targets, retry/backoff/dead-letter placeholders, server-owned uid shard parameterization, and pass/fail proof commands.
- The contract is intentionally disabled: Cloud Run env has `V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED="false"`, Cloud Scheduler is `state: PAUSED`, Cloud Run invoker IAM remains required, Cloud Tasks concurrency is one, and enablement requires later production gates plus an explicit patch to `V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=true`.
- Added `backend/tests/unit/test_v17_vector_repair_outbox_deployment_contract.py` and registered it in `backend/test.sh` to assert the static contract contains the required disabled/OIDC/IAM/retry/dead-letter fields and does not claim production IAM, deployed resources, or Pinecone deletion proof.
- Updated `docs/epics/v17_firestore_iam_deployment.md` to link the artifact and record the key readiness caveat: the current worker entrypoint is CLI one-tick code, so an HTTP shim (or a deliberate Cloud Run Job + OAuth trigger design) must exist before applying the HTTP Cloud Tasks/Scheduler shape.
- No Cloud Run service, Cloud Tasks queue, Cloud Scheduler job, IAM binding, production Firestore rules validation, Pinecone delete/upsert, shared-`ns2` proof, telemetry alert, benchmark, or production approval was created or claimed.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing contract artifact (`1 failed`), GREEN static contract test (`1 passed`), focused wrapper/outbox/doc regression, disabled CLI smoke JSON, full `pytest tests/unit/test_v17_*.py -q`, and async scan exit 0 with pre-existing findings only.

This closes only the static disabled deployment/proof contract artifact for Cloud Run/Tasks/Scheduler. Remaining P0-4/P0 work:

- Add the worker HTTP shim or switch to a Cloud Run Job trigger pattern and validate the selected trigger end-to-end.
- Run real OIDC/IAM proof commands from the artifact against the target project and attach exact output.
- Validate production Firestore IAM/service-account bindings and deployed Security Rules.
- Run real Pinecone duplicate stale physical-ID delete/repair/tombstone precedence validation and shared-`ns2` isolation proof.
- Add central retry/dead-letter/backlog telemetry/alerts, overfetch/refill/budgets, app/key/scope auth, benchmarks, and explicit rollout gates.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 disabled HTTP trigger shim for Cloud Run/Tasks OIDC

Continued Oracle P0-4 by resolving the prior CLI-vs-HTTP trigger-surface caveat with a minimal disabled-by-default ASGI shim, without deploying cloud resources or changing the production rollout verdict:

- Added `create_v17_vector_repair_outbox_worker_app(...)` and `run_v17_vector_repair_outbox_worker_http_tick(...)` in `backend/scripts/v17_vector_repair_outbox_worker_entrypoint.py`.
- The module-level `app` exposes `POST /v17-vector-repair-outbox-worker/tick` for a Cloud Run service command such as `uvicorn scripts.v17_vector_repair_outbox_worker_entrypoint:app --host 0.0.0.0 --port 8080`.
- The HTTP shim is fail-closed by default: absent/false `V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED` returns the deterministic no-op JSON summary and does not build Firestore/Pinecone/embedding dependencies or lease/process/ack records.
- Enabled HTTP execution still requires server-owned env config for explicit `V17_VECTOR_REPAIR_OUTBOX_UID` and stable `V17_VECTOR_REPAIR_OUTBOX_WORKER_ID`; there is no request-body uid and no unbounded scan.
- Authentication is deliberately documented as Cloud Run IAM (`roles/run.invoker`) plus Cloud Scheduler/Tasks OIDC `serviceAccountEmail`/`audience` at the platform layer; the app does not add a weak app-level bearer-token scheme.
- Updated the static deployment YAML and Firestore/IAM deployment doc to use the HTTP shim service command and to remove the prior “HTTP shim must exist” caveat. The artifact remains disabled (`V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=false`, Scheduler `PAUSED`).
- No Cloud Run service, Cloud Tasks queue, Cloud Scheduler job, IAM binding, production Firestore rules validation, Pinecone delete/upsert, shared-`ns2` proof, telemetry alert, benchmark, or production approval was created or claimed.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED HTTP shim tests (`5 failed, 10 passed` for missing `create_v17_vector_repair_outbox_worker_app` and Cloud Run IAM documentation), RED deployment contract test (`1 failed` for missing `uvicorn`/HTTP shim contract), GREEN focused trigger tests (`36 passed`), disabled CLI smoke JSON, full `pytest tests/unit/test_v17_*.py -q` (`248 passed, 1 warning`), and async scan exit 0 with pre-existing findings only.

This closes only the local executable trigger-surface mismatch. Remaining P0-4/P0 work:

- Run real OIDC/IAM proof commands from the artifact against the target project and attach exact output.
- Validate production Firestore IAM/service-account bindings and deployed Security Rules.
- Run real Pinecone duplicate stale physical-ID delete/repair/tombstone precedence validation and shared-`ns2` isolation proof.
- Add central retry/dead-letter/backlog telemetry/alerts, overfetch/refill/budgets, app/key/scope auth, benchmarks, and explicit rollout gates.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 read-only OIDC/IAM proof runner for disabled HTTP worker

Continued Oracle P0-4 by adding a safe read-only proof runner for the disabled Cloud Run HTTP shim, without claiming production cloud proof or changing the production rollout verdict:

- Added `backend/scripts/v17_vector_repair_outbox_oidc_iam_proof.py`, which inventories the exact OIDC/IAM proof commands by default and only executes read-only `gcloud` `describe` / `get-iam-policy` commands when `--execute` is explicitly passed.
- The runner covers the Cloud Run service description, Cloud Run IAM policy, Scheduler job description, Tasks queue description, project IAM policy, and worker/scheduler service-account IAM policies. It rejects non-allowlisted command verbs in-process.
- Pass/fail checks include disabled worker env (`V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=false`), worker service account, restricted ingress, invoker IAM required, no public Run invoker, scheduler `state=PAUSED`, Scheduler OIDC `serviceAccountEmail`/`audience`, POST method, queue single concurrency plus bounded retry, worker Firestore role (`roles/datastore.user` or narrower custom role), no owner/editor on the worker service account, and scheduler token-creator policy presence.
- Updated the Cloud Run/Tasks/Scheduler deployment YAML and Firestore/IAM deployment doc with the runner command, `--execute` command, prerequisites, pass/fail criteria, known blockers, and explicit non-claims.
- Attempted only safe local discovery/readiness: the runner printed `NOT_RUN` without project/region; `command -v gcloud` produced no output; `--execute` exited 2 with `NOT_RUN` prerequisites including missing project, missing region, and `gcloud CLI is not installed or not on PATH`. Therefore no production OIDC/IAM proof was run or claimed.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing proof-runner/static reference tests (`2 failed`), GREEN proof-runner test (`2 passed`), readiness command outputs (`NOT_RUN` and safe `--execute` prerequisite failure), focused vector/outbox/docs regression (`38 passed`), full V17 regression (`250 passed, 1 warning`), and async scan exit 0 with pre-existing findings only.

This closes only the readiness/proof-runner artifact for the Cloud Run OIDC/IAM slice. Remaining P0-4/P0 work:

- Run the proof runner with `--execute` against an authenticated target project and attach exact JSON output before unpausing Scheduler or enabling the worker.
- Validate production Firestore IAM and deployed Security Rules in the real Firebase project.
- Run real Pinecone duplicate stale physical-ID delete/repair/tombstone validation in `ns2` and prove shared-namespace isolation.
- Add central retry/dead-letter/backlog telemetry and alerts.
- Complete overfetch/refill/budgets, app/key/scope auth, benchmarks, and explicit rollout gates.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 Firestore IAM/deployed Security Rules proof-runner readiness artifact

Continued Oracle P0-4 by adding a safe production Firestore IAM/deployed Security Rules validation runner for the V17 vector repair outbox paths, without claiming real cloud proof or changing the production rollout verdict:

- Added `backend/scripts/v17_firestore_rules_iam_proof.py`, a safe-by-default runner that inventories production Firestore IAM and deployed Security Rules proof commands by default and only executes read-only `gcloud` / Firebase commands when `--execute` is explicitly passed.
- The runner covers `gcloud firestore databases describe`, project IAM, worker/backend service-account IAM policies, and deployed Firestore rules via `firebase firestore:rules:get`.
- Pass/fail criteria cover client denial on `users/{uid}/memory_outbox/{record_id}`, Admin worker service-account Firestore IAM, server-owned `users/{uid}/memory_control/state`, no client enablement of `vector_repair_outbox_enabled`, and no broad public IAM access.
- Static tests assert the runner contains the required outbox/control/gate proof targets and that generated commands do not contain mutating deployment/database/IAM operations.
- Attempted only safe local readiness: inventory mode printed JSON `status: NOT_RUN` with missing project; `command -v gcloud` and `command -v firebase` produced no output; `--execute` exited 2 with `status: NOT_RUN` prerequisites for missing project, missing `gcloud`, and missing `firebase`. Therefore no production Firestore IAM/deployed-rules proof was run or claimed.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing runner/doc tests (`2 failed`), GREEN static test (`2 passed`), readiness command outputs (`NOT_RUN` and safe `--execute` prerequisite failure), focused vector/outbox/docs regression (`40 passed`), full V17 regression (`252 passed, 1 warning`), and async scan exit 0 with pre-existing findings only.

This closes only the readiness/proof-runner artifact for the production Firestore IAM/deployed Security Rules validation slice. Remaining P0-4/P0 work:

- Run this Firestore proof runner with `--execute` against an authenticated target Firebase project and attach exact JSON output before enabling `vector_repair_outbox_enabled` or the worker.
- Run the OIDC/IAM proof runner with `--execute` against the target project and attach exact JSON output before unpausing Scheduler or enabling the worker.
- Run real Pinecone duplicate stale physical-ID delete/repair/tombstone validation in `ns2` and prove shared-namespace isolation.
- Add central retry/dead-letter/backlog telemetry and alerts.
- Complete overfetch/refill/budgets, app/key/scope auth, benchmarks, and explicit rollout gates.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 Pinecone repair/shared-ns2 validation readiness artifact

Continued Oracle P0-4 by adding a safe real-Pinecone validation readiness runner/artifact for the duplicate stale physical-ID/tombstone/repair/retry/shared-`ns2` proof that Oracle still requires, without claiming real Pinecone evidence or changing the production rollout verdict:

- Added `backend/scripts/v17_pinecone_repair_validation_readiness.py`, a safe-by-default runner that emits `status=NOT_RUN` readiness JSON in default mode and performs no Pinecone delete/upsert/query mutation.
- The readiness artifact records exact prerequisites and pass/fail criteria for duplicate stale physical IDs, tombstone/delete precedence for missing/deleted/tombstoned/purged authoritative items, live stale item repair/upsert, retry/dead-letter behavior, shared `ns2` read-only isolation, and legacy vectors not touched.
- Execute mode is gated by explicit credentials/config (`PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `PINECONE_INDEX_HOST`) plus `--allow-throwaway-mutation`, a non-`ns2` `--test-namespace`, a long `v17-proof-...` `--throwaway-prefix`, exact `--confirm-throwaway-prefix`, and optional `--shared-ns2-readonly`; the runner refuses shared `ns2` mutation.
- Static tests assert the safety gates and ensure no broad delete/update command terms are present; `backend/test.sh` now includes the test file.
- Local readiness runs printed `NOT_RUN` with missing Pinecone prerequisites; `--execute` also reported missing explicit mutation/namespace/prefix gates. Therefore no real Pinecone validation, no deletion/upsert, no tombstone precedence proof, no retry/dead-letter proof, and no shared `ns2` isolation proof was run or claimed.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing runner/doc tests (`3 failed`), GREEN static test (`3 passed`), readiness command outputs (`NOT_RUN` and safe `--execute` prerequisite failure), focused vector/outbox/docs regression, full V17 regression, and async scan exit 0 with pre-existing findings only.

This closes only the Pinecone validation readiness/non-claim artifact. Remaining P0-4/P0 work:

- Implement/run the real throwaway Pinecone fixture validation with exact PASS/FAIL output for duplicate stale physical IDs, delete/repair/tombstone precedence, retry/dead-letter, and post-run absence of prefix-scoped stale vectors.
- Produce read-only shared `ns2` coexistence evidence proving legacy queries exclude V17 schema records and baseline legacy recall remains intact, or choose a separate namespace/filter before production inserts.
- Run the OIDC/IAM and Firestore IAM/deployed-rules proof runners against target cloud projects and attach exact output.
- Add central retry/dead-letter/backlog telemetry and alerts, overfetch/refill/budgets, app/key/scope auth, benchmarks, and explicit rollout gates.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-4 central retry/dead-letter/backlog telemetry seam

Continued Oracle P0-4 by adding a fake-injectable low-cardinality telemetry and alert contract for the V17 vector repair outbox worker, without claiming production metrics wiring or changing the production rollout verdict:

- Added `backend/database/v17_vector_repair_outbox_telemetry.py` with `V17VectorRepairOutboxTelemetryConfig` and `emit_v17_vector_repair_outbox_worker_telemetry(...)`.
- The seam converts deterministic worker tick summaries plus optional backlog/duration inputs into central-emitter-ready metric/event payloads for leased/processed/skipped/failed records, delete/repair actions, retry failures, dead letters, ack failures, pending/dead-letter backlog counts, oldest pending age, and tick duration.
- Labels are bounded to `worker_component`, `status`, `action`, `reason`, and `event_type`; uid, worker id, vector id, memory id, record id, idempotency key, and raw error text are excluded from metric/event labels.
- `run_v17_vector_repair_outbox_worker_tick(...)` now accepts an optional injected telemetry emitter/config/backlog/duration and records telemetry emission failures under `summary["telemetry"]` without masking lease/process/ack cleanup results.
- Updated the Cloud Run/Tasks/Scheduler contract and Firestore/IAM deployment doc with metric names, allowed/forbidden labels, alert thresholds, pass/fail criteria, and explicit non-claims.
- This is still a seam only. It does **not** wire Prometheus/OpenTelemetry/Cloud Monitoring, create dashboards or alert policies, run production worker telemetry, validate OIDC/IAM/deployed rules, call Pinecone, prove shared `ns2`, run benchmarks, or approve rollout.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing telemetry module (`ModuleNotFoundError`), GREEN telemetry tests (`4 passed`), focused vector/outbox/doc regression, full V17 regression, and async scan exit 0 with pre-existing findings only.

This closes only the central telemetry payload/emitter seam. Remaining P0-4/P0 work:

- Wire the seam to the production metrics/log backend and create dashboard/alert policies with exact output before enabling the worker.
- Run OIDC/IAM and Firestore IAM/deployed-rules proof runners against target cloud projects and attach exact JSON output.
- Run real Pinecone duplicate stale physical-ID delete/repair/tombstone validation in `ns2` and prove shared-namespace isolation.
- Complete overfetch/refill/budgets, app/key/scope auth, benchmarks, and explicit rollout gates.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1 shared V17 product authorization decision seam

Returned from the locally exhausted P0-4 seam work to Oracle P0-1 and added the first shared product-route authorization seam, without changing the production rollout verdict:

- Added `backend/utils/memory/v17_product_authorization.py` with `V17ProductAuthorizationContext`, `V17ProductAuthorizationDecision`, and `authorize_v17_product_memory_route(...)`.
- The seam is pure/fake-injectable and carries `uid`, `consumer`, `surface`, optional `app_id`/`key_id`/`scopes`, explicit Archive request intent, the global read gate, per-user rollout/default grant state, persisted Archive capability, and deterministic deny reasons.
- The decision checks the global read gate before per-user rollout reads and denies missing/malformed/disabled/no-grant control states before any vector query or `users/{uid}/memory_items` access.
- Default product authorization always builds an Omi-chat policy with `archive_capability=false`, even when a persisted Archive capability exists; persisted capability alone does not make Archive default-visible.
- Archive authorization requires both `explicit_archive_request=true` and persisted server-owned Archive capability; explicit request alone is denied and persisted capability without explicit request is denied before per-user rollout/item reads.
- Wired product `/v17/memory/search`, `/v17/memory/vector/search`, and `/v17/memory/archive/search` through the shared seam before memory/vector reads while preserving existing default Archive-unavailable behavior.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED import failure for missing `utils.memory.v17_product_authorization`, GREEN seam tests (`5 passed`), focused product/default rollout regression (`34 passed`), full `pytest tests/unit/test_v17_*.py -q` (`264 passed, 1 warning`), and async scan exit 0 with pre-existing findings only.

This addresses the narrow Oracle P0-1 subpoint that product default/vector/Archive routes share a server-side authorization decision before `memory_items` access. Remaining P0-1/P0-6/P0 work:

- Persist and enforce app/key/scope-specific grants for MCP/developer/third-party memory access; this seam only carries the context and does not yet implement per-key grant storage.
- Add real FastAPI dependency/scope tests for product and external surfaces.
- Continue P0-7 overfetch/refill/budget work and real cloud/Pinecone/Firestore/benchmark evidence.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 app/key/scope V17 memory grant contract seam

Continued Oracle P0-1/P0-6 with the first fake-injectable app/key/scope grant contract for external V17 memory access, without wiring production route behavior or changing the production rollout verdict:

- Extended `backend/utils/memory/v17_product_authorization.py` with `V17MemoryGrantOperation`, `V17AppKeyScopeGrantDecision`, and `authorize_v17_app_key_scope_memory_grant(...)`.
- The contract models `consumer`/surface, `app_id`, `key_id`, authenticated scopes, required memory operation (`default_read`, `archive_read`, `write`), a persisted per-consumer/app/key grant shape, and deterministic fail-closed denial reasons.
- External consumers (`developer_api`, `mcp`, `third_party`) require both an authenticated scope (`memories.read`, `memories.archive.read`, or `memories.write`) and a matching persisted grant at `grants.<consumer>.apps.<app_id>.keys.<key_id>` with boolean `enabled`, operation flag, and scope list. Request/auth scopes alone cannot self-grant V17 memory access.
- First-party `omi_chat` remains on the existing rollout/default-grant product authorization path and is not required to have an app/key grant in this seam.
- Archive is not default-visible: default read grants build policies with `archive_capability=false`; Archive read requires the stronger `memories.archive.read` scope plus `archive_read=true` and still remains subject to the existing explicit Archive request and persisted Archive capability when composed with the product route seam.
- Inspected current route/auth inventory: developer keys carry stored `scopes` but only return uid from route dependencies; MCP REST/SSE API key models currently do not persist scopes; MCP SSE advertises OAuth `memories.read`/`memories.write`; product `/v17` routes are first-party `omi_chat`. Therefore this slice is a contract/helper plus tests, not route enforcement for MCP/developer yet.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing grant-operation import, GREEN grant/product authorization tests (`11 passed`), focused product/default rollout regression (`40 passed`), full `pytest tests/unit/test_v17_*.py -q` (`270 passed, 1 warning`), and async scan exit 0 with pre-existing findings only.

This addresses only the first contract/helper subpoint for Oracle P0-1/P0-6 app/key/scope authorization. Remaining work:

- Persist a server-owned per-app/per-key grant document/field, with emulator/cloud IAM/rules proof that clients cannot self-grant.
- Carry key id/app id/scopes through developer and MCP REST/SSE auth dependencies, including MCP key scope storage or OAuth token introspection, then compose this seam before V17 memory reads/writes.
- Add route-level tests for MCP REST, MCP streamable HTTP/SSE tools, developer default/vector/list, and third-party app integrations.
- Keep Archive unavailable by default and require explicit Archive query plus persisted Archive capability in addition to app/key scope grants.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 server-owned app/key grant storage/read helper and local rules proof

Continued Oracle P0-1/P0-6 by adding the first server-owned persisted per-app/per-key grant storage/read seam and local client self-grant denial proof, without route enforcement or changing the production rollout verdict:

- Added `backend/database/v17_app_key_memory_grants.py` with canonical path constants for `users/{uid}/memory_control/v17_app_key_memory_grants`, a fake-injectable `read_v17_app_key_memory_grants_state(uid, db_client)`, and a pure contract-shape builder for admin/test tooling.
- The persisted document intentionally stores the exact nested authorization shape consumed by `authorize_v17_app_key_scope_memory_grant(...)`: `grants.<consumer>.apps.<app_id>.keys.<key_id>`.
- Missing documents return absent state with `missing_v17_app_key_memory_grants_state`; malformed top-level state returns `malformed_v17_app_key_memory_grants_state` and then fails closed through the grant authorization helper.
- Valid grant state feeds the existing app/key/scope authorization helper for default read while keeping `archive_capability=false`; Archive grants only produce Archive capability through the explicit `ARCHIVE_READ` operation path and do not make Archive default-visible.
- Extended the local Firestore rules emulator harness to assert that a signed-in client cannot read/create/update/delete `users/v17-emulator-user/memory_control/v17_app_key_memory_grants` with an attempted `grants.developer_api.apps.client-app.keys.client-key` self-grant. The local emulator proof passed.
- Added `docs/epics/v17_app_key_memory_grants_readiness.md` with path/schema, conversion rules, emulator command, route dependency blockers, and explicit non-claims.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing storage module, RED emulator harness static test for missing self-grant denial target, GREEN storage/static tests, local emulator PASS, focused V17 regression, full V17 regression, and async scan exit 0 with pre-existing findings only.

This closes only the storage/read helper plus local rules-emulator denial subpoint. Remaining P0-1/P0-6 work:

- Wire developer/MCP/third-party route dependencies to carry authenticated `app_id`, `key_id`, and verified scopes into this storage+authorization seam before any V17 read/write.
- Persist MCP key scopes / OAuth token scope introspection and add route-level FastAPI tests for REST and streamable HTTP/SSE.
- Run deployed Firestore rules/IAM proof against a real target project before claiming cloud readiness.
- Keep Archive unavailable by default and require explicit Archive query plus persisted Archive capability in addition to app/key scope grants.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 Developer API app/key/scope default-read composition seam

Continued Oracle P0-1/P0-6 by carrying authenticated Developer API key context into the stored app/key grant authorization seam for one narrow V17 read path, without changing the production rollout verdict:

- Extended Developer API key lookup/cache/auth context to carry `uid`, stable `app_id`, `key_id`, and verified scopes while preserving existing uid-only dependencies that return `auth.uid`.
- Added `get_developer_v17_default_memory_read_context(...)` to translate verified Developer API scopes (`memories:read`, `memories:write`) into the V17 app/key grant scope vocabulary (`memories.read`, `memories.write`) and build `V17ProductAuthorizationContext` for `consumer='developer_api'` / `surface='developer_default_memory_read'`.
- Added `authorize_v17_external_default_memory_read(...)`, which reads `users/{uid}/memory_control/v17_app_key_memory_grants` and composes it with `authorize_v17_app_key_scope_memory_grant(..., operation=DEFAULT_READ)`.
- Wired Developer API default memory list (`GET /v1/dev/user/memories` without category filters) to require that composition before V17 default-list reads. Missing app/key identity, missing/wrong scope, missing/malformed grant state, or missing persisted default-read grant returns 403 before V17 `memory_items` access.
- Allowed default-read policies keep `archive_capability=false`; Archive remains unavailable by default and no Archive path was exposed.

This closes only the first Developer API default-list composition subpoint. Remaining P0-1/P0-6 work:

- Apply the same app/key/scope grant composition to Developer API vector search before V17 vector reads.
- MCP REST/SSE still need persisted key scopes or OAuth token introspection plus route execution context carrying app/key/scope identity.
- Add real FastAPI dependency tests once local route-test dependencies are available; the current dependency coverage is static plus unit seam tests because this local environment still lacks `fastapi`.
- Run deployed Firestore rules/IAM proof against a real target project before claiming cloud readiness.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 Developer API vector app/key/scope composition seam

Continued Oracle P0-1/P0-6 by applying the same Developer API app/key/scope V17 grant composition to the concrete Developer API vector search route, without changing the production rollout verdict:

- Changed `GET /v1/dev/user/memories/vector/search` from the uid-only `get_uid_with_memories_read` dependency to `get_developer_v17_default_memory_read_context(...)`.
- The route now derives `uid` from the authenticated V17 product authorization context and calls `authorize_v17_external_default_memory_read(auth_context, db_client=db)` before reading developer rollout state or calling `search_v17_default_developer_memories_vector(...)`.
- Missing app/key identity, missing/wrong authenticated `memories.read` scope, missing/malformed persisted app/key grant state, disabled grant, missing persisted scope, or missing `default_read=true` returns 403 before any V17 vector query, repair/outbox callback, or `users/{uid}/memory_items` hydration.
- Valid app/key/scope grant continues to the existing V17 vector adapter and mandatory projection/account-generation fences. Default-read vector policy keeps `archive_capability=false`; no Archive vector path or default Archive exposure was added.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED route-order/static test (`1 failed, 19 passed`), GREEN focused tests (`35 passed`), full `pytest tests/unit/test_v17_*.py -q` (`280 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes the narrow Developer API vector-route P0-1/P0-6 app/key/scope composition subpoint. Remaining P0-1/P0-6 work:

- MCP REST/SSE still need persisted key scopes or OAuth token introspection plus route execution context carrying app/key/scope identity before V17 reads/tools execute.
- Deployed Firestore rules/IAM proof against a real target project remains not run.
- Add real FastAPI dependency tests once local route-test dependencies are available; current coverage remains static plus unit seam tests.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 MCP REST/SSE app/key/scope context readiness slice

Continued Oracle P0-1/P0-6 with the first MCP V17 authorization context/readiness helper, without route enforcement or changing the production rollout verdict:

- Added `McpV17VerifiedAuth`, `MCP_V17_DEFAULT_MEMORY_READ_SURFACE`, and `build_mcp_v17_default_memory_read_context(...)` in `backend/utils/mcp_memories.py`.
- The helper can carry `uid`, stable `app_id`, `key_id`, verified MCP scopes, `consumer='mcp'`, and `surface='mcp_default_memory_read'` into `V17ProductAuthorizationContext` for the existing `authorize_v17_external_default_memory_read(...)` composition seam.
- Existing uid-only MCP compatibility is preserved: REST routes still use `get_uid_from_mcp_api_key`, and streamable HTTP/SSE `execute_tool(...)` still receives `user_id` only.
- Missing app/key identity or missing verified `memories.read` scope fails closed through deterministic shared grant reasons before any future V17 read can proceed; valid injected MCP context plus stored `grants.mcp.apps.{app_id}.keys.{key_id}` default-read grant allows a default-read policy with `archive_capability=false`.
- Added `docs/epics/v17_mcp_app_key_scope_readiness.md`, listing MCP REST routes/tools, SSE tool security schemes/OAuth advertised scopes, current returned values, MCP key model/storage gaps, required future route execution context, safe composition point, RED tests needed, blockers, and explicit non-claims.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing MCP helper import, GREEN helper tests (`5 passed`), focused auth/MCP/product regression (`32 passed`), full `pytest tests/unit/test_v17_*.py -q` (`285 passed, 1 warning`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the first MCP context/readiness helper subpoint. Remaining P0-1/P0-6 work:

- Persist MCP key scopes or add OAuth token introspection so REST/SSE can supply real verified `app_id`, `key_id`, and scopes.
- Wire MCP REST `/v1/mcp/memories/search` and streamable HTTP/SSE `search_memories` to deny before V17 vector/default reads when app/key/scope grant composition fails.
- Decide whether `get_memories` becomes V17 default-list; if so, wire the same context before `memory_items` access.
- Deployed Firestore rules/IAM proof against a real target project remains not run.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 persisted MCP API-key auth-context contract

Continued Oracle P0-1/P0-6 by adding a backward-compatible persisted MCP API-key app/key/scope contract, without route enforcement or changing the production rollout verdict:

- Extended `mcp_api_keys/{key_id}` creation/model/cache/read shapes to carry optional server-owned `app_id`, `key_id`, and persisted `scopes`; new keys get stable `app_id='mcp-api'` and no implicit scopes.
- Added `database.mcp_api_key.get_user_and_scopes_by_api_key(...)` while preserving `get_user_id_by_api_key(...)` / `get_uid_from_mcp_api_key(...)` uid-only compatibility for existing MCP routes and old key docs/cache entries.
- Added `get_mcp_api_key_auth(...)` and `get_mcp_v17_default_memory_read_context(...)`; the V17 helper only builds a MCP `V17ProductAuthorizationContext` when persisted `memories.read`, `app_id`, and `key_id` are present. Old keys and keys without persisted scopes fail closed for V17 authorization rather than inheriting advertised MCP/OAuth scopes.
- Added unit coverage proving old docs still authenticate uid-only, missing app/scope context fails closed through the shared grant seam, persisted `memories.read` + app/key identity can compose with `grants.mcp.apps.mcp-api.keys.{key_id}` default-read grants, and default policies keep `archive_capability=false`.
- Updated `docs/epics/v17_mcp_app_key_scope_readiness.md` to reflect the storage/cache/dependency contract, migration/default behavior, OAuth-introspection gap, and remaining REST/SSE route wiring blockers.

This closes only the persisted MCP API-key auth-context contract subpoint. Remaining P0-1/P0-6 work:

- Add a server/admin migration or OAuth introspection path that actually persists/verifies MCP key scopes for production keys; do not self-grant from client-supplied/advertised scopes.
- Wire MCP REST `/v1/mcp/memories/search` and streamable HTTP/SSE `search_memories` to pass the verified context into `authorize_v17_external_default_memory_read(...)` and deny before V17 vector/default reads when composition fails.
- Carry verified auth context through SSE session/tool execution instead of only `user_id: str`.
- Deployed Firestore rules/IAM proof against a real target project remains not run.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 MCP REST memory search app/key/scope composition

Continued Oracle P0-1/P0-6 by wiring the concrete MCP REST memory-search route through the persisted MCP API-key app/key/scope context and server-owned app/key grant composition, without changing the production rollout verdict:

- Changed REST `GET /v1/mcp/memories/search` from uid-only `get_uid_from_mcp_api_key` to `get_mcp_v17_default_memory_read_context(...)`.
- The route now calls `authorize_v17_external_default_memory_read(auth_context, db_client=db)` before reading MCP rollout state, calling `search_v17_default_mcp_memories_vector(...)`, touching legacy vector fallback, or hydrating `users/{uid}/memory_items`.
- Missing app/key identity, missing/wrong persisted `memories.read` scope, missing/malformed `users/{uid}/memory_control/v17_app_key_memory_grants`, disabled grant, missing persisted scope, or missing `default_read=true` returns 403 before V17 reads/vector side effects.
- Valid persisted MCP key scope plus a matching stored `grants.mcp.apps.{app_id}.keys.{key_id}` default-read grant reaches the existing V17 MCP vector adapter; the resulting default-read policy keeps `archive_capability=false`.
- Existing uid-only MCP auth compatibility is preserved for untouched REST routes such as `/v1/mcp/profile` and `GET /v1/mcp/memories`; no Archive path/default exposure was added.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED route-order/static test (`1 failed, 14 passed`), GREEN route/static tests (`15 passed`), focused MCP/auth/product regression (`37 passed, 2 warnings`), full V17 regression (`290 passed, 3 warnings`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the narrow MCP REST `/v1/mcp/memories/search` P0-1/P0-6 app/key/scope composition subpoint. Remaining P0-1/P0-6 work:

- Wire streamable HTTP/SSE `search_memories` through verified app/key/scope context and stored grant composition before tool V17 reads.
- Add a production MCP key-scope migration or OAuth token introspection path; do not infer scopes from advertised MCP tool metadata.
- Deployed Firestore rules/IAM proof against a real target project remains not run.
- Add real FastAPI dependency tests once local route-test dependencies are available; current coverage remains static plus unit seam tests.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 MCP streamable HTTP/SSE search_memories app/key/scope composition

Continued Oracle P0-1/P0-6 by wiring streamable HTTP/SSE MCP `search_memories` tool execution through persisted MCP API-key app/key/scope context and server-owned app/key grant composition, without changing the production rollout verdict:

- Added `authenticate_api_key_auth_context(...)` in `backend/routers/mcp_sse.py`, so POST `/v1/mcp/sse` authenticates bearer tokens through persisted MCP API-key auth context (`uid`, `app_id`, `key_id`, persisted scopes) instead of uid-only auth for tool execution.
- `MCPSession`, `handle_mcp_message(...)`, and `execute_tool(...)` now thread an optional `V17ProductAuthorizationContext` into tool calls while keeping uid-only helper compatibility available for untouched/non-V17 direct paths.
- The `search_memories` tool calls `authorize_v17_external_default_memory_read(auth_context, db_client=db)` before reading MCP rollout state, calling `search_v17_default_mcp_memories_vector(...)`, touching legacy vector fallback, or hydrating `memory_items` candidates.
- Missing app/key identity, missing/wrong persisted `memories.read` scope, missing/malformed `users/{uid}/memory_control/v17_app_key_memory_grants`, disabled grant, missing persisted grant scope, or missing `default_read=true` fails closed with MCP tool error `-32009` before V17 reads/vector side effects.
- Valid persisted MCP key scope plus a matching stored `grants.mcp.apps.{app_id}.keys.{key_id}` default-read grant reaches the existing V17 MCP vector adapter; default-read policy keeps `archive_capability=false` and no Archive path/default exposure was added.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED SSE route/static tests (`2 failed, 14 passed`), GREEN route/static tests (`16 passed`), focused MCP/auth/product regression (`38 passed, 2 warnings`), full V17 regression (`291 passed, 3 warnings`), and async blocker scan exit 0 with pre-existing findings only.

This closes only the narrow streamable HTTP/SSE `search_memories` P0-1/P0-6 app/key/scope composition subpoint. Remaining P0-1/P0-6 work:

- Add a production MCP key-scope migration or OAuth token introspection path; do not infer scopes from advertised MCP tool metadata.
- Deployed Firestore rules/IAM proof against a real target project remains not run.
- Add real FastAPI dependency tests once local route-test dependencies are available; current coverage remains static plus unit seam tests.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 MCP API-key scope readiness runner / server-owned assignment contract

Continued Oracle P0-1/P0-6 by adding a production-safe MCP API-key scope migration/introspection readiness runner and explicit server-owned scope assignment contract, without changing the production rollout verdict:

- Added `backend/scripts/v17_mcp_api_key_scope_readiness.py` with default `status=NOT_RUN`, `read_only=true`, `mutation_allowed=false`; default mode performs no Firestore reads or writes.
- `--execute` inventories `mcp_api_keys/{key_id}` documents and distinguishes keys missing `app_id`, missing/malformed `scopes`, verified persisted `memories.read`, and unknown scopes. It does not infer scopes from advertised MCP tool metadata, OAuth security scheme advertisements, or client requests.
- Writes are unreachable unless both `--execute` and `--allow-write` are supplied with a deterministic server-owned assignment file mapping existing key IDs to `{app_id, scopes}`.
- Assignment preserves key IDs/users/hashes/prefixes and only allows the server-owned scope allowlist `memories.read`, `memories.write`, and `memories.archive.read`; unknown scopes are denied before mutation.
- Updated `docs/epics/v17_mcp_app_key_scope_readiness.md` with commands, prerequisites, pass/fail criteria, and non-claims.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing-runner/doc failures (`4 failed`), GREEN runner/doc tests (`4 passed`), default readiness run `python3 backend/scripts/v17_mcp_api_key_scope_readiness.py` produced JSON `status: "NOT_RUN"`, focused MCP/auth/product regression and full V17 regression were rerun, and async scan remained pre-existing findings only.

This closes only the readiness-runner/server-owned assignment-contract subpoint. Remaining P0-1/P0-6 work:

- The runner was not executed against production and no production MCP key scopes were migrated.
- No OAuth token introspection was implemented.
- Deployed Firestore rules/IAM proof against a real target project remains not run.
- App/key memory grants at `users/{uid}/memory_control/v17_app_key_memory_grants` still require server-owned product/admin assignment separate from MCP key scopes.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 Firestore/IAM proof scope extension for MCP keys and app/key grants

Continued Oracle P0-1/P0-6 by extending the existing safe-by-default Firestore IAM/deployed Security Rules proof runner to include the external-auth/server-owned state required by MCP key scope and app/key grants, without changing the production rollout verdict:

- Extended `backend/scripts/v17_firestore_rules_iam_proof.py` pass/fail inventory to include `mcp_api_keys/{key_id}` and `users/{uid}/memory_control/v17_app_key_memory_grants` alongside the existing V17 vector repair outbox/control paths.
- The runner remains default `status=NOT_RUN`, read-only, and non-mutating. `--execute` still only allows `gcloud`/Firebase describe/get commands; it does not deploy rules, change IAM, mutate Firestore, assign MCP scopes, or assign app/key grants.
- Updated checked-in `firestore.rules` comments to make the server-owned MCP API-key and V17 app/key grant boundaries explicit; client rules still deny direct read/create/update/delete.
- Updated Firestore/IAM docs with the new proof-scope paths and pass/fail criteria.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED proof-scope test failures (`2 failed`), GREEN proof runner/doc tests (`2 passed`), default readiness run `python3 backend/scripts/v17_firestore_rules_iam_proof.py` produced JSON `status: "NOT_RUN"` with missing target-project prerequisite, execute readiness run returned exit 2 `status: "NOT_RUN"` due to missing project/`gcloud`/`firebase`, focused MCP/auth/proof tests passed, full V17 regression passed, and async scan remained pre-existing findings only.

This closes only the proof-runner scope-extension/readiness subpoint. Remaining P0-1/P0-6 work:

- The deployed Firestore/IAM proof was not run against a real target project because target project credentials/CLI prerequisites were unavailable locally.
- Production MCP key scopes were not migrated, and production app/key grants were not assigned.
- OAuth token introspection remains unimplemented.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-1/P0-6 V17 app/key memory grant assignment readiness runner

Continued Oracle P0-1/P0-6 by adding a safe admin-readiness runner for server-owned V17 app/key memory grant assignment at `users/{uid}/memory_control/v17_app_key_memory_grants`, without changing the production rollout verdict:

- Added `backend/scripts/v17_app_key_memory_grant_assignment_readiness.py` with default `status=NOT_RUN`, `read_only=true`, `mutation_allowed=false`; default mode performs no Firestore reads or writes.
- `--execute --assignment-file ...` validates a deterministic assignment plan for `uid`, `consumer`, `app_id`, `key_id`, persisted scopes, `default_read`, `archive_read`, `write`, and `archive_default_visible=false` without mutating Firestore.
- Writes are unreachable unless both `--execute` and `--allow-write` are supplied with a deterministic assignment file; write plans target only `users/{uid}/memory_control/v17_app_key_memory_grants` at `grants.<consumer>.apps.<app_id>.keys.<key_id>`.
- The runner denies unknown consumers, unknown scopes, unknown capabilities/fields, malformed booleans, `archive_default_visible=true`, and operation flags that lack their required scopes. It never infers grants from MCP advertised metadata, client request fields, or key scopes alone.
- Archive remains not default-visible even when an explicit `archive_read` capability is assigned.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing-runner/doc failures (`5 failed`), GREEN runner/doc tests, default readiness run `python3 backend/scripts/v17_app_key_memory_grant_assignment_readiness.py` produced JSON `status: "NOT_RUN"`, focused P0-1/P0-6 tests passed, full V17 regression passed, and async scan remained pre-existing findings only.

This closes only the readiness-runner/admin-assignment-contract subpoint. Remaining P0-1/P0-6 work:

- The runner was not executed against production and no production app/key grants were assigned.
- Production MCP key scopes were not migrated.
- OAuth token introspection remains unimplemented.
- Deployed Firestore/IAM proof against a real target project remains not run.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-5 shared ns2 legacy/V17 isolation local readiness

Continued Oracle P0-5 by adding a safe local guard/readiness slice for shared `ns2` legacy/V17 vector isolation, without changing the production rollout verdict:

- Added `backend/scripts/v17_shared_ns2_legacy_isolation_readiness.py` with default `status=NOT_RUN`, `read_only=true`, and `mutation_allowed=false`; default mode performs no Pinecone query or mutation.
- The runner inventories legacy `ns2` memory search paths (`database.vector_db.find_similar_memories`, `database.vector_db.search_memories_by_vector`), required V17 metadata barriers, stale/deleted physical-ID risk, and P0-7 overfetch/refill implications.
- Added `build_legacy_memory_vector_filter(...)` in `backend/database/vector_db.py` and wired legacy `find_similar_memories(...)` plus `search_memories_by_vector(...)` to include exact uid filtering and `v17_schema_version: {"$exists": false}` before top-k, preserving subject filtering where applicable.
- This local guard prevents V17 schema vectors from consuming legacy top-k slots in the legacy adapters before hydration. It does not prove real Pinecone coexistence, stale/deleted physical-ID cleanup, baseline recall retention, or provider behavior.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED missing-runner/filter tests (`4 failed`), GREEN readiness/filter tests (`4 passed`), default readiness run `python3 backend/scripts/v17_shared_ns2_legacy_isolation_readiness.py` produced JSON `status: "NOT_RUN"`, execute readiness returned exit 2 due missing Pinecone prerequisites, focused vector/filter tests passed, full V17 regression passed, and async scan remained pre-existing findings only.

This closes only the local shared-`ns2` legacy-filter/readiness subpoint. Remaining P0-5 work:

- No real Pinecone shared `ns2` proof was run because provider credentials/config were unavailable.
- No production baseline recall/coexistence benchmark was run.
- Stale/deleted physical-ID and duplicate V17 physical-ID proof remains provider-backed work.
- If metadata filtering is unsafe in real Pinecone, a separate namespace decision remains open.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-7 bounded vector overfetch/refill/candidate-budget hardening

Started Oracle P0-7 with a narrow local algorithmic hardening slice for V17 default vector search, without changing the production rollout verdict:

- `fetch_default_v17_vector_memory_search(...)` now uses configurable, fake-injectable bounded overfetch/refill parameters: `overfetch_factor` defaults to 3 and is capped at 10; `max_candidates` defaults to 50 and is hard capped at `MAX_V17_VECTOR_SEARCH_LIMIT=100`.
- The first vector query requests more candidates than the return `limit`; if early candidates are removed by freshness/hydration/access checks and the vector source returned a full candidate window, the service refills by increasing the request limit up to the candidate budget. Returned items remain clipped to caller `limit`.
- Hydration no longer scans the full `users/{uid}/memory_items` collection for vector search. The service hydrates only vector candidate IDs through `users/{uid}/memory_items/{memory_id}` document gets, caching already-read/missing candidate IDs across refill attempts.
- Response observability now includes low-cardinality counts for overfetch factor, candidate budget/request limit, vector query count, queried candidates, hydrated candidates, hydration rejects by missing/stale/access-denied class, returned count, and budget exhaustion. It does not log candidate IDs.
- Mandatory P0-4 fences are preserved: missing required projection commit/account generation still fails before vector query/hydration; hit-level uid/account-generation/item-revision/source/content/projection checks still reject during hydration; Archive remains default-unavailable.
- Product route, Omi chat, MCP, and developer vector caller tests were updated to expect default overfetch and candidate-ID hydration.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED vector-service tests failed on the missing `overfetch_factor` parameter (`2 failed, 9 passed`); GREEN vector-service tests passed (`11 passed`); focused product/chat/MCP/developer vector caller regression passed (`60 passed`); full V17 regression passed (`306 passed, 3 warnings`); async scan remained pre-existing findings only.

This closes only the first bounded local P0-7 overfetch/refill/candidate-budget seam. Remaining P0-7/P0 work:

- This refill implementation re-queries larger top-K windows through the existing fake/Pinecone seam; real provider pagination/refill behavior, latency, and recall were not proven.
- Explicit vector-search timeouts, rate limits, central monotonic telemetry/alerts, and high-volume load tests remain incomplete.
- Real Pinecone/Firestore benchmarks with malformed metadata, cross-user hits, expired Short-term, Archive, deleted/tombstoned sources, duplicate revisions, partial outages, and high-volume accounts remain required.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-7 V17 vector-search low-cardinality telemetry seam

Continued Oracle P0-7 with a narrow local central telemetry seam for hydrated V17 vector search, without changing the production rollout verdict:

- Added `backend/utils/memory/v17_vector_search_telemetry.py` with `V17VectorSearchTelemetryConfig` and `emit_v17_vector_search_telemetry(...)`.
- Wired optional `telemetry_emitter` / `telemetry_config` into `fetch_default_v17_vector_memory_search(...)`; missing or disabled telemetry is a no-op.
- Emitted fake-injectable low-cardinality metric/event payloads for vector query count, queried/hydrated/vector-rejected candidates, candidate request limit/budget, hydration rejects by bounded reason, returned count, empty-after-hydration, and candidate-budget exhaustion.
- Telemetry emitter failures are recorded in `response["telemetry"]` and do not mask successful search results or fail-closed filtering behavior.
- Payload labels are bounded to `component`, `consumer`, `surface`, `mode`, `status`, `reason`, and `event_type`; tests forbid uid, raw query text, memory IDs, and vector IDs in emitted payloads.
- Mandatory P0-4 fences and candidate-ID hydration remain unchanged; Archive remains default-unavailable.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED collection failure for missing telemetry module (`ModuleNotFoundError`), GREEN vector-service tests passed (`13 passed`), focused product/chat/MCP/developer vector caller regression passed (`60 passed`), full V17 regression passed (`308 passed, 3 warnings`), and async scan remained pre-existing findings only.

This closes only the fake-injectable central telemetry payload/emitter subpoint. Remaining P0-7/P0 work after this telemetry slice:

- No Prometheus/OpenTelemetry/Cloud Monitoring sink, dashboard, or alert policy was implemented or exercised.
- Explicit vector-search timeout/rate-limit controls remained incomplete until the follow-up slice below.
- Real Pinecone/Firestore provider pagination/refill behavior, load, recall, and latency benchmarks remain unproven.
- Real Pinecone/Firestore benchmarks with malformed metadata, cross-user hits, expired Short-term, Archive, deleted/tombstoned sources, duplicate revisions, partial outages, and high-volume accounts remain required.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-7 V17 vector-search timeout/rate-limit control seam

Continued Oracle P0-7 with explicit fake-injectable local timeout/rate-limit controls for hydrated V17 vector search, without changing the production rollout verdict:

- `fetch_default_v17_vector_memory_search(...)` now accepts bounded `max_vector_queries`, `max_candidate_hydration_reads`, `timeout_seconds`, and an injected monotonic `clock` for deterministic tests without sleeps.
- Required projection commit/account generation fences still fail before any vector query or Firestore hydration.
- The service stops refill when the vector-query budget is exhausted and stops candidate document gets when the hydration-read budget or injected deadline is exhausted.
- It returns already validated results clipped to caller `limit`, does not fall back to legacy, and does not expose Archive by default.
- Response state now includes `search_status`, `vector_query_budget_exhausted`, `hydration_read_budget_exhausted`, `timeout_exhausted`, budget/read counters, and `legacy_fallback_used=false`.
- Candidates not read because the hydration budget/deadline stopped hydration are not marked as missing-authoritative repair/purge candidates.
- Telemetry adds low-cardinality timeout/control-exhaustion metrics/events using bounded labels only; tests continue to forbid uid, raw query, memory IDs, vector IDs, raw errors, and idempotency labels.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED vector-service tests failed on missing control kwargs (`4 failed, 13 passed`); GREEN vector-service tests passed (`17 passed`); focused product/chat/MCP/developer vector caller regression passed (`60 passed`); full V17 regression passed (`312 passed, 3 warnings`); async scan remained pre-existing findings only.

This closes only the local fake-injectable timeout/rate-limit control subpoint. Remaining P0-7/P0 work:

- No Prometheus/OpenTelemetry/Cloud Monitoring sink, dashboard, or alert policy was implemented or exercised.
- Real Pinecone/Firestore provider pagination/refill behavior and provider-level timeout semantics remain unproven.
- Real load, recall, latency, malformed metadata, cross-user hit, expired Short-term, Archive, deleted/tombstoned source, duplicate revision, partial outage, and high-volume account benchmarks remain required.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — P0-7 V17 vector-search provider-proof readiness artifact

Continued Oracle P0-7 with `backend/scripts/v17_vector_search_provider_readiness.py`, a safe-by-default provider-proof/readiness artifact for the real Pinecone/Firestore evidence still required before production rollout:

- Default CLI output is an honest `status=NOT_RUN`, `read_only=true`, `mutation_allowed=false`, `provider_calls_executed=false`, `benchmark_evidence_collected=false`, and `production_rollout_approved=false`.
- The artifact inventories required prerequisites/config: `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `PINECONE_INDEX_HOST`, `V17_PROVIDER_PROOF_FIRESTORE_PROJECT`, `V17_PROVIDER_PROOF_UID`, plus optional proof namespace.
- Planned read-only proof cases cover provider pagination/refill semantics, provider vector query timeout behavior, Firestore candidate-ID hydration read counts, malformed/stale metadata, cross-user hits, expired Short-term, Archive default-unavailable, deleted/tombstoned sources, duplicate revisions, partial outages, high-volume account candidate budgets, and load/recall/latency criteria.
- `--execute` remains read-only and exits nonzero with `NOT_RUN` when prerequisites are missing; no Pinecone upsert/delete/update and no Firestore create/set/update/delete operations are planned or performed.
- Static tests assert the script contains no provider/Firestore mutating method calls and that non-claims are explicit.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED readiness tests failed on missing runner/docs (`4 failed`); intermediate GREEN for runner failed only on missing docs (`1 failed, 3 passed`); final GREEN readiness tests passed; default readiness output returned `NOT_RUN` with missing prerequisites; execute without prerequisites exited 2 with `NOT_RUN`; full V17 regression and async scan remained green/pre-existing only.

This closes only a readiness/non-claim artifact for future provider proof. Remaining P0-7/P0 work:

- No real Pinecone/Firestore provider proof was executed.
- Provider pagination/refill, provider-level timeout semantics, load/recall/latency benchmarks, malformed metadata, cross-user hits, expired Short-term, Archive default-unavailable, deleted/tombstoned sources, duplicate revisions, partial outages, and high-volume account evidence remain **NOT_RUN**.
- No production benchmark evidence, central monitoring sink/alert policy, or production approval is claimed.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0s and required real-service evidence are complete.

### 2026-06-19 — Oracle P0-8 V17 cutover evidence readiness/checklist artifact

Started Oracle P0-8 with `backend/scripts/v17_cutover_evidence_readiness.py`, a safe-by-default production-cutover evidence readiness checklist. It does not attempt cloud/provider execution and does not claim approval:

- Default and `--execute` CLI modes emit `status=BLOCKED`, `read_only=true`, `mutation_allowed=false`, `network_or_provider_calls_executed=false`, `benchmark_evidence_collected=false`, `approval_claimed=false`, and `production_rollout_approved=false`.
- Every gate remains `BLOCKED` or `NOT_RUN` with empty evidence arrays and explicit blockers: milestone Oracle/final approval, real Pinecone validation, real Firestore/cloud IAM/rules validation, recall/precision/latency/no-silent-data-loss benchmarks, production metrics aggregation/central telemetry, T20 repair/projection-consistency, T21 `/v3` compatibility and cursor pagination, T22/T23 external writes and caller coverage, and production cutover approval.
- Each gate inventories required proof commands/artifacts, including follow-up use of the provider readiness runner, Firestore rules/IAM proof runner, central telemetry/dashboard/alert artifacts, T20 repair/projection consistency output, T21 `/v3` compatibility and cursor pagination matrix, T22/T23 external writes and caller coverage matrix, benchmark reports, and an explicit final production owner approval artifact.
- Static tests assert the runner contains no mutating Pinecone/Firestore/deploy command calls, that evidence remains empty, and that approval is not claimed.

Verification is recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED cutover readiness tests initially failed on the missing runner/docs (`4 failed`); after adding the runner but before docs update they failed only on missing exact script/doc terms (`2 failed, 2 passed`); final GREEN readiness tests passed; default and execute readiness commands returned `BLOCKED` with no provider/network calls and `production_rollout_approved=false`; full V17 regression and async scan remained green/pre-existing only.

This closes only the safe checklist/readiness inventory for Oracle P0-8. It does **not** execute or claim final Oracle approval, real Pinecone validation, real Firestore/cloud validation, benchmarks, central telemetry aggregation, T20/T21/T22/T23 completion, or production cutover approval. Production rollout remains **BLOCKED / NO-GO**.

### 2026-06-19 — Oracle P0-8 T20 repair/projection-consistency readiness/proof matrix

Continued Oracle P0-8 with `backend/scripts/v17_t20_repair_projection_consistency_readiness.py`, a safe T20 repair/projection-consistency readiness/proof matrix. It addresses the P0-8/T20 subpoint for projection freshness, vector repair convergence, shared `ns2` isolation, and no-silent-data-loss evidence inventory only:

- Default and `--execute` CLI modes emit `status=BLOCKED`, `read_only=true`, `mutation_allowed=false`, `network_or_provider_calls_executed=false`, `provider_calls_executed=false`, `benchmark_evidence_collected=false`, `approval_claimed=false`, and `production_rollout_approved=false`.
- The proof matrix remains `NOT_RUN` with empty evidence arrays for projection_commit_id parity, account_generation parity, item_revision/source_commit_id/content_hash parity, tombstone/deleted source handling, stale physical vector detection, duplicate vector detection, repair outbox enqueue/dead-letter/backlog, repair worker convergence, shared ns2 legacy/V17 isolation under stale candidates, and no silent data loss.
- The artifact explicitly references existing local seams/runners: `v17_vector_search_provider_readiness.py`, `v17_shared_ns2_legacy_isolation_readiness.py`, `v17_pinecone_repair_validation_readiness.py`, `v17_vector_repair_outbox_telemetry.py`, vector repair outbox record/worker modules, vector metadata gateway, and vector search service.
- The production cutover checklist now points the T20 repair/projection-consistency gate at this matrix and requires proof of projection_commit_id/account_generation/item_revision/source_commit_id/content_hash parity, repair outbox enqueue/dead-letter/backlog, and shared ns2 legacy/V17 isolation under stale candidates.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED matrix tests failed on missing runner/docs (`4 failed`); final GREEN/static/readiness/regression/async passed. This slice does **not** execute Pinecone/Firestore/cloud calls, mutate shared `ns2` or Firestore, collect benchmarks, wire central telemetry, claim T20 completion, or approve cutover. Production rollout remains **BLOCKED / NO-GO**.

### 2026-06-19 — Oracle P0-8 T21 `/v3` compatibility and cursor pagination readiness/proof matrix

Continued Oracle P0-8 with `backend/scripts/v17_t21_v3_compatibility_cursor_readiness.py`, a safe T21 `/v3` compatibility and cursor pagination readiness/proof matrix. It addresses the P0-8/T21 subpoint for legacy/V17 reader compatibility, cursor pagination readiness, caller response-shape compatibility, and regression evidence inventory only:

- Default and `--execute` CLI modes emit `status=BLOCKED`, `read_only=true`, `mutation_allowed=false`, `network_or_provider_calls_executed=false`, `provider_calls_executed=false`, `benchmark_evidence_collected=false`, `approval_claimed=false`, and `production_rollout_approved=false`.
- The proof matrix remains `NOT_RUN` with empty evidence arrays for `/v3` endpoint compatibility, stable cursor pagination, category filters, stable ordering, disabled/malformed/no-grant behavior, enabled-but-empty behavior, deleted/non-active records, Archive default-unavailable, external response shape compatibility, developer category filtering, MCP REST/SSE shape consistency, and product/developer/MCP/chat caller regression evidence.
- The artifact explicitly references existing local route/adapter/test surfaces: `backend/routers/memories.py GET /v3/memories`, `backend/database/memories.py get_memories`, `backend/utils/memory/v17_product_memory_read_service.py`, `backend/utils/memory/v17_developer_memory_adapter.py`, `backend/utils/memory/v17_mcp_memory_adapter.py`, `backend/utils/memory/v17_chat_memory_adapter.py`, `backend/routers/mcp.py`, `backend/routers/mcp_sse.py`, `backend/routers/developer.py`, and existing V17 read/caller tests.
- The production cutover checklist now points the T21 gate at this matrix and requires proof of `/v3` endpoint compatibility, stable cursor pagination, category filters, stable ordering, disabled/malformed/no-grant behavior, enabled-but-empty behavior, deleted/non-active record exclusion, Archive default-unavailable, external response shape compatibility, developer category filtering, MCP REST/SSE shape consistency, and product/developer/MCP/chat caller regression coverage.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED matrix tests failed on missing runner/docs/cutover links (`4 failed`); final GREEN/static/readiness/regression/async passed. This slice does **not** execute production traffic, Pinecone/Firestore/cloud calls, mutate shared `ns2` or Firestore, collect benchmarks, wire central telemetry, claim T21 completion, or approve cutover. Production rollout remains **BLOCKED / NO-GO**.

## Not-run / not-claimed caveats preserved

- Oracle review has now run and is recorded here, but it blocks production rollout.
- Real Pinecone validation was **not** run.
- Production Firestore cloud IAM/deployed Security Rules validation was **not** run; only local Firestore emulator outbox persistence/rules/lease contention gates exist.
- Benchmark/no-silent-data-loss validation for vector search quality, latency, and recall was **not** run.
- Production metrics aggregation/central `/metrics` integration was **not** completed.
- Production rollout/cutover is **not** approved.

## Exact Oracle answer

```text
According to a document from June 19, 2026, this is **ready for architecture/milestone review, but a production read or vector cutover is a NO-GO**. The happy-path unit tests support the intended pattern—authoritative hydration excludes stale Short-term and Archive—but the implementation still has control-plane bypasses, unsafe fallback semantics, read/write split-brain, optional vector freshness fences, and no real-service or benchmark evidence. 

## Verdict

**BLOCK production rollout.**

Do not enable V17 as an authoritative read path for customers, MCP, developer API, or chat. A tightly isolated shadow test that cannot affect returned results may continue, but the current code should not be treated as fail-closed production behavior.

## P0 issues

### P0-1 — Product default read is not rollout-gated; Archive capability is client-self-granted

`GET /v17/memory/search` authenticates the user and immediately reads `memory_items`; it never checks `memory_control/state`, rollout mode, allowlisting, or the Omi-chat grant.

`GET /v17/memory/archive/search` treats `include_archive=true` as sufficient to construct `archive_capability=True`. That is an explicit query, but it is **not** a server-authorized capability. It does not check a persisted Archive opt-in, app policy, rollout state, or global Archive kill switch.

The response fields `archive_default_visible=False` and `archive_capability_granted=True` merely describe the locally constructed policy; they are not authorization controls. This contradicts the documented contract that both app/admin policy and an explicit request are required.

**Required fix:** Every V17 product route must call one shared server-side authorization decision before any `memory_items` access. Archive must require both a persisted capability and an explicit Archive query.

---

### P0-2 — “Fail closed” is conflated with an unsafe legacy downgrade

The rollout helper collapses several materially different states into “V17 disabled”:

* intentionally off;
* missing or malformed control state;
* missing consumer grant;
* unsupported consumer;
* control-plane inconsistency.

MCP, chat, and the developer list then interpret `None` as “use legacy.” This is not necessarily fail-closed:

* A revoked or missing grant can still result in legacy memory disclosure.
* A malformed or unavailable control document can fall back to legacy after V17-only writes have begun, hiding new memories or resurrecting deleted/superseded ones.
* `disabled_v17_default_read_rollout_decision` marks legacy reads authoritative without proving `fallback_projection_ready`, reconciliation, generation, or epoch safety.
* Recognized malformed states downgrade to legacy, while real Firestore/network exceptions are not caught and instead fail with a 500.

Behavior also differs by surface:

| Surface          | Disabled/malformed/no grant | Enabled but V17 returns zero           |
| ---------------- | --------------------------- | -------------------------------------- |
| Product vector   | 403                         | Empty result                           |
| Developer vector | 403                         | Empty result                           |
| Developer list   | Legacy fallback             | V17 result                             |
| Chat             | Legacy fallback             | “No V17 vector memories…”; no fallback |
| MCP REST         | Legacy fallback             | Empty list; no fallback                |
| MCP SSE          | Legacy fallback             | Empty list; no fallback                |

Thus an empty or under-indexed V17 vector result silently suppresses legacy memories, while a control-plane failure can silently re-enable legacy.

**Required fix:** Replace the Boolean/`None` contract with an explicit decision:

* `USE_V17`
* `USE_LEGACY_SAFE`
* `DENY_MEMORY`
* optionally `SHADOW_ONLY`

`USE_LEGACY_SAFE` must require proven reconciliation, compatible projection readiness, matching epochs/generation, and an explicit policy permitting downgrade. Operational errors, grant revocation, and malformed state must not automatically mean legacy.

---

### P0-3 — Reads are V17 while MCP/developer writes and deletes remain legacy

The shown MCP and developer create/edit/delete routes still mutate the legacy memory collection and legacy vectors. Meanwhile, search or list may read authoritative V17 `memory_items`.

Consequences include:

* a newly created memory is not visible in V17 search;
* an edit can leave V17 content unchanged;
* deleting a legacy memory can leave the V17 item and V17 vector searchable;
* a category parameter on the developer list bypasses V17 and forces the legacy path;
* rollbacks and user expectations become dependent on which endpoint was used.

This is exactly the T22 external-write-semantics work that remains after the current milestone. Enabling reads before that work creates an externally visible split-brain system. 

**Required fix:** Before any authoritative read cutover, either:

1. move all applicable create/edit/delete routes through the V17 write/deletion service, or
2. disable those writes for the pilot and prove reconciliation, or
3. implement a tested, durable dual-write/outbox protocol.

Deletion must update both authoritative state and all compatibility/vector projections before success is reported.

---

### P0-4 — Vector freshness and purge fences are optional in production callers

The design correctly treats vectors as candidates, but its strongest consistency check is optional:

* `required_projection_commit_id` defaults to `None`;
* none of the shown production callers supplies it;
* `uid`, `account_generation`, `item_revision`, `source_commit_id`, and `content_hash` are optional when parsing a vector hit.

Even if the unseen hydration gateway compares a hit with its item, it is not shown receiving the **current control-plane account generation**. A stale vector and a stale-but-not-yet-deleted item can agree with each other while both belong to a purged generation.

Additionally, vector IDs include tier and revision. Every transition or revision produces a new physical vector ID, making correct deletion of prior IDs mandatory. That cleanup, tombstone precedence, and repair flow were not validated.

**Required fix:** Make the following mandatory, not optional:

* expected current account generation;
* exact uid;
* item revision;
* content hash;
* source commit/version;
* projection commit/version;
* source/tombstone state.

Missing fence metadata must reject the hit. Projection workers must delete previous tier/revision IDs, and repair must prove no duplicate or stale IDs remain.

---

### P0-5 — Shared `ns2` isolation from legacy search is unproven

The V17 query has schema and tier filters, but the legacy vector functions are explicitly left untouched. With both schemas in `ns2`, an unchanged legacy top-k query may:

* retrieve V17 vectors and lose useful legacy slots;
* produce different results for non-enabled users;
* accidentally hydrate a local legacy record using a V17 hit with the same logical ID;
* be influenced by Archive or stale V17 embeddings even when the item is later dropped.

“Legacy code untouched” is not evidence that legacy behavior remains unchanged. No real Pinecone validation or legacy-plus-V17 coexistence benchmark was run.

**Required fix:** Prove with real `ns2` data that legacy queries explicitly exclude V17 schema records and retain baseline recall. Otherwise add a legacy schema filter or separate namespace before inserting production V17 vectors.

**2026-06-19 local readiness slice:** Added `backend/scripts/v17_shared_ns2_legacy_isolation_readiness.py`, a safe-by-default shared-namespace artifact that inventories the legacy `ns2` memory search paths (`find_similar_memories`, `search_memories_by_vector`), the required V17 metadata barriers (`v17_schema_version`, `uid`, `memory_tier`, `status`, `source_state`, `restricted_sensitivity`, account/revision/source/content/projection fences), and remaining stale/deleted physical-ID plus overfetch/refill risks. Default output is `status=NOT_RUN`, `read_only=true`, `mutation_allowed=false`; `--execute` only checks provider prerequisites for a future read-only inventory and performs no Pinecone query or mutation in this slice.

Also added a narrow local code guard: legacy queries exclude V17 schema before top-k selection via `{'v17_schema_version': {'$exists': False}}`, so legacy queries exclude V17 schema records instead of letting V17 Short-term/Long-term/Archive/stale/tombstoned candidates consume legacy result slots. No real Pinecone shared `ns2` proof, recall benchmark, provider query output, production coexistence validation, or rollout approval is claimed; real shared-`ns2` data validation and baseline recall evidence remain required.

---

### P0-6 — Third-party authorization is not shown at app/key granularity

The V17 grant is stored per user and broad consumer—`mcp` or `developer_api`—rather than per MCP app, developer key, OAuth client, or installation. Enabling it appears to enable every corresponding key for the user.

More seriously, the shown MCP streamable-HTTP path advertises OAuth scopes in tool metadata, but `authenticate_api_key` returns only a user ID and `execute_tool` receives no scope set. No scope enforcement is visible. Unless an unseen key lookup rejects by scope, metadata such as `MEMORIES_READ_SECURITY` is documentation rather than authorization. 

**Required fix:** Carry authenticated key/app identity and verified scopes into `MemoryAccessPolicy`. Enforce `memories.read` at execution time on every MCP transport, and store grants per app/key where product policy requires differentiated access.

---

### P0-7 — The vector search algorithm is not production-shaped

`fetch_default_v17_vector_memory_search` queries only `limit` vector candidates and then loads the entire authoritative `memory_items` collection into a dictionary.

That creates two severe risks:

1. **Unbounded cost and latency:** every vector search can read all Short-term, Long-term, and Archive documents for the user.
2. **Silent recall collapse:** stale Short-term, Archive, restricted, processed, or stale-revision vectors can consume all top-k slots. Hydration removes them, but there is no overfetch or refill, so the caller may receive zero results even when eligible results exist below top-k.

The tests prove filtering, not adequate recall after filtering. 

**Required fix:** Batch-fetch only candidate IDs, overfetch by a measured factor or iteratively refill, place strict read/candidate budgets, add timeouts and rate limiting, and load-test high-volume users.

---

### P0-8 — Required cutover evidence is explicitly absent

The artifact states that the following were not run or completed:

* milestone-specific Oracle review;
* real Pinecone validation;
* real Firestore/cloud validation for these paths;
* recall, precision, latency, and no-silent-data-loss benchmarks;
* production metrics aggregation;
* production cutover approval.

T20’s repair/projection-consistency work and T21’s `/v3` compatibility and cursor-pagination requirements are also not demonstrated. T22/T23 remain applicable because external writes and caller coverage are incomplete.

## P1 issues

### P1-1 — Rollout document parsing is too permissive

* `data.get('uid', uid)` accepts a rollout document with no uid.
* A stale top-level grant can override an explicitly false or absent nested grant.
* Multiple aliases create ambiguous revocation precedence.
* Firestore timeouts, permission errors, and transport exceptions are outside the caught exception set.

Require a versioned schema, exact uid, one canonical grant location, explicit-false precedence, and bounded reads with defined error handling.

### P1-2 — Sensitive-data policy is duplicated and incomplete

The vector metadata code has a hard-coded restricted-label set that does not visibly cover the complete normative taxonomy, including categories such as third-party personal data and safety risk, and it depends on exact singular label spelling.

Authoritative hydration remains the final control, but restricted vectors can still pollute top-k and starve safe results. Move sensitivity decisions to the central policy module and emit a single derived vector eligibility field.

### P1-3 — Caller/API behavior is inconsistent

* MCP `search_memories` may use V17, while MCP `get_memories` remains legacy.
* MCP REST and SSE return different shapes and have different fallback chains.
* Developer category filtering forces legacy.
* Developer formatting fabricates fields such as `private`, `reviewed=True`, `edited=False`, and `category=other`.
* Product, MCP, chat, and developer disagree on whether disabled rollout means 403 or legacy.

These differences need an explicit compatibility contract before external rollout.

### P1-4 — Current metrics are not production counters

The low-cardinality labels are a good constraint, but the current Prometheus text is derived from a single admin inspection of three consumer decisions. A metric named `_total` is therefore not monotonic, process-lifetime traffic telemetry, and does not measure actual searches.

Missing production metrics include:

* V17/legacy/deny path selection;
* vector query errors and latency;
* candidate, parse-reject, hydration-reject, and returned counts;
* empty-after-hydration rate;
* stale revision/generation mismatch;
* fallback reason;
* Firestore documents read;
* per-surface success and error rate.

The milestone itself acknowledges that central aggregation is incomplete. 

### P1-5 — Chat treats memory content as prompt text

The chat adapter concatenates memory content directly into an LLM-facing string. Fresh Short-term content is source-backed and potentially untrusted. There is no visible escaping, structured-data boundary, injection marking, or output-size budget in the adapter.

Treat retrieved memory as quoted evidence, cap item/content lengths, and test prompt-injection payloads.

### P1-6 — Test coverage is largely fake/static wiring coverage

The supplied tests use fake Firestore collections, fake vector queries, and source-text ordering assertions. They do not exercise real FastAPI dependencies, response-model filtering, Pinecone filters, Firestore exceptions, scope enforcement, or cross-store behavior. Some legacy router test attempts were explicitly not run because of missing dependencies.

## Required fixes and gates before rollout

1. **Gate every V17 route** with the same versioned rollout decision; add a global emergency kill switch independent of the per-user Firestore read.
2. **Implement server-authorized Archive capability**, separate from the explicit query flag, with audit logging and revocation tests.
3. **Introduce the tri-state/quad-state read decision** and prohibit legacy downgrade unless reconciliation proves it safe.
4. **Complete T22/T23 for every applicable surface**, especially MCP/developer create, edit, delete, list, tools, agent paths, and existing `/v3` compatibility.
5. **Make vector consistency fences mandatory**, including current account generation, and complete outbox, stale-ID deletion, repair, and tombstone precedence.
6. **Prove shared-namespace isolation** against real Pinecone data for both V17 and legacy callers.
7. **Replace full-collection hydration** with candidate-ID batch hydration and measured overfetch/refill.
8. **Enforce scopes and app/key-specific grants** on MCP REST, MCP streamable HTTP/SSE, and developer keys.
9. **Add central, monotonic, low-cardinality telemetry and alerts**, including empty-after-hydration and unsafe-fallback attempts.
10. **Run real cloud validation and benchmarks** with malformed metadata, cross-user hits, expired Short-term, Archive, deleted/tombstoned sources, duplicate revisions, partial outages, and high-volume accounts.
11. **Run the milestone Oracle review** and close all P0 findings.
12. **Cut over through shadow comparison and canaries**, with documented abort thresholds and a tested rollback that cannot lose or resurrect data.

## Decisions requiring product-owner input

1. **Archive authorization:** Is an authenticated first-party user’s `include_archive=true` sufficient, or must Archive require a persisted user/app opt-in? Should Archive vector search exist now or remain non-vector?
2. **Fallback semantics:** On missing/malformed control state, revoked grant, vector outage, or empty V17 results, should the system deny memory, return an error, use last-known-safe state, merge legacy and V17, or fall back only when reconciliation is proven?
3. **Meaning of the default-memory grant:** Is it merely rollout eligibility, or a privacy/consent control? If it is consent, legacy fallback after grant removal is unacceptable.
4. **Third-party scope:** Should every MCP/developer key for a user share one memory grant, or must policy be per app, key, OAuth client, or installation?
5. **Short-term exposure:** Should fresh source-backed Short-term memory be available by default to MCP/developer apps, or only to first-party chat unless the user grants a stronger scope?
6. **Read/write sequencing:** Must T22 V17 writes and deletes land before read cutover, or will pilot accounts have external memory writes disabled?
7. **API strategy:** Should existing `/v3`, MCP, and developer endpoints switch behavior additively, or should `/v17` endpoints remain private/experimental until compatibility is complete?
8. **Launch thresholds:** Define acceptable recall regression, p95/p99 latency, empty-after-hydration rate, stale-vector rate, error rate, and the required observation period before increasing the allowlist.

**Bottom line:** authoritative hydration is the right foundation, and the tested stale Short-term/Archive exclusion is useful. It is not yet a safe production system because authorization, downgrade behavior, write/read convergence, vector fencing, shared-namespace coexistence, and real operational validation remain unresolved.
```
