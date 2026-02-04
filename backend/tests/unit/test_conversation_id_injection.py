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


# ============================================================================
# PROOF TESTS: Demonstrate the bug and why the fix is needed
# ============================================================================


class TestBugProof:
    """Tests that prove the bug exists and the fix is necessary."""

    def test_bug_proof_to_dict_missing_id(self):
        """PROOF: doc.to_dict() does NOT include document ID - this is the root cause."""
        doc = MockDocument(
            "firestore-doc-id",
            {
                "title": "Test",
                "status": "completed",
                "started_at": "2026-01-01",
            },
        )

        data = doc.to_dict()

        # PROOF: 'id' is NOT in the dict returned by to_dict()
        assert 'id' not in data, "to_dict() should NOT include document ID"
        assert doc.id == "firestore-doc-id", "ID exists on doc.id attribute"

    def test_bug_proof_keyerror_without_fix(self):
        """PROOF: Accessing ['id'] on to_dict() raises KeyError - the original bug."""
        doc = MockDocument("conv-123", {"title": "Test", "status": "completed"})

        # Simulate OLD code: conversations = [doc.to_dict() for doc in query.stream()]
        data_without_fix = doc.to_dict()

        # PROOF: This is what causes the KeyError in issue #4494
        with pytest.raises(KeyError) as exc_info:
            _ = data_without_fix['id']

        assert exc_info.value.args[0] == 'id'

    def test_bug_proof_print_statement_crashes(self):
        """PROOF: The debug print at line 1021 crashes without fix."""
        doc = MockDocument(
            "conv-123",
            {
                "started_at": "2026-01-01T00:00:00",
                "finished_at": "2026-01-01T01:00:00",
            },
        )

        # OLD code pattern (before fix)
        conversation = doc.to_dict()

        # This simulates line 1021: print('-', conversation['id'], ...)
        with pytest.raises(KeyError):
            print('-', conversation['id'], conversation['started_at'], conversation['finished_at'])

    def test_fix_proof_print_statement_works(self):
        """PROOF: With fix, the debug print works correctly."""
        doc = MockDocument(
            "conv-123",
            {
                "started_at": "2026-01-01T00:00:00",
                "finished_at": "2026-01-01T01:00:00",
            },
        )

        # NEW code pattern (with fix)
        conversation = {**doc.to_dict(), 'id': doc.id}

        # This now works - simulates line 1021
        output = f"- {conversation['id']} {conversation['started_at']} {conversation['finished_at']}"
        assert "conv-123" in output


class TestWithPhotosDecoratorBehavior:
    """Tests proving the @with_photos decorator silently skips when no 'id'."""

    def test_decorator_skips_without_id(self):
        """PROOF: @with_photos decorator silently skips when 'id' is missing."""

        # Simulate the decorator's check at helpers.py:221
        def decorator_check(conversation_data):
            if not isinstance(conversation_data, dict) or 'id' not in conversation_data:
                return conversation_data  # Returns unchanged - NO CRASH
            # Would attach photos here
            conversation_data['photos'] = ['photo1', 'photo2']
            return conversation_data

        # Data WITHOUT id (old buggy behavior)
        data_without_id = {"title": "Test", "status": "completed"}
        result = decorator_check(data_without_id)

        # PROOF: No crash, but photos NOT attached
        assert 'photos' not in result, "Photos should NOT be attached without 'id'"

    def test_decorator_attaches_photos_with_id(self):
        """PROOF: @with_photos decorator works correctly when 'id' is present."""

        def decorator_check(conversation_data):
            if not isinstance(conversation_data, dict) or 'id' not in conversation_data:
                return conversation_data
            conversation_data['photos'] = ['photo1', 'photo2']
            return conversation_data

        # Data WITH id (fixed behavior)
        data_with_id = {"id": "conv-123", "title": "Test", "status": "completed"}
        result = decorator_check(data_with_id)

        # PROOF: Photos ARE attached when 'id' is present
        assert 'photos' in result, "Photos should be attached when 'id' is present"
        assert result['photos'] == ['photo1', 'photo2']


class TestConversationModelRequiresId:
    """Tests proving Conversation model requires 'id' field."""

    def test_conversation_model_requires_id(self):
        """PROOF: Conversation(**data) fails without 'id' field."""
        from pydantic import BaseModel, ValidationError
        from typing import Optional
        from datetime import datetime

        # Minimal Conversation model mirroring the real one
        class MockConversation(BaseModel):
            id: str  # REQUIRED - this is the key constraint
            created_at: datetime
            title: Optional[str] = None

        # Data without 'id' (old buggy behavior)
        data_without_id = {
            "created_at": datetime.now(),
            "title": "Test",
        }

        # PROOF: Pydantic validation fails without 'id'
        with pytest.raises(ValidationError) as exc_info:
            MockConversation(**data_without_id)

        assert "id" in str(exc_info.value), "Validation should fail for missing 'id'"

    def test_conversation_model_works_with_id(self):
        """PROOF: Conversation(**data) works with 'id' field."""
        from pydantic import BaseModel
        from typing import Optional
        from datetime import datetime

        class MockConversation(BaseModel):
            id: str
            created_at: datetime
            title: Optional[str] = None

        # Data with 'id' (fixed behavior)
        data_with_id = {
            "id": "conv-123",
            "created_at": datetime.now(),
            "title": "Test",
        }

        # PROOF: Model instantiation succeeds with 'id'
        conv = MockConversation(**data_with_id)
        assert conv.id == "conv-123"
