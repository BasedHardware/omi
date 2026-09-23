"""Hermetic tests for Whoop weekly summary null score guards and date parameter sanitization.

Runs under standard library unittest without third-party dependencies.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


def load_whoop_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    def Query(default=None, **kwargs):
        return default

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _Response:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    requests = ModuleType("requests")
    requests.get = lambda *args, **kwargs: None
    requests.post = lambda *args, **kwargs: None

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = object
    fastapi.Query = Query
    fastapi.HTTPException = HTTPException

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = _Response
    responses.RedirectResponse = _Response
    responses.JSONResponse = _Response

    db = ModuleType("db")
    for name in (
        "store_whoop_tokens",
        "update_whoop_tokens",
        "delete_whoop_tokens",
        "store_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
    ):
        setattr(db, name, lambda *args, **kwargs: None)
    for name in ("get_whoop_tokens", "get_uid_from_oauth_state", "get_user_setting"):
        setattr(db, name, lambda *args, **kwargs: None)

    models = ModuleType("models")
    models.ChatToolResponse = ChatToolResponse

    spec = importlib.util.spec_from_file_location(
        "whoop_app_hardening", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "requests": requests,
            "dotenv": dotenv,
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "db": db,
            "models": models,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_whoop_app()


class FakeChatRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class TestMeasurementsAndSummaryHardening(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(app, "get_valid_access_token", return_value="test-token")
        self.addCleanup(patcher.stop)
        patcher.start()

    # -------------------------------------------------------------
    # Helper unit tests
    # -------------------------------------------------------------
    def test_clean_date_param(self):
        self.assertEqual(app._clean_date_param("2026-09-20"), "2026-09-20")
        self.assertEqual(app._clean_date_param("2026-09-20T12:30:00Z"), "2026-09-20")
        self.assertIsNone(app._clean_date_param("invalid-date"))
        self.assertIsNone(app._clean_date_param(False))
        self.assertIsNone(app._clean_date_param(20260920))
        self.assertIsNone(app._clean_date_param(None))
        self.assertIsNone(app._clean_date_param(""))

    def test_safe_float(self):
        self.assertEqual(app._safe_float("1.85"), 1.85)
        self.assertEqual(app._safe_float(42), 42.0)
        self.assertEqual(app._safe_float(3.14), 3.14)
        self.assertIsNone(app._safe_float("invalid"))
        self.assertIsNone(app._safe_float(None))
        self.assertEqual(app._safe_float(None, 0.0), 0.0)
        self.assertEqual(app._safe_float("invalid", 10.0), 10.0)

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

        with patch.object(app, "whoop_fetch_all_records", side_effect=fake_fetch_all):
            response = asyncio.run(app.tool_get_weekly_summary(FakeChatRequest({"uid": "u1"})))

        self.assertIsNone(response.error)
        result = response.result
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

        with patch.object(app, "whoop_api_request", side_effect=fake_request):
            # Test with valid date
            asyncio.run(app.tool_get_recovery(FakeChatRequest({"uid": "u1", "date": "2026-09-20"})))
            self.assertEqual(captured_params.get("start"), "2026-09-20T00:00:00.000Z")
            self.assertEqual(captured_params.get("end"), "2026-09-20T23:59:59.999Z")

            # Test with invalid date representation (e.g. non-string or boolean)
            captured_params.clear()
            asyncio.run(app.tool_get_recovery(FakeChatRequest({"uid": "u1", "date": False})))
            self.assertNotIn("start", captured_params)
            self.assertNotIn("end", captured_params)
            self.assertEqual(captured_params.get("limit"), 1)


if __name__ == "__main__":
    unittest.main()
