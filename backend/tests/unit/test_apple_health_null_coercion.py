"""Unit tests verifying defensive null coercion and ISO timestamp handling in apple_health_tools.py.

Ensures that:
1. Null/None numeric metrics in steps, sleep, heart rate, workouts, and summary
   do not crash with TypeError or format errors.
2. ISO 8601 string timestamps in workout startDate are parsed and formatted without
   raising TypeError: unsupported operand type(s) for /: 'str' and 'int'.
3. Numeric epoch timestamps (in milliseconds) continue to work properly.
4. Coercion helpers safely handle booleans, None, invalid strings, and numbers.
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure backend directory and local directory are on sys.path
TEST_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TEST_DIR.parent.parent
for p in (TEST_DIR, BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from utils.retrieval.tools.apple_health_tools import (
    _safe_float,
    _safe_int,
    _workout_timestamp,
    get_apple_health_steps_tool,
    get_apple_health_sleep_tool,
    get_apple_health_heart_rate_tool,
    get_apple_health_workouts_tool,
    get_apple_health_summary_tool,
)


class TestSafeCoercionHelpers(unittest.TestCase):
    """Test _safe_float and _safe_int against various types."""

    def test_safe_float(self):
        self.assertEqual(_safe_float(None), 0.0)
        self.assertEqual(_safe_float(None, 5.5), 5.5)
        self.assertEqual(_safe_float(True), 0.0)
        self.assertEqual(_safe_float(False), 0.0)
        self.assertEqual(_safe_float(42), 42.0)
        self.assertEqual(_safe_float(3.14), 3.14)
        self.assertEqual(_safe_float("12.5"), 12.5)
        self.assertEqual(_safe_float("invalid"), 0.0)
        self.assertEqual(_safe_float([]), 0.0)

    def test_safe_int(self):
        self.assertEqual(_safe_int(None), 0)
        self.assertEqual(_safe_int(None, 10), 10)
        self.assertEqual(_safe_int(True), 0)
        self.assertEqual(_safe_int(False), 0)
        self.assertEqual(_safe_int(42), 42)
        self.assertEqual(_safe_int(3.9), 3)
        self.assertEqual(_safe_int("100"), 100)
        self.assertEqual(_safe_int("invalid"), 0)
        self.assertEqual(_safe_int({}), 0)


class TestAppleHealthNullCoercion(unittest.TestCase):
    """Test Apple Health retrieval tools when Firestore records contain nulls or ISO timestamps."""

    def setUp(self):
        self.config = {"configurable": {"user_id": "test_user_001"}}

    @patch("utils.retrieval.tools.apple_health_tools.prepare_apple_health_access")
    def test_steps_tool_null_metrics(self, mock_prepare):
        """Verify get_apple_health_steps_tool handles None totals, averages, and daily steps."""
        mock_prepare.return_value = (
            "test_user_001",
            {
                "last_synced": "2026-10-21T12:00:00Z",
                "health_data": {
                    "steps": {
                        "total": None,
                        "average_per_day": None,
                        "daily": [
                            {"date": "2026-10-21", "steps": None},
                            {"date": "2026-10-20", "steps": 5000},
                        ],
                    }
                },
            },
            None,
        )

        result = get_apple_health_steps_tool.func(self.config)
        self.assertNotIn("Failed to retrieve step data", result)
        self.assertIn("Total Steps: 0", result)
        self.assertIn("Average Steps per Day: 0", result)
        self.assertIn("0 steps", result)
        self.assertIn("5,000 steps", result)

    @patch("utils.retrieval.tools.apple_health_tools.prepare_apple_health_access")
    def test_sleep_tool_null_metrics(self, mock_prepare):
        """Verify get_apple_health_sleep_tool handles None total_sleep_hours and sleepHours."""
        mock_prepare.return_value = (
            "test_user_001",
            {
                "last_synced": "2026-10-21T12:00:00Z",
                "health_data": {
                    "sleep": {
                        "total_sleep_hours": None,
                        "daily": [
                            {"date": "2026-10-21", "sleepHours": None},
                            {"date": "2026-10-20", "sleepHours": 7.5},
                        ],
                    }
                },
            },
            None,
        )

        result = get_apple_health_sleep_tool.func(self.config)
        self.assertNotIn("Failed to retrieve sleep data", result)
        self.assertIn("Total Sleep: 0.0 hours", result)
        self.assertIn("Average per Night: 0.0 hours", result)
        self.assertIn("0.0 hours", result)
        self.assertIn("7.5 hours", result)

    @patch("utils.retrieval.tools.apple_health_tools.prepare_apple_health_access")
    def test_heart_rate_tool_null_metrics(self, mock_prepare):
        """Verify get_apple_health_heart_rate_tool handles None or missing avg/min/max."""
        mock_prepare.return_value = (
            "test_user_001",
            {
                "last_synced": "2026-10-21T12:00:00Z",
                "health_data": {
                    "heart_rate": {
                        "average": None,
                        "minimum": None,
                        "maximum": 120,
                    }
                },
            },
            None,
        )

        result = get_apple_health_heart_rate_tool.func(self.config)
        self.assertNotIn("Failed to retrieve heart rate data", result)
        self.assertNotIn("Average Heart Rate:", result)
        self.assertNotIn("Minimum Heart Rate:", result)
        self.assertIn("Maximum Heart Rate: 120 bpm", result)

    @patch("utils.retrieval.tools.apple_health_tools.prepare_apple_health_access")
    def test_workouts_tool_iso_start_date_and_null_metrics(self, mock_prepare):
        """Verify get_apple_health_workouts_tool parses ISO startDate strings and handles null duration/calories."""
        mock_prepare.return_value = (
            "test_user_001",
            {
                "last_synced": "2026-10-21T12:00:00Z",
                "health_data": {
                    "workouts": [
                        {
                            "type": "Running",
                            "startDate": "2026-10-21T08:30:00Z",
                            "durationMinutes": None,
                            "caloriesBurned": None,
                            "distanceKm": None,
                        },
                        {
                            "type": "Yoga",
                            "startDate": 1729500000000,  # Numeric ms timestamp
                            "durationMinutes": 60,
                            "caloriesBurned": 220,
                            "distanceKm": None,
                        },
                    ]
                },
            },
            None,
        )

        result = get_apple_health_workouts_tool.func(self.config)
        self.assertNotIn("Failed to retrieve workout data", result)
        self.assertIn("Running", result)
        self.assertIn("Duration: 0 minutes", result)
        self.assertIn("Yoga", result)
        self.assertIn("Duration: 60 minutes", result)
        self.assertIn("Calories: 220 kcal", result)

    @patch("utils.retrieval.tools.apple_health_tools.prepare_apple_health_access")
    def test_summary_tool_null_metrics(self, mock_prepare):
        """Verify get_apple_health_summary_tool renders all sections cleanly when metrics contain nulls."""
        mock_prepare.return_value = (
            "test_user_001",
            {
                "last_synced": "2026-10-21T12:00:00Z",
                "health_data": {
                    "steps": {
                        "total": None,
                        "average_per_day": None,
                        "daily": [{"date": "2026-10-21", "steps": None}],
                    },
                    "active_energy": {
                        "total": None,
                        "average_per_day": None,
                        "daily": [{"date": "2026-10-21", "calories": None}],
                    },
                    "sleep": {
                        "total_sleep_hours": None,
                        "daily": [{"date": "2026-10-21", "sleepHours": None}],
                    },
                    "heart_rate": {
                        "average": None,
                        "minimum": None,
                        "maximum": None,
                    },
                    "workouts": [
                        {
                            "type": "Swimming",
                            "startDate": "2026-10-21T10:00:00Z",
                            "durationMinutes": None,
                        }
                    ],
                },
            },
            None,
        )

        result = get_apple_health_summary_tool.func(self.config)
        self.assertNotIn("Failed to retrieve health summary", result)
        self.assertIn("STEPS", result)
        self.assertIn("Total: 0", result)
        self.assertIn("Daily Average: 0", result)
        self.assertIn("ACTIVE ENERGY", result)
        self.assertIn("Total: 0 kcal", result)
        self.assertIn("Daily Average: 0 kcal", result)
        self.assertIn("SLEEP", result)
        self.assertIn("Total Hours: 0.0", result)
        self.assertIn("WORKOUTS", result)
        self.assertIn("Swimming: 1", result)


if __name__ == "__main__":
    unittest.main()
