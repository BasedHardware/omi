"""Tests verifying notification_settings_tools.py validation, string coercion, and exception boundaries.

Ensures that manage_daily_summary_tool handles string hour representations, null actions,
and database errors without unhandled exceptions.
"""

import os
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _module(name, **attrs):
    mod = ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _package(name):
    mod = _module(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    return mod


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


@pytest.fixture(scope="module", autouse=True)
def _notification_settings_module():
    """Load notification_settings_tools with isolated dependencies."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)

    mock_notif_db = _module(
        "database.notifications",
        set_daily_summary_enabled=MagicMock(),
        get_daily_summary_enabled=MagicMock(return_value=True),
        set_daily_summary_hour_local=MagicMock(),
        get_daily_summary_hour_local=MagicMock(return_value=22),
    )

    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "database": _package("database"),
        "database.notifications": mock_notif_db,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools._notification_settings_tools_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "notification_settings_tools.py"),
        )
        globals()["notif_tool"] = module
        globals()["notif_db"] = mock_notif_db
        yield
        globals().pop("notif_tool", None)
        globals().pop("notif_db", None)


class TestNotificationSettingsTools(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_uid_123"}}

    def test_set_time_coerces_string_hour(self):
        notif_db.get_daily_summary_enabled.return_value = True
        res = notif_tool.manage_daily_summary_tool.func(
            action="set_time",
            hour="21",
            config=self.config,
        )
        self.assertIn("Daily summary time changed to 9:00 PM.", res)
        notif_db.set_daily_summary_hour_local.assert_called_with("test_uid_123", 21)

    def test_set_time_validates_out_of_range(self):
        res1 = notif_tool.manage_daily_summary_tool.func(
            action="set_time",
            hour=25,
            config=self.config,
        )
        self.assertIn("Error: Hour must be between 0 and 23", res1)

        res2 = notif_tool.manage_daily_summary_tool.func(
            action="set_time",
            hour="invalid",
            config=self.config,
        )
        self.assertIn("Error: Hour must be between 0 and 23", res2)

    def test_guards_null_action(self):
        res = notif_tool.manage_daily_summary_tool.func(
            action=None,
            config=self.config,
        )
        self.assertIn("Error: Action must be specified", res)

    def test_enable_and_get_settings(self):
        notif_db.get_daily_summary_hour_local.return_value = 8
        res_enable = notif_tool.manage_daily_summary_tool.func(
            action="enable",
            config=self.config,
        )
        self.assertIn("Daily summary notifications enabled. You'll receive them at 8:00 AM.", res_enable)

        notif_db.get_daily_summary_enabled.return_value = True
        res_get = notif_tool.manage_daily_summary_tool.func(
            action="get_settings",
            config=self.config,
        )
        self.assertIn("Daily summary is enabled, scheduled for 8:00 AM daily.", res_get)

    def test_sanitizes_database_exceptions(self):
        notif_db.set_daily_summary_enabled.side_effect = RuntimeError("secret_db_credentials_leak")
        res = notif_tool.manage_daily_summary_tool.func(
            action="enable",
            config=self.config,
        )
        self.assertEqual(res, "Failed to update notification settings. Please try again.")
        self.assertNotIn("secret_db_credentials_leak", res)
        notif_db.set_daily_summary_enabled.side_effect = None


if __name__ == "__main__":
    unittest.main()
