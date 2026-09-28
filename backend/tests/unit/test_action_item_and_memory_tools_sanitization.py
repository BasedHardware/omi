"""Unit tests verifying exception sanitization in action item and memory retrieval tools.

Failure-Class: none
Ensures internal exception messages and database errors are never returned directly in tool output strings.
"""

from unittest.mock import patch
from utils.retrieval.tools import action_item_tools, memory_tools

SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"


def test_get_action_items_tool_exception_sanitized():
    with patch(
        "utils.retrieval.tools.action_item_tools.action_items_db.get_action_items",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = action_item_tools.get_action_items_tool(config={"configurable": {"user_id": "test-uid-123"}})
    assert SENTINEL_ERROR not in res
    assert "Error: Failed to retrieve action items." in res


def test_create_action_item_tool_exception_sanitized():
    with patch(
        "utils.retrieval.tools.action_item_tools.action_items_db.create_action_item",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = action_item_tools.create_action_item_tool(
            description="Do dishes", config={"configurable": {"user_id": "test-uid-123"}}
        )
    assert SENTINEL_ERROR not in res
    assert "Error: Failed to create action item." in res


def test_update_action_item_tool_exception_sanitized():
    with patch(
        "utils.retrieval.tools.action_item_tools.action_items_db.update_action_item_description",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = action_item_tools.update_action_item_tool(
            action_item_id="item-123",
            description="New description",
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert SENTINEL_ERROR not in res
    assert "Error: Failed to update action item." in res


def test_search_memories_tool_exception_sanitized():
    with patch(
        "utils.retrieval.tools.memory_tools.memory_service.read",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = memory_tools.search_memories_tool(
            query="test query", config={"configurable": {"user_id": "test-uid-123"}}
        )
    assert SENTINEL_ERROR not in res
    assert "Error searching memories: Failed to search memories." in res
