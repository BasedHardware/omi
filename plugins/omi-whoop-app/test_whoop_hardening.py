import sys
import unittest
from pathlib import Path

# Ensure plugins/omi-whoop-app is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import the formatters directly from main
from main import (
    format_recovery_score,
    format_strain_score,
    format_sleep,
    format_workout,
    WHOOP_REQUEST_TIMEOUT,
)


class TestWhoopHardening(unittest.TestCase):
    def test_timeout_configuration(self):
        self.assertEqual(WHOOP_REQUEST_TIMEOUT, 10)

    # -------------------------------------------------------------
    # format_recovery_score tests
    # -------------------------------------------------------------
    def test_recovery_none_input(self):
        self.assertEqual(format_recovery_score(None), "No recovery data available")

    def test_recovery_non_dict_input(self):
        self.assertEqual(format_recovery_score(["not", "a", "dict"]), "No recovery data available")

    def test_recovery_empty_dict(self):
        self.assertEqual(format_recovery_score({}), "No recovery score available")

    def test_recovery_score_is_none(self):
        self.assertEqual(format_recovery_score({"score": None}), "No recovery score available")

    def test_recovery_score_inner_field_none(self):
        self.assertEqual(format_recovery_score({"score": {"recovery_score": None}}), "No recovery score available")

    def test_recovery_score_invalid_type(self):
        self.assertEqual(format_recovery_score({"score": {"recovery_score": "invalid"}}), "No recovery score available")

    def test_recovery_valid_high(self):
        res = format_recovery_score({
            "score": {
                "recovery_score": 85,
                "hrv_rmssd_milli": 62.4,
                "resting_heart_rate": 52,
                "spo2_percentage": 98.5,
                "skin_temp_celsius": 33.5
            }
        })
        self.assertIn("Recovery: 85%", res)
        self.assertIn("Green (High)", res)
        self.assertIn("HRV:** 62.4 ms", res)
        self.assertIn("Resting HR:** 52 bpm", res)

    def test_recovery_valid_moderate_and_low(self):
        res_yellow = format_recovery_score({"score": {"recovery_score": 50}})
        self.assertIn("Yellow (Moderate)", res_yellow)

        res_red = format_recovery_score({"score": {"recovery_score": 25}})
        self.assertIn("Red (Low)", res_red)

    # -------------------------------------------------------------
    # format_strain_score tests
    # -------------------------------------------------------------
    def test_strain_none_input(self):
        self.assertEqual(format_strain_score(None), "No strain data available")

    def test_strain_non_dict_input(self):
        self.assertEqual(format_strain_score("invalid"), "No strain data available")

    def test_strain_empty_dict(self):
        self.assertEqual(format_strain_score({}), "No strain data available")

    def test_strain_score_is_none(self):
        self.assertEqual(format_strain_score({"score": None}), "No strain data available")

    def test_strain_field_none(self):
        self.assertEqual(format_strain_score({"score": {"strain": None}}), "No strain data available")

    def test_strain_field_invalid_type(self):
        self.assertEqual(format_strain_score({"score": {"strain": "bad"}}), "No strain data available")

    def test_strain_valid_levels(self):
        res_high = format_strain_score({
            "score": {
                "strain": 18.5,
                "kilojoule": 4500,
                "average_heart_rate": 140,
                "max_heart_rate": 180
            }
        })
        self.assertIn("Day Strain: 18.5", res_high)
        self.assertIn("Overreaching", res_high)
        self.assertIn("Calories Burned:", res_high)
        self.assertIn("Average HR:** 140 bpm", res_high)

        res_med = format_strain_score({"score": {"strain": 12.0}})
        self.assertIn("Medium", res_med)

        res_low = format_strain_score({"score": {"strain": 6.0}})
        self.assertIn("Low", res_low)

    # -------------------------------------------------------------
    # format_sleep tests
    # -------------------------------------------------------------
    def test_sleep_none_input(self):
        self.assertEqual(format_sleep(None), "No sleep data available")

    def test_sleep_non_dict_input(self):
        self.assertEqual(format_sleep(12345), "No sleep data available")

    def test_sleep_empty_dict(self):
        self.assertEqual(format_sleep({}), "No sleep data available")

    def test_sleep_score_is_none(self):
        self.assertEqual(format_sleep({"score": None}), "No sleep data available")

    def test_sleep_valid_with_stage_summary(self):
        res = format_sleep({
            "score": {
                "stage_summary": {
                    "total_in_bed_time_milli": 28800000,
                    "total_awake_time_milli": 3600000,
                    "total_light_sleep_time_milli": 14400000,
                    "total_slow_wave_sleep_time_milli": 5400000,
                    "total_rem_sleep_time_milli": 5400000
                },
                "sleep_performance_percentage": 88,
                "sleep_efficiency_percentage": 92,
                "sleep_consistency_percentage": 80,
                "respiratory_rate": 14.5
            }
        })
        self.assertIn("Total Sleep: 7.0 hours", res)
        self.assertIn("Sleep Stages:", res)
        self.assertIn("Light: 4.0h | Deep: 1.5h | REM: 1.5h", res)
        self.assertIn("Sleep Performance:** 88%", res)
        self.assertIn("Respiratory Rate:** 14.5 breaths/min", res)

    # -------------------------------------------------------------
    # format_workout tests
    # -------------------------------------------------------------
    def test_workout_none_input(self):
        self.assertEqual(format_workout(None), "No workout data available")

    def test_workout_empty_dict(self):
        res = format_workout({})
        self.assertIn("**Activity**", res)

    def test_workout_valid(self):
        res = format_workout({
            "sport_id": 1,
            "score": {
                "strain": 14.2,
                "average_heart_rate": 155,
                "max_heart_rate": 178,
                "kilojoule": 2500,
                "distance_meter": 7500
            },
            "start": "2026-09-17T06:00:00Z",
            "end": "2026-09-17T06:45:00Z"
        })
        self.assertIn("**Running** (45 min)", res)
        self.assertIn("Strain:** 14.2", res)
        self.assertIn("Distance:** 7.50 km", res)
        self.assertIn("Avg HR:** 155 bpm", res)


if __name__ == "__main__":
    unittest.main()
