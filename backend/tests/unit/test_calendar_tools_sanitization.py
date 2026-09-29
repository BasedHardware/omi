"""Unit tests verifying exception sanitization in calendar retrieval tools.

Failure-Class: none
Ensures invalid date format details and internal exception strings are never leaked in tool output strings.
"""

from utils.retrieval.tools import calendar_tools

SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"


def test_calendar_create_event_invalid_start_time_sanitized():
    res = calendar_tools.create_calendar_event_tool.func(
        title="Sync Meeting",
        start_time=f"bad-time-{SENTINEL_ERROR}",
        end_time="2026-09-29T11:00:00+00:00",
        config={"configurable": {"user_id": "test-uid-123"}},
    )
    assert SENTINEL_ERROR not in res
    assert res == "Error: Invalid start_time format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM."


def test_calendar_create_event_invalid_end_time_sanitized():
    res = calendar_tools.create_calendar_event_tool.func(
        title="Sync Meeting",
        start_time="2026-09-29T10:00:00+00:00",
        end_time=f"bad-time-{SENTINEL_ERROR}",
        config={"configurable": {"user_id": "test-uid-123"}},
    )
    assert SENTINEL_ERROR not in res
    assert res == "Error: Invalid end_time format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM."
