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

## Not-run / not-claimed caveats preserved

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

## Not-run / not-claimed caveats preserved

- Oracle review has now run and is recorded here, but it blocks production rollout.
- Real Pinecone validation was **not** run.
- Real Firestore/cloud validation was **not** run.
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
