import sys
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TestClient is not None:
    from main import app, _clean_date_param, _safe_float


@unittest.skipIf(TestClient is None, "fastapi/httpx test dependencies are not installed")
class TestMeasurementsAndSummaryHardening(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        patcher = patch("main.get_valid_access_token", return_value="test-token")
        self.addCleanup(patcher.stop)
        patcher.start()

    # -------------------------------------------------------------
    # Helper unit tests
    # -------------------------------------------------------------
    def test_clean_date_param(self):
        self.assertEqual(_clean_date_param("2026-09-20"), "2026-09-20")
        self.assertEqual(_clean_date_param("2026-09-20T12:30:00Z"), "2026-09-20")
        self.assertIsNone(_clean_date_param("invalid-date"))
        self.assertIsNone(_clean_date_param(False))
        self.assertIsNone(_clean_date_param(20260920))
        self.assertIsNone(_clean_date_param(None))
        self.assertIsNone(_clean_date_param(""))

    def test_safe_float(self):
        self.assertEqual(_safe_float("1.85"), 1.85)
        self.assertEqual(_safe_float(42), 42.0)
        self.assertEqual(_safe_float(3.14), 3.14)
        self.assertIsNone(_safe_float("invalid"))
        self.assertIsNone(_safe_float(None))
        self.assertEqual(_safe_float(None, 0.0), 0.0)
        self.assertEqual(_safe_float("invalid", 10.0), 10.0)

    # -------------------------------------------------------------
    # Body measurements hardening tests
    # -------------------------------------------------------------
    def test_body_measurements_with_string_numbers(self):
        mock_response = {
            "height_meter": "1.85",
            "weight_kilogram": "80.0",
            "max_heart_rate": "190",
        }
        with patch("main.whoop_api_request", return_value=mock_response):
            response = self.client.post("/tools/get_body_measurements", json={"uid": "u1"})

        self.assertEqual(response.status_code, 200)
        result = response.json().get("result", "")
        self.assertIn("**Height:** 185 cm", result)
        self.assertIn("**Weight:** 80.0 kg (176.4 lb)", result)
        self.assertIn("**Max Heart Rate:** 190 bpm", result)

    def test_body_measurements_with_invalid_types_and_nones(self):
        mock_response = {
            "height_meter": "invalid",
            "weight_kilogram": None,
            "max_heart_rate": -1,
        }
        with patch("main.whoop_api_request", return_value=mock_response):
            response = self.client.post("/tools/get_body_measurements", json={"uid": "u1"})

        self.assertEqual(response.status_code, 200)
        result = response.json().get("result", "")
        self.assertEqual(result, "No body measurements available.")

    # -------------------------------------------------------------
    # Weekly summary hardening tests
    # -------------------------------------------------------------
    def test_weekly_summary_handles_none_and_malformed_scores(self):
        # A mix of uncalculated records (score is None), malformed records, and valid records
        recovery_records = [
            {"score": None},  # uncalculated / pending record
            {"score": {"recovery_score": "70"}},  # string recovery score
            {"score": {"recovery_score": 80}},  # int recovery score
            {"score": "not-a-dict"},  # malformed score
            None,  # non-dict record
        ]
        cycle_records = [
            {"score": None},
            {"score": {"strain": "10.5"}},
            {"score": {"strain": 14.5}},
        ]
        sleep_records = [
            {"score": None},
            {"score": {"stage_summary": None}},
            {
                "score": {
                    "stage_summary": {
                        "total_in_bed_time_milli": 28800000,
                        "total_awake_time_milli": 3600000,
                    }
                }
            },
        ]
        workout_records = [{"id": 1}, {"id": 2}]

        def fake_fetch_all(uid, endpoint, params):
            if endpoint == "/recovery":
                return recovery_records, None
            elif endpoint == "/cycle":
                return cycle_records, None
            elif endpoint == "/activity/sleep":
                return sleep_records, None
            elif endpoint == "/activity/workout":
                return workout_records, None
            return [], None

        with patch("main.whoop_fetch_all_records", side_effect=fake_fetch_all):
            response = self.client.post("/tools/get_weekly_summary", json={"uid": "u1"})

        self.assertEqual(response.status_code, 200)
        result = response.json().get("result", "")
        # Averages should safely compute over valid records without raising AttributeError
        self.assertIn("**Recovery:** Avg 75% (Range: 70%-80%)", result)
        self.assertIn("**Strain:** Avg 12.5 (Total: 25.0)", result)
        self.assertIn("**Sleep:** Avg 7.0h (Range: 7.0h-7.0h)", result)
        self.assertIn("**Workouts:** 2", result)

    # -------------------------------------------------------------
    # Date filter sanitization tests
    # -------------------------------------------------------------
    def test_date_filter_sanitization_in_get_recovery(self):
        captured_params = {}

        def fake_request(uid, method, endpoint, params=None):
            captured_params.update(params or {})
            return {"records": [{"score": {"recovery_score": 75}}]}

        with patch("main.whoop_api_request", side_effect=fake_request):
            # Test with valid date
            self.client.post("/tools/get_recovery", json={"uid": "u1", "date": "2026-09-20"})
            self.assertEqual(captured_params.get("start"), "2026-09-20T00:00:00.000Z")
            self.assertEqual(captured_params.get("end"), "2026-09-20T23:59:59.999Z")

            # Test with invalid date representation (e.g. non-string or boolean)
            captured_params.clear()
            self.client.post("/tools/get_recovery", json={"uid": "u1", "date": False})
            self.assertNotIn("start", captured_params)
            self.assertNotIn("end", captured_params)
            self.assertEqual(captured_params.get("limit"), 1)


if __name__ == "__main__":
    unittest.main()
