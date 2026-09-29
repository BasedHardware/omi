"""Tests verifying exception sanitization in apple_health_tools.py.

Ensures that internal exception details (RuntimeError str(e), traceback, database details, etc.)
are not leaked to chat tool callers or LLM context across all Apple Health tools, while preserving
normal successful data extraction.
"""

import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.retrieval.tools import apple_health_tools as aht


class TestAppleHealthToolsSanitization(unittest.TestCase):
    def setUp(self):
        self.fake_config = {"configurable": {"user_id": "test_user_123"}}
        self.mock_integration = {
            "health_data": {
                "period_days": 7,
                "steps": {
                    "total": 10000,
                    "average_per_day": 5000,
                    "daily": [{"date": "2026-09-28", "steps": 5000}, {"date": "2026-09-29", "steps": 5000}],
                },
                "sleep": {
                    "total_sleep_hours": 8.0,
                    "daily": [{"date": "2026-09-29", "sleepHours": 8.0}],
                },
                "heart_rate": {"average": 70, "minimum": 50, "maximum": 120},
                "workouts": [{"type": "Running", "durationMinutes": 30, "caloriesBurned": 300}],
                "active_energy": {"total": 500, "average_per_day": 250, "daily": []},
            },
            "last_synced": "2026-09-29T10:00:00Z",
        }
        self.tz_patcher = patch.object(aht.notification_db, "get_user_time_zone", return_value="UTC")
        self.tz_patcher.start()

    def tearDown(self):
        self.tz_patcher.stop()

    def test_steps_tool_happy_path(self):
        with patch.object(
            aht, "prepare_apple_health_access", return_value=("test_user_123", self.mock_integration, None)
        ):
            result = aht.get_apple_health_steps_tool.func(config=self.fake_config)
            self.assertIn("Apple Health Step Data", result)
            self.assertIn("10,000", result)

    def test_sleep_tool_happy_path(self):
        with patch.object(
            aht, "prepare_apple_health_access", return_value=("test_user_123", self.mock_integration, None)
        ):
            result = aht.get_apple_health_sleep_tool.func(config=self.fake_config)
            self.assertIn("Apple Health Sleep Data", result)
            self.assertIn("8.0 hours", result)

    def test_heart_rate_tool_happy_path(self):
        with patch.object(
            aht, "prepare_apple_health_access", return_value=("test_user_123", self.mock_integration, None)
        ):
            result = aht.get_apple_health_heart_rate_tool.func(config=self.fake_config)
            self.assertIn("Apple Health Heart Rate", result)
            self.assertIn("70 bpm", result)

    def test_workouts_tool_happy_path(self):
        with patch.object(
            aht, "prepare_apple_health_access", return_value=("test_user_123", self.mock_integration, None)
        ):
            result = aht.get_apple_health_workouts_tool.func(config=self.fake_config)
            self.assertIn("Apple Health Workouts", result)
            self.assertIn("Running", result)

    def test_summary_tool_happy_path(self):
        with patch.object(
            aht, "prepare_apple_health_access", return_value=("test_user_123", self.mock_integration, None)
        ):
            result = aht.get_apple_health_summary_tool.func(config=self.fake_config)
            self.assertIn("Apple Health Summary", result)
            self.assertIn("STEPS", result)
            self.assertIn("HEART RATE", result)

    def test_steps_tool_unexpected_exception_sanitized(self):
        mock_health_data = MagicMock()
        mock_health_data.get.side_effect = RuntimeError("internal firestore secret trace")
        mock_integration = {"health_data": mock_health_data}

        with patch.object(aht, "prepare_apple_health_access", return_value=("test_user_123", mock_integration, None)):
            result = aht.get_apple_health_steps_tool.func(config=self.fake_config)
            self.assertEqual(
                "An unexpected error occurred while retrieving step data. Please try again later.",
                result,
            )
            self.assertNotIn("internal firestore secret trace", result)

    def test_sleep_tool_unexpected_exception_sanitized(self):
        mock_health_data = MagicMock()
        mock_health_data.get.side_effect = RuntimeError("unhandled connection timeout")
        mock_integration = {"health_data": mock_health_data}

        with patch.object(aht, "prepare_apple_health_access", return_value=("test_user_123", mock_integration, None)):
            result = aht.get_apple_health_sleep_tool.func(config=self.fake_config)
            self.assertEqual(
                "An unexpected error occurred while retrieving sleep data. Please try again later.",
                result,
            )
            self.assertNotIn("unhandled connection timeout", result)

    def test_heart_rate_tool_unexpected_exception_sanitized(self):
        mock_health_data = MagicMock()
        mock_health_data.get.side_effect = RuntimeError("db socket connection error")
        mock_integration = {"health_data": mock_health_data}

        with patch.object(aht, "prepare_apple_health_access", return_value=("test_user_123", mock_integration, None)):
            result = aht.get_apple_health_heart_rate_tool.func(config=self.fake_config)
            self.assertEqual(
                "An unexpected error occurred while retrieving heart rate data. Please try again later.",
                result,
            )
            self.assertNotIn("db socket connection error", result)

    def test_workouts_tool_unexpected_exception_sanitized(self):
        mock_health_data = MagicMock()
        mock_health_data.get.side_effect = RuntimeError("redis pool exhausted")
        mock_integration = {"health_data": mock_health_data}

        with patch.object(aht, "prepare_apple_health_access", return_value=("test_user_123", mock_integration, None)):
            result = aht.get_apple_health_workouts_tool.func(config=self.fake_config)
            self.assertEqual(
                "An unexpected error occurred while retrieving workout data. Please try again later.",
                result,
            )
            self.assertNotIn("redis pool exhausted", result)

    def test_summary_tool_unexpected_exception_sanitized(self):
        mock_health_data = MagicMock()
        mock_health_data.get.side_effect = RuntimeError("token decryption failed")
        mock_integration = {"health_data": mock_health_data}

        with patch.object(aht, "prepare_apple_health_access", return_value=("test_user_123", mock_integration, None)):
            result = aht.get_apple_health_summary_tool.func(config=self.fake_config)
            self.assertEqual(
                "An unexpected error occurred while retrieving health summary. Please try again later.",
                result,
            )
            self.assertNotIn("token decryption failed", result)


if __name__ == "__main__":
    unittest.main()
