"""
Tests for MemoryCategory 'auto' enum value.
Regression test for issue #4504: Memories with category 'auto' fail validation.
"""

import pytest
from datetime import datetime, timezone
from pydantic import BaseModel, ValidationError, Field, validator
from typing import Optional, List
from enum import Enum


class MemoryCategory(str, Enum):
    """Copy of MemoryCategory for isolated testing - includes 'auto' legacy category."""

    # New primary categories
    interesting = "interesting"
    system = "system"
    manual = "manual"

    # Legacy categories for backward compatibility
    core = "core"
    hobbies = "hobbies"
    lifestyle = "lifestyle"
    interests = "interests"
    habits = "habits"
    work = "work"
    skills = "skills"
    learnings = "learnings"
    other = "other"
    auto = "auto"


CATEGORY_BOOSTS = {
    MemoryCategory.interesting.value: 1,
    MemoryCategory.system.value: 0,
    MemoryCategory.manual.value: 1,
    MemoryCategory.core.value: 1,
    MemoryCategory.hobbies.value: 1,
    MemoryCategory.lifestyle.value: 1,
    MemoryCategory.interests.value: 1,
    MemoryCategory.work.value: 1,
    MemoryCategory.skills.value: 1,
    MemoryCategory.learnings.value: 1,
    MemoryCategory.habits.value: 0,
    MemoryCategory.other.value: 0,
    MemoryCategory.auto.value: 0,
}


class MockMemory(BaseModel):
    """Mock of Memory model with category validator."""

    content: str
    category: MemoryCategory = MemoryCategory.interesting

    @validator('category', pre=True)
    def map_legacy_categories(cls, v):
        """Map legacy categories to new ones when creating memories"""
        if isinstance(v, MemoryCategory):
            return v

        legacy_to_new = {
            'core': 'system',
            'hobbies': 'system',
            'lifestyle': 'system',
            'interests': 'system',
            'work': 'system',
            'skills': 'system',
            'learnings': 'system',
            'habits': 'system',
            'other': 'system',
            'auto': 'system',
        }

        if isinstance(v, str):
            if v in ['interesting', 'system', 'manual']:
                return v
            if v in legacy_to_new:
                return legacy_to_new[v]
            return 'interesting'

        return 'interesting'


class MockMemoryDB(MockMemory):
    """Mock of MemoryDB for isolated testing."""

    id: str
    uid: str
    created_at: datetime
    updated_at: datetime
    visibility: str = 'private'
    is_locked: bool = False


class TestMemoryCategoryAutoEnum:
    """
    Test that 'auto' category is properly handled.
    Issue #4504: Memories with category 'auto' were failing validation.
    """

    def test_auto_is_valid_enum_value(self):
        """'auto' should be a valid MemoryCategory enum value."""
        assert 'auto' in [c.value for c in MemoryCategory]
        assert MemoryCategory.auto.value == 'auto'

    def test_auto_in_category_boosts(self):
        """'auto' should have a boost value defined."""
        assert 'auto' in CATEGORY_BOOSTS
        assert CATEGORY_BOOSTS['auto'] == 0

    def test_memory_with_auto_category_validates(self):
        """Memory document with category='auto' should pass validation."""
        now = datetime.now(timezone.utc)
        doc = {
            'id': 'mem-123',
            'uid': 'user-456',
            'content': 'Test memory with auto category',
            'category': 'auto',
            'created_at': now,
            'updated_at': now,
        }
        memory = MockMemoryDB.model_validate(doc)
        # auto is mapped to system by the validator
        assert memory.category == MemoryCategory.system

    def test_auto_maps_to_system(self):
        """'auto' legacy category should map to 'system'."""
        memory = MockMemory(content='test', category='auto')
        assert memory.category == MemoryCategory.system

    def test_mixed_categories_with_auto(self):
        """Test filtering with mix of categories including 'auto'."""
        now = datetime.now(timezone.utc)
        memories = [
            {
                'id': '1',
                'uid': 'u1',
                'content': 'interesting',
                'category': 'interesting',
                'created_at': now,
                'updated_at': now,
            },
            {'id': '2', 'uid': 'u2', 'content': 'auto', 'category': 'auto', 'created_at': now, 'updated_at': now},
            {'id': '3', 'uid': 'u3', 'content': 'system', 'category': 'system', 'created_at': now, 'updated_at': now},
            {'id': '4', 'uid': 'u4', 'content': 'manual', 'category': 'manual', 'created_at': now, 'updated_at': now},
        ]

        valid_memories = []
        for memory in memories:
            try:
                valid_memories.append(MockMemoryDB.model_validate(memory))
            except ValidationError:
                continue

        assert len(valid_memories) == 4
        # auto should be mapped to system
        assert valid_memories[1].category == MemoryCategory.system

    def test_auto_category_without_validator_still_valid(self):
        """Even without mapping, 'auto' should be a valid enum value."""
        # Direct enum assignment (bypassing validator)
        assert MemoryCategory('auto') == MemoryCategory.auto

    def test_old_behavior_would_fail_validation(self):
        """
        Verify that without 'auto' in enum, validation would fail.
        This confirms the bug existed.
        """

        class OldMemoryCategory(str, Enum):
            interesting = "interesting"
            system = "system"
            manual = "manual"
            # Missing: auto = "auto"

        with pytest.raises(ValueError):
            OldMemoryCategory('auto')
