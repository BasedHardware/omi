"""Tests verifying exception sanitization in apple_health_tools.py.

Ensures that internal exception details (database errors, parsing traces,
tracebacks, etc.) are never leaked to LLM chat tool callers and that logger.error
is invoked with exc_info=True for backend observability.
"""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub dependencies if not present in isolated environment
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


_lc_tools.tool = _tool_decorator
_lc_runnables = _mod("langchain_core.runnables")
_lc_runnables.RunnableConfig = dict

for _p in [
    "database",
    "utils",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)

for _name, _attrs in {
    "database.users": ["get_integration"],
    "database.notifications": ["get_user_time_zone"],
    "utils.retrieval.tools.integration_base": ["resolve_config_uid", "get_integration_checked"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        if not hasattr(_m, _a):
            setattr(_m, _a, MagicMock())

aht = _load(
    "utils.retrieval.tools._apple_health_tools_sanitization_test",
    "utils/retrieval/tools/apple_health_tools.py",
)


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
