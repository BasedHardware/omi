"""GET /v1/conversations and /v1/conversations/count must reject an inverted date range.

Both endpoints accept start_date/end_date filters and forward them straight to Firestore inequality
filters (created_at >= start, created_at <= end). FastAPI Query() cannot validate one parameter
against another, so an inverted range (start > end) was passed through: Firestore then applies a
contradictory pair of filters and returns an empty list / a count of zero, so the caller cannot tell
a malformed request apart from a genuinely empty result. Both endpoints now validate start <= end
and return 400 first.

The comparison also normalizes timezone awareness first: FastAPI parses a query datetime as naive or
aware depending on whether the client included an offset, and comparing a naive against an aware
datetime raises TypeError (a 500). The endpoints normalize both bounds to UTC before comparing.

The conversations router pulls heavy chains at import time (typesense client construction, the
database/encryption chain, firebase/google clouds, the memory + retrieval graphs), none of which the
pure validation logic touches. They are stubbed inside a module-scoped fixture via the sanctioned
``stub_modules`` + ``load_module_fresh`` seam (see ``backend/docs/test_isolation.md`` and
``testing/import_isolation.py``).
"""

import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def conv():
    """Load a fresh routers.conversations against stubbed database/firebase/google/memory chains."""
    # firebase_admin.auth must expose InvalidIdTokenError as a real exception type (the auth
    # dependency imports it at module load).
    firebase_auth_stub = ModuleType("firebase_admin.auth")
    firebase_auth_stub.InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})

    # utils.other.endpoints exposes the auth dependencies used in route signatures; FastAPI builds
    # the dependants at decoration time, so it needs real callables.
    endpoints_stub = ModuleType("utils.other.endpoints")

    def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
        return "test-uid"

    def _fake_with_rate_limit(dependency, _policy):  # pragma: no cover - returns wrapped dependency
        return dependency

    endpoints_stub.get_current_user_uid = _fake_get_current_user_uid
    endpoints_stub.with_rate_limit = _fake_with_rate_limit
    endpoints_stub.get_user = MagicMock()

    # utils.memory.* — MemorySystem is a str-Enum used in type annotations across the memory graph.
    class _MemorySystem(str, Enum):
        LEGACY = "legacy"
        CANONICAL = "canonical"

    memory_pkg = ModuleType("utils.memory")
    memory_pkg.__path__ = []

    memory_service_stub = ModuleType("utils.memory.memory_service")
    memory_service_stub.MemoryService = MagicMock()

    memory_system_stub = ModuleType("utils.memory.memory_system")
    memory_system_stub.MemorySystem = _MemorySystem

    canonical_activation_stub = ModuleType("utils.memory.canonical_activation")
    canonical_activation_stub.canonical_write_enabled = MagicMock(return_value=False)

    surface_routing_stub = ModuleType("utils.memory.surface_routing")
    surface_routing_stub.pin_memory_system = MagicMock()

    # utils.request_validation — route param annotations; plain int keeps the direct-call path simple.
    request_validation_stub = ModuleType("utils.request_validation")
    request_validation_stub.NonNegativeOffset = int
    request_validation_stub.PositiveLimit = int

    fakes: dict[str, ModuleType] = {
        # third-party / heavy top-level deps
        "ulid": AutoMockModule("ulid"),
        "pinecone": AutoMockModule("pinecone"),
        "typesense": AutoMockModule("typesense"),
        # database chain
        "database._client": AutoMockModule("database._client"),
        "database.conversations": AutoMockModule("database.conversations"),
        "database.action_items": AutoMockModule("database.action_items"),
        "database.memories": AutoMockModule("database.memories"),
        "database.redis_db": AutoMockModule("database.redis_db"),
        "database.users": AutoMockModule("database.users"),
        "database.vector_db": AutoMockModule("database.vector_db"),
        # firebase / google cloud
        "firebase_admin": AutoMockModule("firebase_admin"),
        "firebase_admin.messaging": AutoMockModule("firebase_admin.messaging"),
        "firebase_admin.auth": firebase_auth_stub,
        "firebase_admin.credentials": AutoMockModule("firebase_admin.credentials"),
        "firebase_admin.firestore": AutoMockModule("firebase_admin.firestore"),
        "google.cloud.firestore": AutoMockModule("google.cloud.firestore"),
        "google.cloud.firestore_v1": AutoMockModule("google.cloud.firestore_v1"),
        # utils.other.*
        "utils.other.endpoints": endpoints_stub,
        "utils.other.storage": AutoMockModule("utils.other.storage"),
        # utils.conversations.*
        "utils.conversations.factory": AutoMockModule("utils.conversations.factory"),
        "utils.conversations.render": AutoMockModule("utils.conversations.render"),
        "utils.conversations.process_conversation": AutoMockModule("utils.conversations.process_conversation"),
        "utils.conversations.search": AutoMockModule("utils.conversations.search"),
        "utils.conversations.calendar_linking": AutoMockModule("utils.conversations.calendar_linking"),
        "utils.conversations.calendar_utils": AutoMockModule("utils.conversations.calendar_utils"),
        "utils.conversations.location": AutoMockModule("utils.conversations.location"),
        # utils.llm / speaker / integrations / retrieval
        "utils.llm.conversation_processing": AutoMockModule("utils.llm.conversation_processing"),
        "utils.speaker_identification": AutoMockModule("utils.speaker_identification"),
        "utils.app_integrations": AutoMockModule("utils.app_integrations"),
        "utils.retrieval.tools.calendar_tools": AutoMockModule("utils.retrieval.tools.calendar_tools"),
        "utils.retrieval.tools.google_utils": AutoMockModule("utils.retrieval.tools.google_utils"),
        # utils.memory.*
        "utils.memory": memory_pkg,
        "utils.memory.memory_service": memory_service_stub,
        "utils.memory.memory_system": memory_system_stub,
        "utils.memory.canonical_activation": canonical_activation_stub,
        "utils.memory.surface_routing": surface_routing_stub,
        # utils.request_validation
        "utils.request_validation": request_validation_stub,
    }

    with stub_modules(fakes):
        module = load_module_fresh(
            "routers.conversations",
            os.path.join(str(_BACKEND), "routers", "conversations.py"),
        )
        yield module


def _call_list(conv, **overrides):
    kwargs = dict(
        limit=100,
        offset=0,
        statuses="processing,completed",
        include_discarded=True,
        start_date=None,
        end_date=None,
        folder_id=None,
        starred=None,
        uid="u1",
    )
    kwargs.update(overrides)
    return conv.get_conversations(**kwargs)


def _call_count(conv, **overrides):
    kwargs = dict(
        statuses=None,
        include_discarded=False,
        start_date=None,
        end_date=None,
        folder_id=None,
        starred=None,
        sources=None,
        uid="u1",
    )
    kwargs.update(overrides)
    return conv.get_conversations_count(**kwargs)


def test_inverted_range_list_returns_400(conv):
    with pytest.raises(HTTPException) as exc:
        _call_list(conv, start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1))
    assert exc.value.status_code == 400


def test_inverted_range_count_returns_400(conv):
    with pytest.raises(HTTPException) as exc:
        _call_count(conv, start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1))
    assert exc.value.status_code == 400


def test_mixed_timezone_awareness_inverted_returns_400(conv):
    # A naive bound compared against an aware bound must still yield a clean 400, not a TypeError 500.
    with pytest.raises(HTTPException) as exc:
        _call_list(conv, start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert exc.value.status_code == 400


def test_equal_dates_are_allowed(conv):
    same = datetime(2024, 6, 1)
    with patch.object(conv.conversations_db, "get_conversations_count", return_value=0):
        result = _call_count(conv, start_date=same, end_date=same)
    assert result == {"count": 0}


def test_valid_range_passes_through(conv):
    with patch.object(conv.conversations_db, "get_conversations_count", return_value=0):
        result = _call_count(
            conv, start_date=datetime(2024, 1, 1), end_date=datetime(2024, 12, 31, tzinfo=timezone.utc)
        )
    assert result == {"count": 0}
