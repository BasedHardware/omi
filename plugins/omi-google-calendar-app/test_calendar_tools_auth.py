"""
Hermetic regression tests for Google Calendar chat-tool authentication (#14455).

Verifies all six /tools/* routes require shared-secret authentication
and fail-closed with 503 (unconfigured) or 401 (unauthorized).
"""

import os
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
    from main import app
    from calendar_tools_auth import (
        _SECRET_ENV,
        _QUERY_PARAM,
        require_calendar_tools_auth,
    )

TEST_SECRET = "test_calendar_secret_123"

TOOL_ROUTES = [
    "/tools/list_events",
    "/tools/create_event",
    "/tools/get_event",
    "/tools/update_event",
    "/tools/delete_event",
    "/tools/list_calendars",
]


@unittest.skipIf(TestClient is None, "fastapi/httpx test dependencies are not installed")
class CalendarToolsAuthTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides.clear()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_unconfigured_secret_returns_503(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(_SECRET_ENV, None)
            for route in TOOL_ROUTES:
                resp = self.client.post(route, json={"uid": "victim_uid"})
                self.assertEqual(
                    resp.status_code,
                    503,
                    f"Route {route} did not return 503 when secret is unconfigured",
                )
                self.assertIn("not configured", resp.json().get("detail", ""))

    def test_missing_token_returns_401(self):
        with patch.dict(os.environ, {_SECRET_ENV: TEST_SECRET}):
            for route in TOOL_ROUTES:
                resp = self.client.post(route, json={"uid": "victim_uid"})
                self.assertEqual(
                    resp.status_code,
                    401,
                    f"Route {route} did not return 401 when token is missing",
                )

    def test_invalid_token_returns_401(self):
        with patch.dict(os.environ, {_SECRET_ENV: TEST_SECRET}):
            headers = {"Authorization": "Bearer wrong_secret"}
            for route in TOOL_ROUTES:
                resp = self.client.post(route, json={"uid": "victim_uid"}, headers=headers)
                self.assertEqual(
                    resp.status_code,
                    401,
                    f"Route {route} did not return 401 on bad Bearer token",
                )

    def test_valid_bearer_token_passes_auth(self):
        with patch.dict(os.environ, {_SECRET_ENV: TEST_SECRET}), \
             patch("main.get_valid_access_token", return_value=None):
            headers = {"Authorization": f"Bearer {TEST_SECRET}"}
            resp = self.client.post("/tools/list_events", json={"uid": "valid_user"}, headers=headers)
            # Passes auth check, reaches app logic (which returns error for unconnected account)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Please connect your Google Calendar", resp.json().get("error", ""))

    def test_valid_query_token_passes_auth(self):
        with patch.dict(os.environ, {_SECRET_ENV: TEST_SECRET}), \
             patch("main.get_valid_access_token", return_value=None):
            resp = self.client.post(
                f"/tools/list_events?{_QUERY_PARAM}={TEST_SECRET}",
                json={"uid": "valid_user"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Please connect your Google Calendar", resp.json().get("error", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
