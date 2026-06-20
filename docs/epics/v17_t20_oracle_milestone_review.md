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

### 2026-06-19 — Oracle P0-8 T22/T23 external writes and caller coverage readiness/proof matrix

Continued Oracle P0-8 with `backend/scripts/v17_t22_t23_external_writes_caller_coverage_readiness.py`, a safe T22/T23 external writes and caller coverage readiness/proof matrix. It addresses the P0-8/T22/T23 subpoint for external create/edit/delete/list/search write/read convergence, caller coverage across Developer API, MCP REST/SSE, chat, tools, and agent paths, and durable write-convergence evidence inventory only:

- Default and `--execute` CLI modes emit `status=BLOCKED`, `read_only=true`, `mutation_allowed=false`, `network_or_provider_calls_executed=false`, `provider_calls_executed=false`, `benchmark_evidence_collected=false`, `approval_claimed=false`, and `production_rollout_approved=false`.
- The proof matrix remains `NOT_RUN` with empty evidence arrays for external create/edit/delete/list/search write/read convergence; Developer API write/read paths; MCP REST/SSE write/read/list/search paths; chat/tool/agent caller coverage; dual-write/outbox or V17-write convergence plan; delete/review/import compatibility; no legacy unsafe fallback after V17 writes; app/key/scope grant enforcement; Archive default-unavailable; response-shape compatibility; and rollback/disable behavior.
- The artifact explicitly references existing local route/adapter/test surfaces: `backend/routers/memories.py`, `backend/routers/developer.py`, `backend/routers/mcp.py`, `backend/routers/mcp_sse.py`, `backend/routers/tools.py`, `backend/routers/agent_tools.py`, `backend/database/memories.py`, the legacy write guard, external default-read authorization, V17 Developer/MCP/chat/product adapters, and existing guard/caller tests.
- The production cutover checklist now points the T22/T23 gate at this matrix and requires proof of external create/edit/delete/list/search write/read convergence, Developer API write/read paths, MCP REST/SSE write/read/list/search paths, chat/tool/agent caller coverage, durable V17-write convergence or dual-write/outbox evidence, delete/review/import compatibility, no legacy unsafe fallback after V17 writes, app/key/scope grant enforcement, Archive default-unavailable, response-shape compatibility, and rollback/disable behavior.

Verification recorded in `docs/epics/v17_memory_implementation_tickets.md`: RED matrix tests failed on missing runner/docs/cutover links (`4 failed`); final GREEN/static/readiness/regression/async passed. This slice does **not** execute production traffic, Pinecone/Firestore/cloud calls, mutate shared `ns2` or Firestore, collect benchmarks, execute external writes, wire central telemetry, claim T22/T23 completion, or approve cutover. Production rollout remains **BLOCKED / NO-GO**.

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

**2026-06-19 local hardening slice:** Hardened `backend/utils/memory/v17_default_read_rollout.py` for the first P1-1 parsing fix. Rollout/control docs now require exact `uid` and `schema_version=1`; missing/mismatched uid fails closed with `uid_mismatch`, missing/unsupported schema fails closed with `unsupported_rollout_schema`, and default-memory/Archive grant parsing uses only canonical nested `grants.<consumer>.default_memory` and `grants.<consumer>.archive`. Stale top-level grant aliases no longer override absent or explicit-false nested canonical grants, and touched nested aliases (`developer` for `developer_api`, `chat` for `omi_chat`) no longer create ambiguous revocation precedence. Per-user rollout reads call Firestore `.get(timeout=2.0)` where supported and normalize Firestore/transport-style exceptions to fail-closed `rollout_read_failed` decisions instead of bubbling or implying unsafe legacy fallback.

Verification: RED `cd backend && pytest tests/unit/test_v17_default_read_rollout_decision.py -q` failed on the missing exported schema constant (`ImportError ... 1 error in 0.14s`). Parent GREEN/regression: focused rollout/caller tests `83 passed in 0.39s`; full V17 unit suite `334 passed, 3 warnings in 1.98s`; async audit still reports only pre-existing categories (`HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`). This slice does **not** run production traffic, Firestore/Pinecone/cloud/provider calls, mutate shared `ns2` or Firestore, collect benchmarks, wire central telemetry, or approve rollout. Production rollout remains **BLOCKED / NO-GO**. Remaining P1-1 work: document/migrate existing rollout docs to `schema_version=1` and canonical grant keys only, and align global gate/read-write convergence timeout/error semantics.

**2026-06-19 local schema/readiness slice:** Added `docs/epics/v17_rollout_schema_migration.md` and `backend/scripts/v17_rollout_schema_readiness.py` to make the canonical rollout/control document contract explicit for `schema_version=1`. The checked-in readiness artifact is read-only and inventories canonical valid shapes for `uid`, `schema_version=1`, and canonical nested `grants.<consumer>.default_memory` for `mcp`, `developer_api`, and `omi_chat`, plus optional canonical `grants.<consumer>.archive` for explicit Archive capability. It also records rejected legacy compatibility shapes for missing schema, uid mismatch, top-level `*_default_memory_grant` aliases, and nested `developer`/`chat` aliases; these fail closed through the shared rollout normalizer. `production_rollout_approved=false`; no Firestore read/write, production traffic, cloud/provider call, benchmark, telemetry sink integration, or rollout approval is claimed.

Verification: RED `cd backend && pytest tests/unit/test_v17_rollout_schema_readiness.py -q` → `4 failed in 0.07s` (missing readiness runner and migration note). Interim GREEN blocked on docs: after adding script/docs, same command → `3 passed, 1 failed in 0.06s` (Oracle/ticket docs missing `v17_rollout_schema_readiness.py`). Final GREEN/static: `black --line-length 120 --skip-string-normalization scripts/v17_rollout_schema_readiness.py tests/unit/test_v17_rollout_schema_readiness.py && pytest tests/unit/test_v17_rollout_schema_readiness.py -q` → `1 file reformatted, 1 file left unchanged`, `4 passed in 0.05s`. Readiness: `python3 backend/scripts/v17_rollout_schema_readiness.py --execute` → exit 0 with `status: "NOT_RUN"`, `read_only: true`, `mutation_allowed: false`, `network_or_provider_calls_executed: false`, `firestore_reads_executed: false`, `firestore_writes_executed: false`, `canonical_schema_version: 1`, and `production_rollout_approved: false`. Full V17 regression: `cd backend && pytest tests/unit/test_v17_*.py -q` → `338 passed, 3 warnings in 2.05s`. Async scan: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene: no truncation marker literals or SUB chars under `docs/epics/v17*`. Oracle rollout verdict remains **BLOCKED / NO-GO**. Remaining P1-1 work: align global gate/read-write convergence timeout/error semantics and run real approved migration inventory before any production rollout stage.

**2026-06-19 local global/write-convergence gate read slice:** Aligned `read_v17_global_read_gate(...)` and `read_v17_write_convergence_gate(...)` with the per-user rollout document read helper. Both server-owned gate reads now call Firestore `.get(timeout=2.0)` when supported; SDKs without timeout support still fall back through the shared compatibility helper. Timeout, permission, deadline, or transport exceptions fail closed with explicit low-cardinality reasons: `global_read_gate_read_failed` returns `DENY_MEMORY`, and `write_convergence_gate_read_failed` returns `ready=false`. Existing missing/malformed gate states remain explicit fail-closed decisions (`missing_global_read_gate`, `malformed_global_read_gate`, `missing_write_convergence_gate`, `malformed_write_convergence_gate`). This does not expose Archive by default, does not make stale Short-term default-visible, and preserves exact per-user `uid`/`schema_version=1`/canonical grant parsing.

Verification: RED `cd backend && pytest tests/unit/test_v17_default_read_rollout_decision.py -q` → `4 failed, 13 passed in 0.12s` because global/write-convergence gate reads recorded `timeout=None` instead of `2.0`. GREEN focused after implementation: same command → `17 passed in 0.06s`. Final formatted focused/regression chain `cd backend && black --line-length 120 --skip-string-normalization utils/memory/v17_default_read_rollout.py tests/unit/test_v17_default_read_rollout_decision.py && pytest tests/unit/test_v17_default_read_rollout_decision.py -q && pytest tests/unit/test_v17_*.py -q` → `2 files left unchanged`, `17 passed in 0.05s`, `340 passed, 3 warnings in 2.03s`. Readiness: `python3 backend/scripts/v17_rollout_schema_readiness.py --execute` → exit 0 with `status: "NOT_RUN"`, `read_only: true`, `mutation_allowed: false`, `network_or_provider_calls_executed: false`, `firestore_reads_executed: false`, `firestore_writes_executed: false`, `canonical_schema_version: 1`, and `production_rollout_approved: false`. Async scan: `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene: no truncation marker literals or SUB chars under `docs/epics/v17*`. No production traffic, Firestore/Pinecone/cloud/provider call, Firestore read/write, benchmark, telemetry sink integration, migration execution, or rollout approval is claimed; production rollout remains **BLOCKED / NO-GO**.

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

**2026-06-19 local compatibility-contract/readiness slice:** Added safe-by-default `backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py` plus `backend/tests/unit/test_v17_p1_3_caller_api_compatibility_readiness.py` to inventory the explicit Oracle P1-3 caller/API compatibility contract before external rollout. The artifact remains `status=BLOCKED`, read-only, no mutation, no Firestore reads/writes, no network/provider/cloud calls, no benchmarks, and no approval claimed. It codifies required local decisions for Product V17 routes, `/v3`, Developer API default/category/vector paths, MCP REST `search_memories` and `get_memories`, MCP SSE `search_memories` and `get_memories`, chat `get_memories_tool`/`search_memories_tool`, tools REST memory endpoints, and agent execute-tool callers. Required decisions include MCP search_memories vs get_memories consistency, MCP REST vs SSE shape/fallback consistency, Developer category filtering must not force unsafe legacy, Developer response shape must not fabricate private/reviewed/edited/category defaults, disabled rollout semantics per surface: 403, empty, or legacy-safe, enabled-but-empty semantics, Archive default-unavailable, `/v3` external compatibility, and tools and agent callers. No broad runtime behavior changed; Oracle remains **BLOCKED / NO-GO** pending real compatibility proof and product-approved decisions.

Verification: RED `cd backend && pytest tests/unit/test_v17_p1_3_caller_api_compatibility_readiness.py -q` → `4 failed in 0.08s` (missing runner/docs/test runner). Interim GREEN blocked on docs/test runner: after adding the runner, same command → `1 failed, 3 passed in 0.06s` (Oracle/ticket/test.sh links missing). Final GREEN/static: `cd backend && black --line-length 120 --skip-string-normalization scripts/v17_p1_3_caller_api_compatibility_readiness.py tests/unit/test_v17_p1_3_caller_api_compatibility_readiness.py && pytest tests/unit/test_v17_p1_3_caller_api_compatibility_readiness.py -q` → `1 file reformatted, 1 file left unchanged`, `4 passed in 0.04s`. Readiness from repo root: `python3 backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py --execute` → `BLOCKED True False False False False False False False False 13 11` (`status`, read-only, no mutation, no network/provider calls, no provider calls, no Firestore reads, no Firestore writes, no benchmark evidence, no production approval, no approval claimed, 13 surfaces, 11 behavior cases). Full V17 regression: `cd backend && pytest tests/unit/test_v17_*.py -q` → `344 passed, 3 warnings in 2.05s`. Async scan: `python3 backend/scripts/scan_async_blockers.py` from backend returned `Error: backend/routers not found` (wrong working directory); rerun from repo root `python3 backend/scripts/scan_async_blockers.py` → exit 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene: no truncation-marker literals or SUB chars under `docs/epics/v17*`. This slice does **not** run production traffic, Firestore/Pinecone/cloud/provider calls, Firestore reads/writes, migration execution, benchmark, telemetry sink integration, or rollout approval.

**2026-06-19 local MCP REST/SSE get/search parity hardening slice:** Added `list_v17_default_mcp_memories(...)` plus `V17McpMemoryListResult` and wired MCP REST `GET /v1/mcp/memories` and MCP SSE `get_memories` through the same explicit V17 rollout decision contract used by MCP `search_memories`. Missing/malformed/no-grant/disabled/shadow states now return an empty get/list result and do not touch legacy memory reads unless the shared decision is explicitly `USE_LEGACY_SAFE`; enabled-but-empty V17 get/list returns an empty V17 result without legacy fallback. The get/list adapter uses the shared product default-memory read service with MCP policy and `archive_capability=False`, preserving Archive default-unavailable and preventing stale Short-term default visibility through the default visibility policy. This is still a narrow local hardening slice: it does not resolve all MCP category/review/manual/filter response-shape choices, does not claim route-level production proof, and does not run production traffic, Firestore/Pinecone/cloud/provider calls, Firestore reads/writes, benchmarks, telemetry sink integration, or approval. Oracle remains **BLOCKED / NO-GO** pending remaining P1-3 compatibility decisions.

Verification: RED adapter import `cd backend && pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → collection error `ImportError: cannot import name 'V17McpMemoryListResult'`; RED route parity after adapter implementation: same command → `2 failed, 19 passed in 0.16s` because REST/SSE get paths did not call `list_v17_default_mcp_memories(...)`. GREEN/format/focused: `black --line-length 120 --skip-string-normalization utils/mcp_memories.py routers/mcp.py routers/mcp_sse.py tests/unit/test_v17_mcp_memory_adapter.py && pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → `1 file reformatted, 3 files left unchanged`, `21 passed in 0.13s`. Focused non-V17 MCP search regression attempted `pytest tests/unit/test_mcp_search_memories.py -q` and is environment-blocked at collection with `ModuleNotFoundError: No module named 'fastapi'`. Full V17 regression: `cd backend && pytest tests/unit/test_v17_*.py -q` → `349 passed, 3 warnings in 2.15s`. P1-3 readiness from repo root: `python3 backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py --execute` → `BLOCKED True False False False False False False False False 13 11`. Async scan: `python3 backend/scripts/scan_async_blockers.py` from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`.

**2026-06-19 local Developer API category/response-shape compatibility hardening slice:** Hardened the first Developer API P1-3 runtime seam. `GET /v1/dev/user/memories` no longer forces category-filtered requests into a legacy-safe fallback solely because `categories` is present; it now performs the same app/key/scope grant authorization and server-owned rollout read for filtered and unfiltered Developer default-list calls, then passes normalized category values to `search_v17_default_developer_memories(...)`. The adapter filters V17 default-readable results locally without touching legacy memory reads unless a shared rollout decision explicitly returns `USE_LEGACY_SAFE`. Developer V17 formatting now propagates authoritative V17 `visibility` from `V17MemoryItem` through the product read result (`visibility_source="v17_memory_item.visibility"`) and marks compatibility-derived fields instead of silently fabricating them: `category=other` has `category_source="developer_v17_compatibility_default_no_source_category"`, `reviewed=False` has `reviewed_source="developer_v17_compatibility_default_no_review_state"`, `edited=False` has `edited_source="developer_v17_compatibility_default_no_edit_state"`, and `manually_added=False` has an explicit source marker. Archive remains default-unavailable through the existing Developer V17 policy (`archive_capability=False`), and stale Short-term remains filtered by the shared product default-memory visibility policy. This is still a narrow local hardening slice: it does not prove all Developer legacy client compatibility, does not make `/v3`, tools, agent, chat, or remaining MCP shape decisions, does not run production traffic, Firestore/Pinecone/cloud/provider calls, Firestore reads/writes, benchmarks, telemetry sink integration, or approval. Oracle remains **BLOCKED / NO-GO** pending remaining P1-3 compatibility decisions and production proof.

Verification: RED `cd backend && pytest tests/unit/test_v17_developer_memory_adapter.py -q` → `3 failed, 20 passed in 0.15s` (`developer_category_legacy_safe_fallback_explicit` still present, `search_v17_default_developer_memories()` rejected `categories`, and V17 Developer formatting returned fabricated `visibility='private'` instead of source `public`). GREEN/format/focused/regression: `cd backend && black --line-length 120 --skip-string-normalization utils/memory/v17_developer_memory_adapter.py utils/memory/v17_read_api.py routers/developer.py tests/unit/test_v17_developer_memory_adapter.py && pytest tests/unit/test_v17_developer_memory_adapter.py -q && pytest tests/unit/test_v17_*.py -q` → `4 files left unchanged`, `23 passed in 0.08s`, `352 passed, 3 warnings in 2.06s`. P1-3 readiness from repo root remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py --execute` → status `BLOCKED`, `read_only=true`, `mutation_allowed=false`, `network_or_provider_calls_executed=false`, `provider_calls_executed=false`, `firestore_reads_executed=false`, `firestore_writes_executed=false`, `benchmark_evidence_collected=false`, `production_rollout_approved=false`, `approval_claimed=false`, with 13 surfaces and 11 behavior cases. Async scan: `python3 backend/scripts/scan_async_blockers.py` from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene: no truncation-marker literals or SUB chars under `docs/epics/v17*`.

**2026-06-19 local MCP category/review/manual response-shape source hardening slice:** Hardened the next MCP P1-3 runtime seam. V17 MCP list/search formatting now exposes explicit compatibility-derived source semantics instead of silently fabricating unsupported legacy fields: `category=other` is accompanied by `category_source="mcp_v17_compatibility_default_no_source_category"`, `reviewed=False` by `reviewed_source="mcp_v17_compatibility_default_no_review_state"`, and `manually_added=False` by `manually_added_source="mcp_v17_compatibility_default_no_manual_state"`. MCP REST `CleanerMemory` exposes those additive fields plus V17/default policy metadata so REST responses do not strip the markers, and MCP SSE tool responses continue to return adapter dictionaries directly. `list_v17_default_mcp_memories(...)` now accepts category/review/manual filters and applies them to the explicit compatibility fields; REST `GET /v1/mcp/memories` and SSE `get_memories` pass normalized filters into the shared V17 list adapter. Archive remains default-unavailable through MCP policy (`archive_capability=False`), stale Short-term remains filtered by the shared product default-memory visibility policy, and malformed/no-grant/disabled rollout states still fail closed without unsafe legacy reads unless the shared decision explicitly returns `USE_LEGACY_SAFE`. This is still a narrow local hardening slice: it does not prove all MCP legacy client compatibility, does not resolve `/v3`, tools, agent, chat, production telemetry, or benchmark evidence, and does not run production traffic, Firestore/Pinecone/cloud/provider calls, Firestore reads/writes, benchmarks, telemetry sink integration, or approval. Oracle remains **BLOCKED / NO-GO** pending remaining P1-3 compatibility decisions and production proof.

Verification: RED `cd backend && pytest tests/unit/test_v17_mcp_memory_adapter.py -q` → `3 failed, 21 passed in 0.17s` (`category_source` missing, `list_v17_default_mcp_memories()` rejected `categories`, and REST `CleanerMemory` did not expose source fields). GREEN/format/focused/regression: `cd backend && black --line-length 120 --skip-string-normalization utils/mcp_memories.py routers/mcp.py routers/mcp_sse.py tests/unit/test_v17_mcp_memory_adapter.py && pytest tests/unit/test_v17_mcp_memory_adapter.py -q && pytest tests/unit/test_v17_*.py -q` → `1 file reformatted, 3 files left unchanged`, `24 passed in 0.13s`, `355 passed, 3 warnings in 2.06s`. P1-3 readiness from repo root remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py --execute` → status `BLOCKED`, `read_only=true`, `mutation_allowed=false`, `network_or_provider_calls_executed=false`, `provider_calls_executed=false`, `firestore_reads_executed=false`, `firestore_writes_executed=false`, `benchmark_evidence_collected=false`, `production_rollout_approved=false`, `approval_claimed=false`, with 13 surfaces and 11 behavior cases. Async scan: `python3 backend/scripts/scan_async_blockers.py` from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene: no truncation-marker literals or SUB chars under `docs/epics/v17*`.

**2026-06-19 local `/v3` external compatibility readiness slice:** Added safe-by-default `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` plus `backend/tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py` and registered the test in `backend/test.sh`. The artifact pins the exact `/v3` route surfaces that remain unresolved before broad runtime changes: `GET /v3/memories`, `POST /v3/memories`, `POST /v3/memories/batch`, `PATCH /v3/memories/{memory_id}`, `DELETE /v3/memories/{memory_id}`, and missing single-read/search surfaces (`GET /v3/memories/{memory_id}`, `GET /v3/memories/search`). It explicitly blocks on disabled/malformed/no-grant semantics, enabled-empty semantics, response shape/source metadata, Archive default-unavailable, category/filter behavior, unsafe legacy fallback after V17 writes, and cursor pagination stability. Default and `--execute` modes remain `status=BLOCKED`, read-only, no mutation, no Firestore reads/writes, no network/provider/cloud calls, no benchmarks, no production approval, and no approval claimed. No `/v3` runtime behavior changed; Oracle remains **BLOCKED / NO-GO** pending product-approved compatibility decisions and production proof.

Verification: RED `cd backend && pytest tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `4 failed in 0.07s` (missing runner/test.sh/docs). GREEN/format/focused/readiness/regression/async/docs hygiene: `cd backend && black --line-length 120 --skip-string-normalization scripts/v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py && pytest tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `2 files reformatted`, `4 passed in 0.05s`; readiness from repo root `python3 backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py --execute` → `BLOCKED True False False False False False False False False 7 7`; P1-3 readiness from repo root `python3 backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py --execute` → `BLOCKED True False False False False False False False False 13 11`; full V17 regression `cd backend && pytest tests/unit/test_v17_*.py -q` → `359 passed, 3 warnings in 2.20s`; async scan `python3 backend/scripts/scan_async_blockers.py` from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`; docs hygiene found no truncation-marker literals or SUB chars under `docs/epics/v17*`.

**2026-06-20 local `/v3` observability/telemetry approval readiness slice:** Added safe-by-default `backend/scripts/v17_p1_3_v3_observability_approval_readiness.py` plus `backend/tests/unit/test_v17_p1_3_v3_observability_approval_readiness.py`, registered it in `backend/test.sh`, and linked `observability_approval_readiness_proof` into both `/v3` external compatibility readiness and GET runtime-wiring readiness. The artifact inventories the required future `GET /v3/memories` telemetry labels for read source, route decision, low-cardinality failure reason, control/projection/account generation, cursor validation result/reason, canary cohort/enrollment, no-legacy-fallback, projection source/generation, request limit/cursor/no-offset shape, Archive/default visibility, rollback/read-disable gate, and approval owner/status. It links existing repository mechanisms honestly (`backend/routers/metrics.py` + `backend/utils/metrics.py`, `backend/utils/log_sanitizer.py`, and V17 read-decision model concepts) while marking them **not wired** to `/v3` GET. Blockers remain for a real memory `/v3` telemetry sink, structured event sink choice, server-owned canary artifact, rollback/read-disable gate wiring, and explicit product/privacy/operational approval. Static guardrails preserve no PII/raw memory content, no high-cardinality exception/user/session labels, no secret/cursor token logging, no production calls by default, and no approval claimed. Runtime remains **BLOCKED / NO-GO**; no `backend/routers/memories.py` behavior changed.

Verification: RED `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_p1_3_v3_observability_approval_readiness.py -q` → `6 failed in 0.09s` (missing runner/test.sh/docs/readiness links). GREEN/focused/full/async/docs outputs are recorded in the handoff for this commit; no production telemetry sink, Firestore, cloud, provider, Pinecone, or vector calls were executed.

**2026-06-19 local `/v3` compatibility decision-blocker evidence tightening slice:** Tightened the existing safe `/v3` readiness artifact instead of adding runtime behavior. The artifact now carries exact code-route evidence from `backend/routers/memories.py`: `GET /v3/memories` uses `response_model=List[MemoryDB]`, accepts only `limit`/`offset`, overrides the first page to `limit=5000`, and directly calls `memories_db.get_memories(uid, limit, offset)` with no route-local V17 read decision, no source metadata contract, no category/cursor/include_archive/source query support, and no enabled-empty V17 seam. It also pins write-side blockers for `POST /v3/memories` and `DELETE /v3/memories/{memory_id}` as legacy DB/vector write paths without V17 write/tombstone convergence, so read cutover cannot safely broaden legacy fallback after V17 writes. Added an explicit runtime-decision matrix for disabled, malformed, missing, no-default-memory-grant, enabled-empty, Archive-default, response-shape/source metadata, and cursor-pagination states; all unsafe legacy fallback remains disallowed unless a separate explicit legacy-safe product decision is made. Product dependencies are now enumerated for disabled/malformed/no-grant policy, enabled-empty policy, response-shape/source metadata, cursor pagination, and write convergence before read cutover. The artifact remains `status=BLOCKED`, read-only, no mutation, no Firestore reads/writes, no network/provider/cloud calls, no benchmarks, no production approval, and no approval claimed. No stale Short-term default visibility or Archive default exposure was introduced; no `/v3` runtime behavior changed. Oracle remains **BLOCKED / NO-GO**.

Verification: RED `cd backend && pytest tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `3 failed, 3 passed in 0.07s` (`KeyError: 'route_decorator'`, `KeyError: 'runtime_decision_matrix'`, missing summary counts). GREEN/format/focused: `cd backend && black --line-length 120 --skip-string-normalization scripts/v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py && pytest tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `1 file reformatted, 1 file left unchanged`, `6 passed in 0.05s`. Readiness from repo root: `python3 backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py --execute` → `BLOCKED True False False False False False False False False 7 7 8 5`. Full V17 regression: `cd backend && pytest tests/unit/test_v17_*.py -q` → `383 passed, 3 warnings in 2.34s`. Async scan: `python3 backend/scripts/scan_async_blockers.py` from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`.

**2026-06-19 local `/v3` pure compatibility decision-service seam:** Added the first Oracle-prescribed pure/local `/v3` V17 compatibility decision seam in `backend/utils/memory/v17_v3_compatibility.py` with unit proof in `backend/tests/unit/test_v17_v3_compatibility.py` and registered it in `backend/test.sh`. The service is not wired into `backend/routers/memories.py` and performs no app startup, no Firestore/Pinecone/cloud/provider/network calls, and no mutations. It models Oracle defaults only: non-enrolled users remain legacy-primary; enrolled missing/malformed/uid-mismatch/unsupported-schema/control-timeout states fail closed with 503 and no legacy fallback; absent default-memory grant denies with 403 as privacy/consent default and remains product-overridable only by explicit future decision; enabled-empty/projection-empty returns `200 []` from the V17 compatibility projection with no legacy fallback; write convergence or projection unreadiness fails closed before V17 read cutover; Archive remains default-unavailable; response body contract stays `List[MemoryDB]` with source/read-decision metadata as additive headers only; and V17 cursor mode is additive, opaque/signed/keyset/generation/projection-bound with no offset or first-page `limit=5000` override. The `/v3` readiness artifact now links this local proof as `decision_service_proof` while preserving `status=BLOCKED` / **NO-GO** and no production rollout approval.

Verification: RED `cd backend && pytest tests/unit/test_v17_v3_compatibility.py -q` → collection error `ModuleNotFoundError: No module named 'utils.memory.v17_v3_compatibility'`; RED readiness/docs/test-runner proof `cd backend && pytest tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `3 failed, 6 passed in 0.07s` (`KeyError: 'decision_service_proof'`, missing summary key, missing test.sh registration/docs links). GREEN verification is recorded with the commit summary for this slice; no runtime `/v3` route behavior changed and Oracle remains **BLOCKED / NO-GO**.

**2026-06-19 local `/v3` cursor signing/parsing seam:** Added the next Oracle-prescribed pure/local `/v3` compatibility seam in `backend/utils/memory/v17_v3_cursor.py` with unit proof in `backend/tests/unit/test_v17_v3_cursor.py` and registered it in `backend/test.sh`. The service is not wired into `backend/routers/memories.py` and performs no app startup, no Firestore/Pinecone/cloud/provider/network calls, and no mutations. It creates opaque HMAC-signed keyset cursors over `created_at desc` plus `memory_id desc`, binds `uid`, `account_generation`, `projection_generation`, `filter_hash`, `source`, and `read_mode`, enforces expiry, rejects tampering and mismatched caller context fail-closed, and explicitly disallows offset plus the legacy first-page `limit=5000` override in V17 cursor mode. The `/v3` readiness artifact now links this local proof as `cursor_service_proof` while preserving `status=BLOCKED` / **NO-GO** and no production rollout approval. Archive remains default-unavailable and no stale Short-term default-visible behavior was introduced.

Verification: RED `cd backend && pytest tests/unit/test_v17_v3_cursor.py -q` → collection error `ModuleNotFoundError: No module named 'utils.memory.v17_v3_cursor'`; RED readiness/docs/test-runner proof `cd backend && pytest tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `3 failed, 6 passed in 0.08s` (`cursor_service_proof`, summary key, missing test.sh/docs links). GREEN/format/focused/readiness/regression/async/docs hygiene: `cd backend && black --line-length 120 --skip-string-normalization utils/memory/v17_v3_cursor.py tests/unit/test_v17_v3_cursor.py scripts/v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py && pytest tests/unit/test_v17_v3_cursor.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `4 files left unchanged`, `13 passed in 0.07s`; focused/regression `pytest tests/unit/test_v17_v3_compatibility.py tests/unit/test_v17_v3_cursor.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q && pytest tests/unit/test_v17_*.py -q` → `21 passed in 0.10s`, `398 passed, 3 warnings in 2.32s`; `/v3` readiness summarized `BLOCKED True False False False False False False False False 7 7 8 5 8 2 13 True True`; P1-3 caller readiness summarized `BLOCKED True False False False False False False False False 13 11`; async scan from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`; docs hygiene `docs_hygiene 16 BAD=[]`. No runtime `/v3` route behavior changed and Oracle remains **BLOCKED / NO-GO**.

**2026-06-19 local `/v3` projection-readiness seam:** Added the next Oracle-prescribed pure/local V17-derived compatibility projection readiness seam in `backend/utils/memory/v17_v3_projection_readiness.py` with unit proof in `backend/tests/unit/test_v17_v3_projection_readiness.py` and registered it in `backend/test.sh`. The service is not wired into `backend/routers/memories.py` and performs no app startup, no Firestore/Pinecone/cloud/provider/network calls, and no mutations. It requires external create/update/delete convergence, expected/current account generation match, current projection generation, source `v17_derived_compatibility_projection`, current tombstone/delete fences, and source/projection commit/version/freshness fences before V17 `/v3` read cutover. Missing, stale, inconsistent, ad hoc mapping, or legacy direct-read projection states fail closed and disallow V17 cutover with no legacy fallback. Enabled-empty can return `[]` only when all readiness checks pass. The `/v3` readiness artifact now links this local proof as `projection_readiness_proof` while preserving `status=BLOCKED` / **NO-GO** and no production rollout approval. Archive remains default-unavailable and no stale Short-term default-visible behavior was introduced.

Verification: RED `cd backend && pytest tests/unit/test_v17_v3_projection_readiness.py -q` → collection error `ModuleNotFoundError: No module named 'utils.memory.v17_v3_projection_readiness'`; RED readiness/docs/test-runner proof `cd backend && pytest tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `3 failed, 6 passed in 0.08s` (`projection_readiness_proof`, summary key, missing test.sh/docs links). GREEN/format/focused/readiness/regression/async/docs hygiene: `cd backend && black --line-length 120 --skip-string-normalization utils/memory/v17_v3_projection_readiness.py tests/unit/test_v17_v3_projection_readiness.py scripts/v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py` → `4 files left unchanged`; `pytest tests/unit/test_v17_v3_projection_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `17 passed in 0.07s`; focused/regression `pytest tests/unit/test_v17_v3_projection_readiness.py tests/unit/test_v17_v3_compatibility.py tests/unit/test_v17_v3_cursor.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q && pytest tests/unit/test_v17_*.py -q` → `29 passed in 0.13s`, `406 passed, 3 warnings in 2.36s`; `/v3` readiness summarized `BLOCKED True False False False False False False False False 7 7 8 5 8 2 13 True True True`; P1-3 caller readiness summarized `BLOCKED True False False False False False False False False 13 11`; async scan from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`; docs hygiene `docs_hygiene 16 BAD=[]`. No runtime `/v3` route behavior changed and Oracle remains **BLOCKED / NO-GO**.

**2026-06-19 local `/v3` memory read-service composition seam:** Added the next Oracle-prescribed pure/local `/v3` compatibility read-service seam in `backend/utils/memory/v17_v3_memory_read_service.py` with unit proof in `backend/tests/unit/test_v17_v3_memory_read_service.py` and registered it in `backend/test.sh`. The service composes only caller-supplied local inputs plus the existing decision, cursor, and projection-readiness seams. It is not wired into `backend/routers/memories.py` and performs no app startup, no Firestore/Pinecone/cloud/provider/network calls, and no mutations. Non-enrolled users receive a legacy-primary plan marker only; enrolled missing/malformed/no-grant/write-convergence-not-ready/projection-not-ready states fail closed or deny without legacy fallback; projection-ready empty returns `200 []` with no legacy fallback; projection-ready pages pass through the caller-supplied `List[MemoryDB]`-compatible body and only add read-source/read-decision/next-cursor/Link headers. V17 cursor mode validates the signed cursor context, rejects offset and the legacy first-page `limit=5000` override, and never downgrades to offset or legacy. The `/v3` readiness artifact now links this local proof as `memory_read_service_proof` while preserving `status=BLOCKED` / **NO-GO** and no production rollout approval. Archive remains default-unavailable and no stale Short-term default-visible behavior was introduced.

Verification: RED `cd backend && pytest tests/unit/test_v17_v3_memory_read_service.py -q` → collection error `ModuleNotFoundError: No module named 'utils.memory.v17_v3_memory_read_service'`; RED readiness/docs proof after implementation `cd backend && pytest tests/unit/test_v17_v3_memory_read_service.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `1 failed, 15 passed in 0.13s` (missing docs link for `backend/utils/memory/v17_v3_memory_read_service.py`). GREEN/format/focused/readiness/regression/async/docs hygiene: `cd backend && black --line-length 120 --skip-string-normalization utils/memory/v17_v3_memory_read_service.py tests/unit/test_v17_v3_memory_read_service.py scripts/v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py && pytest tests/unit/test_v17_v3_memory_read_service.py tests/unit/test_v17_v3_projection_readiness.py tests/unit/test_v17_v3_compatibility.py tests/unit/test_v17_v3_cursor.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q && pytest tests/unit/test_v17_*.py -q` → `4 files left unchanged`, `36 passed in 0.16s`, `413 passed, 3 warnings in 2.38s`; `/v3` readiness summarized `BLOCKED True False False False False False False False False 7 7 8 5 8 2 13 True True True True`; P1-3 caller readiness summarized `BLOCKED True False False False False False False False False 13 11`; async scan from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`; docs hygiene `docs_hygiene 16 BAD=[]`. No runtime `/v3` route behavior changed and Oracle remains **BLOCKED / NO-GO**.

**2026-06-19 local `/v3` external write-convergence contract seam:** Added the next Oracle-prescribed pure/local `/v3` compatibility seam in `backend/utils/memory/v17_v3_write_convergence.py` with unit proof in `backend/tests/unit/test_v17_v3_write_convergence.py` and registered it in `backend/test.sh`. The service accepts only caller-supplied local convergence evidence and is not wired into `backend/routers/memories.py`; it performs no app startup, no Firestore/Pinecone/cloud/provider/network calls, and no mutations. It models create/update/delete convergence before V17 `/v3` read cutover: enrolled V17 accounts require a V17-authoritative write path, durable outbox fence, current account/projection generation, and projection update commit before create/update success/read cutover; delete additionally requires tombstone commit, projection removal commit, and vector cleanup/outbox fence before delete success/read cutover. Missing, stale, partial, swallowed-failure, independently dual-written without durable outbox, generation-mismatched, missing projection commit, or unavailable V17-authoritative write path states fail closed. Disabled external writes are safe only when reads remain blocked for the cohort or no external write surface is active. There is no enrolled V17 legacy direct-write fallback knob. The `/v3` readiness artifact now links this local proof as `write_convergence_proof` while preserving `status=BLOCKED` / **NO-GO** and no production rollout approval. Archive remains default-unavailable and no stale Short-term default-visible behavior was introduced.

Verification: RED `cd backend && pytest tests/unit/test_v17_v3_write_convergence.py -q` → collection error `ModuleNotFoundError: No module named 'utils.memory.v17_v3_write_convergence'`; RED readiness/test-runner/docs proof `cd backend && pytest tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `4 failed, 5 passed` (missing `write_convergence_proof`, summary key, implementation-shape link, and test.sh/docs links). GREEN verification is recorded with the commit summary for this slice; no runtime `/v3` route behavior changed and Oracle remains **BLOCKED / NO-GO**.

**2026-06-19 local `/v3` response-shape adapter proof:** Added the next Oracle-prescribed pure/local `/v3` request/response shape adapter proof in `backend/utils/memory/v17_v3_response_adapter.py` with unit proof in `backend/tests/unit/test_v17_v3_response_adapter.py` and registered it in `backend/test.sh`. The adapter consumes only a caller-supplied read-service envelope plus caller-supplied MemoryDB-compatible items; it is not wired into `backend/routers/memories.py` and performs no app startup, no Firestore/Pinecone/cloud/provider/network calls, and no mutations. It preserves the legacy `List[MemoryDB]` body contract: successful projection pages return the exact caller-supplied body, enabled-empty returns `[]` with V17 read-source/read-decision headers, and fail-closed/denied envelopes return no body data and no legacy fallback marker. V17 diagnostics are constrained to additive headers (`X-Omi-Memory-Read-Source`, `X-Omi-Memory-Read-Decision`, `X-Omi-Memory-Next-Cursor`, and `Link rel=next`); ad hoc V17 source/policy/cursor/read-decision/archive/stale Short-term fields in body items are rejected before exposure. The `/v3` readiness artifact now links this local proof as `response_adapter_proof` while preserving `status=BLOCKED` / **NO-GO** and no production rollout approval. Archive remains default-unavailable and no stale Short-term default-visible behavior was introduced.

Verification: RED `cd backend && pytest tests/unit/test_v17_v3_response_adapter.py -q` → collection error `ModuleNotFoundError: No module named 'utils.memory.v17_v3_response_adapter'`; RED readiness/docs proof `cd backend && pytest tests/unit/test_v17_v3_response_adapter.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `1 failed, 14 passed in 0.12s` (missing docs link for `backend/utils/memory/v17_v3_response_adapter.py`). GREEN/format/focused/readiness/regression/async/docs hygiene: `cd backend && black --line-length 120 --skip-string-normalization utils/memory/v17_v3_response_adapter.py tests/unit/test_v17_v3_response_adapter.py scripts/v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py` → `1 file reformatted, 3 files left unchanged`; `pytest tests/unit/test_v17_v3_memory_read_service.py tests/unit/test_v17_v3_projection_readiness.py tests/unit/test_v17_v3_compatibility.py tests/unit/test_v17_v3_cursor.py tests/unit/test_v17_v3_write_convergence.py tests/unit/test_v17_v3_response_adapter.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `47 passed in 0.23s`; `pytest tests/unit/test_v17_*.py -q` → `424 passed, 3 warnings in 2.40s`; `/v3` readiness summarized `BLOCKED True False False False False False False False False 7 7 8 5 8 2 13 True True True True True True`; P1-3 caller readiness summarized `BLOCKED True False False False False False False False False 13 11`; async scan from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`; docs hygiene `docs_hygiene 16 BAD=[]`. No runtime `/v3` route behavior changed and Oracle remains **BLOCKED / NO-GO**.

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

**2026-06-19 local chat prompt-boundary hardening slice:** Hardened the V17 Omi chat memory adapter so default and vector chat memory output now carries an explicit untrusted-evidence boundary notice, default-memory policy marker (`archive_default_visible=False`, `raw_provenance=False`), per-item `memory_id`, source markers (`v17_default_memory` or `v17_vector_memory`), JSON-quoted `content_quoted=...`, and a per-item content cap before text reaches the LangChain chat tool. Prompt-injection-like memory content is no longer emitted as raw bullet text, while relevance/tier/date metadata and existing explicit V17 read decisions are preserved. Archive remains default-unavailable, stale Short-term remains filtered by the shared default visibility policy, and malformed/no-grant/disabled rollout states still fail closed without unsafe legacy reads unless the explicit legacy-safe wrapper is requested. This is a narrow local P1-5 hardening seam only: it does not prove full router/tool production behavior, does not add central telemetry/benchmarks, and does not run production traffic, Firestore/Pinecone/cloud/provider calls, Firestore reads/writes beyond unit fakes, or approval.

Verification: RED `cd backend && pytest tests/unit/test_v17_chat_memory_adapter.py -q` → `4 failed, 6 passed in 0.13s` (adapter still emitted raw prompt text and lacked quoted content/source markers/policy boundary). GREEN/format/focused/regression: `cd backend && black --line-length 120 --skip-string-normalization utils/memory/v17_chat_memory_adapter.py tests/unit/test_v17_chat_memory_adapter.py && pytest tests/unit/test_v17_chat_memory_adapter.py -q && pytest tests/unit/test_v17_*.py -q` → `1 file reformatted, 1 file left unchanged`, `10 passed in 0.09s`, `361 passed, 3 warnings in 2.12s`. P1-3 readiness from repo root remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py --execute` exited 0 with `status=BLOCKED`, read-only, no mutation, no network/provider calls, no Firestore reads/writes, no benchmark, no production approval, no approval claimed, 13 surfaces, 11 behavior cases. `/v3` readiness from repo root remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py --execute` exited 0 with `status=BLOCKED`, read-only, no mutation, no network/provider calls, no Firestore reads/writes, no benchmark, no production approval, no approval claimed, 7 surfaces, 7 gaps. Async scan `python3 backend/scripts/scan_async_blockers.py` from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene found no truncation-marker literals or SUB chars under `docs/epics/v17*`.

**2026-06-19 local chat memory tool caller boundary guard:** Added a fail-closed caller guard for the actual Anthropic chat tool execution seam. `backend/utils/retrieval/agentic.py` now routes `search_memories_tool` and `get_memories_tool` results through `preserve_chat_memory_tool_result_boundary(...)` before they are appended as `tool_result.content`. Compliant V17 memory evidence is preserved only when `content_quoted=...` and `source_marker=v17_default_memory` or `source_marker=v17_vector_memory` keep the untrusted-evidence boundary notice, `policy=default_memory archive_default_visible=False raw_provenance=False`, and `archive_default_visible=False`; V17-like partial output that drops those markers is replaced with `No memories available for this request.` before model context. Denied and enabled-empty strings remain stable and do not introduce an unsafe legacy fallback. This is still a narrow local P1-5 seam: it does not prove tools REST or agent execute-tool wrappers, does not resolve `get_memories_tool` V17 list semantics, and does not run production traffic, Firestore/Pinecone/cloud/provider calls, telemetry, benchmarks, or approval.

Verification: RED `cd backend && pytest tests/unit/test_v17_chat_memory_tool_caller.py -q` → `ModuleNotFoundError: No module named 'utils.retrieval.tool_result_boundaries'` (`1 error in 0.14s`). GREEN/format/focused: `cd backend && black --line-length 120 --skip-string-normalization utils/retrieval/tool_result_boundaries.py utils/retrieval/agentic.py tests/unit/test_v17_chat_memory_tool_caller.py && pytest tests/unit/test_v17_chat_memory_tool_caller.py -q` → `1 file reformatted, 2 files left unchanged`, `4 passed in 0.07s`. Focused/regression: `pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_chat_memory_tool_caller.py -q && pytest tests/unit/test_v17_*.py -q` → `14 passed in 0.10s`, `365 passed, 3 warnings in 2.16s`. P1-3 readiness from repo root remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py --execute` exited 0 with `status=BLOCKED`, read-only, no mutation, no network/provider calls, no Firestore reads/writes, no benchmark, no production approval, no approval claimed, 13 surfaces, 11 behavior cases. `/v3` readiness from repo root remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py --execute` exited 0 with `status=BLOCKED`, read-only, no mutation, no network/provider/cloud/provider calls, no Firestore reads/writes, no benchmark, no production approval, no approval claimed, 7 surfaces, 7 gaps. Async scan `python3 backend/scripts/scan_async_blockers.py` from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene found no truncation-marker literals or SUB chars under `docs/epics/v17*`.

**2026-06-19 local tools REST, agent execute-tool, and chat get/list parity hardening slice:** Extended the P1-5 fail-closed V17 memory evidence-boundary guard to the tools REST memory endpoints and `POST /v1/agent/execute-tool`, so V17-like memory output through those wrappers is preserved only when the quoted-evidence boundary, `content_quoted=...`, source marker, default-memory policy marker, and `archive_default_visible=False` remain intact; malformed/partially unwrapped V17-like output collapses to `No memories available for this request.` before wrapper clients can treat it as instructions. Added `list_v17_default_chat_memories_decision_text(...)` and wired `get_memories_tool` through the same explicit Omi chat rollout decision family used by `search_memories_tool`: disabled/malformed/no-grant states deny without legacy fallback, enabled-empty returns `No V17 default memories found.`, and enabled list results are emitted as quoted V17 default evidence with `source_marker=v17_default_memory`, content caps, the untrusted-evidence boundary notice, and `archive_default_visible=False`. Legacy fallback is still only through explicit `USE_LEGACY_SAFE`; no stale Short-term or Archive default visibility was introduced. This remains a narrow local hardening slice: tools REST still needs a runtime V17 read adapter parity decision beyond boundary guarding, route-level FastAPI response-model proof is not complete, `/v3` compatibility remains blocked, and no production traffic, Firestore/Pinecone/cloud/provider calls, Firestore reads/writes beyond unit fakes, benchmarks, telemetry sink integration, or approval are claimed. Oracle remains **BLOCKED / NO-GO**.

Verification: RED `cd backend && pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_chat_memory_tool_caller.py -q` → collection error `ImportError: cannot import name 'list_v17_default_chat_memories_decision_text' from 'utils.memory.v17_chat_memory_adapter'` (`1 error in 0.19s`). GREEN/format/focused/regression: `cd backend && black --line-length 120 --skip-string-normalization utils/memory/v17_chat_memory_adapter.py utils/retrieval/tools/memory_tools.py routers/tools.py routers/agent_tools.py tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_chat_memory_tool_caller.py && pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_chat_memory_tool_caller.py -q && pytest tests/unit/test_v17_*.py -q` → `6 files left unchanged`, `17 passed in 0.10s`, `368 passed, 3 warnings in 2.12s`. P1-3 readiness from repo root remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py --execute` exited 0 with `status=BLOCKED`, `read_only=true`, `mutation_allowed=false`, `network_or_provider_calls_executed=false`, `provider_calls_executed=false`, `firestore_reads_executed=false`, `firestore_writes_executed=false`, `benchmark_evidence_collected=false`, `production_rollout_approved=false`, `approval_claimed=false`, with 13 surfaces and 11 behavior cases. `/v3` readiness from repo root remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py --execute` exited 0 with `status=BLOCKED`, `read_only=true`, `mutation_allowed=false`, `network_or_provider_calls_executed=false`, `provider_calls_executed=false`, `firestore_reads_executed=false`, `firestore_writes_executed=false`, `benchmark_evidence_collected=false`, `production_rollout_approved=false`, `approval_claimed=false`, with 7 surfaces and 7 gaps. Async scan `python3 backend/scripts/scan_async_blockers.py` from repo root exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`.

**2026-06-19 local tools REST and agent execute-tool route response-shape proof:** Added route-level/FastAPI-adjacent proof for the tools REST memory wrappers and `POST /v1/agent/execute-tool`. `backend/tests/unit/test_v17_tools_agent_route_response_shape.py` imports the actual router modules behind safe in-process dependency stubs, invokes the route functions through their real wrapper envelopes, validates `ToolResponse` and the new agent `ExecuteToolResponse` Pydantic response model, and pins quoted V17 memory evidence preservation versus fail-closed collapse for partial/unbounded V17-like output. The tests cover tools REST get/search and agent execute-tool result shapes, source markers (`v17_default_memory` and `v17_vector_memory`), `content_quoted=...`, `archive_default_visible=False`, prompt-injection-like text preserved only as quoted data, and stable `No memories available for this request.` collapse when required boundaries are missing. This is still a narrow local proof: it does not implement full tools REST runtime V17 read adapter parity, does not run FastAPI `TestClient` with installed production dependencies, does not change V17 memory read decisions, and does not resolve `/v3` compatibility. No production traffic, Firestore/Pinecone/cloud/provider calls, Firestore reads/writes, benchmarks, telemetry sink integration, or approval are claimed. Oracle remains **BLOCKED / NO-GO**.

Verification: RED `cd backend && pytest tests/unit/test_v17_tools_agent_route_response_shape.py -q` → `2 failed, 2 passed in 0.12s` because `routers.agent_tools` had no `ExecuteToolResponse`/route response model. GREEN/format/focused/regression: `cd backend && black --line-length 120 --skip-string-normalization routers/agent_tools.py tests/unit/test_v17_tools_agent_route_response_shape.py && pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_chat_memory_tool_caller.py tests/unit/test_v17_tools_agent_route_response_shape.py -q && pytest tests/unit/test_v17_*.py -q` → `1 file reformatted, 1 file left unchanged`, `21 passed in 0.17s`, `372 passed, 3 warnings in 2.20s`. P1-3 readiness remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py --execute` exited 0 with `status=BLOCKED`, `read_only=true`, `mutation_allowed=false`, `network_or_provider_calls_executed=false`, `provider_calls_executed=false`, `firestore_reads_executed=false`, `firestore_writes_executed=false`, `benchmark_evidence_collected=false`, `production_rollout_approved=false`, `approval_claimed=false`, 13 surfaces and 11 behavior cases. `/v3` readiness remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py --execute` exited 0 with `status=BLOCKED`, same safe/non-claim flags, 7 surfaces and 7 gaps. Async scan `python3 backend/scripts/scan_async_blockers.py` exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`.

**2026-06-19 local tools REST runtime V17 read adapter seam:** Wired tools REST memory read services through the same explicit V17 Omi chat read-decision adapters used by the LangChain chat memory tools. `backend/utils/retrieval/tool_services/memories.py` now calls `list_v17_default_chat_memories_decision_text(...)` for `get_memories_text` and `search_v17_default_chat_memories_vector_decision_text(...)` for `search_memories_text` before any legacy memory DB/vector path. Enabled V17 results keep the shared quoted-evidence boundary, source markers (`v17_default_memory` / `v17_vector_memory`), content caps, and `archive_default_visible=False`; enabled-empty states return stable V17 empty text; denied/malformed/no-grant/missing-vector states return `No memories available for this request.` and do not invoke legacy DB/vector fallbacks. Legacy fallback remains reachable only if the adapter explicitly returns `USE_LEGACY_SAFE`. Added `backend/tests/unit/test_v17_tools_rest_memory_runtime_adapter.py` and registered it in `backend/test.sh`, covering get/search parity, prompt-injection-like payloads preserved only as quoted data, Archive default-unavailable markers, enabled-empty states, and no legacy calls on denied V17 decisions. This is still a narrow local runtime seam: it does not run production traffic, Firestore/Pinecone/cloud/provider calls, Firestore reads/writes beyond unit stubs, benchmarks, telemetry sink integration, real FastAPI `TestClient` production-dependency proof, or approval. `/v3` remains blocked and Oracle remains **BLOCKED / NO-GO**.

Verification: RED `cd backend && pytest tests/unit/test_v17_tools_rest_memory_runtime_adapter.py -q` → `4 failed, 1 warning in 0.10s` because the tools REST service module had no V17 read adapter seam attributes. GREEN/format/focused/regression: `cd backend && black --line-length 120 --skip-string-normalization utils/retrieval/tool_services/memories.py tests/unit/test_v17_tools_rest_memory_runtime_adapter.py` → `1 file reformatted, 1 file left unchanged`; `pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_chat_memory_tool_caller.py tests/unit/test_v17_tools_agent_route_response_shape.py tests/unit/test_v17_tools_rest_memory_runtime_adapter.py -q && pytest tests/unit/test_v17_*.py -q` → `25 passed, 1 warning in 0.19s`, `376 passed, 3 warnings in 2.22s`. P1-3 readiness remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_caller_api_compatibility_readiness.py --execute` summarized `BLOCKED True False False False False False False False False 13 11`. `/v3` readiness remains safe/read-only and blocked: `python3 backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py --execute` summarized `BLOCKED True False False False False False False False False 7 7`. Async scan from repo root `python3 backend/scripts/scan_async_blockers.py` exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene found no literal truncation markers or SUB chars under `docs/epics/v17*`.

**2026-06-19 local tools REST/agent FastAPI TestClient readiness gap:** Added a safe readiness/proof gap artifact for the remaining P1-5/P1-3 real FastAPI `TestClient` route proof. `backend/scripts/v17_p1_5_tools_fastapi_testclient_readiness.py` and `backend/tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py` pin `backend/routers/tools.py` `GET /v1/tools/memories`, `backend/routers/tools.py` `POST /v1/tools/memories/search`, and `backend/routers/agent_tools.py` `POST /v1/agent/execute-tool` as the exact route surfaces still requiring production-dependency TestClient proof. FastAPI `TestClient` production-dependency proof remains BLOCKED/NOT_RUN because `fastapi` is not importable in the local Python verification environment; this artifact remains read-only and records no route execution, app startup, mutation, network/provider/cloud call, Firestore/Pinecone call, benchmark, telemetry sink integration, or approval. It inventories required future behavior cases for response-model serialization, quoted V17 evidence boundary preservation, denied/no-grant fail-closed output, enabled-empty stability, prompt-injection payload preservation as quoted data, and Archive plus stale Short-term default-unavailable behavior. Existing local non-TestClient proof remains limited to `backend/tests/unit/test_v17_tools_agent_route_response_shape.py` and `backend/tests/unit/test_v17_tools_rest_memory_runtime_adapter.py`. Oracle remains **BLOCKED / NO-GO**.

Verification: RED `cd backend && pytest tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py -q` → `4 failed in 0.15s` (missing readiness runner, test.sh registration, and docs links). GREEN/format/focused/readiness/regression: `cd backend && black --line-length 120 --skip-string-normalization scripts/v17_p1_5_tools_fastapi_testclient_readiness.py tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py && pytest tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py -q` → `2 files left unchanged`, `4 passed in 0.12s`; readiness from repo root `python3 backend/scripts/v17_p1_5_tools_fastapi_testclient_readiness.py --execute` summarized `BLOCKED NOT_RUN True False False False False False False False False False 3 6`; focused route/runtime regression `pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_chat_memory_tool_caller.py tests/unit/test_v17_tools_agent_route_response_shape.py tests/unit/test_v17_tools_rest_memory_runtime_adapter.py tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py -q` → `29 passed, 1 warning in 0.30s`; full V17 regression `pytest tests/unit/test_v17_*.py -q` → `380 passed, 3 warnings in 2.33s`. P1-3 readiness remained safe/read-only and blocked (`BLOCKED True False False False False False False False False 13 11`); `/v3` readiness remained safe/read-only and blocked (`BLOCKED True False False False False False False False False 7 7`). Async scan `python3 backend/scripts/scan_async_blockers.py` exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene found no literal truncation markers or SUB chars under `docs/epics/v17*`.

**2026-06-19 local tools REST/agent FastAPI TestClient dependency blocker evidence:** Attempted to move the remaining P1-5/P1-3 tools REST/agent route proof from readiness inventory into a real FastAPI `TestClient` proof. A temporary RED route-proof test targeting `GET /v1/tools/memories`, `POST /v1/tools/memories/search`, and `POST /v1/agent/execute-tool` failed at setup because the local verification Python cannot import `fastapi`. The dependency source is now pinned in the readiness artifact as `backend/requirements.txt` with `fastapi==0.121.0` and `httpx==0.28.0`; the bounded install command `python3 -m pip install --user 'fastapi==0.121.0'` failed with `externally-managed-environment` / PEP 668. To avoid unsafe host mutation, no `--break-system-packages` override, lockfile change, broad dependency install, app startup, TestClient route execution, network/provider/cloud call, Firestore/Pinecone call, mutation, benchmark, telemetry sink integration, or approval was performed. `backend/scripts/v17_p1_5_tools_fastapi_testclient_readiness.py` now emits exact dependency/install blocker evidence while preserving BLOCKED/NOT_RUN and all read-only non-claim flags. Oracle remains **BLOCKED / NO-GO**.

Verification: RED route proof attempt `cd backend && pytest tests/unit/test_v17_tools_fastapi_testclient_route_proof.py -q` → `4 errors in 0.08s` (`ModuleNotFoundError: No module named 'fastapi'`). Bounded install attempt `python3 -m pip install --user 'fastapi==0.121.0'` → exit 1, `externally-managed-environment` / PEP 668. RED blocker-artifact test `cd backend && pytest tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py -q` → `1 failed, 4 passed in 0.18s` (`KeyError: 'dependency_evidence'`). GREEN/format/focused: `cd backend && black --line-length 120 --skip-string-normalization scripts/v17_p1_5_tools_fastapi_testclient_readiness.py tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py && pytest tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py -q` → `1 file reformatted, 1 file left unchanged`, `5 passed in 0.15s`. Readiness from repo root summarized `BLOCKED NOT_RUN True False False False False False False False False False 3 6 fastapi==0.121.0 httpx==0.28.0 1 ModuleNotFoundError`. Focused route/runtime regression `pytest tests/unit/test_v17_chat_memory_adapter.py tests/unit/test_v17_chat_memory_tool_caller.py tests/unit/test_v17_tools_agent_route_response_shape.py tests/unit/test_v17_tools_rest_memory_runtime_adapter.py tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py -q` → `30 passed, 1 warning in 0.31s`; full V17 regression `pytest tests/unit/test_v17_*.py -q` → `381 passed, 3 warnings in 2.35s`. Async scan `python3 backend/scripts/scan_async_blockers.py` exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene found no literal truncation markers or SUB chars under `docs/epics/v17*`.

**2026-06-19 Oracle-prescriptive `/v3` compatibility defaults pin:** Consulted Oracle prescriptively with `consult-oracle --slug v3-v17-compat-prescriptive` over the `/v3` readiness artifact, route tests, Oracle/ticket docs, and `backend/routers/memories.py`. Oracle recommended an additive `/v3` compatibility adapter over V17-authoritative writes and a V17-derived `users/{uid}/memories` compatibility projection; it explicitly advised against ad hoc `memory_items`→`MemoryDB` mapping. The readiness artifact now records Oracle's concrete production defaults: non-enrolled users remain legacy-primary; enrolled malformed/missing/control-timeout states fail closed (`503`); absent/revoked default-memory grant defaults to privacy/consent denial (`403`) unless product explicitly separates rollout eligibility from consent; enabled-empty returns `200 []` with no legacy fallback; Archive is not launched on default `/v3`; body shape remains `List[MemoryDB]` with source/read diagnostics only in additive headers; cursor mode is additive, opaque/HMAC, keyset, and generation/projection-bound; the `limit=5000` first-page override is not used in V17 cursor mode; V17 writes and compatibility projection must land before V17 reads. Oracle identified only two irreducible escalations: the exact meaning of no default-memory grant and the legacy no-cursor compatibility window. No runtime `/v3` behavior changed, and no production traffic, Firestore/Pinecone/cloud/provider calls, Firestore reads/writes, mutation, benchmark, telemetry sink integration, or approval is claimed. Oracle remains **BLOCKED / NO-GO**.

Verification: Oracle browser run completed in 9m34s (`gpt-5.5-pro[browser]`; model-selection caveat `resolved=(unavailable); verified=no`). RED `cd backend && pytest tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `2 failed, 6 passed in 0.07s` (`KeyError: 'oracle_prescriptive_recommendations'`, `KeyError: 'oracle_implementation_shape'`). GREEN/format/focused/regression: `cd backend && black --line-length 120 --skip-string-normalization scripts/v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py && pytest tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q && pytest tests/unit/test_v17_*.py -q` → `2 files left unchanged`, `8 passed in 0.04s`, `385 passed, 3 warnings in 2.23s`. `/v3` readiness summarized `BLOCKED True False False False False False False False False 7 7 8 5 8 2 13`; P1-3 caller readiness summarized `BLOCKED True False False False False False False False False 13 11`. Async scan exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`. Docs hygiene check passed with no marker-literal or SUB chars under `docs/epics/v17*`.

**2026-06-19 `/v3` pure request-parameter adapter proof:** Added `backend/utils/memory/v17_v3_request_adapter.py` and `backend/tests/unit/test_v17_v3_request_adapter.py` as the next pure/local `/v3` proof. The adapter normalizes caller-supplied query parameters into a read-service request contract with no FastAPI dependency, route wiring, app startup, Firestore/Pinecone/cloud/provider/network calls, mutations, telemetry, benchmark, or approval. Legacy `limit`/`offset` remains legacy-primary only

Verification is recorded in `docs/epics/v17_memory_implementation_tickets.md`. Remaining `/v3` work: compose the request adapter with the existing pure read-service/response adapter in a local route-planning proof before any runtime route wiring.

**2026-06-19 `/v3` pure route-planning composition proof:** Added `backend/utils/memory/v17_v3_route_planner.py` and `backend/tests/unit/test_v17_v3_route_planner.py` as the next route-adjacent but not route-wired `/v3` proof. The planner composes local caller-supplied query/control/projection/write/page inputs through the pure request adapter, decision/read service, write-convergence proof, projection-readiness proof, memory read-service, and response adapter. Non-enrolled callers receive only a legacy-primary plan marker while preserving legacy limit/offset semantics. Enrolled valid requests produce a V17 `List[MemoryDB]` response envelope plus additive headers; invalid request/cursor/filter/Archive, malformed/no-grant/projection-not-ready/write-not-ready states fail closed or deny with no legacy fallback; enabled-empty returns `200 []`. No Archive default availability or stale Short-term default-visible behavior was introduced. No FastAPI route wiring, app startup, Firestore/Pinecone/cloud/provider/network calls, mutations, production traffic, benchmark, telemetry sink integration, or rollout approval is claimed.

Verification is recorded in `docs/epics/v17_memory_implementation_tickets.md`. Remaining `/v3` work: prove route-level dependency behavior under controlled TestClient/stubbed seams or add the next pure seam for production control/readiness inputs before any runtime `/v3` wiring.

**2026-06-20 `/v3` server-side control reader fake contract:** Added `backend/utils/memory/v17_v3_control_reader_contract.py` and `backend/tests/unit/test_v17_v3_control_reader_contract.py` as a pure/local, fake-injectable contract artifact for future server-owned V17 control reads. The seam defines typed request/control-state/route-decision objects plus a `V17V3ControlReader` protocol, but does not choose a real control source, import database/cloud/web clients, or touch `backend/routers/memories.py`. The decision mapping preserves non-enrolled legacy-primary routing with legacy offset behavior outside this contract, allows enrolled V17 projection only when all local gates are ready, and fails closed without legacy fallback for missing control docs, stale generations, no grant, projection/write/cursor/Archive gates, and stale Short-term default-hidden. Archive remains default-unavailable and stale Short-term is not default-visible by default. Oracle remains **BLOCKED / NO-GO** until real control source/API, emulator/security/IAM evidence, and runtime route proof exist.

Verification is recorded in `docs/epics/v17_memory_implementation_tickets.md`. Remaining `/v3` work: add a Firestore-emulator/API-backed server control reader proof and security/IAM evidence before any runtime `/v3` wiring.

**2026-06-19 `/v3` pure/static route-signature integration proof:** Added `backend/scripts/v17_p1_3_v3_route_signature_integration.py` and `backend/tests/unit/test_v17_p1_3_v3_route_signature_integration.py` as the next pure/static `/v3` integration proof and registered it in `backend/test.sh`. The proof uses AST/source inspection of `backend/routers/memories.py` only; it does not import FastAPI, router modules, app startup, Firestore/Pinecone/cloud/provider clients, or execute mutations. It pins current `GET /v3/memories`, `POST /v3/memories`, and `DELETE /v3/memories/{memory_id}` route signatures/body models; compares GET `limit`/`offset` to the pure request-adapter/route-planner contract; records the future params -> request adapter -> route planner -> response adapter seam; and preserves the non-claim that runtime still directly calls legacy `memories_db.get_memories(uid, limit, offset)`, legacy create/vector upsert, and legacy validate/delete/vector delete. Offset remains legacy-primary only for V17 cohorts, Archive remains default-unavailable, no stale Short-term default-visible behavior was introduced, and no runtime cutover, benchmark, telemetry sink integration, or approval is claimed. The `/v3` readiness artifact now links this static proof as `route_signature_integration_proof` while preserving `status=BLOCKED` / **NO-GO**.

Verification: RED `cd backend && pytest tests/unit/test_v17_p1_3_v3_route_signature_integration.py -q` → `5 failed in 0.08s` (missing proof runner and readiness link). GREEN/format/focused `black --line-length 120 --skip-string-normalization ... && pytest tests/unit/test_v17_v3_memory_read_service.py tests/unit/test_v17_v3_projection_readiness.py tests/unit/test_v17_v3_compatibility.py tests/unit/test_v17_v3_cursor.py tests/unit/test_v17_v3_write_convergence.py tests/unit/test_v17_v3_response_adapter.py tests/unit/test_v17_v3_request_adapter.py tests/unit/test_v17_v3_route_planner.py tests/unit/test_v17_p1_3_v3_route_signature_integration.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` → `2 files reformatted, 2 files left unchanged`, `65 passed in 0.33s`; full `pytest tests/unit/test_v17_*.py -q` → `442 passed, 3 warnings in 2.58s`; route-signature readiness summarized `BLOCKED True False False False False False False False False 3 5`; `/v3` readiness summarized `BLOCKED True False False False False False False False False 7 7 8 5 True True True True True True True True True`; P1-3 caller readiness summarized `BLOCKED True False False False False False False False False 13 11`; async scan exited 0 with pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`; docs hygiene `docs_hygiene 16 BAD=[]`. Remaining `/v3` work: prove route-level FastAPI dependency/response-model behavior under controlled stubs or production dependencies before any runtime `/v3` wiring.

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

### 2026-06-19 — P1-3 `/v3` controlled FastAPI route contract proof

Continued Oracle P1-3 with a narrow local FastAPI/TestClient proof for `/v3` response-model and dependency behavior, without changing runtime wiring or rollout verdict:

- Added `backend/scripts/v17_p1_3_v3_fastapi_route_contract.py`, a controlled isolated FastAPI mini-app proof for `GET /v3/memories` using the production `MemoryDB` response model. It deliberately does not import `backend/routers/memories.py` or the production app, and stubs only the `database._client.document_id_from_seed` import side effect needed to load the model without constructing Firestore clients.
- Added `backend/tests/unit/test_v17_p1_3_v3_fastapi_route_contract.py` and registered it in `backend/test.sh`.
- Linked the proof from `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` as `fastapi_route_contract_proof` while keeping `/v3` runtime status `BLOCKED`.
- Updated `backend/scripts/v17_p1_5_tools_fastapi_testclient_readiness.py` to preserve the prior PEP 668 `pip --user` blocker evidence and additionally record that repo-managed `backend/venv/bin/python` can import `fastapi==0.121.0`, `httpx==0.28.0`, `starlette==0.49.1`, and `TestClient=OK`. The tools route proof itself remains `BLOCKED/NOT_RUN`.
- The `/v3` proof covers `List[MemoryDB]` legacy-compatible body serialization, additive headers without body mutation, enabled-empty `[]`, fail-closed denied `403` with no body data and no legacy fallback marker, and filtering of V17-only body fields from the `List[MemoryDB]` response body.
- No Firestore, Pinecone, cloud, provider, network, production app startup, production traffic, mutation, benchmark, telemetry sink, or rollout approval is claimed. Archive remains default-unavailable and stale Short-term is not made default-visible.

Verification for this slice:

- RED: `backend/venv/bin/python -m pytest backend/tests/unit/test_v17_p1_3_v3_fastapi_route_contract.py -q` -> `4 failed` before adding the runner/docs/readiness/test.sh registration.
- GREEN focused route proof: `cd backend && venv/bin/python -m pytest tests/unit/test_v17_p1_3_v3_fastapi_route_contract.py -q` -> `4 passed in 1.09s`.
- Normal-env focused `/v3` proof suite: `env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_v3_memory_read_service.py tests/unit/test_v17_v3_projection_readiness.py tests/unit/test_v17_v3_compatibility.py tests/unit/test_v17_v3_cursor.py tests/unit/test_v17_v3_write_convergence.py tests/unit/test_v17_v3_response_adapter.py tests/unit/test_v17_v3_request_adapter.py tests/unit/test_v17_v3_route_planner.py tests/unit/test_v17_p1_3_v3_route_signature_integration.py tests/unit/test_v17_p1_3_v3_fastapi_route_contract.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py -q` -> `74 passed in 2.73s`.
- Normal-env full V17 regression: `env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_*.py -q` -> `446 passed, 3 warnings in 4.85s`.
- Venv proof summary: `venv/bin/python scripts/v17_p1_3_v3_fastapi_route_contract.py --execute` -> `BLOCKED PASSED True 5`.
- `/v3` readiness: `BLOCKED True False False False False False False False False 7 7 True`; tools TestClient readiness: `BLOCKED NOT_RUN True False True True True`.
- Async scan remains pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`; docs hygiene `docs_hygiene 16 BAD=[]`.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0/P1 gates and required real-service evidence are complete.

### 2026-06-19 — P1-3 `/v3` real-router import/dependency-map proof under stubs

Continued the safe bridge toward runtime with a controlled real-router import/dependency-map proof, without changing runtime behavior or rollout verdict:

- Added `backend/scripts/v17_p1_3_v3_real_router_dependency_map.py`, which uses static AST inspection plus a repo-venv subprocess probe to import the real `backend/routers/memories.py` only after explicit stubs are installed for unsafe dependencies: `database.memories`, `database.review_queue`, `database.vector_db`, `database._client`, `utils.executors`, `utils.apps`, and `utils.other.endpoints`.
- Added `backend/tests/unit/test_v17_p1_3_v3_real_router_dependency_map.py` and registered it in `backend/test.sh`.
- Linked the proof from `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` as `real_router_dependency_map_proof` while keeping `/v3` runtime status `BLOCKED`.
- The artifact pins import side effects blocked by stubs, every required import stub, route functions/decorators for `GET /v3/memories`, `POST /v3/memories`, and `DELETE /v3/memories/{memory_id}`, and dependency overrides required before any real-router TestClient proof.
- The future GET seam remains query params -> request adapter -> route planner -> response adapter. No `backend/main.py` import, production app startup, route inclusion, route handler execution, Firestore/Pinecone/cloud/provider/network call, mutation, runtime cutover, benchmark, telemetry sink integration, or rollout approval is claimed.

Verification for this slice:

- RED: `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_p1_3_v3_real_router_dependency_map.py -q` -> `4 failed in 0.07s` before adding the runner/readiness/docs/test.sh registration.
- GREEN focused route proof: `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_p1_3_v3_real_router_dependency_map.py -q` -> `4 passed in 0.83s`.
- Normal-env focused `/v3` proof suite: `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_v3_memory_read_service.py tests/unit/test_v17_v3_projection_readiness.py tests/unit/test_v17_v3_compatibility.py tests/unit/test_v17_v3_cursor.py tests/unit/test_v17_v3_write_convergence.py tests/unit/test_v17_v3_response_adapter.py tests/unit/test_v17_v3_request_adapter.py tests/unit/test_v17_v3_route_planner.py tests/unit/test_v17_p1_3_v3_route_signature_integration.py tests/unit/test_v17_p1_3_v3_fastapi_route_contract.py tests/unit/test_v17_p1_3_v3_real_router_dependency_map.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_5_tools_fastapi_testclient_readiness.py -q` -> `78 passed in 3.59s`.
- Normal-env full V17 regression: `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_*.py -q` -> `450 passed, 3 warnings in 5.53s`.
- Venv real-router proof test: `cd backend && venv/bin/python -m pytest tests/unit/test_v17_p1_3_v3_real_router_dependency_map.py -q` -> `4 passed in 0.85s`.
- Real-router dependency-map summary: `venv/bin/python scripts/v17_p1_3_v3_real_router_dependency_map.py --execute` -> `BLOCKED True True 7 3 False`.
- Existing FastAPI route-contract summary: `venv/bin/python scripts/v17_p1_3_v3_fastapi_route_contract.py --execute` -> `BLOCKED PASSED True 5`.
- `/v3` readiness: `BLOCKED True False False False False False False False False 7 7 True True`.
- Async scan remains pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`; docs hygiene `docs_hygiene 16 BAD=[]`.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0/P1 gates and required real-service evidence are complete.

### 2026-06-19 — P1-3 `/v3` real-router GET-only TestClient proof under stubs

Continued the safe bridge toward runtime with a controlled real-router GET-only TestClient proof, without changing runtime behavior or rollout verdict:

- Added `backend/scripts/v17_p1_3_v3_real_router_get_testclient.py`, which launches repo-managed `backend/venv/bin/python`, installs explicit import stubs, imports the real `routers.memories` module, builds a minimal `FastAPI()` app, overrides auth to `stubbed-test-uid`, includes the real router, and executes only `GET /v3/memories` plus `GET /v3/memories?limit=17&offset=3`.
- Added `backend/tests/unit/test_v17_p1_3_v3_real_router_get_testclient.py` and registered it in `backend/test.sh`.
- Linked the proof from `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` as `real_router_get_testclient_proof` while keeping `/v3` runtime status `BLOCKED`.
- The proof records current runtime behavior, not desired future cutover: `GET /v3/memories` still reaches stubbed legacy `memories_db.get_memories(uid, limit, offset)`. The default first page currently coerces `offset=0` to `limit=5000`; explicit `limit=17&offset=3` reaches the legacy stub unchanged.
- The response serializes through the real route response model as `List[MemoryDB]` compatible data; POST/DELETE/vector/persona/executor mutation paths remain unexecuted; V17 request adapter, route planner, and response adapter are not invoked yet.
- No `backend/main.py` import, production app startup, real Firestore/Pinecone/cloud/provider/network call, mutation, runtime cutover, benchmark, telemetry sink integration, or rollout approval is claimed. Archive remains default-unavailable and stale Short-term is not made default-visible.

Verification for this slice:

- RED: `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_p1_3_v3_real_router_get_testclient.py -q` -> `4 failed in 0.07s` before adding the runner/readiness/docs/test.sh registration.
- Parent recovery fixed the sibling-proof import by loading `v17_p1_3_v3_real_router_dependency_map.py` via `Path(__file__).with_name(...)`, then tightened the response assertion around behavior rather than optional `None` fields added by `response_model` serialization.
- Focused GREEN: `black --line-length 120 --skip-string-normalization scripts/v17_p1_3_v3_real_router_get_testclient.py tests/unit/test_v17_p1_3_v3_real_router_get_testclient.py scripts/v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_p1_3_v3_real_router_get_testclient.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py -q` -> `1 file reformatted, 3 files left unchanged`, `13 passed in 1.47s`.
- Venv proof: `venv/bin/python -m pytest tests/unit/test_v17_p1_3_v3_real_router_get_testclient.py -q` -> `4 passed in 1.39s`; `venv/bin/python scripts/v17_p1_3_v3_real_router_get_testclient.py --execute` -> `BLOCKED True True True True False 2`.
- Normal-env focused `/v3` proof suite: `82 passed in 4.99s`.
- Normal-env full V17 regression: `454 passed, 3 warnings in 7.18s`.
- `/v3` readiness: `BLOCKED True False False False False False False False False 7 7 True`; docs hygiene `docs_hygiene 16 BAD=[]`.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0/P1 gates and required real-service evidence are complete.

### 2026-06-19 — P1-3 `/v3` GET runtime-wiring remaining-gates readiness

Created the next safe readiness artifact after the real-router GET legacy baseline proof, without changing `backend/routers/memories.py` or runtime behavior:

- Added `backend/scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py`, a read-only BLOCKED inventory of the exact remaining real-service/runtime gates before future `GET /v3/memories` V17 cutover.
- Added `backend/tests/unit/test_v17_p1_3_v3_get_runtime_wiring_readiness.py` and registered it in `backend/test.sh`.
- Linked the new artifact from `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` as `get_runtime_wiring_readiness_proof` while keeping `/v3` runtime status `BLOCKED`.
- The gate inventory covers real server-side V17 cohort/enrollment/control fail-closed reads, real V17-derived MemoryDB-compatible compatibility projection reads including empty projection state, external create/update/delete write-convergence/source-of-truth evidence, real cursor signing secret/config and validation integration, real route-level dependency overrides/auth/rate-limit TestClient behavior, non-enrolled legacy compatibility including `offset=0 -> limit=5000`, enrolled no-grant/projection-not-ready/write-not-ready no-fallback behavior, Archive default-unavailable and stale Short-term not default-visible proof, observability/telemetry, and explicit approval gates.
- It ties each gate to existing local proof artifacts (`v17_v3_compatibility`, cursor, projection readiness, memory read service, write convergence, response/request adapters, route planner, route-signature integration, FastAPI route contract, real-router dependency map, and real-router GET TestClient) while marking real service/runtime evidence still missing.
- It documents a proposed safe future cutover sequence but deliberately does not implement runtime wiring, production writes, Archive default visibility, telemetry sink integration, cloud validation, benchmarks, or approval.

Verification for this slice:

- RED: `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_p1_3_v3_get_runtime_wiring_readiness.py -q` -> `6 failed in 0.08s` before adding the runner/test.sh/docs/external-readiness link.
- Focused GREEN and full verification outputs are recorded with the local commit summary for this slice.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0/P1 gates and required real-service evidence are complete.

### 2026-06-19 — P1-3 `/v3` GET dependency/auth/rate-limit TestClient proof

Added the next controlled route-level proof under stubs, without changing `backend/routers/memories.py` or the rollout verdict:

- Added `backend/scripts/v17_p1_3_v3_get_dependency_auth_readiness.py`, which launches repo-managed `backend/venv/bin/python`, imports the real `routers.memories` only after explicit stubs, and builds minimal FastAPI apps without importing `backend/main.py`.
- Added `backend/tests/unit/test_v17_p1_3_v3_get_dependency_auth_readiness.py` and registered it in `backend/test.sh`.
- Linked `get_dependency_auth_readiness_proof` from both `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` and `backend/scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py`.
- The proof records that current `GET /v3/memories` uses `auth.get_current_user_uid` (`utils.other.endpoints.get_current_user_uid` equivalent), has no current route-level rate-limit dependency, can be auth-overridden to a stub uid under TestClient, and is blocked in the controlled proof when the auth override is absent.
- With auth override, the route still calls stubbed legacy `memories_db.get_memories(uid, limit, offset)`, preserving the non-enrolled legacy baseline. No V17 cohort/control dependency is present or invoked.
- No runtime wiring, mutating route execution, real Firestore/Pinecone/cloud/provider/network call, benchmark, telemetry sink integration, Archive default visibility, stale Short-term default visibility, or approval is claimed.

Verification for this slice:

- RED: `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_p1_3_v3_get_dependency_auth_readiness.py -q` -> `6 failed in 0.08s` before adding the runner/test.sh/docs/readiness links.
- Focused GREEN: `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_p1_3_v3_get_dependency_auth_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_get_runtime_wiring_readiness.py -q` -> `21 passed in 1.51s`.
- Venv proof: `venv/bin/python -m pytest tests/unit/test_v17_p1_3_v3_get_dependency_auth_readiness.py -q` -> `6 passed in 1.41s`; readiness summary `PARTIAL PARTIAL True True True True False 1 False False False`.
- Normal-env focused `/v3` proof suite: `89 passed in 5.08s`; normal-env full V17 regression: `466 passed, 3 warnings in 8.63s`.
- Readiness summaries: GET dependency/auth `PARTIAL PARTIAL True True True True False 1 False False False`; GET runtime-wiring `BLOCKED BLOCKED True False False False 9 13 8 4`; `/v3` external compatibility `BLOCKED True False False False False False False False 7 7 True`.
- Async scan remains pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`; docs hygiene `docs_hygiene 16 BAD=[]`.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0/P1 gates and required real-service evidence are complete.

### 2026-06-19 — P1-3 `/v3` projection store/API readiness

Added the next real-service-adjacent gate as a safe readiness/local contract artifact for the V17-derived compatibility projection read API/store needed before future `GET /v3/memories` cutover:

- Added `backend/scripts/v17_p1_3_v3_projection_store_readiness.py`, a read-only BLOCKED inventory of the exact production store/API requirements for a V17-derived compatibility projection that can feed `/v3/memories`.
- Added `backend/tests/unit/test_v17_p1_3_v3_projection_store_readiness.py` and registered it in `backend/test.sh`.
- Linked `projection_store_readiness_proof` from both `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` and `backend/scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py`.
- The artifact records that the canonical projection path/API is still blocked until chosen, while pinning required MemoryDB materialization fields without V17-only body leakage, account/projection generation and freshness fences, source commit/version/evidence fences, delete/tombstone/vector cleanup fences, enabled-empty `[]` with no legacy fallback, Archive default-unavailable and stale Short-term not default-visible requirements, cursor pagination plus non-enrolled legacy offset compatibility, and a fake-injectable reader interface shape for future route wiring.
- It ties these requirements to the existing local pure projection-readiness, memory-read-service, request/response adapter, route-planner, write-convergence, cursor, FastAPI route-contract, and GET runtime-wiring proofs while marking real Firestore/API/emulator/cloud evidence still missing.
- No production store writes, runtime route wiring, real Firestore/Pinecone/cloud/provider/network call, emulator/cloud evidence, benchmark, telemetry sink integration, Archive default visibility, stale Short-term default visibility, or approval is claimed.

Verification for this slice:

- RED: `cd backend && pytest tests/unit/test_v17_p1_3_v3_projection_store_readiness.py -q` -> `7 failed in 0.09s` before adding the runner/test.sh/docs/readiness links.
- Focused GREEN and full verification outputs are recorded with the local commit summary for this slice.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0/P1 gates and required real-service evidence are complete.

### 2026-06-19 — P1-3 `/v3` control reader readiness

Added the next real-service-adjacent gate as a safe readiness/local contract artifact for the server-side V17 cohort/enrollment/control reader needed before future `GET /v3/memories` cutover:

- Added `backend/scripts/v17_p1_3_v3_control_reader_readiness.py`, a read-only BLOCKED inventory of exact production control reader requirements.
- Added `backend/tests/unit/test_v17_p1_3_v3_control_reader_readiness.py` and registered it in `backend/test.sh`.
- Linked `control_reader_readiness_proof` from both `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` and `backend/scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py`.
- The artifact records that the canonical control source/path/API is still blocked until chosen, requires server-owned control reads with no direct client control reads, defines a fake-injectable control reader interface shape without route wiring, and pins fail-closed semantics for missing control doc, stale generation, no grant, projection-not-ready, write-convergence-not-ready, invalid/missing cursor secret, Archive-not-allowed, and stale Short-term default-hidden states.
- Non-enrolled users preserve legacy-primary behavior including `offset=0 -> limit=5000` only on the legacy path; enrolled V17 users must not fall back to legacy on V17 gate failures.
- It ties these requirements to the existing local pure decision, cursor, projection, memory read-service, write-convergence, request/response adapter, route-planner, FastAPI route-contract, dependency/auth, projection-store, and GET runtime-wiring proofs while marking real Firestore/API/emulator/security rules/IAM evidence still missing.
- No production control reader, runtime route wiring, real Firestore/Pinecone/cloud/provider/network call, emulator/security-rules/IAM evidence, benchmark, telemetry sink integration, Archive default visibility, stale Short-term default visibility, or approval is claimed.

Verification for this slice:

- RED: `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_p1_3_v3_control_reader_readiness.py -q` -> `8 failed in 0.10s` before adding the runner/test.sh/docs/readiness links.
- Focused GREEN: `cd backend && black --line-length 120 --skip-string-normalization scripts/v17_p1_3_v3_control_reader_readiness.py tests/unit/test_v17_p1_3_v3_control_reader_readiness.py scripts/v17_p1_3_v3_external_compatibility_readiness.py scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_get_runtime_wiring_readiness.py && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_p1_3_v3_control_reader_readiness.py tests/unit/test_v17_p1_3_v3_projection_store_readiness.py tests/unit/test_v17_p1_3_v3_external_compatibility_readiness.py tests/unit/test_v17_p1_3_v3_get_runtime_wiring_readiness.py -q` -> `2 files reformatted, 4 files left unchanged`, `30 passed in 0.21s`.
- Normal-env focused `/v3` proof suite: `104 passed in 5.08s`; normal-env full V17 regression: `481 passed, 3 warnings in 8.54s`.
- Readiness summaries: control reader `BLOCKED BLOCKED True False False False 8 8 8 12 5 7`; GET runtime-wiring `BLOCKED BLOCKED True False False False 9 15 8 4`; `/v3` external compatibility `BLOCKED True False False False False False False False 7 7 True`.
- Async scan remains pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`; docs hygiene `docs_hygiene 16 BAD=[]`.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0/P1 gates and required real-service evidence are complete.

### 2026-06-20 — P1-3 `/v3` Firestore-emulator/security control reader readiness

Added the next real-service-adjacent readiness artifact for future Firestore-emulator/API-backed validation of the server-side V17 `/v3` control reader, without requiring cloud credentials or changing runtime behavior:

- Added `backend/scripts/v17_p1_3_v3_control_reader_emulator_readiness.py`, a safe default `BLOCKED`/`NOT_RUN` inventory that never starts Firestore emulators, reads or writes Firestore cloud/emulator data, calls cloud/provider/network services, mutates state, implements a production reader, wires routes, or claims approval.
- Added `backend/tests/unit/test_v17_p1_3_v3_control_reader_emulator_readiness.py` and registered it in `backend/test.sh`.
- Linked `control_reader_emulator_readiness_proof` from the `/v3` external compatibility readiness, control-reader readiness, and GET runtime-wiring readiness chains.
- The artifact records the exact prerequisites for emulator/API-backed proof against the resolved canonical server-side control source `users/{uid}/memory_control/state`; Firestore emulator config/env/tooling; control-doc fixture schema with `uid`, `schema_version`, `mode`, `mode_epoch`, `cutover_epoch`, `account_generation`, `fallback_projection_ready`, `persistent_v17_writes_started`, `writes_blocked`, `stage_gates`, and `grants`; an API-backed server-reader harness; and separate static rules, emulator-denial, and cloud IAM evidence.
- Security/IAM evidence requirements explicitly disallow direct client control reads, require future server-principal allowed evidence, and keep rules-static, emulator, and cloud IAM proofs separate.
- Required proof cases are pinned to `v17_v3_control_reader_contract.py`: non-enrolled legacy boundary, enrolled V17 projection allowed only when all gates are ready, and fail-closed/no-fallback cases for missing control doc, stale generation, no grant, projection not ready, write convergence not ready, invalid/missing cursor secret, Archive not allowed, and stale Short-term default-hidden.
- Local detection now finds the checked-in Firebase emulator configuration, explicit client-denial rules harness, and control-reader Admin-context emulator harness/script. `/v3` runtime remains **BLOCKED / NO-GO**.

Verification for this slice is superseded by the later 2026-06-20 emulator/API-backed proof section below. Production rollout remains **BLOCKED / NO-GO** until all Oracle P0/P1 gates and required real-service evidence are complete.

### 2026-06-20 — Oracle follow-up: reuse existing rollout control state for `/v3`

Consulted Oracle after David asked whether the codebase already had phased rollout and partial migration tracking. Oracle's prescriptive answer: the codebase already has the necessary primitives, and the `/v3` integration must reuse the existing canonical state instead of inventing a parallel control document.

- Canonical source is resolved to `users/{uid}/memory_control/state` via `V17Collections(uid).memory_control_state`.
- Existing rollout/migration primitives are `V17Mode.off/shadow/write/read`, `V17RolloutState`, `stage_gates`, `mode_epoch`, `cutover_epoch`, `account_generation`, `fallback_projection_ready`, `persistent_v17_writes_started`, `writes_blocked`, and `grants`.
- Added `backend/utils/memory/v17_v3_control_state_adapter.py`, which maps the existing persisted rollout state into the `/v3` control contract without reading `memory_items`, wiring routers, starting cloud/emulator services, or mutating state.
- Updated `backend/utils/memory/v17_v3_control_reader_contract.py` to use a `V17V3ControlReadResult` envelope so non-enrolled users can skip control reads while enrolled users with missing/malformed state fail closed.
- Effective mode is the lower-ranked value of configured global mode and persisted per-user mode. `off`, `shadow`, and `write` are legacy-primary; effective `read` requires global read gate, `omi_chat` default-memory grant, write convergence, projection readiness, account-generation equality, cursor secret, and Archive capability when explicitly requested.
- Removed synthetic route-control concepts that do not exist in the persisted rollout document: `control_generation`, `source_generation`, and Short-term freshness/default-visibility control fields. Stale Short-term remains a read-service/item-filtering concern, not a route-control gate.
- Readiness artifacts now mark the canonical source/path decision as locally resolved while preserving overall `/v3` runtime **BLOCKED / NO-GO** for emulator/API proof, rules/IAM, production reader, projection store, runtime wiring, observability, benchmark, and approval gates.

Verification for this slice:

- RED: focused adapter/contract tests failed before implementation with missing `utils.memory.v17_v3_control_state_adapter` and missing `V17V3ControlReadResult` imports (`2 errors in 0.16s`).
- Focused linked GREEN: `68 passed in 0.26s` for default rollout, adapter, contract, control-reader readiness, emulator readiness, runtime-wiring readiness, and external compatibility readiness tests.
- Full normal-env V17 regression: `509 passed, 3 warnings in 8.97s`.
- Readiness summaries: control reader `BLOCKED` with local adapter proof and canonical source resolved; emulator `BLOCKED` with persisted rollout fixture schema and no emulator harness claim.
- Async scan remains pre-existing `HIGH async helpers with blocking: 41`, `STRUCTURAL mixed await+sync DB: 10`.
- Docs hygiene `docs_hygiene 16 BAD=[]`.
- Production rollout remains **BLOCKED / NO-GO** until all Oracle P0/P1 gates and required real-service evidence are complete.

### 2026-06-20 — P1-3 `/v3` control reader emulator/API-backed proof against canonical state

Implemented and ran the next narrow local Firestore-emulator proof for the server-side V17 `/v3` control-reader seam against the accepted canonical path `users/{uid}/memory_control/state`, without wiring runtime `/v3` routes or touching production Firestore:

- Added `backend/scripts/v17_p1_3_v3_control_reader_emulator_test.py`, an emulator-only Python/Admin-context fixture harness. It refuses to run unless `FIRESTORE_EMULATOR_HOST` is set, seeds only local emulator docs, and maps emulator-read rollout fixtures through `read_v17_v3_control(...)`, `V17V3ControlState`, and `decide_v17_v3_control_route(...)`.
- Extended `backend/scripts/v17_firestore_rules_emulator_test.mjs` to assert signed-in client `getDoc`, `setDoc`, `updateDoc`, and `deleteDoc` are denied specifically for `users/{uid}/memory_control/state`.
- Added `npm run test:v17-v3-control-reader:emulator`, which starts the local Firestore emulator and runs both the client-denial rules proof and Admin-context control-reader mapping proof.
- Fixture schema matches the persisted rollout doc fields: `uid`, `schema_version`, `mode`, `mode_epoch`, `cutover_epoch`, `account_generation`, `fallback_projection_ready`, `persistent_v17_writes_started`, `writes_blocked`, `stage_gates`, and `grants`. Synthetic `cohort_enrolled`, `control_generation`, `projection_ready`, and Short-term freshness/default-visible control fields remain absent.
- Emulator proof cases cover V17 projection success plus missing, malformed, no-grant, projection-not-ready, write-convergence-not-ready, and global-gate-closed fail-closed outcomes with no legacy fallback. Non-enrolled no-read boundary remains covered by pure adapter tests.
- Readiness now records the canonical path/API as resolved to `users/{uid}/memory_control/state`, the fixture schema as locally proven in the harness, and the client-denial emulator harness as present. Overall `/v3` runtime remains **BLOCKED / NO-GO** until production route wiring, projection/observability/benchmark, cloud IAM/server-principal evidence, and approval gates pass.

Verification for this slice:

- RED: focused readiness test failed before implementation with `4 failed, 2 passed` on missing control-reader emulator harness/script, fixture readiness status, emulator security status, and summary counts; first emulator run also failed honestly on the Admin-context `write_not_ready` expectation, then the harness was corrected to use the write-convergence gate.
- Emulator: `npm run test:v17-v3-control-reader:emulator` starts the local Firestore emulator, prints expected client `PERMISSION_DENIED` logs, then `PASS: signed-in client read/write denial asserted for 8 V17 collections, users/{uid}/memory_control/state, and V17 app/key memory grant self-grant path` and `PASS: emulator Admin-context fixture read from users/{uid}/memory_control/state mapped through read_v17_v3_control/decide_v17_v3_control_route for 7 cases; no production Firestore or runtime /v3 wiring used`.
- Focused/linked, full V17, async scan, docs hygiene, and commit SHA are recorded in the subagent handoff for this slice.
- Non-claims preserved: no production cloud calls, no cloud IAM/server-principal proof, no `backend/routers/memories.py` wiring, no production reader/cutover approval, no Archive default visibility, and no stale Short-term route-control field.

### 2026-06-20 — P1-3 fenced `/v3` compatibility projection reader + emulator proof

Implemented Oracle's prescribed server-only V17 compatibility projection reader without route wiring:

- Added `backend/utils/memory/v17_v3_projection_reader_contract.py` and `backend/database/v17_v3_compatibility_projection.py` for a fenced reader over server-owned `users/{uid}/v3_compatibility_projection/state` and `users/{uid}/v3_compatibility_projection_items/{memory_id}`.
- Added `backend/tests/unit/test_v17_v3_compatibility_projection.py` with strict fail-closed coverage for missing/malformed state, schema/uid/source mismatch, caller-supplied expected account-generation mismatch, projection generation/commit/fence mismatch, incomplete write/delete/tombstone convergence, invalid payload whole-page failure, Archive/deleted/tombstone/stale Short-term default exclusion, stable `created_at DESC`, document-id DESC keyset pagination, and offset rejection.
- Added `backend/scripts/v17_p1_3_v3_projection_reader_emulator_test.py` and `npm run test:v17-v3-projection-reader:emulator`. The emulator proof asserts signed-in client denial for projection state/items via the shared rules harness, then proves Admin-context ready-empty, generation mismatch, stale commit/fence, Archive/tombstone/stale Short-term exclusion, and two-page keyset ordering.
- Updated `backend/database/v17_collections.py`, `firestore.rules`, `backend/scripts/v17_firestore_rules_emulator_test.mjs`, `backend/test.sh`, `package.json`, and `backend/scripts/v17_p1_3_v3_projection_store_readiness.py`. Projection store readiness now records local implementation/emulator evidence while overall runtime remains **BLOCKED / NO-GO**.

Verification for this slice:

- RED: `cd backend && env -u VIRTUAL_ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin python3 -m pytest tests/unit/test_v17_v3_compatibility_projection.py -q` initially failed with `ModuleNotFoundError: No module named 'database.v17_v3_compatibility_projection'`.
- GREEN/focused/full/emulator/readiness/async/docs hygiene and commit SHA are recorded in the subagent handoff for this slice.
- Non-claims preserved: no `backend/routers/memories.py`, `backend/main.py`, POST/PATCH/DELETE route change, no runtime `/v3` behavior change, no production rollout approval, no production Firestore/cloud/provider/vector calls, no Archive default visibility, no stale Short-term default visibility, no legacy fallback/merge for V17 projection failures, and no client-supplied generation trust.

### 2026-06-20 — P1-3 `/v3` trusted account-generation source/readiness

Added the next safe V17 `/v3` gate for trusted account-generation sourcing without changing `backend/routers/memories.py` or runtime behavior:

- Added `backend/utils/memory/v17_v3_account_generation_source.py`, a fake-injectable reader for the independent server-owned `users/{uid}/memory_state/head` account-generation source.
- Added `backend/tests/unit/test_v17_v3_account_generation_source.py` covering missing/malformed state head, uid mismatch, source mismatch, unsupported schema, malformed generation, read failure, and distinct state-head/control/projection documents.
- Added `backend/scripts/v17_p1_3_v3_account_generation_readiness.py` plus `backend/tests/unit/test_v17_p1_3_v3_account_generation_readiness.py`; registered both new tests in `backend/test.sh`.
- Linked `account_generation_readiness_proof` from `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` and `backend/scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py`. Runtime readiness now has an explicit `real_trusted_account_generation_source` BLOCKED gate.
- Future `GET /v3/memories` must derive `expected_account_generation` from the trusted state-head reader, then require trusted account generation == control account generation == projection account generation == cursor account generation when a cursor is present. Copying control/projection generation into the expected-generation request remains explicitly forbidden.
- Runtime remains **BLOCKED / NO-GO** pending state-head writer/emulator/runtime integration evidence proving the source is maintained by the server-owned account lifecycle/apply path and stays in lockstep with control/projection/cursor generations.

Verification for this slice is recorded in `docs/epics/v17_memory_implementation_tickets.md` and the local commit summary. Preserved non-claims: no route wiring, no production Firestore/cloud/provider/vector calls, no production rollout approval, no client-supplied generation trust, and no legacy fallback/merge for V17 failures.

### 2026-06-20 — P1-3 `/v3` state-head writer/emulator integration

Completed the next safe trusted account-generation source proof without changing `backend/routers/memories.py` or runtime behavior:

- Updated `backend/database/v17_memory_apply_store.py` so committed V17 apply writes `users/{uid}/memory_state/head` from committed server-owned `MemoryControlState` in the same transaction as `memory_control/state`, `memory_commits/{commit_id}`, `memory_items/*`, and `memory_outbox/*`.
- The state-head contains `schema_version`, `uid`, `source='v17_memory_state_head'`, `account_generation`, `head_commit_id`, `commit_sequence`, and `updated_at`, matching `read_v17_v3_trusted_account_generation(...)`.
- Extended `backend/tests/unit/test_v17_firestore_apply_store.py` to prove the written state-head is readable by the trusted generation reader.
- Extended `backend/scripts/v17_firestore_rules_emulator_test.mjs` to deny signed-in client direct `get`/`set`/`update`/`delete` on `users/{uid}/memory_state/head`.
- Extended `backend/scripts/v17_firestore_python_apply_emulator_test.py` and added `npm run test:v17-v3-state-head:emulator` to prove Admin/server apply writes the state-head on the local Firestore emulator and the trusted reader returns the committed account generation/head commit.
- Updated account-generation and runtime-readiness artifacts to record local writer/emulator evidence while preserving overall `/v3` runtime **BLOCKED / NO-GO** until route integration, remaining gates, telemetry, rollback, and approval are complete.

Verification for this slice:

- RED: `pytest tests/unit/test_v17_firestore_apply_store.py -q` -> `1 failed, 5 passed`, because `users/u1/memory_state/head` was not written.
- Focused GREEN: `52 passed in 0.30s`.
- Full normal-env V17 regression: `549 passed, 3 warnings in 8.87s`.
- Emulator proof: `npm run test:v17-v3-state-head:emulator` -> client PERMISSION_DENIED logs expected, `PASS: signed-in client read/write denial asserted for 10 V17 collections, users/{uid}/memory_control/state, users/{uid}/memory_state/head, and V17 app/key memory grant self-grant path`; `PASS: Python apply_long_term_patch_firestore committed and replayed V17 docs on Firestore emulator including users/{uid}/memory_state/head trusted account-generation state-head (...)`.
- Production rollout remains **BLOCKED / NO-GO**; no runtime `/v3` behavior, route wiring, production Firestore/cloud/provider/vector call, client-supplied generation trust, control/projection self-compare, or legacy fallback/merge was introduced.

### 2026-06-20 — P1-3 `/v3` real-router pre-wiring/fail-closed matrix proof

Added a safe pre-wiring proof that makes the future `GET /v3/memories` dispatcher behavior concrete while preserving current runtime behavior:

- Added `backend/scripts/v17_p1_3_v3_real_router_fail_closed_matrix.py` and `backend/tests/unit/test_v17_p1_3_v3_real_router_fail_closed_matrix.py`; registered the test in `backend/test.sh`.
- Linked `real_router_fail_closed_matrix_proof` from `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` and `backend/scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py`.
- Current real-router baseline remains legacy-only under stubs via the existing TestClient proof: `offset=0 -> limit=5000`, explicit nonzero `limit`/`offset` preserved, no V17 adapters invoked, and no mutating routes executed.
- Future dispatcher matrix is intentionally proven only at a pure helper/route-planner seam with fake readers: non-enrolled legacy calls legacy only; enrolled projection success calls projection reader only; fail-closed states call neither legacy nor projection; no-grant/archive denial returns 403; projection/control/account/cursor mismatch fails closed; enabled-empty returns `[]` with no legacy fallback.
- Runtime remains **BLOCKED / NO-GO**. No `backend/routers/memories.py` change, no runtime `/v3` behavior change, no production rollout approval, no production Firestore/cloud/provider/vector call, no Archive default visibility, no stale Short-term default visibility, and no legacy fallback/merge for V17 failures is claimed.

### 2026-06-20 — P1-3 `/v3` write-convergence/delete/tombstone pre-runtime matrix proof

Added the next safe pre-runtime proof for the write-convergence/delete/tombstone gates future `GET /v3/memories` must require before returning V17 projection data:

- Added `backend/scripts/v17_p1_3_v3_write_convergence_tombstone_matrix.py` and `backend/tests/unit/test_v17_p1_3_v3_write_convergence_tombstone_matrix.py`; registered the test in `backend/test.sh`.
- Linked `write_convergence_tombstone_matrix_proof` from `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` and `backend/scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py`.
- The matrix uses only pure route-planner/projection/write-convergence seams with fake caller contexts and fake in-memory readers. It proves V17 projection success requires create, update, and delete convergence plus matching account/projection/tombstone/freshness fences.
- Fail-closed cases cover create convergence false, update convergence false, delete convergence false, tombstone fence missing, tombstone generation stale/mismatched, and enabled-empty with missing tombstone fence. These cases call no fake legacy reader, call no fake projection reader, and disallow legacy fallback or V17/legacy merge.
- Default visibility non-claims are preserved through explicit Archive default-denied and stale Short-term default-hidden cases.
- Runtime remains **BLOCKED / NO-GO**. No `backend/routers/memories.py` change, no runtime `/v3` behavior change, no production rollout approval, no production Firestore/cloud/provider/vector call, no Archive default visibility, no stale Short-term default visibility, and no legacy fallback/merge for V17 failures is claimed.

### 2026-06-20 — P1-3 `/v3` cursor secret/source integration readiness

Added a safe pre-runtime readiness proof for future `/v3` cursor-secret/source integration while keeping the real route blocked:

- Added `backend/scripts/v17_p1_3_v3_cursor_secret_readiness.py` and `backend/tests/unit/test_v17_p1_3_v3_cursor_secret_readiness.py`; registered the test in `backend/test.sh`.
- Linked `cursor_secret_readiness_proof` from `backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py` and `backend/scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py`.
- The readiness artifact does not read environment secret values and does not invent production secret material. It records the exact blocker: no existing runtime-owned V17 `/v3` cursor signing secret/config source is wired; a server-owned `V17_V3_CURSOR_SIGNING_SECRET` or managed secret must be injected before runtime route changes.
- Under fake server-owned secret material only, the pure cursor matrix proves first-page no-cursor needs no client-secret trust; signed cursors preserve account generation, projection generation, source, and keyset; and tampered, expired, account/projection generation mismatch, source mismatch, wrong-secret, and client-supplied-secret cases fail closed without legacy fallback.
- Runtime remains **BLOCKED / NO-GO**. No `backend/routers/memories.py` change, no runtime `/v3` behavior change, no production rollout approval, no production secret read, no production Firestore/cloud/provider/vector call, no client-supplied cursor secret trust, no Archive default visibility, no stale Short-term default visibility, and no legacy fallback/merge for V17 failures is claimed.

### 2026-06-20 — P1-3 `/v3` canary enrollment and approval artifact schema seam

Added the local-only canary/approval artifact seam behind the observability approval gate without changing `backend/routers/memories.py` or runtime behavior:

- Added `backend/utils/memory/v17_v3_canary_approval.py` and `backend/tests/unit/test_v17_v3_canary_approval_artifact.py`.
- The schema pins server-owned artifact fields for future `GET /v3/memories`: exact route scope, bounded cohorts (`shadow`, `canary_1`, `canary_5`, `canary_25`), owner/status fields, rollback plan, monitoring gates, expiration/issued timestamps, and approval ids/timestamps as metadata only.
- Validation fails closed for missing/malformed artifacts, unsupported or mismatched cohorts, missing rollback plans, missing monitoring gates, pending/rejected/missing approvals, stale artifacts, route mismatches, and high-cardinality/sensitive key or value misuse (user/session ids, cursor tokens, secrets, request payloads, raw memory content).
- Approved artifacts produce only bounded telemetry labels (`canary_cohort`, `canary_enrollment`, `approval_owner`, `approval_status`, `approval_artifact_status`, `route_scope`), with no raw user ids, memory content, secrets, cursor tokens, or request payloads.
- `backend/scripts/v17_p1_3_v3_observability_approval_readiness.py` now links the local proof as `v17_v3_canary_approval_artifact_schema_seam` while keeping readiness **BLOCKED** and preserving no production rollout approval.
- Runtime remains **BLOCKED / NO-GO**. No `backend/routers/memories.py` change, no runtime `/v3` behavior change, no production telemetry sink, no production Firestore/cloud/provider/vector calls, no Archive default visibility, no stale Short-term default visibility, and no legacy fallback/merge is claimed.

### 2026-06-20 — P1-3 `/v3` local telemetry API/sink and rollback/read-disable config seam

Added the local pure seam behind the observability/approval readiness gate without changing `backend/routers/memories.py` or runtime behavior:

- Added `backend/utils/memory/v17_v3_local_telemetry.py` and `backend/tests/unit/test_v17_v3_local_telemetry.py`.
- The telemetry seam builds a sanitized low-cardinality future `GET /v3/memories` decision event, defaults to a no-op sink, and supports only injected fake sinks in tests; it rejects raw memory content, cursor tokens, secret material, user/session identifiers, arbitrary extra labels, and high-cardinality failure reasons.
- The rollback/read-disable seam is pure/config-shaped: enrolled V17 users fail closed for missing, malformed, disabled, or emergency-disabled server-owned config, while non-enrolled callers remain outside the V17 read seam.
- `backend/scripts/v17_p1_3_v3_observability_approval_readiness.py` now links this local proof as `v17_v3_local_telemetry_and_rollback_seam`; remaining blockers are real route wiring, real telemetry sink/config source, canary enrollment artifact, rollback gate wiring, and explicit product/privacy/ops approval.
- Runtime remains **BLOCKED / NO-GO**. No production telemetry sink, Firestore/cloud/provider/vector call, PII/raw memory telemetry, secret/cursor-token logging, Archive default visibility, stale Short-term default visibility, legacy fallback/merge, or production approval is claimed.
