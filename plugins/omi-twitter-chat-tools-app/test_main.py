"""Hermetic regression tests for plugins/omi-twitter-chat-tools-app/main.py.

Standard library only: requests, dotenv, fastapi, and pydantic are replaced
with minimal stubs before importing the module under test so the suite
runs without site-packages.

Covers two boundary defects:
- max_results was only upper-clamped (`min(v, 100)`), so 0 / negative /
  non-integer values were sent to Twitter (whose documented minimum is 5
  for timelines/mentions/tweets and 10 for recent search) or raised a
  TypeError inside min().
- tweet_id and username were interpolated into request paths unencoded,
  so a value containing '/' or '?' rewrote the target endpoint.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    requests = types.ModuleType("requests")
    requests.get = requests.post = requests.delete = lambda *a, **k: None
    sys.modules["requests"] = requests

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    fastapi = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    class Request:
        pass

    def Query(default=None, **kwargs):
        return default

    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.HTTPException = HTTPException
    fastapi.Query = Query
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")

    class _Resp:
        def __init__(self, *args, **kwargs):
            pass

    responses.HTMLResponse = _Resp
    responses.RedirectResponse = _Resp
    responses.JSONResponse = _Resp
    sys.modules["fastapi.responses"] = responses

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for klass in reversed(type(self).__mro__):
                for field in getattr(klass, "__annotations__", {}):
                    if field in kwargs:
                        setattr(self, field, kwargs[field])
                    elif hasattr(type(self), field):
                        setattr(self, field, getattr(type(self), field))
                    else:
                        setattr(self, field, None)

    pydantic.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic


_install_module_stubs()
import main  # noqa: E402


class _FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _run(coro):
    return asyncio.run(coro)


class _EndpointCase(unittest.TestCase):
    """Shared scaffolding: authenticated user, captured API request."""

    def setUp(self):
        self.captured = {}

        def fake_api_request(uid, method, endpoint, params=None, json_data=None):
            self.captured = {
                "method": method,
                "endpoint": endpoint,
                "params": params or {},
                "json_data": json_data or {},
            }
            return {"data": []}

        self._patches = [
            mock.patch.object(main, "get_valid_access_token", lambda uid: "tok"),
            mock.patch.object(main, "get_user_id", lambda uid: "tw-uid"),
            mock.patch.object(main, "twitter_api_request", fake_api_request),
        ]
        for patcher in self._patches:
            patcher.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])


class MaxResultsBoundsTests(_EndpointCase):
    def test_parse_helper_clamps_to_bounds(self):
        self.assertEqual(main._parse_max_results({}), 10)
        self.assertEqual(main._parse_max_results({"max_results": 0}), 5)
        self.assertEqual(main._parse_max_results({"max_results": -3}), 5)
        self.assertEqual(main._parse_max_results({"max_results": 500}), 100)
        self.assertEqual(main._parse_max_results({"max_results": "20"}), 20)
        self.assertIsNone(main._parse_max_results({"max_results": "abc"}))
        self.assertIsNone(main._parse_max_results({"max_results": None}))
        # Search endpoint has a higher documented minimum.
        self.assertEqual(
            main._parse_max_results({"max_results": 2}, minimum=10), 10
        )

    def test_timeline_sends_clamped_max_results(self):
        _run(main.tool_get_timeline(_FakeRequest({"uid": "u1", "max_results": 0})))
        self.assertEqual(self.captured["params"]["max_results"], 5)

    def test_mentions_sends_clamped_max_results(self):
        _run(main.tool_get_mentions(_FakeRequest({"uid": "u1", "max_results": 999})))
        self.assertEqual(self.captured["params"]["max_results"], 100)

    def test_my_tweets_sends_clamped_max_results(self):
        _run(main.tool_get_my_tweets(_FakeRequest({"uid": "u1", "max_results": 1})))
        self.assertEqual(self.captured["params"]["max_results"], 5)

    def test_search_enforces_minimum_of_10(self):
        _run(
            main.tool_search_tweets(
                _FakeRequest({"uid": "u1", "query": "ai", "max_results": 3})
            )
        )
        self.assertEqual(self.captured["params"]["max_results"], 10)

    def test_non_integer_max_results_returns_error(self):
        resp = _run(
            main.tool_get_timeline(
                _FakeRequest({"uid": "u1", "max_results": "many"})
            )
        )
        self.assertIsNotNone(resp.error)


class PathInterpolationTests(_EndpointCase):
    def test_tweet_id_is_url_encoded_in_unlike_path(self):
        _run(
            main.tool_unlike_tweet(
                _FakeRequest({"uid": "u1", "tweet_id": "123/../admin"})
            )
        )
        self.assertEqual(
            self.captured["endpoint"], "/users/tw-uid/likes/123%2F..%2Fadmin"
        )

    def test_tweet_id_is_url_encoded_in_delete_path(self):
        _run(
            main.tool_delete_tweet(
                _FakeRequest({"uid": "u1", "tweet_id": "1?user_id=evil"})
            )
        )
        self.assertEqual(self.captured["endpoint"], "/tweets/1%3Fuser_id%3Devil")

    def test_username_is_url_encoded_in_profile_path(self):
        _run(
            main.tool_get_user_profile(
                _FakeRequest({"uid": "u1", "username": "a/b"})
            )
        )
        self.assertEqual(self.captured["endpoint"], "/users/by/username/a%2Fb")


if __name__ == "__main__":
    unittest.main()
