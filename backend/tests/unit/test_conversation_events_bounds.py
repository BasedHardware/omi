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
"""

import hashlib
import os
import uuid
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
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

    surface_routing = ModuleType("utils.memory.surface_routing")
    surface_routing.pin_memory_system = MagicMock()

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
        "utils.conversations.search": _pkg("utils.conversations.search"),
        "utils.conversations.calendar_linking": _pkg("utils.conversations.calendar_linking"),
        "utils.conversations.calendar_utils": _pkg("utils.conversations.calendar_utils"),
        "utils.conversations.location": _pkg("utils.conversations.location"),
        "utils.llm": _pkg("utils.llm"),
        "utils.llm.conversation_processing": _pkg("utils.llm.conversation_processing"),
        "utils.speaker_identification": _pkg("utils.speaker_identification"),
        "utils.app_integrations": _pkg("utils.app_integrations"),
        "utils.memory": _pkg("utils.memory"),
        "utils.memory.memory_service": memory_service,
        "utils.memory.memory_system": memory_system,
        "utils.memory.canonical_activation": canonical_activation,
        "utils.memory.surface_routing": surface_routing,
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
