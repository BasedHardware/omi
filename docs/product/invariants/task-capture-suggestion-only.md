# INV-TASK-2: Automatic task capture proposes, it never writes

**Status:** locked

**Statement:** A task the user did not ask for is never written to their task list. Every automatically derived task — from a conversation, from the screen, from a proactive notification — is a pending Candidate that becomes an action item only through an explicit user gesture, and a Candidate nobody acts on expires rather than accumulating.

## Why

Measured on a dogfood account on 2026-08-20: of 124 surviving action items, 3 carried `source='manual'`. 340 of 353 accepted Candidates were accepted within two seconds of creation — machine acceptance, not a human gesture — and 1,014 Candidates sat pending with no expiry, growing by ~100/day. Four independent code paths were writing automatic tasks directly, each of them a fallback rather than a happy path.

## MUST NOT

- Return a capture-policy outcome that means "create a task now". `auto_accept_silent` and `create_direct` are deleted, not disabled.
- Create a Candidate and accept it in the same request, on any surface.
- Fall back to an action-item writer when the Candidate path is unavailable, disabled, or errors. Defer and retry instead; silence is the correct failure.
- Let a rollout, workflow mode, or capability default route capture onto a writer. `off` is what a control endpoint reports when its own read fails, so it must be inert, never "legacy staging".
- Expose an acceptance path on a capture-delivery client. A pipeline that *can* accept eventually will.
- Let one rejected extraction item drag its siblings onto a writer. Policy rejection is per item.
- Admit a proposal the Suggested surface will not show. A stored, invisible Candidate is a dropped one that also costs storage.
- Let the backend and desktop capture policies diverge. They share one frozen fixture.

## Surfaces

- Backend conversation extraction, the shared capture policy, and the Candidate lifecycle
- Desktop screen extraction, candidate delivery, and the suggestion moment
- Suggested-task projections on desktop and mobile, and the conversation-summary action-item list
- Chat, MCP, developer API and manual create — **out of scope**: these carry a real user gesture and write directly by design

## Guard tests

- `.github/scripts/check_task_capture_authority.py` — static: no creating outcome, no accept in extraction, no writer in `_save_action_items`, no accept on the capture client, and no create anchor on a source governed by the shared capture policy
- `.github/scripts/test_check_task_capture_authority.py` — proves that guard fails on each shape that shipped
- `backend/tests/unit/test_conversation_suggestion_visibility.py` — every admitted capture kind reaches the Suggested surface
- `backend/tests/unit/test_backend_candidate_capture.py` — extraction proposes and never accepts; a rejected item is dropped alone
- `backend/tests/unit/test_task_intelligence_contract_freeze.py` — the frozen fixture's outcomes stay disjoint from the creating ones
- `backend/tests/unit/test_process_conversation_usage_context.py` — capture reporting itself unavailable still touches no writer
- `desktop/macos/Desktop/Tests/TaskIntelligenceContractFixtureTests.swift` — no workflow mode permits a legacy effect; delivery leaves the proposal pending

## Path globs

- `backend/utils/task_intelligence/capture_policy.py`
- `backend/utils/task_intelligence/conversation_capture.py`
- `backend/utils/task_intelligence/backend_capture.py`
- `backend/utils/conversations/process_conversation.py`
- `backend/database/candidates.py`
- `backend/routers/candidates.py`
- `backend/routers/staged_tasks.py`
- `backend/config/task_intelligence_sources_v1.json`
- `backend/tests/unit/fixtures/task_intelligence/capture_v2.json`
- `desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/TaskExtraction/**`
- `desktop/macos/Desktop/Sources/MainWindow/Tasks/SuggestedTasksStore.swift`

## PR rule

Name this invariant ID in the PR body if you touch the path globs above.
