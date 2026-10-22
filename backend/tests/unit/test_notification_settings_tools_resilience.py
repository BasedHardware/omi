import os
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.retrieval.tools.notification_settings_tools import (
    manage_daily_summary_tool,
    _resolve_uid,
    _format_hour,
)


def test_resolve_uid_variants():
    # 1. Configurable user_id
    assert _resolve_uid({"configurable": {"user_id": "u1"}}) == "u1"

    # 2. Configurable uid alias
    assert _resolve_uid({"configurable": {"uid": "u2"}}) == "u2"

    # 3. Top-level user_id
    assert _resolve_uid({"user_id": "u3"}) == "u3"

    # 4. Top-level uid alias
    assert _resolve_uid({"uid": "u4"}) == "u4"

    # 5. Non-dict or empty
    assert _resolve_uid(None) is None
    assert _resolve_uid({}) is None
    assert _resolve_uid("string") is None
    assert _resolve_uid(12345) is None


def test_format_hour():
    assert _format_hour(0) == "12:00 AM (midnight)"
    assert _format_hour(12) == "12:00 PM (noon)"
    assert _format_hour(8) == "8:00 AM"
    assert _format_hour(21) == "9:00 PM"
    assert _format_hour("22") == "10:00 PM"
    assert _format_hour("invalid") == "10:00 PM"  # fallback default 22


def test_manage_daily_summary_tool_missing_uid():
    res = manage_daily_summary_tool.func("enable", config={})
    assert res == "Error: User ID not found"


def test_manage_daily_summary_tool_invalid_action():
    # None action
    res = manage_daily_summary_tool.func(None, config={"user_id": "u1"})
    assert res == "Error: Action must be a non-empty string ('enable', 'disable', 'set_time', 'get_settings')."

    # Empty action
    res = manage_daily_summary_tool.func("   ", config={"user_id": "u1"})
    assert res == "Error: Action must be a non-empty string ('enable', 'disable', 'set_time', 'get_settings')."

    # Unknown action
    res = manage_daily_summary_tool.func("dance", config={"user_id": "u1"})
    assert res == "Unknown action: dance. Use 'enable', 'disable', 'set_time', or 'get_settings'."


@patch("database.notifications.set_daily_summary_hour_local")
@patch("database.notifications.get_daily_summary_enabled")
@patch("database.notifications.set_daily_summary_enabled")
def test_manage_daily_summary_tool_set_time(mock_set_enabled, mock_get_enabled, mock_set_hour):
    mock_get_enabled.return_value = True

    # 1. Valid integer hour
    res = manage_daily_summary_tool.func("set_time", hour=9, config={"uid": "user_1"})
    assert res == "Daily summary time changed to 9:00 AM."
    mock_set_hour.assert_called_with("user_1", 9)

    # 2. String numeric hour (coercion)
    mock_set_hour.reset_mock()
    res = manage_daily_summary_tool.func("set_time", hour="21", config={"uid": "user_1"})
    assert res == "Daily summary time changed to 9:00 PM."
    mock_set_hour.assert_called_with("user_1", 21)

    # 3. Missing hour parameter
    res = manage_daily_summary_tool.func("set_time", hour=None, config={"uid": "user_1"})
    assert res == "Error: Please specify the hour (0-23). Example: 22 for 10 PM, 9 for 9 AM."

    # 4. Out of bounds hour
    res = manage_daily_summary_tool.func("set_time", hour=24, config={"uid": "user_1"})
    assert res == "Error: Hour must be between 0 and 23. You provided 24."
    res = manage_daily_summary_tool.func("set_time", hour=-1, config={"uid": "user_1"})
    assert res == "Error: Hour must be between 0 and 23. You provided -1."

    # 5. Non-numeric hour string
    res = manage_daily_summary_tool.func("set_time", hour="noon", config={"uid": "user_1"})
    assert res == "Error: Hour must be an integer between 0 and 23. You provided noon."


@patch("database.notifications.set_daily_summary_enabled")
@patch("database.notifications.get_daily_summary_hour_local")
def test_manage_daily_summary_tool_enable(mock_get_hour, mock_set_enabled):
    mock_get_hour.return_value = 20
    res = manage_daily_summary_tool.func("enable", config={"user_id": "u1"})
    assert res == "Daily summary notifications enabled. You'll receive them at 8:00 PM."
    mock_set_enabled.assert_called_with("u1", True)


@patch("database.notifications.set_daily_summary_enabled")
def test_manage_daily_summary_tool_disable(mock_set_enabled):
    res = manage_daily_summary_tool.func("disable", config={"user_id": "u1"})
    assert res == "Daily summary notifications disabled."
    mock_set_enabled.assert_called_with("u1", False)


@patch("database.notifications.get_daily_summary_enabled")
@patch("database.notifications.get_daily_summary_hour_local")
def test_manage_daily_summary_tool_get_settings(mock_get_hour, mock_get_enabled):
    mock_get_hour.return_value = 8

    # Enabled
    mock_get_enabled.return_value = True
    res = manage_daily_summary_tool.func("get_settings", config={"user_id": "u1"})
    assert res == "Daily summary is enabled, scheduled for 8:00 AM daily."

    # Disabled
    mock_get_enabled.return_value = False
    res = manage_daily_summary_tool.func("get_settings", config={"user_id": "u1"})
    assert res == "Daily summary is currently disabled. Last set time was 8:00 AM."


@patch("database.notifications.set_daily_summary_enabled")
def test_manage_daily_summary_tool_database_exception_handling(mock_set_enabled):
    mock_set_enabled.side_effect = RuntimeError("Firestore unavailable")
    res = manage_daily_summary_tool.func("enable", config={"user_id": "u1"})
    assert res == "Error: Unable to update notification settings right now."
