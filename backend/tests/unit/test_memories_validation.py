"""
Tests for memories validation filtering logic.
Regression test for issue #4501: ResponseValidationError after KeyError fix.
"""

import pytest
from datetime import datetime, timezone
from pydantic import BaseModel, ValidationError, Field
from typing import Optional, List
from enum import Enum


class MemoryCategory(str, Enum):
    """Copy of MemoryCategory for isolated testing."""

    interesting = "interesting"
    system = "system"
    manual = "manual"
    core = "core"


class MockMemoryDB(BaseModel):
    """
    Minimal mock of MemoryDB for testing validation logic.
    Mirrors required fields from the real MemoryDB model.
    """

    id: str
    uid: str
    content: str
    category: MemoryCategory = MemoryCategory.interesting
    created_at: datetime
    updated_at: datetime
    visibility: str = 'private'
    is_locked: bool = False


class TestMemoryValidationFiltering:
    """
    Test the validation filtering logic used in get_memories endpoint.
    The fix catches ValidationError and skips invalid docs.
    """

    def test_valid_memory_passes_validation(self):
        """Valid memory with all required fields should pass validation."""
        valid_doc = {
            'id': 'mem-123',
            'uid': 'user-456',
            'content': 'Test memory content',
            'category': 'interesting',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        }
        memory = MockMemoryDB.model_validate(valid_doc)
        assert memory.id == 'mem-123'
        assert memory.content == 'Test memory content'

    def test_missing_id_fails_validation(self):
        """Memory missing required 'id' field should fail validation."""
        invalid_doc = {
            # 'id': missing
            'uid': 'user-456',
            'content': 'Test memory content',
            'category': 'interesting',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        }
        with pytest.raises(ValidationError):
            MockMemoryDB.model_validate(invalid_doc)

    def test_missing_content_fails_validation(self):
        """Memory missing required 'content' field should fail validation."""
        invalid_doc = {
            'id': 'mem-123',
            'uid': 'user-456',
            # 'content': missing
            'category': 'interesting',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        }
        with pytest.raises(ValidationError):
            MockMemoryDB.model_validate(invalid_doc)

    def test_missing_uid_fails_validation(self):
        """Memory missing required 'uid' field should fail validation."""
        invalid_doc = {
            'id': 'mem-123',
            # 'uid': missing
            'content': 'Test memory content',
            'category': 'interesting',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        }
        with pytest.raises(ValidationError):
            MockMemoryDB.model_validate(invalid_doc)

    def test_missing_created_at_fails_validation(self):
        """Memory missing required 'created_at' field should fail validation."""
        invalid_doc = {
            'id': 'mem-123',
            'uid': 'user-456',
            'content': 'Test memory content',
            'category': 'interesting',
            # 'created_at': missing
            'updated_at': datetime.now(timezone.utc),
        }
        with pytest.raises(ValidationError):
            MockMemoryDB.model_validate(invalid_doc)

    def test_filter_invalid_memories_logic(self):
        """
        Test the filtering logic used in get_memories endpoint.
        Invalid docs should be caught and skipped, valid ones returned.
        """
        now = datetime.now(timezone.utc)
        valid_doc = {
            'id': 'mem-valid',
            'uid': 'user-456',
            'content': 'Valid memory',
            'category': 'interesting',
            'created_at': now,
            'updated_at': now,
        }
        invalid_doc_missing_id = {
            'uid': 'user-456',
            'content': 'Invalid - no id',
            'category': 'interesting',
            'created_at': now,
            'updated_at': now,
        }
        invalid_doc_missing_content = {
            'id': 'mem-invalid',
            'uid': 'user-456',
            'category': 'interesting',
            'created_at': now,
            'updated_at': now,
        }

        # Simulate the filtering logic from the endpoint
        memories = [valid_doc, invalid_doc_missing_id, invalid_doc_missing_content]
        valid_memories = []
        for memory in memories:
            try:
                valid_memories.append(MockMemoryDB.model_validate(memory))
            except ValidationError:
                continue

        assert len(valid_memories) == 1
        assert valid_memories[0].id == 'mem-valid'

    def test_all_invalid_returns_empty_list(self):
        """If all memories are invalid, should return empty list (not crash)."""
        now = datetime.now(timezone.utc)
        invalid_docs = [
            {'uid': 'user-456', 'content': 'No id', 'created_at': now, 'updated_at': now},
            {'id': 'mem-1', 'content': 'No uid', 'created_at': now, 'updated_at': now},
            {'id': 'mem-2', 'uid': 'user-456', 'created_at': now, 'updated_at': now},  # no content
        ]

        valid_memories = []
        for memory in invalid_docs:
            try:
                valid_memories.append(MockMemoryDB.model_validate(memory))
            except ValidationError:
                continue

        assert len(valid_memories) == 0

    def test_mixed_valid_invalid_preserves_order(self):
        """Valid memories should be returned in original order."""
        now = datetime.now(timezone.utc)
        memories = [
            {'id': 'first', 'uid': 'u1', 'content': 'First', 'created_at': now, 'updated_at': now},
            {'uid': 'u2', 'content': 'Invalid'},  # missing id, created_at, updated_at
            {'id': 'second', 'uid': 'u3', 'content': 'Second', 'created_at': now, 'updated_at': now},
        ]

        valid_memories = []
        for memory in memories:
            try:
                valid_memories.append(MockMemoryDB.model_validate(memory))
            except ValidationError:
                continue

        assert len(valid_memories) == 2
        assert valid_memories[0].id == 'first'
        assert valid_memories[1].id == 'second'

    def test_missing_updated_at_fails_validation(self):
        """Memory missing required 'updated_at' field should fail validation."""
        now = datetime.now(timezone.utc)
        invalid_doc = {
            'id': 'mem-123',
            'uid': 'user-456',
            'content': 'Test memory content',
            'category': 'interesting',
            'created_at': now,
            # 'updated_at': missing
        }
        with pytest.raises(ValidationError):
            MockMemoryDB.model_validate(invalid_doc)

    def test_invalid_type_datetime_fails_validation(self):
        """Memory with invalid type for datetime field should fail validation."""
        invalid_doc = {
            'id': 'mem-123',
            'uid': 'user-456',
            'content': 'Test memory content',
            'category': 'interesting',
            'created_at': 'not-a-datetime',  # invalid type
            'updated_at': 'also-not-datetime',  # invalid type
        }
        with pytest.raises(ValidationError):
            MockMemoryDB.model_validate(invalid_doc)

    def test_invalid_type_in_mixed_list(self):
        """Invalid type values should be filtered out in mixed list."""
        now = datetime.now(timezone.utc)
        memories = [
            {'id': 'valid', 'uid': 'u1', 'content': 'Valid', 'created_at': now, 'updated_at': now},
            {'id': 'bad-date', 'uid': 'u2', 'content': 'Bad', 'created_at': 'invalid', 'updated_at': now},
            {'id': 'missing-updated', 'uid': 'u3', 'content': 'Missing', 'created_at': now},
        ]

        valid_memories = []
        for memory in memories:
            try:
                valid_memories.append(MockMemoryDB.model_validate(memory))
            except ValidationError:
                continue

        assert len(valid_memories) == 1
        assert valid_memories[0].id == 'valid'
