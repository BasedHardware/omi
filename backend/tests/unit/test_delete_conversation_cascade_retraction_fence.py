"""Cascade delete must consult the retraction-skip guard.

`DELETE /v1/conversations/{id}?cascade=true` is the app's only delete path
(`app/lib/backend/http/api/conversations.dart:136`). It called
`MemoryService.retract_conversation_memories` with no error handling, and that
runs through the canonical replace boundary fenced by
`_require_canonical_intake_enabled()` whenever `MEMORY_MODE` is not write/read.

Production runs `off`, so every cascade delete raised and returned 500 — 100% of
sampled requests from 13 Aug onward. It was never reported; it was found while
fixing the merge failure that shares the same cause.

This is a **static checker, not behavioural coverage**: it reads the endpoint's
source rather than exercising the route, because importing `routers.conversations`
into a unit-test session pulls in enough global state to break neighbouring
import-isolated suites. The behaviour it protects — when the skip is allowed and
when retraction must still run — is covered against the real helper in
test_merge_skips_retraction_without_canonical_memories.py.
"""

from __future__ import annotations

import pathlib
import re

ROUTER = pathlib.Path(__file__).resolve().parents[2] / "routers" / "conversations.py"


def _delete_conversation_source() -> str:
    source = ROUTER.read_text()
    start = source.index("def delete_conversation(")
    end = source.index("\n@router.", start)
    return source[start:end]


def test_the_cascade_branch_guards_retraction_behind_the_skip_helper():
    body = _delete_conversation_source()
    assert "retract_conversation_memories" in body, "expected the cascade branch to still retract"
    assert "retraction_can_be_skipped" in body, (
        "cascade delete must consult retraction_can_be_skipped; without it the canonical "
        "fence turns every delete into a 500"
    )


def test_the_guard_precedes_the_retraction_call():
    body = _delete_conversation_source()
    assert body.index("retraction_can_be_skipped") < body.index(
        "retract_conversation_memories"
    ), "the guard must run before the retraction it protects"


def test_the_retraction_call_is_inside_the_guard():
    # `if not retraction_can_be_skipped(...)` — a guard that does not actually
    # gate the call would satisfy the ordering check above but fix nothing.
    body = _delete_conversation_source()
    guarded = re.search(
        r"if not retraction_can_be_skipped\([^)]*\):\s*\n"
        r"\s+try:\s*\n\s+memory_service\.retract_conversation_memories\(",
        body,
    )
    assert guarded, "retraction must be inside the `if not retraction_can_be_skipped(...)` branch"


def test_exhausted_replacement_conflict_maps_to_retryable_503_before_any_delete():
    # #11726: concurrent same-uid deletes raced the account-global memory
    # control CAS into an unhandled RuntimeError → 500. The exhausted conflict
    # is retryable (retraction is idempotent), and nothing has been deleted
    # yet at that point, so the route must answer 503 while the conversation
    # and its live memories stay intact.
    body = _delete_conversation_source()
    mapped = re.search(
        r"try:\s*\n\s+memory_service\.retract_conversation_memories\([^)]*\)\s*\n"
        r"\s+except ConversationReplacementConflictError[^:]*:\s*\n"
        r"((?:\s+.*\n)*?)\s+raise HTTPException\(\s*\n\s+status_code=503,",
        body,
    )
    assert mapped, "the retract call must map ConversationReplacementConflictError to a 503"
    assert (
        "conversations_db.delete_conversation" in body.split("except ConversationReplacementConflictError")[1]
    ), "the conversation document delete must stay in the post-retract success path"
