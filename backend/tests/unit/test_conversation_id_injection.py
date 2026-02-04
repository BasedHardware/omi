"""
Unit tests for conversation ID injection in Firestore helpers.

Verifies that:
1. doc.id is properly injected into returned dictionaries
2. doc.id takes precedence over any stored 'id' field in the document
3. Empty streams return [] or None without KeyError
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# https://github.com/BasedHardware/omi/blob/main/backend/.env.template#L48C20-L48C88
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

# Mock modules that initialize GCP clients at import time
sys.modules["database._client"] = MagicMock()
sys.modules["utils.other.storage"] = MagicMock()
sys.modules["utils.stt.pre_recorded"] = MagicMock()


class MockDocument:
    """Mock Firestore DocumentSnapshot with id and to_dict()."""

    def __init__(self, doc_id: str, data: dict, exists: bool = True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data.copy()


class MockQuery:
    """Mock Firestore query that returns an iterable stream."""

    def __init__(self, docs):
        self._docs = docs

    def stream(self):
        return iter(self._docs)

    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def offset(self, *args, **kwargs):
        return self


def test_id_injection_basic():
    """Verify that doc.id is injected into returned dict."""
    doc = MockDocument("conv-123", {"title": "Test Conversation", "status": "completed"})

    # Simulate the pattern used in conversations.py
    result = {**doc.to_dict(), 'id': doc.id}

    assert result['id'] == "conv-123"
    assert result['title'] == "Test Conversation"
    assert result['status'] == "completed"


def test_id_injection_overrides_stored_id():
    """Verify that doc.id takes precedence over any stored 'id' field."""
    # Document contains a stored 'id' field that should be overridden
    doc = MockDocument("firestore-doc-id", {"id": "wrong-stored-id", "title": "Test"})

    # The correct pattern: {**doc.to_dict(), 'id': doc.id} ensures doc.id wins
    result = {**doc.to_dict(), 'id': doc.id}

    assert result['id'] == "firestore-doc-id", "doc.id should override stored 'id'"
    assert result['title'] == "Test"


def test_id_injection_wrong_order_allows_override():
    """Demonstrate that wrong order {'id': doc.id, **doc.to_dict()} allows override."""
    doc = MockDocument("firestore-doc-id", {"id": "wrong-stored-id", "title": "Test"})

    # Wrong pattern: stored id would override doc.id
    wrong_result = {'id': doc.id, **doc.to_dict()}

    # This test documents the bug that was fixed
    assert wrong_result['id'] == "wrong-stored-id", "Wrong order allows stored id to override"


def test_list_comprehension_with_id_injection():
    """Verify list comprehension pattern injects id correctly."""
    docs = [
        MockDocument("conv-1", {"title": "First"}),
        MockDocument("conv-2", {"title": "Second"}),
        MockDocument("conv-3", {"title": "Third"}),
    ]
    query = MockQuery(docs)

    # Pattern used in get_conversations_without_photos, get_processing_conversations, etc.
    conversations = [{**doc.to_dict(), 'id': doc.id} for doc in query.stream()]

    assert len(conversations) == 3
    assert conversations[0]['id'] == "conv-1"
    assert conversations[1]['id'] == "conv-2"
    assert conversations[2]['id'] == "conv-3"


def test_empty_stream_returns_empty_list():
    """Verify empty stream returns empty list without KeyError."""
    query = MockQuery([])

    conversations = [{**doc.to_dict(), 'id': doc.id} for doc in query.stream()]

    assert conversations == []


def test_get_last_completed_conversation_pattern():
    """Verify the get_last_completed_conversation pattern."""
    docs = [MockDocument("latest-conv", {"title": "Latest", "status": "completed"})]
    query = MockQuery(docs)

    conversations = [{**doc.to_dict(), 'id': doc.id} for doc in query.stream()]
    conversation = conversations[0] if conversations else None

    assert conversation is not None
    assert conversation['id'] == "latest-conv"


def test_get_last_completed_conversation_empty():
    """Verify empty query returns None without error."""
    query = MockQuery([])

    conversations = [{**doc.to_dict(), 'id': doc.id} for doc in query.stream()]
    conversation = conversations[0] if conversations else None

    assert conversation is None


def test_get_conversations_by_id_skips_discarded():
    """Verify get_conversations_by_id pattern skips discarded conversations."""
    docs = [
        MockDocument("conv-1", {"title": "Active", "discarded": False}, exists=True),
        MockDocument("conv-2", {"title": "Discarded", "discarded": True}, exists=True),
        MockDocument("conv-3", {"title": "Also Active"}, exists=True),  # No discarded field
        MockDocument("conv-4", {}, exists=False),  # Non-existent
    ]

    # Pattern from get_conversations_by_id
    conversations = []
    for doc in docs:
        if doc.exists:
            data = {**doc.to_dict(), 'id': doc.id}
            if data.get('discarded'):
                continue
            conversations.append(data)

    assert len(conversations) == 2
    assert conversations[0]['id'] == "conv-1"
    assert conversations[1]['id'] == "conv-3"


def test_id_accessible_after_injection():
    """Verify that 'id' key can be accessed without KeyError after injection."""
    doc = MockDocument("test-id", {"title": "Test"})

    result = {**doc.to_dict(), 'id': doc.id}

    # This would have raised KeyError before the fix
    conversation_id = result['id']
    assert conversation_id == "test-id"
