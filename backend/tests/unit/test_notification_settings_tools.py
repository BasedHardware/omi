from unittest.mock import MagicMock, patch
import pytest

from utils.retrieval.tools.notification_settings_tools import (
    _format_hour,
    manage_daily_summary_tool,
)


def test_format_hour():
    assert _format_hour(0) == "12:00 AM (midnight)"
    assert _format_hour(12) == "12:00 PM (noon)"
    assert _format_hour(9) == "9:00 AM"
    assert _format_hour(22) == "10:00 PM"
    assert _format_hour("15") == "3:00 PM"


def test_invalid_action():
    config = {'configurable': {'user_id': 'u1'}}
    res_none = manage_daily_summary_tool.invoke({'action': None}, config=config)
    assert "Action must be a valid non-empty string" in res_none

    res_empty = manage_daily_summary_tool.invoke({'action': '   '}, config=config)
    assert "Action must be a valid non-empty string" in res_empty

    res_unknown = manage_daily_summary_tool.invoke({'action': 'fly_to_moon'}, config=config)
    assert "Unknown action: fly_to_moon" in res_unknown


def test_missing_config_or_user_id():
    res_no_cfg = manage_daily_summary_tool.invoke({'action': 'enable'}, config=None)
    assert "Configuration not available" in res_no_cfg

    res_no_uid = manage_daily_summary_tool.invoke({'action': 'enable'}, config={})
    assert "User ID not found" in res_no_uid


@patch('utils.retrieval.tools.notification_settings_tools.notification_db')
def test_top_level_user_id(mock_db):
    mock_db.get_daily_summary_hour_local.return_value = 20
    res = manage_daily_summary_tool.invoke({'action': 'enable'}, config={'user_id': 'u_direct'})
    assert "Daily summary notifications enabled" in res
    mock_db.set_daily_summary_enabled.assert_called_with('u_direct', True)


@patch('utils.retrieval.tools.notification_settings_tools.notification_db')
def test_action_enable(mock_db):
    mock_db.get_daily_summary_hour_local.return_value = 21
    res = manage_daily_summary_tool.invoke({'action': 'enable'}, config={'configurable': {'user_id': 'u1'}})
    assert "Daily summary notifications enabled" in res
    assert "9:00 PM" in res
    mock_db.set_daily_summary_enabled.assert_called_with('u1', True)


@patch('utils.retrieval.tools.notification_settings_tools.notification_db')
def test_action_disable(mock_db):
    res = manage_daily_summary_tool.invoke({'action': 'disable'}, config={'configurable': {'user_id': 'u1'}})
    assert "Daily summary notifications disabled" in res
    mock_db.set_daily_summary_enabled.assert_called_with('u1', False)


@patch('utils.retrieval.tools.notification_settings_tools.notification_db')
def test_set_time_valid(mock_db):
    mock_db.get_daily_summary_enabled.return_value = True
    res = manage_daily_summary_tool.invoke({
        'action': 'set_time',
        'hour': 8,
    }, config={'configurable': {'user_id': 'u1'}})
    assert "Daily summary time changed to 8:00 AM" in res
    mock_db.set_daily_summary_hour_local.assert_called_with('u1', 8)


@patch('utils.retrieval.tools.notification_settings_tools.notification_db')
def test_set_time_string_coercion(mock_db):
    mock_db.get_daily_summary_enabled.return_value = True
    res = manage_daily_summary_tool.invoke({
        'action': 'set_time',
        'hour': "22",
    }, config={'configurable': {'user_id': 'u1'}})
    assert "Daily summary time changed to 10:00 PM" in res
    mock_db.set_daily_summary_hour_local.assert_called_with('u1', 22)


def test_set_time_out_of_bounds_or_invalid():
    config = {'configurable': {'user_id': 'u1'}}
    res_none = manage_daily_summary_tool.invoke({'action': 'set_time', 'hour': None}, config=config)
    assert "Please specify the hour (0-23)" in res_none

    res_neg = manage_daily_summary_tool.invoke({'action': 'set_time', 'hour': -1}, config=config)
    assert "Hour must be between 0 and 23" in res_neg

    res_over = manage_daily_summary_tool.invoke({'action': 'set_time', 'hour': 25}, config=config)
    assert "Hour must be between 0 and 23" in res_over

    res_str = manage_daily_summary_tool.invoke({'action': 'set_time', 'hour': 'abc'}, config=config)
    assert "Hour must be an integer between 0 and 23" in res_str


@patch('utils.retrieval.tools.notification_settings_tools.notification_db')
def test_action_get_settings(mock_db):
    mock_db.get_daily_summary_enabled.return_value = True
    mock_db.get_daily_summary_hour_local.return_value = 9
    res_enabled = manage_daily_summary_tool.invoke({'action': 'get_settings'}, config={'configurable': {'user_id': 'u1'}})
    assert "Daily summary is enabled, scheduled for 9:00 AM daily" in res_enabled

    mock_db.get_daily_summary_enabled.return_value = False
    res_disabled = manage_daily_summary_tool.invoke({'action': 'get_settings'}, config={'configurable': {'user_id': 'u1'}})
    assert "Daily summary is currently disabled" in res_disabled
