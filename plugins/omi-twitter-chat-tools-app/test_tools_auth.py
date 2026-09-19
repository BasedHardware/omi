"""
Hermetic regression tests for Twitter chat-tool authentication (#14451).

Verifies all ten /tools/* routes require shared-secret authentication (Bearer token or query param)
and fail-closed with 503 (unconfigured) or 401 (unauthorized) to prevent unauthorized actions using victim tokens.
"""

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# Ensure hermetic imports if optional dependencies are not pre-installed
if "requests" not in sys.modules:
    sys.modules["requests"] = types.ModuleType("requests")
if "dotenv" not in sys.modules:
    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv_mod

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TestClient is not None:
    from main import app
    from twitter_tools_auth import (
        _TWITTER_TOOLS_SECRET_ENV,
        _QUERY_TOKEN_PARAM,
        require_twitter_tools_auth,
    )

TEST_SECRET = "test_twitter_secret_value_123"

TOOL_ROUTES = [
    "/tools/post_tweet",
    "/tools/get_timeline",
    "/tools/get_my_tweets",
    "/tools/get_mentions",
    "/tools/search_tweets",
    "/tools/like_tweet",
    "/tools/unlike_tweet",
    "/tools/retweet",
    "/tools/delete_tweet",
    "/tools/get_user_profile",
]


@unittest.skipIf(TestClient is None, "fastapi/httpx test dependencies are not installed")
class TwitterToolsAuthTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides.clear()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_unconfigured_secret_returns_503(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(_TWITTER_TOOLS_SECRET_ENV, None)
            for route in TOOL_ROUTES:
                resp = self.client.post(route, json={"uid": "victim_uid"})
                self.assertEqual(
                    resp.status_code,
                    503,
                    f"Route {route} did not return 503 when secret is unconfigured",
                )
                self.assertIn("not configured", resp.json().get("detail", ""))

    def test_missing_token_returns_401(self):
        with patch.dict(os.environ, {_TWITTER_TOOLS_SECRET_ENV: TEST_SECRET}):
            for route in TOOL_ROUTES:
                resp = self.client.post(route, json={"uid": "victim_uid"})
                self.assertEqual(
                    resp.status_code,
                    401,
                    f"Route {route} did not return 401 when token is missing",
                )

    def test_invalid_token_returns_401(self):
        with patch.dict(os.environ, {_TWITTER_TOOLS_SECRET_ENV: TEST_SECRET}):
            headers = {"Authorization": "Bearer wrong_secret"}
            for route in TOOL_ROUTES:
                resp = self.client.post(route, json={"uid": "victim_uid"}, headers=headers)
                self.assertEqual(
                    resp.status_code,
                    401,
                    f"Route {route} did not return 401 on bad Bearer token",
                )

    def test_valid_bearer_token_passes_auth(self):
        with patch.dict(os.environ, {_TWITTER_TOOLS_SECRET_ENV: TEST_SECRET}), \
             patch("main.get_valid_access_token", return_value="valid_token"), \
             patch("main.get_user_id", return_value="user_123"), \
             patch("main.twitter_api_request", return_value={"data": []}):
            headers = {"Authorization": f"Bearer {TEST_SECRET}"}
            resp = self.client.post("/tools/get_timeline", json={"uid": "valid_user"}, headers=headers)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("No tweets in your timeline.", resp.json().get("result", ""))

    def test_valid_query_token_passes_auth(self):
        with patch.dict(os.environ, {_TWITTER_TOOLS_SECRET_ENV: TEST_SECRET}), \
             patch("main.get_valid_access_token", return_value="valid_token"), \
             patch("main.get_user_id", return_value="user_123"), \
             patch("main.twitter_api_request", return_value={"data": []}):
            resp = self.client.post(
                f"/tools/get_timeline?{_QUERY_TOKEN_PARAM}={TEST_SECRET}",
                json={"uid": "valid_user"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("No tweets in your timeline.", resp.json().get("result", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
