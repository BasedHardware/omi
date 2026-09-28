"""Unit tests verifying exception sanitization in screen activity and notification settings tools.

Failure-Class: none
Ensures invalid date format details and internal database exceptions are never leaked in tool output strings.
"""

from unittest.mock import patch
from utils.retrieval.tools import screen_activity_tools, notification_settings_tools

SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"


def test_screen_activity_invalid_date_sanitization():
    res = screen_activity_tools.get_screen_activity_tool(
        start_date=f"bad-date-{SENTINEL_ERROR}",
        end_date="2026-09-28T22:00:00+00:00",
        config={"configurable": {"user_id": "test-uid-123"}},
    )
    assert res == "Error: Invalid date format. Use YYYY-MM-DDTHH:MM:SS+HH:MM."
    assert SENTINEL_ERROR not in res


def test_screen_activity_database_exception_sanitization():
    with patch(
        "utils.retrieval.tools.screen_activity_tools.screen_activity_db.get_screen_activity_summary",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = screen_activity_tools.get_screen_activity_tool(
            start_date="2026-09-28T00:00:00+00:00",
            end_date="2026-09-28T22:00:00+00:00",
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert res == "Error: Failed to retrieve screen activity."
    assert SENTINEL_ERROR not in res


def test_notification_settings_database_exception_sanitization():
    with patch(
        "utils.retrieval.tools.notification_settings_tools.notification_db.get_daily_summary_enabled",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = notification_settings_tools.manage_daily_summary_tool(
            action="get_settings",
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert res == "Error: Failed to update or retrieve notification settings."
    assert SENTINEL_ERROR not in res


def test_notification_settings_enable_database_exception_sanitized():
    with patch(
        "utils.retrieval.tools.notification_settings_tools.notification_db.set_daily_summary_enabled",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = notification_settings_tools.manage_daily_summary_tool(
            action="enable",
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert res == "Error: Failed to update or retrieve notification settings."
    assert SENTINEL_ERROR not in res
