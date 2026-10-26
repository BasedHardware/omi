"""Hermetic unit tests for notification_settings_tools.py resilience.

Verifies:
1. Config resilience: configurable.user_id, configurable.uid, top-level user_id, top-level uid, and agent_config_context fallback.
2. Numeric coercion: int, float, string-encoded integers, invalid hours, and bool rejection for hour.
3. Action resilience: case-insensitivity, whitespace trimming, None handling, and invalid action messaging.
4. Error handling: unconfigured states and missing user id.
"""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


_mod("database.users")
for _p in ["database", "utils", "utils.retrieval", "utils.retrieval.tools"]:
    _pkg(_p)

notif_db_mock = _mod("database.notifications")
notif_db_mock.set_daily_summary_enabled = MagicMock()
notif_db_mock.set_daily_summary_hour_local = MagicMock()
notif_db_mock.get_daily_summary_hour_local = MagicMock(return_value=22)
notif_db_mock.get_daily_summary_enabled = MagicMock(return_value=True)

agentic_mock = _mod("utils.retrieval.agentic")
agentic_mock.agent_config_context = MagicMock()
agentic_mock.agent_config_context.get.return_value = None

sys.path.insert(0, str(BACKEND_DIR))

# Ensure integration_base is loaded for resolve_config_uid
spec_base = importlib.util.spec_from_file_location(
    "utils.retrieval.tools.integration_base",
    str(BACKEND_DIR / "utils/retrieval/tools/integration_base.py"),
)
integration_base = importlib.util.module_from_spec(spec_base)
sys.modules["utils.retrieval.tools.integration_base"] = integration_base
spec_base.loader.exec_module(integration_base)

spec = importlib.util.spec_from_file_location(
    "utils.retrieval.tools._test_notification_settings_tools",
    str(BACKEND_DIR / "utils/retrieval/tools/notification_settings_tools.py"),
)
notif_tools = importlib.util.module_from_spec(spec)
sys.modules["utils.retrieval.tools._test_notification_settings_tools"] = notif_tools
spec.loader.exec_module(notif_tools)


class TestNotificationSettingsToolsResilience(unittest.TestCase):
    def setUp(self):
        notif_db_mock.set_daily_summary_enabled.reset_mock()
        notif_db_mock.set_daily_summary_hour_local.reset_mock()
        notif_db_mock.get_daily_summary_hour_local.reset_mock()
        notif_db_mock.get_daily_summary_enabled.reset_mock()
        notif_db_mock.get_daily_summary_hour_local.return_value = 22
        notif_db_mock.get_daily_summary_enabled.return_value = True
        agentic_mock.agent_config_context.get.return_value = None

    def test_resolve_uid_from_configurable_user_id(self):
        config = {"configurable": {"user_id": "user_canonical_123"}}
        res = notif_tools._resolve_uid(config)
        self.assertEqual(res, "user_canonical_123")

    def test_resolve_uid_from_configurable_uid_alias(self):
        config = {"configurable": {"uid": "user_alias_456"}}
        res = notif_tools._resolve_uid(config)
        self.assertEqual(res, "user_alias_456")

    def test_resolve_uid_from_top_level_user_id(self):
        config = {"user_id": "user_top_789"}
        res = notif_tools._resolve_uid(config)
        self.assertEqual(res, "user_top_789")

    def test_resolve_uid_from_top_level_uid(self):
        config = {"uid": "user_top_uid_012"}
        res = notif_tools._resolve_uid(config)
        self.assertEqual(res, "user_top_uid_012")

    def test_resolve_uid_fallback_to_agent_config_context(self):
        agentic_mock.agent_config_context.get.return_value = {"configurable": {"user_id": "ctx_user_999"}}
        res = notif_tools._resolve_uid(None)
        self.assertEqual(res, "ctx_user_999")

    def test_resolve_uid_missing_returns_none(self):
        self.assertIsNone(notif_tools._resolve_uid({}))
        self.assertIsNone(notif_tools._resolve_uid(None))
        self.assertIsNone(notif_tools._resolve_uid({"configurable": None}))

    def test_manage_daily_summary_no_config(self):
        res = notif_tools.manage_daily_summary_tool.func(action="enable", config=None)
        self.assertEqual(res, "Error: Configuration not available")

    def test_manage_daily_summary_no_uid(self):
        res = notif_tools.manage_daily_summary_tool.func(action="enable", config={})
        self.assertEqual(res, "Error: User ID not found")

    def test_manage_daily_summary_enable(self):
        config = {"configurable": {"user_id": "user_enable"}}
        res = notif_tools.manage_daily_summary_tool.func(action=" ENABLE ", config=config)
        notif_db_mock.set_daily_summary_enabled.assert_called_once_with("user_enable", True)
        self.assertIn("Daily summary notifications enabled", res)
        self.assertIn("10:00 PM", res)

    def test_manage_daily_summary_disable(self):
        config = {"configurable": {"user_id": "user_disable"}}
        res = notif_tools.manage_daily_summary_tool.func(action="Disable", config=config)
        notif_db_mock.set_daily_summary_enabled.assert_called_once_with("user_disable", False)
        self.assertEqual(res, "Daily summary notifications disabled.")

    def test_manage_daily_summary_set_time_string_hour(self):
        config = {"configurable": {"user_id": "user_time_1"}}
        res = notif_tools.manage_daily_summary_tool.func(action="set_time", hour="9", config=config)
        notif_db_mock.set_daily_summary_hour_local.assert_called_once_with("user_time_1", 9)
        self.assertIn("Daily summary time changed to 9:00 AM", res)

    def test_manage_daily_summary_set_time_float_hour(self):
        config = {"configurable": {"user_id": "user_time_2"}}
        res = notif_tools.manage_daily_summary_tool.func(action="set_time", hour=21.0, config=config)
        notif_db_mock.set_daily_summary_hour_local.assert_called_once_with("user_time_2", 21)
        self.assertIn("Daily summary time changed to 9:00 PM", res)

    def test_manage_daily_summary_set_time_auto_enables_if_disabled(self):
        config = {"configurable": {"user_id": "user_time_3"}}
        notif_db_mock.get_daily_summary_enabled.return_value = False
        res = notif_tools.manage_daily_summary_tool.func(action="set_time", hour=14, config=config)
        notif_db_mock.set_daily_summary_enabled.assert_called_once_with("user_time_3", True)
        self.assertIn("Daily summary time changed to 2:00 PM and notifications enabled.", res)

    def test_manage_daily_summary_set_time_missing_hour(self):
        config = {"configurable": {"user_id": "user_err"}}
        res = notif_tools.manage_daily_summary_tool.func(action="set_time", hour=None, config=config)
        self.assertEqual(res, "Error: Please specify the hour (0-23). Example: 22 for 10 PM, 9 for 9 AM.")

    def test_manage_daily_summary_set_time_invalid_range(self):
        config = {"configurable": {"user_id": "user_err"}}
        res_negative = notif_tools.manage_daily_summary_tool.func(action="set_time", hour=-1, config=config)
        self.assertIn("Error: Hour must be between 0 and 23", res_negative)

        res_overflow = notif_tools.manage_daily_summary_tool.func(action="set_time", hour=25, config=config)
        self.assertIn("Error: Hour must be between 0 and 23", res_overflow)

    def test_manage_daily_summary_set_time_boolean_rejected(self):
        config = {"configurable": {"user_id": "user_err"}}
        res = notif_tools.manage_daily_summary_tool.func(action="set_time", hour=True, config=config)
        self.assertIn("Error: Hour must be between 0 and 23", res)

    def test_manage_daily_summary_get_settings_enabled(self):
        config = {"configurable": {"user_id": "user_settings"}}
        notif_db_mock.get_daily_summary_enabled.return_value = True
        notif_db_mock.get_daily_summary_hour_local.return_value = 8
        res = notif_tools.manage_daily_summary_tool.func(action="get_settings", config=config)
        self.assertEqual(res, "Daily summary is enabled, scheduled for 8:00 AM daily.")

    def test_manage_daily_summary_get_settings_disabled(self):
        config = {"configurable": {"user_id": "user_settings"}}
        notif_db_mock.get_daily_summary_enabled.return_value = False
        notif_db_mock.get_daily_summary_hour_local.return_value = 0
        res = notif_tools.manage_daily_summary_tool.func(action="get_settings", config=config)
        self.assertEqual(res, "Daily summary is currently disabled. Last set time was 12:00 AM (midnight).")

    def test_manage_daily_summary_unknown_action(self):
        config = {"configurable": {"user_id": "user_act"}}
        res = notif_tools.manage_daily_summary_tool.func(action="invalid_command", config=config)
        self.assertIn("Unknown action: invalid_command", res)


if __name__ == "__main__":
    unittest.main()
