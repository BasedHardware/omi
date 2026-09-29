"""Tests for duplicate conversation ID validation on POST /v1/conversations/merge.

Vulnerability / Invariant:
Merging requires at least 2 distinct conversations.
Supplying duplicate conversation IDs (e.g. ['c1', 'c1'] or ['c1', 'c2', 'c1'])
would otherwise bypass the `len(request.conversation_ids) < 2` count check,
causing perform_merge_async to duplicate segments, photos, and audio files,
and delete the source conversation (irreversible data corruption).
The endpoint and validator must reject duplicate conversation IDs with HTTP 400.
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
    """Load a fresh routers.conversations against stubbed dependencies."""
    firebase_auth_stub = ModuleType("firebase_admin.auth")
    firebase_auth_stub.InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})

    endpoints_stub = ModuleType("utils.other.endpoints")

    def _fake_get_current_user_uid():
        return "test-uid"

    def _fake_with_rate_limit(dependency, _policy):
        return dependency

    endpoints_stub.get_current_user_uid = _fake_get_current_user_uid
    endpoints_stub.with_rate_limit = _fake_with_rate_limit
    endpoints_stub.get_user = MagicMock()

    class _MemorySystem(str, Enum):
        LEGACY = "legacy"
        CANONICAL = "canonical"

    memory_system_stub = ModuleType("utils.memory.memory_system")
    setattr(memory_system_stub, "MemorySystem", _MemorySystem)

    memory_pkg = ModuleType("utils.memory")
    memory_pkg.__path__ = []

    memory_service_stub = ModuleType("utils.memory.memory_service")
    setattr(memory_service_stub, "MemoryService", MagicMock())

    canonical_activation_stub = ModuleType("utils.memory.canonical_activation")
    setattr(canonical_activation_stub, "canonical_write_enabled", MagicMock(return_value=False))

    retraction_scope_stub = ModuleType("utils.memory.retraction_scope")
    for _name in [
        "canonical_intake_is_fenced",
        "historical_source_conversation_ids",
        "retraction_can_be_skipped",
    ]:
        setattr(retraction_scope_stub, _name, MagicMock())

    canonical_adapter_stub = ModuleType("utils.memory.canonical_memory_adapter")

    class _ConversationReplacementConflictError(RuntimeError):
        pass

    setattr(canonical_adapter_stub, "ConversationReplacementConflictError", _ConversationReplacementConflictError)

    request_validation_stub = ModuleType("utils.request_validation")
    request_validation_stub.NonNegativeOffset = int
    request_validation_stub.PositiveLimit = int

    conversations_db_stub = AutoMockModule("database.conversations")
    conversations_db_stub.get_conversation = MagicMock(return_value={"id": "c1", "status": "completed"})

    fakes: dict[str, ModuleType] = {
        "ulid": AutoMockModule("ulid"),
        "pinecone": AutoMockModule("pinecone"),
        "typesense": AutoMockModule("typesense"),
        "database._client": AutoMockModule("database._client"),
        "database.conversations": conversations_db_stub,
        "database.action_items": AutoMockModule("database.action_items"),
        "database.memories": AutoMockModule("database.memories"),
        "database.redis_db": AutoMockModule("database.redis_db"),
        "database.users": AutoMockModule("database.users"),
        "database.vector_db": AutoMockModule("database.vector_db"),
        "firebase_admin": AutoMockModule("firebase_admin"),
        "firebase_admin.messaging": AutoMockModule("firebase_admin.messaging"),
        "firebase_admin.auth": firebase_auth_stub,
        "firebase_admin.credentials": AutoMockModule("firebase_admin.credentials"),
        "firebase_admin.firestore": AutoMockModule("firebase_admin.firestore"),
        "google.cloud.firestore": AutoMockModule("google.cloud.firestore"),
        "google.cloud.firestore_v1": AutoMockModule("google.cloud.firestore_v1"),
        "utils.other.endpoints": endpoints_stub,
        "utils.other.storage": AutoMockModule("utils.other.storage"),
        "utils.screen_frames": AutoMockModule("utils.screen_frames"),
        "utils.screen_frames.store": AutoMockModule("utils.screen_frames.store"),
        "utils.conversations.factory": AutoMockModule("utils.conversations.factory"),
        "utils.conversations.render": AutoMockModule("utils.conversations.render"),
        "utils.conversations.process_conversation": AutoMockModule("utils.conversations.process_conversation"),
        "utils.conversations.search": AutoMockModule("utils.conversations.search"),
        "utils.conversations.mcp_transcript_search": AutoMockModule("utils.conversations.mcp_transcript_search"),
        "utils.conversations.calendar_linking": AutoMockModule("utils.conversations.calendar_linking"),
        "utils.conversations.calendar_utils": AutoMockModule("utils.conversations.calendar_utils"),
        "utils.conversations.location": AutoMockModule("utils.conversations.location"),
        "utils.conversations.analytics": AutoMockModule("utils.conversations.analytics"),
        "utils.llm.conversation_processing": AutoMockModule("utils.llm.conversation_processing"),
        "utils.speaker_identification": AutoMockModule("utils.speaker_identification"),
        "utils.app_integrations": AutoMockModule("utils.app_integrations"),
        "utils.retrieval.tools.calendar_tools": AutoMockModule("utils.retrieval.tools.calendar_tools"),
        "utils.retrieval.tools.google_utils": AutoMockModule("utils.retrieval.tools.google_utils"),
        "utils.memory": memory_pkg,
        "utils.memory.memory_service": memory_service_stub,
        "utils.memory.memory_system": memory_system_stub,
        "utils.memory.canonical_activation": canonical_activation_stub,
        "utils.memory.retraction_scope": retraction_scope_stub,
        "utils.memory.canonical_memory_adapter": canonical_adapter_stub,
        "utils.request_validation": request_validation_stub,
    }

    with stub_modules(fakes):
        module = load_module_fresh(
            "routers.conversations",
            os.path.join(str(_BACKEND), "routers", "conversations.py"),
        )
        yield module


def test_merge_rejects_duplicate_conversation_ids(conv):
    """POST /v1/conversations/merge must reject duplicate identical IDs with HTTP 400."""
    from models.conversation import MergeConversationsRequest
    from starlette.background import BackgroundTasks

    req = MergeConversationsRequest(conversation_ids=["c1", "c1"])
    with pytest.raises(HTTPException) as exc_info:
        conv.merge_conversations(
            request=req,
            background_tasks=BackgroundTasks(),
            uid="test-uid",
        )
    assert exc_info.value.status_code == 400
    assert "duplicate" in exc_info.value.detail.lower()


def test_merge_rejects_duplicate_ids_in_mixed_list(conv):
    """POST /v1/conversations/merge must reject duplicate IDs when mixed with distinct ones."""
    from models.conversation import MergeConversationsRequest
    from starlette.background import BackgroundTasks

    req = MergeConversationsRequest(conversation_ids=["c1", "c2", "c1"])
    with pytest.raises(HTTPException) as exc_info:
        conv.merge_conversations(
            request=req,
            background_tasks=BackgroundTasks(),
            uid="test-uid",
        )
    assert exc_info.value.status_code == 400
    assert "duplicate" in exc_info.value.detail.lower()
