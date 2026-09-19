"""Hermetic regression: a request for fewer posts than an X API v2 endpoint's
max_results floor must not be sent below the floor.

X rejects max_results outside the endpoint's range with HTTP 400. Floors:
GET /2/tweets/search/recent 10, GET /2/users/:id/tweets and
GET /2/users/:id/mentions 5, GET /2/users/:id/timelines/reverse_chronological
1; ceiling 100 everywhere (X API v2 reference, mirrored in tweepy's Client
docs). The handlers used to clamp only the ceiling, so "show my last 3
tweets" became max_results=3 and every such call failed.

Import the production module with framework-only stubs, then exercise the
real handlers against a seam that enforces the documented ranges. No network,
credentials, or third-party packages required.

Run: python3 plugins/omi-twitter-chat-tools-app/test_max_results.py
"""

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

MAIN_PATH = Path(__file__).resolve().parent / "main.py"

# Documented max_results ranges per endpoint path suffix.
RANGES = {
    "/tweets/search/recent": (10, 100),
    "/tweets": (5, 100),
    "/mentions": (5, 100),
    "/timelines/reverse_chronological": (1, 100),
}


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    def module(name, **attributes):
        value = ModuleType(name)
        value.__dict__.update(attributes)
        return value

    db = module("db")
    for name in (
        "store_twitter_tokens",
        "get_twitter_tokens",
        "update_twitter_tokens",
        "delete_twitter_tokens",
        "store_oauth_state",
        "get_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
        "get_user_setting",
    ):
        setattr(db, name, lambda *args, **kwargs: None)

    stubs = {
        "fastapi": module("fastapi", FastAPI=FastAPI, Request=object, Query=lambda *a, **k: None, HTTPException=Exception),
        "fastapi.responses": module("fastapi.responses", HTMLResponse=str, RedirectResponse=str, JSONResponse=dict),
        "dotenv": module("dotenv", load_dotenv=lambda *a, **k: None),
        "requests": module("requests"),
        "db": db,
        "models": module("models", ChatToolResponse=ChatToolResponse),
    }
    spec = importlib.util.spec_from_file_location("twitter_chat_tools_under_test", MAIN_PATH)
    loaded = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(loaded)
    return loaded


app = load_app()


def _request(body):
    class _Request:
        async def json(self):
            return body

    return _Request()


class _XApi:
    """Stands in for twitter_api_request and enforces the documented ranges."""

    def __init__(self):
        self.calls = []

    def __call__(self, uid, method, endpoint, params=None, json_data=None):
        self.calls.append((endpoint, dict(params or {})))
        for suffix, (floor, ceiling) in RANGES.items():
            if endpoint.endswith(suffix):
                break
        else:
            raise AssertionError(f"unexpected endpoint {endpoint}")
        value = params["max_results"]
        if not isinstance(value, int) or not floor <= value <= ceiling:
            return {
                "error": f"The `max_results` query parameter value [{value}] is not between {floor} and {ceiling}",
                "status_code": 400,
            }
        return {
            "data": [
                {"id": str(1000 + index), "text": f"post {index}", "author_id": "u1", "created_at": "2026-09-14T10:00:00.000Z"}
                for index in range(value)
            ],
            "includes": {"users": [{"id": "u1", "name": "User", "username": "user"}]},
        }


TOOLS = (
    # handler, floor, extra body
    ("tool_get_timeline", 1, {}),
    ("tool_get_my_tweets", 5, {}),
    ("tool_get_mentions", 5, {}),
    ("tool_search_tweets", 10, {"query": "omi"}),
)


class MaxResultsRespectsEndpointFloors(unittest.TestCase):
    def setUp(self):
        self.api = _XApi()
        for target, value in (
            ("twitter_api_request", self.api),
            ("get_valid_access_token", lambda uid: "token"),
            ("get_user_id", lambda uid: "u1"),
            ("log", lambda msg: None),
        ):
            patcher = patch.object(app, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, name, **body):
        handler = getattr(app, name)
        return asyncio.run(handler(_request({"uid": "user", **body})))

    def test_small_requests_are_sent_at_the_floor_and_trimmed(self):
        for name, floor, extra in TOOLS:
            for requested in (1, 3, floor - 1 if floor > 1 else 1):
                with self.subTest(tool=name, requested=requested):
                    self.api.calls.clear()
                    response = self.call(name, max_results=requested, **extra)
                    self.assertIsNone(response.error, response.error)
                    self.assertEqual(self.api.calls[-1][1]["max_results"], max(floor, requested))
                    self.assertEqual(response.result.count("ID: `"), requested, response.result)

    def test_in_range_requests_pass_through_unchanged(self):
        for name, floor, extra in TOOLS:
            for requested in (floor, 25, 100):
                with self.subTest(tool=name, requested=requested):
                    self.api.calls.clear()
                    response = self.call(name, max_results=requested, **extra)
                    self.assertIsNone(response.error, response.error)
                    self.assertEqual(self.api.calls[-1][1]["max_results"], requested)
                    self.assertEqual(response.result.count("ID: `"), requested)

    def test_ceiling_and_non_integer_inputs_are_normalised(self):
        for name, floor, extra in TOOLS:
            for requested, expected in ((250, 100), ("7", max(floor, 7)), ("many", 10), (None, 10), (0, floor), (-4, floor), (float("inf"), 10), (float("nan"), 10), (1e309, 10)):
                with self.subTest(tool=name, requested=requested):
                    self.api.calls.clear()
                    response = self.call(name, max_results=requested, **extra)
                    self.assertIsNone(response.error, response.error)
                    self.assertEqual(self.api.calls[-1][1]["max_results"], expected)

    def test_default_is_ten(self):
        for name, floor, extra in TOOLS:
            with self.subTest(tool=name):
                self.api.calls.clear()
                response = self.call(name, **extra)
                self.assertIsNone(response.error, response.error)
                self.assertEqual(self.api.calls[-1][1]["max_results"], 10)
                self.assertEqual(response.result.count("ID: `"), 10)


if __name__ == "__main__":
    unittest.main()
