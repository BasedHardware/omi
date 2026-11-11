"""Tests verifying exception sanitization in apple_health_tools.py.

Ensures that internal exception details (database errors, parsing traces,
tracebacks, etc.) are never leaked to LLM chat tool callers and that logger.error
is invoked with exc_info=True for backend observability.
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
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
def _apple_health_module():
    """Load Apple Health tools with temporary dependencies, restored after this test module."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)
    users = _module("database.users", get_integration=MagicMock())
    notifications = _module("database.notifications", get_user_time_zone=MagicMock())
    integration_base = _module(
        "utils.retrieval.tools.integration_base",
        resolve_config_uid=MagicMock(),
        get_integration_checked=MagicMock(),
    )
    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "database": _package("database"),
        "database.users": users,
        "database.notifications": notifications,
        "utils": _package("utils"),
        "utils.retrieval": _package("utils.retrieval"),
        "utils.retrieval.tools": _package("utils.retrieval.tools"),
        "utils.retrieval.tools.integration_base": integration_base,
    }

    with stub_modules(stubs):
        model_text = load_module_fresh("utils.model_text", str(BACKEND_DIR / "utils" / "model_text.py"))
        load_module_fresh("utils.user_clock", str(BACKEND_DIR / "utils" / "user_clock.py"))
        module = load_module_fresh(
            "utils.retrieval.tools._apple_health_tools_sanitization_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "apple_health_tools.py"),
        )
        globals()["_model_text"] = model_text
        globals()["aht"] = module
        yield
        globals().pop("_model_text", None)
        globals().pop("aht", None)


class FailingIntegration:
    """Mock integration object that raises when health_data or its properties are accessed."""

    def __init__(self, exc: Exception):
        self.exc = exc

    def get(self, key, default=None):
        raise self.exc


class TestAppleHealthToolsSanitization(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_uid_123"}}
        self.mock_integration = {
            "connected": True,
            "health_data": {
                "steps": {
                    "daily": [{"date": "2026-09-27", "steps": 8500}],
                    "total": 8500,
                    "target": 10000,
                },
                "sleep": {
                    "total_sleep_hours": 7.5,
                    "daily": [{"date": "2026-09-27", "sleepHours": 7.5}],
                },
                "heart_rate": {
                    "average": 72,
                    "minimum": 58,
                    "maximum": 135,
                },
                "workouts": [
                    {
                        "type": "Running",
                        "duration_minutes": 30,
                        "calories": 320,
                    }
                ],
            },
            "last_synced": "2026-09-27T08:00:00Z",
        }

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_workout_and_sync_timestamps_use_turn_timezone(self, mock_prep):
        integration = {
            "health_data": {"workouts": [{"type": "Running", "startDate": 1790407080000, "durationMinutes": 30}]},
            "last_synced": "2026-09-26T07:18:00Z",
        }
        mock_prep.return_value = ("test_uid_123", integration, None)
        result = aht.get_apple_health_workouts_tool.func(
            config={"configurable": {"user_id": "test_uid_123", "user_timezone": "Asia/Ho_Chi_Minh"}}
        )
        assert "Sat 26 Sep 2026, 14:18 Asia/Ho_Chi_Minh (UTC+07:00)" in result

    def test_health_context_uses_last_sync_as_window_end_and_marks_stale(self):
        clock = aht.DisplayClock.from_name("Asia/Ho_Chi_Minh")
        last_sync = datetime(2026, 9, 26, 11, 0, tzinfo=timezone.utc)

        context = aht._health_period_context({"last_synced": last_sync.isoformat()}, clock, 7)

        assert "Covered dates: Sat 19 Sep 2026 – Sat 26 Sep 2026." in context
        assert "Data last synced: Sat 26 Sep 2026, 18:00 Asia/Ho_Chi_Minh (UTC+07:00)." in context
        assert "Data may be stale because the last sync was over 24 hours ago." in context

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_workouts_are_newest_first_and_cap_is_reported(self, mock_prep):
        start = datetime(2026, 9, 1, tzinfo=timezone.utc)
        workouts = [
            {
                "type": f"workout-{index}",
                "startDate": (start + timedelta(days=index)).timestamp() * 1000,
                "durationMinutes": 30,
            }
            for index in range(11)
        ]
        mock_prep.return_value = (
            "test_uid_123",
            {
                "health_data": {"period_days": 7, "workouts": workouts},
                "last_synced": datetime.now(timezone.utc).isoformat(),
            },
            None,
        )

        result = aht.get_apple_health_workouts_tool.func(
            config={"configurable": {"user_id": "test_uid_123", "user_timezone": "Asia/Ho_Chi_Minh"}}
        )

        assert "Apple Health Workouts (10 shown of 11, newest first):" in result
        assert "Showing 10 of 11 workouts" in result
        assert "workout-10" in result and "workout-0" not in result
        assert result.index("workout-10") < result.index("workout-9")

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_get_apple_health_steps_tool_sanitizes_exception(self, mock_prep):
        mock_prep.return_value = (
            "test_uid_123",
            FailingIntegration(RuntimeError("postgres://secret_admin:pass123@db.prod.internal:5432/omi")),
            None,
        )
        result = aht.get_apple_health_steps_tool.func(config=self.config)
        self.assertEqual("Failed to retrieve step data.", result)
        self.assertNotIn("postgres", result)
        self.assertNotIn("pass123", result)
        self.assertNotIn("RuntimeError", result)

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_get_apple_health_sleep_tool_sanitizes_exception(self, mock_prep):
        mock_prep.return_value = (
            "test_uid_123",
            FailingIntegration(ValueError("internal_sleep_record_parsing_trace_stack")),
            None,
        )
        result = aht.get_apple_health_sleep_tool.func(config=self.config)
        self.assertEqual("Failed to retrieve sleep data.", result)
        self.assertNotIn("internal_sleep_record_parsing_trace_stack", result)
        self.assertNotIn("ValueError", result)

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_get_apple_health_heart_rate_tool_sanitizes_exception(self, mock_prep):
        mock_prep.return_value = (
            "test_uid_123",
            FailingIntegration(KeyError("bpm_record_corrupted_key")),
            None,
        )
        result = aht.get_apple_health_heart_rate_tool.func(config=self.config)
        self.assertEqual("Failed to retrieve heart rate data.", result)
        self.assertNotIn("bpm_record_corrupted_key", result)
        self.assertNotIn("KeyError", result)

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_get_apple_health_workouts_tool_sanitizes_exception(self, mock_prep):
        mock_prep.return_value = (
            "test_uid_123",
            FailingIntegration(RuntimeError("timeout connecting to firestore cluster replica")),
            None,
        )
        result = aht.get_apple_health_workouts_tool.func(config=self.config)
        self.assertEqual("Failed to retrieve workout data.", result)
        self.assertNotIn("firestore cluster replica", result)
        self.assertNotIn("RuntimeError", result)

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_get_apple_health_summary_tool_sanitizes_exception(self, mock_prep):
        mock_prep.return_value = (
            "test_uid_123",
            FailingIntegration(Exception("summary_calculation_internal_error")),
            None,
        )
        result = aht.get_apple_health_summary_tool.func(config=self.config)
        self.assertEqual("Failed to retrieve health summary.", result)
        self.assertNotIn("summary_calculation_internal_error", result)

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_get_apple_health_steps_tool_success(self, mock_prep):
        mock_prep.return_value = ("test_uid_123", self.mock_integration, None)
        result = aht.get_apple_health_steps_tool.func(config=self.config)
        self.assertIn("Apple Health Step Data", result)
        self.assertIn("8,500 steps", result)

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_get_apple_health_sleep_tool_success(self, mock_prep):
        mock_prep.return_value = ("test_uid_123", self.mock_integration, None)
        result = aht.get_apple_health_sleep_tool.func(config=self.config)
        self.assertIn("Apple Health Sleep Data", result)
        self.assertIn("7.5 hours", result)
        self.assertIn("Covered dates: Sun 20 Sep 2026 – Sun 27 Sep 2026.", result)
        self.assertIn("Data last synced:", result)

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_get_apple_health_heart_rate_tool_success(self, mock_prep):
        mock_prep.return_value = ("test_uid_123", self.mock_integration, None)
        result = aht.get_apple_health_heart_rate_tool.func(config=self.config)
        self.assertIn("Apple Health Heart Rate Data", result)
        self.assertIn("72 bpm", result)

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_get_apple_health_workouts_tool_success(self, mock_prep):
        mock_prep.return_value = ("test_uid_123", self.mock_integration, None)
        result = aht.get_apple_health_workouts_tool.func(config=self.config)
        self.assertIn("Apple Health Workouts", result)
        self.assertIn("Running", result)

    @patch("utils.retrieval.tools._apple_health_tools_sanitization_test.prepare_apple_health_access")
    def test_get_apple_health_summary_tool_success(self, mock_prep):
        mock_prep.return_value = ("test_uid_123", self.mock_integration, None)
        result = aht.get_apple_health_summary_tool.func(config=self.config)
        self.assertIn("Apple Health Summary", result)
        self.assertIn("8,500", result)


if __name__ == "__main__":
    unittest.main()
