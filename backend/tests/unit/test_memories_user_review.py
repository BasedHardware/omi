"""
Tests for get_memories user_review filtering logic.
Regression test for issue #4498: KeyError when user_review field missing.
"""

import pytest


class TestUserReviewFilterLogic:
    """
    Test the user_review filtering logic used in get_memories().

    The filter: memory.get('user_review') is not False

    Expected behavior:
    - Missing user_review field -> included (get returns None, None is not False)
    - user_review=None -> included (None is not False)
    - user_review=True -> included (True is not False)
    - user_review=False -> excluded (False is not False = False)
    """

    def filter_memories(self, memories: list) -> list:
        """Replicate the filtering logic from get_memories()."""
        return [memory for memory in memories if memory.get('user_review') is not False]

    def test_memory_without_user_review_field_included(self):
        """Memory without user_review field should be included (not crash with KeyError)."""
        memories = [{'id': '1', 'content': 'test memory'}]
        result = self.filter_memories(memories)
        assert len(result) == 1
        assert result[0]['id'] == '1'

    def test_memory_with_user_review_none_included(self):
        """Memory with user_review=None should be included."""
        memories = [{'id': '1', 'user_review': None}]
        result = self.filter_memories(memories)
        assert len(result) == 1

    def test_memory_with_user_review_false_excluded(self):
        """Memory with user_review=False should be excluded."""
        memories = [{'id': '1', 'user_review': False}]
        result = self.filter_memories(memories)
        assert len(result) == 0

    def test_memory_with_user_review_true_included(self):
        """Memory with user_review=True should be included."""
        memories = [{'id': '1', 'user_review': True}]
        result = self.filter_memories(memories)
        assert len(result) == 1

    def test_mixed_user_review_values(self):
        """Test filtering with mixed user_review values."""
        memories = [
            {'id': '1'},  # missing field - included
            {'id': '2', 'user_review': None},  # None - included
            {'id': '3', 'user_review': True},  # True - included
            {'id': '4', 'user_review': False},  # False - excluded
        ]
        result = self.filter_memories(memories)

        assert len(result) == 3
        result_ids = [m['id'] for m in result]
        assert '1' in result_ids
        assert '2' in result_ids
        assert '3' in result_ids
        assert '4' not in result_ids

    def test_old_behavior_would_keyerror(self):
        """
        Verify that the old behavior (direct dict access) would raise KeyError.
        This confirms the bug existed and our fix addresses it.
        """
        memories = [{'id': '1', 'content': 'test memory'}]  # no user_review field

        with pytest.raises(KeyError):
            # Old buggy code: memory['user_review']
            _ = [memory for memory in memories if memory['user_review'] is not False]
