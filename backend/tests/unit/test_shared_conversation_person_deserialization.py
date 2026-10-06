"""Tests for safe Person deserialization in shared conversations and workers.

Regression tests for:
1. Public /v1/conversations/{id}/shared:
   If a conversation references a speaker whose stored Person document is malformed
   (e.g., missing the required 'name' field), building [Person(**p) for p in people_data]
   raised an unhandled pydantic ValidationError, returning HTTP 500 on the public unauthenticated route.
   Using Person.deserialize_many_safe skips malformed records and returns the shared conversation.
2. JIT first-open worker (run_first_open_derived_work):
   When resolving speaker people records during first open processing, malformed person docs
   crashed the background worker with ValidationError. Using Person.deserialize_many_safe
   ensures background obligations proceed cleanly without worker aborts.
3. Conversation processing notes v2 and main pipeline:
   Building prompt_people and processing people records safely ignores malformed person documents.
"""

from __future__ import annotations

import types
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from models.conversation import (
    Conversation,
    project_shared_conversation,
)
from models.conversation_enums import ConversationSource, ConversationStatus, ConversationVisibility
from models.other import Person
from models.structured import Structured
from models.transcript_segment import TranscriptSegment


def _build_test_conversation() -> Conversation:
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    return Conversation(
        id="c1",
        created_at=now,
        started_at=now,
        finished_at=now,
        language="en",
        source=ConversationSource.omi,
        status=ConversationStatus.completed,
        visibility=ConversationVisibility.shared,
        structured=Structured(
            title="Meeting with Alice",
            overview="Discussion on safe deserialization.",
            emoji="🤝",
        ),
        transcript_segments=[
            TranscriptSegment(
                id="seg-1",
                text="Hello from Alice",
                speaker="SPEAKER_00",
                speaker_id=0,
                is_user=False,
                person_id="p_valid",
                start=0.0,
                end=1.5,
            ),
            TranscriptSegment(
                id="seg-2",
                text="Corrupt speaker segment",
                speaker="SPEAKER_01",
                speaker_id=1,
                is_user=False,
                person_id="p_corrupt",
                start=1.5,
                end=3.0,
            ),
        ],
    )


def test_shared_conversation_person_deserialization_skips_malformed_record():
    """Verify that malformed Person records do not crash the projection and are safely skipped."""
    conversation = _build_test_conversation()
    raw_people_data = [
        {"id": "p_valid", "name": "Alice"},
        {"id": "p_corrupt"},  # Missing required 'name' field
        {"id": "p_null_name", "name": None},  # Invalid name type
    ]

    # Unsafe direct deserialization raises ValidationError
    with pytest.raises(ValidationError):
        _ = [Person(**p) for p in raw_people_data]

    # Safe deserialization skips malformed entries and keeps valid ones
    safe_people = Person.deserialize_many_safe(raw_people_data)
    assert len(safe_people) == 1
    assert safe_people[0].id == "p_valid"
    assert safe_people[0].name == "Alice"

    # project_shared_conversation with safe_people succeeds without error
    shared_response = project_shared_conversation(conversation, safe_people)
    dumped = shared_response.model_dump(mode="json")
    assert dumped["id"] == "c1"
    assert dumped["people"] == [{"id": "p_valid", "name": "Alice"}]


def test_jit_first_open_worker_skips_malformed_person_records(monkeypatch):
    """JIT first-open worker must not crash when users_db returns malformed person documents."""
    import utils.conversations.jit_first_open_worker as worker

    mock_proc = types.ModuleType("utils.conversations.process_conversation")
    mock_proc.deserialize_conversation = lambda d: types.SimpleNamespace(
        id="c1",
        discarded=False,
        source="omi",
        language="en",
        folder_id="f1",
        structured=None,
        apps_results=[],
        suggested_summarization_apps=[],
        get_person_ids=lambda: ["p_valid", "p_corrupt"],
    )
    mock_proc.users_db = types.SimpleNamespace(
        get_people_by_ids=lambda uid, pids: [
            {"id": "p_valid", "name": "Alice"},
            {"id": "p_corrupt"},  # Missing 'name'
        ]
    )
    passed_people = []

    def fake_trigger_conversation_apps(*args, **kwargs):
        passed_people.extend(kwargs.get("people", []))
        return True

    mock_proc.trigger_conversation_apps = fake_trigger_conversation_apps
    mock_proc.conversation_apps_opt_in_only = lambda: False
    mock_proc.AppUsageAttribution = types.SimpleNamespace(AUTOMATIC_PROCESSING="auto")
    mock_proc.resolve_authorized_first_open_plan = lambda **kw: types.SimpleNamespace(defer_derived_work=True)
    mock_proc.conversations_db = types.SimpleNamespace(
        FIRST_OPEN_EFFECTS=[],
        first_open_effect_is_authorized=lambda *a, **k: True,
        complete_first_open_effect=lambda *a, **k: True,
        commit_first_open_conversation_patch=lambda *a, **k: True,
    )

    import sys

    monkeypatch.setitem(sys.modules, "utils.conversations.process_conversation", mock_proc)

    effects = {"folder_assignment": {"state": "complete"}}
    payload = {"id": "c1", "jit_first_open": {"effects": effects}}

    # In unpatched code, run_first_open_derived_work raises ValidationError at line 61.
    # In patched code, Person.deserialize_many_safe allows it to complete cleanly,
    # and only valid people are passed to downstream app triggers.
    worker.run_first_open_derived_work("test_uid", payload, "test_token")
    assert len(passed_people) == 1
    assert passed_people[0].id == "p_valid"
    assert passed_people[0].name == "Alice"


def test_process_conversation_people_records_skip_malformed():
    """Verify Person.deserialize_many_safe handles various malformed document shapes for prompt builders."""
    records = [
        {"id": "p1", "name": "Bob"},
        {"id": "p2"},  # Missing name
        {"id": "p3", "name": 123},  # Invalid type for name
        {"random_key": "junk"},  # Completely invalid
    ]

    safe_people = Person.deserialize_many_safe(records)
    assert len(safe_people) == 1
    assert safe_people[0].id == "p1"
    assert safe_people[0].name == "Bob"
