"""Regression test for PATCH /v1/conversations/{id}/events index bounds.

set_conversation_events_state took parallel lists events_idx / values and only guarded the
UPPER bound (event_idx >= len(events)). Two bugs followed:

  1. A negative event_idx (e.g. -1) passed the guard and wrote to events[-1] -- silent
     corruption of the wrong event.
  2. events_idx and values of mismatched length let data.values[i] raise IndexError -> HTTP 500.

The fix rejects a length mismatch with 422 and bounds-checks both ends
(0 <= event_idx < len(events)) so a negative or out-of-range index is skipped instead of
corrupting data or 500ing. This test loads the conversations router fresh against stubbed heavy
dependencies (the router pulls in clients that construct at import time -- typesense, pinecone,
firebase -- so the fakes must precede the import) and calls the handler directly.

The same index-bounds class also affected PATCH /v1/conversations/{id}/segments/{segment_idx}/assign
(set_assignee_conversation_segment), which indexed transcript_segments[segment_idx] with no bound at
all: an out-of-range idx 500ed (IndexError) and a negative idx silently mutated the wrong segment.
Because that route targets a single named segment rather than a batch of parallel arrays, the fix
returns 404 for a missing segment instead of skipping. Those regression tests live alongside the
events ones below since they share the fixture and the same failure class.
"""

import hashlib
import os
import uuid
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


def _pkg(name):
    """AutoMockModule that also presents as a package (sets ``__path__``)."""
    mod = AutoMockModule(name)
    mod.__path__ = []
    return mod


@pytest.fixture(scope="module")
def router():
    """Load ``routers.conversations`` fresh against stubbed heavy dependencies.

    The router transitively constructs clients at import time (typesense, pinecone,
    firebase), so those modules (and their parent packages) must be faked *before* the
    router is exec'd. ``utils`` itself stays real so ``utils.executors`` and the real
    ``models.*`` chain load normally. Everything loaded inside the ``with`` is evicted on
    teardown by ``stub_modules``, keeping the suite hermetic.
    """

    # database._client -- richer than an AutoMock: db proxy + helpers used by the router.
    client_mod = ModuleType("database._client")
    client_mod.db = MagicMock(name="db")
    client_mod.get_firestore_client = lambda: client_mod.db

    def _document_id_from_seed(seed: str) -> str:
        seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
        return str(uuid.UUID(bytes=seed_hash[:16], version=4))

    client_mod.document_id_from_seed = _document_id_from_seed

    # firebase_admin.auth needs a real InvalidIdTokenError class on it.
    fa_auth = _pkg("firebase_admin.auth")
    fa_auth.InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})

    # utils.other.endpoints exposes the auth dependencies used in route signatures; FastAPI
    # needs real callables to build the dependants, so provide small stand-ins.
    endpoints = ModuleType("utils.other.endpoints")

    def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
        return "test-uid"

    def _fake_with_rate_limit(dependency, _policy):  # pragma: no cover - returns wrapped dependency
        return dependency

    endpoints.get_current_user_uid = _fake_get_current_user_uid
    endpoints.with_rate_limit = _fake_with_rate_limit
    endpoints.get_user = MagicMock()

    # utils.memory.memory_system carries the MemorySystem enum the router binds at import.
    class _MemorySystem(str, Enum):
        LEGACY = "legacy"
        CANONICAL = "canonical"

    memory_system = ModuleType("utils.memory.memory_system")
    setattr(memory_system, "MemorySystem", _MemorySystem)

    canonical_activation = ModuleType("utils.memory.canonical_activation")
    setattr(canonical_activation, "canonical_write_enabled", MagicMock(return_value=False))

    memory_service = ModuleType("utils.memory.memory_service")
    memory_service.MemoryService = MagicMock()

    retraction_scope = ModuleType("utils.memory.retraction_scope")
    setattr(retraction_scope, "retraction_can_be_skipped", MagicMock(return_value=False))

    # The router imports the typed conflict raised by exhausted cascade-retract
    # CAS retries (#11726); expose it as a real RuntimeError subclass so the
    # except-clause in delete_conversation binds to something concrete.
    canonical_adapter = ModuleType("utils.memory.canonical_memory_adapter")

    class _ConversationReplacementConflictError(RuntimeError):
        pass

    setattr(canonical_adapter, "ConversationReplacementConflictError", _ConversationReplacementConflictError)

    request_validation = ModuleType("utils.request_validation")
    setattr(request_validation, "NonNegativeOffset", int)
    setattr(request_validation, "PositiveLimit", int)

    fakes = {
        # top-level third-party
        "ulid": _pkg("ulid"),
        "pinecone": _pkg("pinecone"),
        "typesense": _pkg("typesense"),
        # database (parent package faked; _client is the rich stub)
        "database": _pkg("database"),
        "database._client": client_mod,
        "database.conversations": _pkg("database.conversations"),
        "database.action_items": _pkg("database.action_items"),
        "database.memories": _pkg("database.memories"),
        "database.redis_db": _pkg("database.redis_db"),
        "database.cache": _pkg("database.cache"),
        "database.apps": _pkg("database.apps"),
        "database.folders": _pkg("database.folders"),
        "database.trends": _pkg("database.trends"),
        "database.calendar_meetings": _pkg("database.calendar_meetings"),
        "database.tasks": _pkg("database.tasks"),
        "database.goals": _pkg("database.goals"),
        "database.llm_usage": _pkg("database.llm_usage"),
        "database.chat": _pkg("database.chat"),
        "database.notifications": _pkg("database.notifications"),
        "database.fair_use": _pkg("database.fair_use"),
        "database.webhook_health": _pkg("database.webhook_health"),
        "database.mem_db": _pkg("database.mem_db"),
        "utils.apps": _pkg("utils.apps"),
        "utils.conversations.merge_conversations": _pkg("utils.conversations.merge_conversations"),
        "database.users": _pkg("database.users"),
        "database.vector_db": _pkg("database.vector_db"),
        # firebase
        "firebase_admin": _pkg("firebase_admin"),
        "firebase_admin.messaging": _pkg("firebase_admin.messaging"),
        "firebase_admin.auth": fa_auth,
        "firebase_admin.credentials": _pkg("firebase_admin.credentials"),
        "firebase_admin.firestore": _pkg("firebase_admin.firestore"),
        # google.cloud
        "google": _pkg("google"),
        "google.cloud": _pkg("google.cloud"),
        "google.cloud.firestore": _pkg("google.cloud.firestore"),
        "google.cloud.firestore_v1": _pkg("google.cloud.firestore_v1"),
        # utils.* -- intermediate packages faked; ``utils`` itself stays real.
        "utils.other": _pkg("utils.other"),
        "utils.other.endpoints": endpoints,
        "utils.other.storage": _pkg("utils.other.storage"),
        "utils.conversations": _pkg("utils.conversations"),
        "utils.conversations.factory": _pkg("utils.conversations.factory"),
        "utils.conversations.render": _pkg("utils.conversations.render"),
        "utils.conversations.process_conversation": _pkg("utils.conversations.process_conversation"),
        "utils.conversations.meeting_receipt": _pkg("utils.conversations.meeting_receipt"),
        "utils.conversations.search": _pkg("utils.conversations.search"),
        "utils.conversations.calendar_linking": _pkg("utils.conversations.calendar_linking"),
        "utils.conversations.calendar_utils": _pkg("utils.conversations.calendar_utils"),
        "utils.conversations.location": _pkg("utils.conversations.location"),
        "utils.conversations.analytics": _pkg("utils.conversations.analytics"),
        "utils.llm": _pkg("utils.llm"),
        "utils.llm.conversation_processing": _pkg("utils.llm.conversation_processing"),
        "utils.speaker_identification": _pkg("utils.speaker_identification"),
        "utils.app_integrations": _pkg("utils.app_integrations"),
        "utils.memory": _pkg("utils.memory"),
        "utils.memory.memory_service": memory_service,
        "utils.memory.memory_system": memory_system,
        "utils.memory.canonical_activation": canonical_activation,
        "utils.memory.retraction_scope": retraction_scope,
        "utils.memory.canonical_memory_adapter": canonical_adapter,
        "utils.retrieval": _pkg("utils.retrieval"),
        "utils.retrieval.tools": _pkg("utils.retrieval.tools"),
        "utils.retrieval.tools.calendar_tools": _pkg("utils.retrieval.tools.calendar_tools"),
        "utils.retrieval.tools.google_utils": _pkg("utils.retrieval.tools.google_utils"),
        "utils.request_validation": request_validation,
    }

    with stub_modules(fakes):
        conv = load_module_fresh(
            "routers.conversations",
            os.path.join(str(_BACKEND), "routers", "conversations.py"),
        )
        from models.conversation import SetConversationEventsStateRequest

        yield SimpleNamespace(conv=conv, SetConversationEventsStateRequest=SetConversationEventsStateRequest)


class _FakeEvent:
    """Minimal stand-in for a structured event: tracks .created and is .dict()-able."""

    def __init__(self):
        self.created = False

    def model_dump(self):
        return {"created": self.created}


def _fake_conversation_with_events(count):
    events = [_FakeEvent() for _ in range(count)]
    structured = SimpleNamespace(events=events)
    return SimpleNamespace(structured=structured), events


def test_mismatched_lengths_returns_422(router):
    """events_idx longer than values must fail request validation before router code runs."""
    with pytest.raises(ValidationError):
        router.SetConversationEventsStateRequest(events_idx=[0, 1], values=[True])


def test_negative_index_is_skipped_not_corrupting(router):
    """A negative event_idx (-1) must NOT write to the last event."""
    convo, events = _fake_conversation_with_events(2)
    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ):
        data = router.SetConversationEventsStateRequest(events_idx=[-1], values=[True])
        result = router.conv.set_conversation_events_state("c1", data, uid="u1")

    # No event should have been mutated by the out-of-range negative index.
    assert all(event.created is False for event in events)
    assert result == {"status": "Ok"}


def test_valid_index_still_updates(router):
    """Sanity: an in-range index still applies the value (fix must not break the happy path)."""
    convo, events = _fake_conversation_with_events(2)
    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ):
        data = router.SetConversationEventsStateRequest(events_idx=[1], values=[True])
        router.conv.set_conversation_events_state("c1", data, uid="u1")

    assert events[1].created is True
    assert events[0].created is False


class _FakeSegment:
    """Minimal transcript segment: assignable (.is_user / .person_id) and model_dump-able."""

    def __init__(self, segment_id=None):
        self.id = segment_id
        self.is_user = False
        self.person_id = None

    def model_dump(self):
        return {"id": self.id, "is_user": self.is_user, "person_id": self.person_id}


def _fake_conversation_with_segments(count, status=None, with_ids=False):
    segments = [_FakeSegment(f"segment-{index}" if with_ids else None) for index in range(count)]
    return SimpleNamespace(transcript_segments=segments, status=status), segments


def _segment_assign_handler(conv):
    """Return the real segments/{segment_idx}/assign handler off its APIRoute.

    Two functions share the name ``set_assignee_conversation_segment`` in the module -- the second
    (the ``assign-speaker/{speaker_id}`` route) rebinds the module global -- so the module attribute
    points at the wrong one. The registered route captured the correct function object at decoration
    time, so pull the handler from ``router.routes`` by path instead.
    """
    target = "/v1/conversations/{conversation_id}/segments/{segment_idx}/assign"
    for route in conv.router.routes:
        if getattr(route, "path", None) == target and "PATCH" in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError("segments/{segment_idx}/assign route is not registered")


def test_segment_assign_out_of_range_returns_404(router):
    """An out-of-range segment_idx must raise 404, not IndexError -> HTTP 500."""
    convo, segments = _fake_conversation_with_segments(2)
    handler = _segment_assign_handler(router.conv)
    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ):
        with pytest.raises(HTTPException) as exc:
            handler("c1", 999, "is_user", uid="u1")

    assert exc.value.status_code == 404
    # Nothing mutated: the guard fired before any assignment.
    assert all(seg.is_user is False and seg.person_id is None for seg in segments)


def test_segment_assign_negative_index_returns_404(router):
    """A negative segment_idx (-1) must 404 instead of silently mutating the last segment."""
    convo, segments = _fake_conversation_with_segments(2)
    handler = _segment_assign_handler(router.conv)
    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ):
        with pytest.raises(HTTPException) as exc:
            handler("c1", -1, "person_id", value="person-9", uid="u1")

    assert exc.value.status_code == 404
    assert segments[-1].person_id is None  # last segment untouched


def test_segment_assign_valid_index_still_updates(router):
    """Sanity: an in-range index still applies the assignment (fix must not break the happy path)."""
    convo, segments = _fake_conversation_with_segments(2)
    handler = _segment_assign_handler(router.conv)
    emitted = []
    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ), patch.object(router.conv, "emit_product_event", side_effect=lambda **event: emitted.append(event)):
        result = handler("c1", 1, "is_user", value="true", uid="u1")

    assert segments[1].is_user is True
    assert segments[0].is_user is False  # untouched
    assert result is convo
    assert emitted == [
        {
            "uid": "u1",
            "event": "Speaker Identity Confirmed",
            "properties": {
                "conversation_id": "c1",
                "confirmation": "corrected",
                "assignment": "self",
                "scope": "segment",
                "affected_segment_count": 1,
            },
        }
    ]


def test_segment_assign_repeating_the_same_identity_is_an_acceptance(router):
    convo, segments = _fake_conversation_with_segments(1)
    segments[0].is_user = True
    handler = _segment_assign_handler(router.conv)
    emitted = []

    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ), patch.object(router.conv, "emit_product_event", side_effect=lambda **event: emitted.append(event)):
        handler("c1", 0, "is_user", value="true", uid="u1")

    assert len(emitted) == 1
    assert emitted[0]["properties"]["confirmation"] == "accepted"


def test_bulk_assign_resolves_legacy_positional_target_and_persists_canonical_id(router):
    """The desktop's #index fallback must resolve to the same segment the backend persists."""
    convo, segments = _fake_conversation_with_segments(
        2,
        status=router.conv.ConversationStatus.completed,
        with_ids=True,
    )
    background_tasks = router.conv.BackgroundTasks()
    data = router.conv.BulkAssignSegmentsRequest(
        segment_ids=["#index:0"],
        assign_type="person_id",
        value="person-9",
    )

    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ), patch.object(router.conv.conversations_db, "update_conversation_segments"):
        result = router.conv.assign_segments_bulk("c1", data, background_tasks, uid="u1")

    assert result is convo
    assert segments[0].person_id == "person-9"
    assert segments[0].is_user is False
    assert segments[1].person_id is None
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].kwargs["segment_ids"] == ["segment-0"]


def test_bulk_assign_exact_id_still_supports_user_assignment(router):
    """Already-shipped clients using persisted IDs retain the existing assignment path."""
    convo, segments = _fake_conversation_with_segments(
        2,
        status=router.conv.ConversationStatus.completed,
        with_ids=True,
    )
    segments[0].person_id = "old-person"
    background_tasks = router.conv.BackgroundTasks()
    data = router.conv.BulkAssignSegmentsRequest(
        segment_ids=["segment-0"],
        assign_type="is_user",
        value="true",
    )

    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ), patch.object(router.conv.conversations_db, "update_conversation_segments"):
        router.conv.assign_segments_bulk("c1", data, background_tasks, uid="u1")

    assert segments[0].is_user is True
    assert segments[0].person_id is None
    assert segments[1].is_user is False
    assert background_tasks.tasks == []


def test_bulk_assign_rejects_unresolved_target_without_partial_mutation(router):
    """A stale or malformed target must fail closed instead of reporting a silent no-op."""
    convo, segments = _fake_conversation_with_segments(
        2,
        status=router.conv.ConversationStatus.completed,
        with_ids=True,
    )
    segments[0].person_id = "old-person"
    background_tasks = router.conv.BackgroundTasks()
    data = router.conv.BulkAssignSegmentsRequest(
        segment_ids=["segment-0", "#index:99"],
        assign_type="person_id",
        value="person-9",
    )
    update = MagicMock()

    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ), patch.object(router.conv.conversations_db, "update_conversation_segments", update):
        with pytest.raises(HTTPException) as exc:
            router.conv.assign_segments_bulk("c1", data, background_tasks, uid="u1")

    assert exc.value.status_code == 409
    assert segments[0].person_id == "old-person"
    assert update.call_count == 0
    assert background_tasks.tasks == []
