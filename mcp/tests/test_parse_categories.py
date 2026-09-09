"""
Tests for the shared _parse_categories helper used by the get_memories and
get_conversations tool dispatchers.

Regression coverage for a crash where the get_conversations dispatcher passed
raw JSON strings straight through to get_conversations(), whose category
serialization calls `c.value` and raised `'str' object has no attribute
'value'` for any non-empty categories filter.
"""

import logging
from unittest.mock import MagicMock

import pytest

from mcp_server_omi.server import ConversationCategory, MemoryCategory, _parse_categories


class TestParseCategories:
    def test_converts_valid_strings_to_conversation_enum(self):
        logger = logging.getLogger("test")
        result = _parse_categories(["work", "travel"], ConversationCategory, logger)
        assert result == [ConversationCategory.work, ConversationCategory.travel]

    def test_converts_valid_strings_to_memory_enum(self):
        logger = logging.getLogger("test")
        result = _parse_categories(["work"], MemoryCategory, logger)
        assert result == [MemoryCategory.work]

    def test_empty_list_returns_empty_list(self):
        logger = logging.getLogger("test")
        assert _parse_categories([], ConversationCategory, logger) == []

    def test_invalid_category_is_dropped_and_logged(self):
        logger = MagicMock(spec=logging.Logger)
        result = _parse_categories(["not-a-real-category"], ConversationCategory, logger)
        assert result == []
        logger.warning.assert_called_once()

    def test_non_list_input_raises_value_error(self):
        logger = logging.getLogger("test")
        with pytest.raises(ValueError):
            _parse_categories("work", ConversationCategory, logger)

    def test_result_values_have_value_attribute(self):
        # This is the direct regression check: every element returned must be
        # an enum member (so `.value` works downstream), never a raw string.
        logger = logging.getLogger("test")
        result = _parse_categories(["work"], ConversationCategory, logger)
        assert all(hasattr(c, "value") for c in result)
        assert result[0].value == "work"
