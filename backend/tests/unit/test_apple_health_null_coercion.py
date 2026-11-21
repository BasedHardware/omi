"""Tests verifying null-safety and ISO date coercion in apple_health_tools.py.

Ensures that None metrics, string values, missing keys, and ISO 8601 start dates
never cause fatal TypeError / format crashes in HealthKit tools.
"""

import os
import unittest
from datetime import datetime, timezone
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
    """Load Apple Health tools with isolated dependencies for testing."""
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
            "utils.retrieval.tools._apple_health_tools_null_coercion_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "apple_health_tools.py"),
        )
        globals()["_model_text"] = model_text
        globals()["aht"] = module
        yield
        globals().pop("_model_text", None)
        globals().pop("aht", None)


class TestAppleHealthNullCoercion(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_uid_123"}}

    @patch("utils.retrieval.tools._apple_health_tools_null_coercion_test.prepare_apple_health_access")
    def test_workouts_tool_handles_iso_dates_and_null_metrics(self, mock_prep):
        integration = {
            "health_data": {
                "period_days": 7,
                "workouts": [
                    {
                        "type": "Running",
                        "startDate": "2026-10-21T08:00:00Z",
                        "durationMinutes": None,
                        "caloriesBurned": None,
                        "distanceKm": None,
                    },
                    {
                        "type": "Cycling",
                        "startDate": 1792600000000,
                        "durationMinutes": 45.5,
                        "caloriesBurned": "350",
                        "distanceKm": "15.2",
                    },
                ],
            },
            "last_synced": "2026-10-21T10:00:00Z",
        }
        mock_prep.return_value = ("test_uid_123", integration, None)
        res = aht.get_apple_health_workouts_tool.func(config=self.config)
        self.assertNotIn("Failed to retrieve", res)
        self.assertIn("Running", res)
        self.assertIn("Duration: 0 minutes", res)
        self.assertIn("Cycling", res)
        self.assertIn("Duration: 46 minutes", res)
        self.assertIn("Calories: 350 kcal", res)
        self.assertIn("Distance: 15.20 km", res)

    @patch("utils.retrieval.tools._apple_health_tools_null_coercion_test.prepare_apple_health_access")
    def test_steps_tool_handles_null_metrics(self, mock_prep):
        integration = {
            "health_data": {
                "period_days": 7,
                "steps": {
                    "total": None,
                    "average_per_day": None,
                    "daily": [
                        {"date": "2026-10-21", "steps": None},
                        {"date": "2026-10-20", "steps": "7500"},
                    ],
                },
            },
            "last_synced": "2026-10-21T10:00:00Z",
        }
        mock_prep.return_value = ("test_uid_123", integration, None)
        res = aht.get_apple_health_steps_tool.func(config=self.config)
        self.assertNotIn("Failed to retrieve", res)
        self.assertIn("Total Steps: 0", res)
        self.assertIn("Average Steps per Day: 0", res)
        self.assertIn("0 steps", res)
        self.assertIn("7,500 steps", res)

    @patch("utils.retrieval.tools._apple_health_tools_null_coercion_test.prepare_apple_health_access")
    def test_sleep_tool_handles_null_metrics(self, mock_prep):
        integration = {
            "health_data": {
                "period_days": 7,
                "sleep": {
                    "total_sleep_hours": None,
                    "daily": [
                        {"date": "2026-10-21", "sleepHours": None},
                        {"date": "2026-10-20", "sleepHours": "7.5"},
                    ],
                },
            },
            "last_synced": "2026-10-21T10:00:00Z",
        }
        mock_prep.return_value = ("test_uid_123", integration, None)
        res = aht.get_apple_health_sleep_tool.func(config=self.config)
        self.assertNotIn("Failed to retrieve", res)
        self.assertIn("Total Sleep: 0.0 hours", res)
        self.assertIn("Average per Night: 0.0 hours", res)
        self.assertIn("0.0 hours", res)
        self.assertIn("7.5 hours", res)

    @patch("utils.retrieval.tools._apple_health_tools_null_coercion_test.prepare_apple_health_access")
    def test_heart_rate_tool_handles_null_and_string_metrics(self, mock_prep):
        integration = {
            "health_data": {
                "period_days": 7,
                "heart_rate": {
                    "average": "72.4",
                    "minimum": None,
                    "maximum": "120",
                },
            },
            "last_synced": "2026-10-21T10:00:00Z",
        }
        mock_prep.return_value = ("test_uid_123", integration, None)
        res = aht.get_apple_health_heart_rate_tool.func(config=self.config)
        self.assertNotIn("Failed to retrieve", res)
        self.assertIn("Average Heart Rate: 72 bpm", res)
        self.assertNotIn("Minimum Heart Rate", res)
        self.assertIn("Maximum Heart Rate: 120 bpm", res)

    @patch("utils.retrieval.tools._apple_health_tools_null_coercion_test.prepare_apple_health_access")
    def test_summary_tool_handles_null_metrics(self, mock_prep):
        integration = {
            "health_data": {
                "period_days": 7,
                "steps": {"total": None, "average_per_day": None, "daily": [{"date": "2026-10-21", "steps": None}]},
                "active_energy": {
                    "total": None,
                    "average_per_day": None,
                    "daily": [{"date": "2026-10-21", "calories": None}],
                },
                "sleep": {"total_sleep_hours": None, "daily": [{"date": "2026-10-21", "sleepHours": None}]},
                "heart_rate": {"average": None, "minimum": None, "maximum": None},
                "workouts": [{"type": "Yoga", "startDate": "2026-10-21T07:00:00Z", "durationMinutes": None}],
            },
            "last_synced": "2026-10-21T10:00:00Z",
        }
        mock_prep.return_value = ("test_uid_123", integration, None)
        res = aht.get_apple_health_summary_tool.func(config=self.config)
        self.assertNotIn("Failed to retrieve", res)
        self.assertIn("STEPS", res)
        self.assertIn("ACTIVE ENERGY", res)
        self.assertIn("SLEEP", res)
        self.assertIn("WORKOUTS", res)


if __name__ == "__main__":
    unittest.main()
