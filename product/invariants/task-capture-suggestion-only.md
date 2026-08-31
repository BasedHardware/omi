# INV-TASK-2: Capture proposes only where a Suggested surface exists

**Status:** locked

**Statement:** Screen capture, proactive capture, and desktop conversation capture never write a task. Each derived task is a pending Candidate that becomes an action item only through an explicit user gesture, and a Candidate nobody acts on expires rather than accumulating. A client with no Suggested surface is not proposed to at all: its conversation extraction writes what the conservative prompt admits, and admits nothing when nothing qualifies.

## Why

Measured on a dogfood account on 2026-08-20: of 124 surviving action items, 3 carried `source='manual'`. 340 of 353 accepted Candidates were accepted within two seconds of creation — machine acceptance, not a human gesture — and 1,014 Candidates sat pending with no expiry, growing by ~100/day. Four independent code paths were writing automatic tasks directly, each of them a fallback rather than a happy path.

That volume is a property of screen capture, which samples continuously. Conversation extraction is bounded by the conversation and gated by a prompt that admits explicit "Hey Omi" commands and the few concrete commitments, or returns nothing. Proposing from it on a client with nowhere to review proposals is the failure this invariant exists to prevent, one level up: between 2026-08-23 and 2026-08-30 every phone, pendant and watch conversation produced Candidates no mobile surface renders, and they expired unseen at two days. Where review is possible the queue holds; where it is not, the extractor's own filter decides and the result is a task.

## MUST NOT

- Return a capture-policy outcome that means "create a task now". `auto_accept_silent` and `create_direct` are deleted, not disabled.
- Create a Candidate and accept it in the same request, on any surface.
- Fall back to an action-item writer when the Candidate path is unavailable, disabled, or errors on a proposing surface. Defer and retry instead; silence is the correct failure.
- Let a rollout, workflow mode, or capability default route capture onto a writer. `off` is what a control endpoint reports when its own read fails, so it must be inert, never "legacy staging".
- Expose an acceptance path on a capture-delivery client. A pipeline that *can* accept eventually will.
- Let one rejected extraction item drag its siblings onto a writer. Policy rejection is per item.
- Propose to a client whose Suggested surface does not exist. A Candidate nothing renders is a dropped task that also costs storage.
- Give a writing surface the loose extraction prompt. Without a review queue, the prompt is the filter.
- Let the backend and desktop capture policies diverge. They share one frozen fixture.

## Surfaces

- Desktop conversation extraction, the shared capture policy, and the Candidate lifecycle
- Desktop screen extraction, candidate delivery, and the suggestion moment
- Suggested-task projections on desktop, and the conversation-summary action-item list
- Conversation extraction on clients with no Suggested surface — in scope for the writing half: the source predicate and the conservative prompt
- Chat, MCP, developer API and manual create — **out of scope**: these carry a real user gesture and write directly by design

## Guard tests

- `.github/scripts/check_task_capture_authority.py` — static: no creating outcome, no accept in extraction, no accept on the capture client, and no create anchor on a source governed by the shared capture policy
- `.github/scripts/test_check_task_capture_authority.py` — proves that guard fails on each shape that shipped
- `backend/tests/unit/test_conversation_suggestion_visibility.py` — every admitted capture kind reaches the Suggested surface
- `backend/tests/unit/test_backend_candidate_capture.py` — behavioural: a desktop conversation proposes and never accepts or writes, a rejected item is dropped alone, and every other client's conversation writes its tasks and proposes nothing
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
