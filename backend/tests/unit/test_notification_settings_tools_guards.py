"""Unit tests for notification_settings_tools input validation, hour coercion, and config fallbacks."""

from unittest.mock import MagicMock, patch
import pytest

import utils.retrieval.tools.notification_settings_tools as notif_tools


class TestNotificationSettingsToolsGuards:
    mod = notif_tools

    def test_parse_hour(self):
        assert self.mod._parse_hour(0) == 0
        assert self.mod._parse_hour(12) == 12
        assert self.mod._parse_hour(23) == 23
        assert self.mod._parse_hour("21") == 21
        assert self.mod._parse_hour(" 9 ") == 9
        assert self.mod._parse_hour("0") == 0
        assert self.mod._parse_hour(21.0) == 21
        assert self.mod._parse_hour(21.5) is None
        assert self.mod._parse_hour(None) is None
        assert self.mod._parse_hour(True) is None
        assert self.mod._parse_hour(False) is None
        assert self.mod._parse_hour("abc") is None
        assert self.mod._parse_hour("21a") is None
        assert self.mod._parse_hour(float("nan")) is None
        assert self.mod._parse_hour(float("inf")) is None

    def test_format_hour(self):
        assert self.mod._format_hour(0) == "12:00 AM (midnight)"
        assert self.mod._format_hour(12) == "12:00 PM (noon)"
        assert self.mod._format_hour(9) == "9:00 AM"
        assert self.mod._format_hour(21) == "9:00 PM"
        assert self.mod._format_hour("21") == "9:00 PM"
        assert self.mod._format_hour(21.0) == "9:00 PM"

    def test_action_validation(self):
        cfg = {"configurable": {"user_id": "u1"}}
        assert "Action must be specified" in self.mod.manage_daily_summary_tool.func(None, config=cfg)
        assert "Action must be specified" in self.mod.manage_daily_summary_tool.func("", config=cfg)
        assert "Action must be specified" in self.mod.manage_daily_summary_tool.func("   ", config=cfg)
        assert "Unknown action: test" in self.mod.manage_daily_summary_tool.func("test", config=cfg)

    def test_top_level_config_fallback(self):
        cfg = {"user_id": "top_uid"}
        with (
            patch.object(self.mod.notification_db, "get_daily_summary_enabled", return_value=True),
            patch.object(self.mod.notification_db, "get_daily_summary_hour_local", return_value=20),
        ):
            res = self.mod.manage_daily_summary_tool.func("get_settings", config=cfg)
            assert "Daily summary is enabled" in res
            assert "8:00 PM" in res

    def test_missing_user_id_error(self):
        cfg = {"configurable": {}}
        res = self.mod.manage_daily_summary_tool.func("get_settings", config=cfg)
        assert res == "Error: User ID not found"

    def test_set_time_string_hour_coercion(self):
        cfg = {"configurable": {"user_id": "u1"}}
        with (
            patch.object(self.mod.notification_db, "set_daily_summary_hour_local") as mock_set_hour,
            patch.object(self.mod.notification_db, "get_daily_summary_enabled", return_value=True),
        ):
            res = self.mod.manage_daily_summary_tool.func("set_time", hour="21", config=cfg)
            assert "Daily summary time changed to 9:00 PM." == res
            mock_set_hour.assert_called_once_with("u1", 21)

    def test_set_time_boolean_hour_rejected(self):
        cfg = {"configurable": {"user_id": "u1"}}
        res = self.mod.manage_daily_summary_tool.func("set_time", hour=True, config=cfg)
        assert "Error: Hour must be between 0 and 23. You provided True." == res

    def test_set_time_out_of_bounds_and_invalid(self):
        cfg = {"configurable": {"user_id": "u1"}}
        assert "Error: Please specify the hour (0-23)" in self.mod.manage_daily_summary_tool.func("set_time", hour=None, config=cfg)
        assert "Error: Hour must be between 0 and 23" in self.mod.manage_daily_summary_tool.func("set_time", hour=-1, config=cfg)
        assert "Error: Hour must be between 0 and 23" in self.mod.manage_daily_summary_tool.func("set_time", hour=24, config=cfg)
        assert "Error: Hour must be between 0 and 23" in self.mod.manage_daily_summary_tool.func("set_time", hour="invalid", config=cfg)

    def test_set_time_enables_if_disabled(self):
        cfg = {"configurable": {"user_id": "u1"}}
        with (
            patch.object(self.mod.notification_db, "set_daily_summary_hour_local") as mock_set_hour,
            patch.object(self.mod.notification_db, "get_daily_summary_enabled", return_value=False),
            patch.object(self.mod.notification_db, "set_daily_summary_enabled") as mock_set_enabled,
        ):
            res = self.mod.manage_daily_summary_tool.func("set_time", hour=18, config=cfg)
            assert "Daily summary time changed to 6:00 PM and notifications enabled." == res
            mock_set_hour.assert_called_once_with("u1", 18)
            mock_set_enabled.assert_called_once_with("u1", True)

    def test_disable_action(self):
        cfg = {"configurable": {"user_id": "u1"}}
        with patch.object(self.mod.notification_db, "set_daily_summary_enabled") as mock_set_enabled:
            res = self.mod.manage_daily_summary_tool.func("disable", config=cfg)
            assert "Daily summary notifications disabled." == res
            mock_set_enabled.assert_called_once_with("u1", False)

    def test_database_error_handled_gracefully(self):
        cfg = {"configurable": {"user_id": "u1"}}
        with patch.object(self.mod.notification_db, "set_daily_summary_enabled", side_effect=RuntimeError("Firestore connection refused")):
            res = self.mod.manage_daily_summary_tool.func("enable", config=cfg)
            assert "Error: Failed to update notification settings. Please try again later." == res
