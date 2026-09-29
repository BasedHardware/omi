"""Unit tests verifying date format exception sanitization in search_conversations_tool.

Failure-Class: none
Ensures invalid date format details and internal exception strings are never leaked in tool output strings.
"""

from unittest.mock import patch
from utils.retrieval.tools import conversation_tools

SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"


def test_search_conversations_invalid_start_date_sanitized():
    with patch("utils.retrieval.tools.conversation_tools.get_user_timezone", return_value="UTC"):
        res = conversation_tools.search_conversations_tool.func(
            query="test",
            start_date=f"bad-start-{SENTINEL_ERROR}",
            end_date="2026-09-29T12:00:00+00:00",
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert SENTINEL_ERROR not in res
    assert res == "Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone."


def test_search_conversations_invalid_end_date_sanitized():
    with patch("utils.retrieval.tools.conversation_tools.get_user_timezone", return_value="UTC"):
        res = conversation_tools.search_conversations_tool.func(
            query="test",
            start_date="2026-09-29T10:00:00+00:00",
            end_date=f"bad-end-{SENTINEL_ERROR}",
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert SENTINEL_ERROR not in res
    assert res == "Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone."
