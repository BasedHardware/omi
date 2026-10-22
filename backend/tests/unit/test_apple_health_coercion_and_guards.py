"""Unit tests for apple_health_tools input validation, numeric coercion, and None guards."""

from unittest.mock import MagicMock, patch
import pytest

import utils.retrieval.tools.apple_health_tools as aht


class TestAppleHealthCoercionAndGuards:
    mod = aht

    def test_safe_float(self):
        assert self.mod._safe_float(10) == 10.0
        assert self.mod._safe_float(10.5) == 10.5
        assert self.mod._safe_float("15.5") == 15.5
        assert self.mod._safe_float("0") == 0.0
        assert self.mod._safe_float(None, 0.0) == 0.0
        assert self.mod._safe_float(True, 0.0) == 0.0
        assert self.mod._safe_float(False, 0.0) == 0.0
        assert self.mod._safe_float("abc", 0.0) == 0.0
        assert self.mod._safe_float(float("nan"), 0.0) == 0.0
        assert self.mod._safe_float(float("inf"), 0.0) == 0.0

    def test_safe_int(self):
        assert self.mod._safe_int(10) == 10
        assert self.mod._safe_int("10") == 10
        assert self.mod._safe_int(" 25 ") == 25
        assert self.mod._safe_int(25.0) == 25
        assert self.mod._safe_int(25.5, 0) == 0  # non-integer float rejects
        assert self.mod._safe_int(None, 0) == 0
        assert self.mod._safe_int(True, 0) == 0
        assert self.mod._safe_int(False, 0) == 0
        assert self.mod._safe_int("invalid", 0) == 0

    def test_get_apple_health_data_none_guard(self):
        with patch.object(self.mod.users_db, "get_integration", return_value={"health_data": None}):
            assert self.mod.get_apple_health_data("u1") == {}
            assert self.mod.get_apple_health_data("u1", "steps") is None

        with patch.object(self.mod.users_db, "get_integration", return_value=None):
            assert self.mod.get_apple_health_data("u1") is None

    @patch("utils.retrieval.tools.apple_health_tools.prepare_apple_health_access")
    def test_steps_tool_string_coercion_and_none_health_data(self, mock_prep):
        # 1. health_data is None in integration
        mock_prep.return_value = ("u1", {"connected": True, "health_data": None, "last_synced": "2026-09-27T08:00:00Z"}, None)
        res = self.mod.get_apple_health_steps_tool.func(config={"configurable": {"user_id": "u1"}})
        assert "No step data found" in res

        # 2. String total and steps in daily
        mock_prep.return_value = (
            "u1",
            {
                "connected": True,
                "health_data": {
                    "steps": {
                        "total": "12500",
                        "average_per_day": "2500",
                        "daily": [None, {"date": "2026-09-27", "steps": "6000"}],
                    }
                },
                "last_synced": "2026-09-27T08:00:00Z",
            },
            None,
        )
        res = self.mod.get_apple_health_steps_tool.func(config={"configurable": {"user_id": "u1"}})
        assert "Total Steps: 12,500" in res
        assert "Average Steps per Day: 2,500" in res
        assert "6,000 steps" in res

    @patch("utils.retrieval.tools.apple_health_tools.prepare_apple_health_access")
    def test_sleep_tool_string_coercion(self, mock_prep):
        mock_prep.return_value = (
            "u1",
            {
                "connected": True,
                "health_data": {
                    "sleep": {
                        "total_sleep_hours": "7.5",
                        "daily": [{"date": "2026-09-27", "sleepHours": "7.5"}],
                    }
                },
                "last_synced": "2026-09-27T08:00:00Z",
            },
            None,
        )
        res = self.mod.get_apple_health_sleep_tool.func(config={"configurable": {"user_id": "u1"}})
        assert "Total Sleep: 7.5 hours" in res
        assert "Average per Night: 7.5 hours" in res
        assert "7.5 hours" in res

    @patch("utils.retrieval.tools.apple_health_tools.prepare_apple_health_access")
    def test_heart_rate_tool_string_coercion(self, mock_prep):
        mock_prep.return_value = (
            "u1",
            {
                "connected": True,
                "health_data": {
                    "heart_rate": {
                        "average": "72",
                        "minimum": "55",
                        "maximum": "130",
                    }
                },
                "last_synced": "2026-09-27T08:00:00Z",
            },
            None,
        )
        res = self.mod.get_apple_health_heart_rate_tool.func(config={"configurable": {"user_id": "u1"}})
        assert "Average Heart Rate: 72 bpm" in res
        assert "Minimum Heart Rate: 55 bpm" in res
        assert "Maximum Heart Rate: 130 bpm" in res

    @patch("utils.retrieval.tools.apple_health_tools.prepare_apple_health_access")
    def test_workouts_tool_string_coercion_and_timestamp(self, mock_prep):
        mock_prep.return_value = (
            "u1",
            {
                "connected": True,
                "health_data": {
                    "workouts": [
                        None,  # malformed entry
                        {
                            "type": "Cycling",
                            "durationMinutes": "45",
                            "caloriesBurned": "350",
                            "distanceKm": "15.25",
                            "startDate": "1790407080000",
                        },
                    ]
                },
                "last_synced": "2026-09-27T08:00:00Z",
            },
            None,
        )
        res = self.mod.get_apple_health_workouts_tool.func(config={"configurable": {"user_id": "u1"}})
        assert "Cycling" in res
        assert "Duration: 45 minutes" in res
        assert "Calories: 350 kcal" in res
        assert "Distance: 15.25 km" in res

    @patch("utils.retrieval.tools.apple_health_tools.prepare_apple_health_access")
    def test_summary_tool_comprehensive_coercion(self, mock_prep):
        mock_prep.return_value = (
            "u1",
            {
                "connected": True,
                "health_data": {
                    "steps": {"total": "8000", "average_per_day": "4000", "daily": [{"date": "2026-09-27", "steps": "4000"}]},
                    "active_energy": {"total": "500", "average_per_day": "250", "daily": [{"date": "2026-09-27", "calories": "250"}]},
                    "sleep": {"total_sleep_hours": "8", "daily": [{"date": "2026-09-27", "sleepHours": "8"}]},
                    "heart_rate": {"average": "70", "minimum": "50", "maximum": "120"},
                    "workouts": [{"type": "Walking"}, "invalid_workout", None],
                },
                "last_synced": "2026-09-27T08:00:00Z",
            },
            None,
        )
        res = self.mod.get_apple_health_summary_tool.func(config={"configurable": {"user_id": "u1"}})
        assert "Apple Health Summary" in res
        assert "Total: 8,000" in res
        assert "Total: 500 kcal" in res
        assert "Total Hours: 8.0" in res
        assert "Average: 70 bpm" in res
        assert "Walking: 1" in res
