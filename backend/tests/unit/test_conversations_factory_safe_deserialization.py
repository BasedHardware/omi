"""Hermetic unit tests for safe batch deserialization in conversation factory.

Validates that malformed or legacy Firestore records do not crash batch operations
such as RAG context retrieval, Year-in-Review Wrapped generation, or user batch feeds.
Mirrors Person.deserialize_many_safe and Message.deserialize_many_safe.
"""

from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _ensure_stub(name: str):
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None):
        return existing
    if existing is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# Stub database chain so models/utils can import without Firestore credentials
_ensure_stub("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], "__path__", [])
for _sub in ["_client", "redis_db", "users", "folders", "auth"]:
    _ensure_stub(f"database.{_sub}")
sys.modules["database._client"].db = MagicMock()
sys.modules["database.auth"].get_user_name = MagicMock(return_value="TestUser")
sys.modules["database.users"].get_people_by_ids = MagicMock(return_value=[])
sys.modules["database.folders"].get_folders = MagicMock(return_value=[])

for _mod in [
    "models",
    "models.conversation",
    "models.conversation_enums",
    "models.structured",
    "utils",
    "utils.conversations",
    "utils.conversations.factory",
]:
    _existing = sys.modules.get(_mod)
    if _existing is not None and not getattr(_existing, "__file__", None):
        del sys.modules[_mod]

from models.conversation import Conversation
from models.conversation_enums import CategoryEnum
from models.structured import Structured
from utils.conversations.factory import (
    deserialize_conversation,
    deserialize_conversations,
)


def _make_conversation(conv_id: str = "valid-1") -> Conversation:
    now = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    return Conversation(
        id=conv_id,
        created_at=now,
        started_at=now,
        finished_at=now,
        structured=Structured(
            title=f"Title {conv_id}",
            overview=f"Overview {conv_id}",
            category=CategoryEnum.personal,
        ),
    )


def test_batch_deserialization_skips_malformed_records():
    """Verify malformed records are safely skipped while valid records are preserved."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    existing_conv = _make_conversation("existing-conv")

    items = [
        {
            "id": "valid-dict-1",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "structured": {"title": "Valid 1", "overview": "Overview 1"},
        },
        existing_conv,
        {"id": "corrupt-no-structured", "created_at": now},  # Missing required 'structured'
        {"corrupt_garbage": True},  # Missing 'id', 'created_at', 'structured'
        {
            "id": "corrupt-invalid-date",
            "created_at": "not-a-valid-iso-date",
            "structured": {"title": "Bad Date", "overview": "Bad Date"},
        },
        {
            "id": "valid-dict-2",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "structured": {"title": "Valid 2", "overview": "Overview 2"},
        },
    ]

    # In safe deserialization, corrupted items are skipped without fatal ValidationError
    results = deserialize_conversations(items)
    assert len(results) == 3
    assert results[0].id == "valid-dict-1"
    assert results[1].id == "existing-conv"
    assert results[2].id == "valid-dict-2"


def test_batch_deserialization_on_error_callback():
    """Verify on_error callback is invoked with offending record and exception."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    skipped_items = []
    skipped_exceptions = []

    def handle_error(item, exc):
        skipped_items.append(item)
        skipped_exceptions.append(exc)

    items = [
        {
            "id": "valid-1",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "structured": {"title": "Valid 1", "overview": "Overview 1"},
        },
        {"id": "corrupt-record"},  # Missing structured & created_at
    ]

    results = deserialize_conversations(items, on_error=handle_error)
    assert len(results) == 1
    assert results[0].id == "valid-1"
    assert len(skipped_items) == 1
    assert skipped_items[0] == {"id": "corrupt-record"}
    assert len(skipped_exceptions) == 1
    assert isinstance(skipped_exceptions[0], Exception)


def test_batch_deserialization_all_corrupted():
    """Verify an all-corrupt batch returns empty list instead of crashing."""
    items = [
        {"bad": 1},
        {"corrupt": "data"},
    ]
    results = deserialize_conversations(items)
    assert results == []


def test_batch_deserialization_empty_list():
    """Verify empty input returns empty list."""
    assert deserialize_conversations([]) == []


def test_batch_deserialization_safe_alias():
    """Verify deserialize_conversations_safe is exposed as an alias matching repo conventions."""
    from utils.conversations.factory import deserialize_conversations_safe

    assert deserialize_conversations_safe is deserialize_conversations
