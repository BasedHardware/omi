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


class TestScreenActivityToolsSanitization(unittest.TestCase):
    def setUp(self):
        tools_mock = AutoMockModule("langchain_core.tools")
        tools_mock.tool = _fake_tool

        self._stub_cm = stub_modules({
            "langchain_core": AutoMockModule("langchain_core"),
            "langchain_core.tools": tools_mock,
            "langchain_core.runnables": AutoMockModule("langchain_core.runnables"),
            "database": AutoMockModule("database"),
            "database.screen_activity": AutoMockModule("database.screen_activity"),
            "database.vector_db": AutoMockModule("database.vector_db"),
            "database.notifications": AutoMockModule("database.notifications"),
            "database._client": AutoMockModule("database._client"),
            "utils.llm.clients": AutoMockModule("utils.llm.clients"),
            "utils.retrieval.agentic": AutoMockModule("utils.retrieval.agentic"),
        })
        self._stub_cm.__enter__()
        tools_path = str(Path(backend_dir) / "utils" / "retrieval" / "tools" / "screen_activity_tools.py")
        self.screen_tools = load_module_fresh("utils.retrieval.tools.screen_activity_tools", tools_path)

    def tearDown(self):
        self._stub_cm.__exit__(None, None, None)

    def test_get_screen_activity_tool_invalid_date_sanitized(self):
        res = self.screen_tools.get_screen_activity_tool(
            start_date="not-a-date",
            end_date="also-not-a-date",
            config={"configurable": {"user_id": "u1"}},
        )
        self.assertEqual(res, "Error: Invalid date format. Use YYYY-MM-DDTHH:MM:SS+HH:MM.")
        self.assertNotIn("Details:", res)
        self.assertNotIn("ValueError", res)

    def test_get_screen_activity_tool_db_exception_sanitized(self):
        import database.screen_activity as screen_activity_db
        screen_activity_db.get_screen_activity_summary = MagicMock(
            side_effect=RuntimeError("Firestore connection refused: internal_secret_key=xyz")
        )

        res = self.screen_tools.get_screen_activity_tool(
            start_date="2026-09-01T00:00:00+00:00",
            end_date="2026-09-02T00:00:00+00:00",
            config={"configurable": {"user_id": "u1"}},
        )
        self.assertEqual(res, "Error retrieving screen activity summary")
        self.assertNotIn("internal_secret_key", res)
        self.assertNotIn("RuntimeError", res)


if __name__ == "__main__":
    unittest.main()
