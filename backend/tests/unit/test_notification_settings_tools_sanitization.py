from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

backend_dir = str(Path(__file__).resolve().parent.parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules


def _fake_tool(fn=None, *args, **kwargs):
    if fn is not None and callable(fn):
        return fn
    def decorator(func):
        return func
    return decorator


class TestNotificationSettingsToolsSanitization(unittest.TestCase):
    def setUp(self):
        tools_mock = AutoMockModule("langchain_core.tools")
        tools_mock.tool = _fake_tool

        self._stub_cm = stub_modules({
            "langchain_core": AutoMockModule("langchain_core"),
            "langchain_core.tools": tools_mock,
            "langchain_core.runnables": AutoMockModule("langchain_core.runnables"),
            "database": AutoMockModule("database"),
            "database.notifications": AutoMockModule("database.notifications"),
            "utils.retrieval.agentic": AutoMockModule("utils.retrieval.agentic"),
        })
        self._stub_cm.__enter__()
        tools_path = str(Path(backend_dir) / "utils" / "retrieval" / "tools" / "notification_settings_tools.py")
        self.notif_tools = load_module_fresh("utils.retrieval.tools.notification_settings_tools", tools_path)

    def tearDown(self):
        self._stub_cm.__exit__(None, None, None)

    def test_manage_daily_summary_tool_db_exception_handled(self):
        import database.notifications as notification_db
        notification_db.set_daily_summary_enabled = MagicMock(
            side_effect=RuntimeError("Firestore connection failed: secret_token=12345")
        )

        res = self.notif_tools.manage_daily_summary_tool(
            action="enable",
            config={"configurable": {"user_id": "u1"}},
        )
        self.assertEqual(res, "Error: Failed to manage daily summary settings")
        self.assertNotIn("secret_token", res)
        self.assertNotIn("Firestore", res)

    def test_manage_daily_summary_tool_success_path(self):
        import database.notifications as notification_db
        notification_db.set_daily_summary_enabled = MagicMock()
        notification_db.get_daily_summary_hour_local = MagicMock(return_value=20)

        res = self.notif_tools.manage_daily_summary_tool(
            action="enable",
            config={"configurable": {"user_id": "u1"}},
        )
        self.assertIn("Daily summary notifications enabled", res)
        self.assertIn("8:00 PM", res)


if __name__ == "__main__":
    unittest.main()
