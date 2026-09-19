"""
Hermetic regression tests for Whoop chat-tool authentication (#14453).

Verifies all seven /tools/* routes require shared-secret authentication (Bearer token or query param)
and fail-closed with 503 (unconfigured) or 401 (unauthorized) to protect sensitive user health data.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TestClient is not None:
    from main import app
    from whoop_tools_auth import (
        _WHOOP_TOOLS_SECRET_ENV,
        _QUERY_TOKEN_PARAM,
        require_whoop_tools_auth,
    )

TEST_SECRET = "test_whoop_secret_value_123"

TOOL_ROUTES = [
    "/tools/get_recovery",
    "/tools/get_strain",
    "/tools/get_sleep",
    "/tools/get_workouts",
    "/tools/get_weekly_summary",
    "/tools/get_body_measurements",
    "/tools/get_profile",
]


@unittest.skipIf(TestClient is None, "fastapi/httpx test dependencies are not installed")
class WhoopToolsAuthTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides.clear()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_unconfigured_secret_returns_503(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(_WHOOP_TOOLS_SECRET_ENV, None)
            for route in TOOL_ROUTES:
                resp = self.client.post(route, json={"uid": "victim_uid"})
                self.assertEqual(
                    resp.status_code,
                    503,
                    f"Route {route} did not return 503 when secret is unconfigured",
                )
                self.assertIn("not configured", resp.json().get("detail", ""))

    def test_missing_token_returns_401(self):
        with patch.dict(os.environ, {_WHOOP_TOOLS_SECRET_ENV: TEST_SECRET}):
            for route in TOOL_ROUTES:
                resp = self.client.post(route, json={"uid": "victim_uid"})
                self.assertEqual(
                    resp.status_code,
                    401,
                    f"Route {route} did not return 401 when token is missing",
                )

    def test_invalid_token_returns_401(self):
        with patch.dict(os.environ, {_WHOOP_TOOLS_SECRET_ENV: TEST_SECRET}):
            headers = {"Authorization": "Bearer wrong_secret"}
            for route in TOOL_ROUTES:
                resp = self.client.post(route, json={"uid": "victim_uid"}, headers=headers)
                self.assertEqual(
                    resp.status_code,
                    401,
                    f"Route {route} did not return 401 on bad Bearer token",
                )

    def test_valid_bearer_token_passes_auth(self):
        with patch.dict(os.environ, {_WHOOP_TOOLS_SECRET_ENV: TEST_SECRET}), \
             patch("main.get_valid_access_token", return_value="valid_token"), \
             patch("main.whoop_api_request", return_value={"records": []}):
            headers = {"Authorization": f"Bearer {TEST_SECRET}"}
            resp = self.client.post("/tools/get_recovery", json={"uid": "valid_user"}, headers=headers)
            self.assertEqual(resp.status_code, 200)

    def test_valid_query_token_passes_auth(self):
        with patch.dict(os.environ, {_WHOOP_TOOLS_SECRET_ENV: TEST_SECRET}), \
             patch("main.get_valid_access_token", return_value="valid_token"), \
             patch("main.whoop_api_request", return_value={"records": []}):
            resp = self.client.post(
                f"/tools/get_recovery?{_QUERY_TOKEN_PARAM}={TEST_SECRET}",
                json={"uid": "valid_user"},
            )
            self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
