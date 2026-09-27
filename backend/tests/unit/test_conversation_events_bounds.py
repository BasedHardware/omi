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
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from utils.manual_speaker_assignments import manual_assignment
from fastapi import HTTPException
from pydantic import ValidationError

from testing.import_isolation import (
    AutoMockModule,
    load_module_fresh,
    package_submodule_stubs,
    stub_modules,
)

_BACKEND = Path(__file__).resolve().parents[2]

# routers.conversations imports the list-read budget seam at module level
# (#11831). The seam is stdlib-only and budget-optional; install the real
# module (loaded under a private name) so the from-import binds real symbols.
import importlib.util as _importlib_util

_list_budget_path = _BACKEND / "utils" / "other" / "list_budget.py"
_list_budget_spec = _importlib_util.spec_from_file_location("_omi_real_list_budget", str(_list_budget_path))
list_budget_real = _importlib_util.module_from_spec(_list_budget_spec)
_list_budget_spec.loader.exec_module(list_budget_real)


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
        "database.screen_frames": _pkg("database.screen_frames"),
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
        "database.firestore_read_metrics": _pkg("database.firestore_read_metrics"),
        "utils.apps": _pkg("utils.apps"),
        # routers.conversations also imports utils.product_metrics (#15099). Its
        # real import chain reaches utils.account_cutover -> database.read_boundary,
        # which cannot resolve under the faked "database" parent; the fake keeps
        # the suite hermetic and its teardown from evicting real firestore modules
        # that later files in the same shard process re-import (duplicate protos).
        "utils.product_metrics": _pkg("utils.product_metrics"),
        "database.users": _pkg("database.users"),
        "database.vector_db": _pkg("database.vector_db"),
        "services.conversation_frame_evidence": _pkg("services.conversation_frame_evidence"),
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
        "utils.other.list_budget": list_budget_real,
        "utils.other.storage": _pkg("utils.other.storage"),
        # utils.conversations.* is DERIVED, not listed: a new module in that package
        # must not break this suite at collection. See package_submodule_stubs.
        **package_submodule_stubs("utils.conversations"),
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
        self.speaker_id = 0
        self.start = 0
        self.end = 1

    def model_dump(self):
        return {
            "id": self.id,
            "is_user": self.is_user,
            "person_id": self.person_id,
            "speaker_id": self.speaker_id,
            "text": "test",
            "start": self.start,
            "end": self.end,
        }


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


@pytest.fixture(autouse=True)
def manual_command_seam(router, monkeypatch):
    """Route contract uses real selection policy; transaction coverage is separate."""

    def assign(uid, cid, **kwargs):
        convo = router.conv.deserialize_conversation({})
        raw = dict(
            status=getattr(convo, 'status', None),
            transcript_segments=[s.model_dump() for s in convo.transcript_segments],
        )
        before = [dict(s) for s in raw['transcript_segments']]
        updated, receipt, resolved, _ = manual_assignment(raw, **kwargs)
        selected_before = [s for i, s in enumerate(before) if updated[i]['id'] in resolved]
        for segment, data in zip(convo.transcript_segments, updated):
            segment.id, segment.is_user, segment.person_id = data['id'], data['is_user'], data['person_id']
        return raw, resolved, [], selected_before

    monkeypatch.setattr(router.conv.conversations_db, 'assign_conversation_speaker', assign)


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
    assert 'Unable to resolve transcript segment assignment target(s): #index:99' == exc.value.detail
    assert segments[0].person_id == "old-person"
    assert update.call_count == 0
    assert background_tasks.tasks == []


def _speaker_assign_handler(conv):
    target = "/v1/conversations/{conversation_id}/assign-speaker/{speaker_id}"
    for route in conv.router.routes:
        if getattr(route, "path", None) == target and "PATCH" in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError("assign-speaker route is not registered")


def test_locked_assign_routes_return_402_with_main_detail(router, monkeypatch):
    def locked(*args, **kwargs):
        raise PermissionError('Conversation is locked')

    monkeypatch.setattr(router.conv.conversations_db, 'assign_conversation_speaker', locked)
    convo, _ = _fake_conversation_with_segments(1, with_ids=True)
    index_handler = _segment_assign_handler(router.conv)
    speaker_handler = _speaker_assign_handler(router.conv)
    with patch.object(router.conv, "deserialize_conversation", return_value=convo):
        for call in (
            lambda: index_handler("c1", 0, "is_user", value="true", uid="u1"),
            lambda: speaker_handler("c1", 0, "person_id", value="person-9", uid="u1"),
            lambda: router.conv.assign_segments_bulk(
                "c1",
                router.conv.BulkAssignSegmentsRequest(segment_ids=["segment-0"], assign_type="person_id", value="p"),
                router.conv.BackgroundTasks(),
                uid="u1",
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                call()
            assert exc.value.status_code == 402
            assert exc.value.detail == "A paid plan is required to access this conversation."


@pytest.mark.parametrize(
    'value,expected_user',
    [('true', True), ('1', True), ('false', False), ('null', False), (None, False)],
)
def test_is_user_assign_parses_true_false_null_and_omitted(router, value, expected_user):
    convo, segments = _fake_conversation_with_segments(1, with_ids=True)
    handler = _segment_assign_handler(router.conv)
    kwargs = dict(assign_type="is_user", uid="u1")
    if value is not None:
        kwargs['value'] = value
    with patch.object(router.conv, "deserialize_conversation", return_value=convo):
        handler("c1", 0, **kwargs)
    assert segments[0].is_user is expected_user


class _FakeActionItem:
    def __init__(self, description):
        self.description = description
        self.completed = False
        self.created_at = None
        self.completed_at = None

    def model_dump(self):
        return {"description": self.description, "completed": self.completed}


def _set_action_item_status(router, mirrored, values):
    convo = SimpleNamespace(
        structured=SimpleNamespace(action_items=[_FakeActionItem("Send the budget")]),
        created_at=None,
    )
    notifications = ModuleType("utils.notifications")
    notifications.sync_action_item_reminder = MagicMock()
    data = router.conv.SetConversationActionItemsStateRequest(items_idx=[0], values=values)
    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ), patch.object(router.conv.conversations_db, "update_conversation_action_items"), patch.object(
        router.conv.action_items_db, "get_action_items_by_conversation", return_value=mirrored
    ), patch.object(
        router.conv.action_items_db, "mark_action_item_completed"
    ) as mark, patch.dict(
        "sys.modules", {"utils.notifications": notifications}
    ):
        router.conv.set_action_item_status(data, "c1", uid="u1")
    return mark, notifications.sync_action_item_reminder


def test_checking_off_a_conversation_task_cancels_its_reminder(router):
    due = datetime(2026, 9, 20, 9, tzinfo=timezone.utc)
    mirrored = [{"id": "task-1", "description": "Send the budget", "due_at": due}]

    mark, reminder = _set_action_item_status(router, mirrored, [True])

    mark.assert_called_once_with("u1", "task-1", True)
    reminder.assert_called_once_with(
        user_id="u1", action_item_id="task-1", description="Send the budget", completed=True, due_at=due
    )


def test_unchecking_a_conversation_task_rearms_its_reminder(router):
    due = datetime(2026, 9, 20, 9, tzinfo=timezone.utc)
    mirrored = [{"id": "task-1", "description": "Send the budget", "due_at": due}]

    mark, reminder = _set_action_item_status(router, mirrored, [False])

    mark.assert_called_once_with("u1", "task-1", False)
    reminder.assert_called_once_with(
        user_id="u1", action_item_id="task-1", description="Send the budget", completed=False, due_at=due
    )


def _delete_conversation_action_item(router, mirrored, description="Send the budget"):
    """Run the swipe-delete handler that removes one task from a conversation.

    That DELETE path mirrors the removal into the standalone action_items collection,
    so a deleted row can still own a client-scheduled reminder. The client only
    cancels it on the deletion data message (ActionItemNotificationHandler
    .handleDeletionMessage), so the handler must send one.
    """
    convo = SimpleNamespace(
        structured=SimpleNamespace(action_items=[_FakeActionItem(description)]),
        created_at=None,
    )
    notifications = ModuleType("utils.notifications")
    notifications.sync_action_item_reminder = MagicMock()
    data = router.conv.DeleteActionItemRequest(description=description, completed=False)
    with patch.object(router.conv, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router.conv, "deserialize_conversation", return_value=convo
    ), patch.object(router.conv.conversations_db, "update_conversation_action_items"), patch.object(
        router.conv.action_items_db, "get_action_items_by_conversation", return_value=mirrored
    ), patch.object(
        router.conv.action_items_db, "delete_action_item"
    ) as delete, patch.dict(
        "sys.modules", {"utils.notifications": notifications}
    ):
        router.conv.delete_action_item(data, "c1", uid="u1")
    return delete, notifications.sync_action_item_reminder


def test_deleting_a_conversation_task_cancels_its_reminder(router):
    due = datetime(2026, 9, 20, 9, tzinfo=timezone.utc)
    mirrored = [{"id": "task-1", "description": "Send the budget", "due_at": due, "completed": False}]

    delete, reminder = _delete_conversation_action_item(router, mirrored)

    delete.assert_called_once_with("u1", "task-1")
    reminder.assert_called_once_with(user_id="u1", action_item_id="task-1", description="", completed=True, due_at=None)


def test_deleting_a_task_without_a_live_reminder_sends_nothing(router):
    due = datetime(2026, 9, 20, 9, tzinfo=timezone.utc)
    mirrored = [
        {"id": "task-done", "description": "Send the budget", "due_at": due, "completed": True},
        {"id": "task-other", "description": "Something else", "due_at": due, "completed": False},
    ]

    delete, reminder = _delete_conversation_action_item(router, mirrored)

    delete.assert_called_once_with("u1", "task-done")
    reminder.assert_not_called()
