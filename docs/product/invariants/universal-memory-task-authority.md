# INV-MEM-5: Universal memory and task authority

**Status:** proposed

**Proposed on:** 2026-08-11

**Statement:** Every authenticated account uses one canonical memory policy and one task-intelligence policy. Historical memory and staged-task documents may remain physically readable through bounded compatibility adapters, but UID allowlists, store origin, clients, and rollout metadata never select a different product authority.

This rule and its guards must remain unchanged for seven days before a separate PR may promote it to `locked`.

## MUST NOT

- Grant or deny memory, task intelligence, goals, workstreams, recommendations, or Chat-first through a fixed UID list.
- Route an account to different memory or task business logic because it is enrolled, dogfood, canonical, legacy, or outside a cohort.
- Create or mutate a historical `users/{uid}/memories` row after universal canonical writes are enabled, except idempotent redaction/deletion owned by lazy materialization or account deletion.
- Treat the historical adapter as a mutation, lifecycle, privacy, graph, vector, or task authority.
- Fall back to a legacy writer or unfenced historical read when canonical state, tombstone, generation, or readiness validation fails.
- Expose the same logical record twice because canonical and historical physical records coexist.
- Use text similarity to infer record identity, mutation ownership, or deletion precedence.
- Require a bulk historical backfill, LLM reprocessing, or re-embedding before an existing user can use universal memory or task features.
- Remove account-generation, ownership, idempotency, device, privacy, proactive-user-choice, or global incident/cost fences while deleting cohort logic.
- Let export, delete-all, account deletion, source deletion, search, graph, MCP, developer tools, or released client APIs bypass the universal authority.

## Surfaces

- Memory REST, chat, agent, MCP, tools, integration, developer, import, and conversation-processing paths
- Memory apply, consolidation, maintenance, graph, search/vector/keyword projection, review, privacy, export, and account deletion
- Task Candidate, action-item, goal, workstream, recurrence, recommendation, Chat-first, staged-task compatibility, and proactive interruption paths
- Flutter, macOS, Windows, web, OpenAPI, generated clients, runtime/deploy contracts, runbooks, and operational telemetry

## Guard tests

- `backend/tests/unit/test_universal_memory_task_authority.py` - arbitrary authenticated UIDs share one memory/task decision; static production imports and legacy-writer ownership are constrained
- `backend/tests/unit/test_memory_service_parity.py` - canonical and historical records share one released service contract
- `backend/tests/unit/test_memory_mutation_contract.py` - historical mutations materialize or tombstone through canonical authority without resurrection
- `backend/tests/unit/test_backend_candidate_capture.py` - universal Candidate capture has explicit no-drop/no-duplicate behavior
- `backend/tests/unit/test_account_deletion_projection_fence.py` - delete fences close over both origins and derived providers
- `backend/scripts/check_app_client_openapi_compatibility.py` - released clients remain directionally compatible

Guard names may be refined during implementation, but equivalent behavioral and static coverage must land in the same PR before this proposal can be locked.

## Path globs

- deleted UID-cohort selectors and any attempted replacement
- `backend/config/memory_rollout.py`
- `backend/utils/memory/**`
- `backend/database/memories.py`
- `backend/database/memory_*.py`
- `backend/models/memory_*.py`
- `backend/models/product_memory.py`
- `backend/routers/memories.py`
- `backend/routers/memory_*.py`
- `backend/routers/knowledge_graph.py`
- `backend/services/users/data_export.py`
- `backend/services/users/account_deletion.py`
- `backend/utils/task_intelligence/**`
- `backend/database/candidates.py`
- `backend/database/goals.py`
- `backend/database/workstreams.py`
- `backend/database/task_recommendations.py`
- `backend/database/chat_first_intents.py`
- `backend/database/recurrence_inbox.py`
- `backend/routers/canonical_task_access.py`
- `backend/routers/candidates.py`
- `backend/routers/goals.py`
- `backend/routers/workstreams.py`
- `backend/routers/task_recommendations.py`
- `backend/routers/chat_first.py`
- `app/lib/backend/http/api/memories.dart`
- `app/lib/backend/schema/memory.dart`
- `desktop/macos/Desktop/Sources/**`
- `desktop/windows/src/**`
- `docs/memory/**`
- `docs/epics/universal_memory_task_convergence.md`
- `docs/runbooks/*memory*`
- `docs/rollout/*memory*`
- `backend/deploy/runtime_env*`
- `.github/workflows/gcp_memory_maintenance_job*.yml`

## PR rule

Name `INV-MEM-5` in the PR body if you touch the path globs above while universal convergence is in progress.

## Related invariants

- `INV-MEM-1`: exactly three product memory layers and default access policy
- `INV-MEM-2`: vector results hydrate against authoritative state
- `INV-MEM-3`: canonical failure never bleeds into legacy fallback
- `INV-MEM-4`: canonical consolidation is the sole new Long-term admission authority
- `INV-TASK-1`: task list completeness and bounded pagination
- `INV-CUTOVER-1`: account-generation and whole-account cutover authority must not be duplicated
- `INV-DATA-1`: production-family identity and data-plane continuity
- `INV-INT-1`: integration behavior is contract- and harness-backed

## Implementation record

[`docs/epics/universal_memory_task_convergence.md`](../../epics/universal_memory_task_convergence.md) is the canonical scope ledger, phased deletion checklist, and verification plan.
