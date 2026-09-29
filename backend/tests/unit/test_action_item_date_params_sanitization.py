"""Unit tests verifying date format exception sanitization in action item tools.

Failure-Class: none
Ensures invalid date format details and internal exception strings are never leaked in tool output strings.
"""

from unittest.mock import patch
from utils.retrieval.tools import action_item_tools

SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"


def test_get_action_items_invalid_start_date_sanitized():
    with patch("utils.retrieval.tools.action_item_tools.get_user_timezone", return_value="UTC"):
        res = action_item_tools.get_action_items_tool.func(
            start_date=f"bad-start-{SENTINEL_ERROR}",
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert SENTINEL_ERROR not in res
    assert res == "Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone."


def test_create_action_item_invalid_due_at_sanitized():
    with patch("utils.retrieval.tools.action_item_tools.get_user_timezone", return_value="UTC"):
        res = action_item_tools.create_action_item_tool.func(
            description="Buy groceries",
            due_at=f"bad-due-{SENTINEL_ERROR}",
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert SENTINEL_ERROR not in res
    assert res == "Error: Invalid due_at format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone."
