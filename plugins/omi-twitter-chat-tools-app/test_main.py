"""
Hermetic test suite for the Twitter / X chat tools app.

Exercises manifest schemas, parameter sanitization (_safe_max_results),
format_tweet formatting, and tool endpoint logic without network or third-party dependencies.
Can run under pure standard library Python (e.g., under python3 -S).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class HTTPException(Exception):
        def __init__(self, status_code=400, detail=""):
            self.status_code = status_code
            self.detail = detail

    class Request:
        def __init__(self, json_data=None):
            self._json = json_data or {}

        async def json(self):
            return self._json

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.HTTPException = HTTPException
    fastapi.Query = lambda default=None, **kwargs: default

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.RedirectResponse = str
    responses.JSONResponse = dict

    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    requests = ModuleType("requests")
    requests.get = Mock()
    requests.post = Mock()
    requests.delete = Mock()

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    db = ModuleType("db")
    db.store_twitter_tokens = Mock()
    db.get_twitter_tokens = Mock(return_value=None)
    db.update_twitter_tokens = Mock()
    db.delete_twitter_tokens = Mock()
    db.store_oauth_state = Mock()
    db.get_oauth_state = Mock()
    db.delete_oauth_state = Mock()
    db.store_user_setting = Mock()
    db.get_user_setting = Mock()

    models = ModuleType("models")

    class ChatToolResponse(BaseModel):
        result: str | None = None
        error: str | None = None

    models.ChatToolResponse = ChatToolResponse

    spec = importlib.util.spec_from_file_location(
        "omi_twitter_main", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "pydantic": pydantic,
            "requests": requests,
            "dotenv": dotenv,
            "db": db,
            "models": models,
        },
    ):
        spec.loader.exec_module(module)
    return module, Request


app, MockRequest = load_app()


class TwitterUnitHelperTests(unittest.TestCase):
    def test_safe_max_results_bounds(self):
        self.assertEqual(app._safe_max_results(None), 10)
        self.assertEqual(app._safe_max_results(""), 10)
        self.assertEqual(app._safe_max_results("invalid"), 10)
        self.assertEqual(app._safe_max_results(0), 1)
        self.assertEqual(app._safe_max_results(-5), 1)
        self.assertEqual(app._safe_max_results(50), 50)
        self.assertEqual(app._safe_max_results("50"), 50)
        self.assertEqual(app._safe_max_results(200), 100)

    def test_format_tweet_null_safety(self):
        # Non-dict tweet returns empty string
        self.assertEqual(app.format_tweet(None), "")
        self.assertEqual(app.format_tweet("not-a-dict"), "")

        # Valid tweet with missing metrics and includes
        tweet = {
            "id": "12345",
            "text": "Hello world from Omi!",
            "public_metrics": None,
        }
        output = app.format_tweet(tweet)
        self.assertIn("Hello world from Omi!", output)
        self.assertIn("ID: `12345`", output)

    def test_format_tweet_with_author_and_metrics(self):
        tweet = {
            "id": "12345",
            "text": "AI agents are awesome",
            "author_id": "auth_1",
            "created_at": "2026-09-16T10:00:00Z",
            "public_metrics": {
                "like_count": 42,
                "retweet_count": 7,
                "reply_count": 3,
            },
        }
        includes = {
            "users": [
                {"id": "auth_1", "name": "Aditya", "username": "1234adi1234"}
            ]
        }
        output = app.format_tweet(tweet, includes)
        self.assertIn("**@1234adi1234** (Aditya)", output)
        self.assertIn("AI agents are awesome", output)
        self.assertIn("Likes: 42 | Retweets: 7 | Replies: 3", output)


class TwitterEndpointAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_manifest_structure(self):
        manifest = await app.get_omi_tools_manifest()
        self.assertIn("tools", manifest)
        self.assertGreaterEqual(len(manifest["tools"]), 9)

        # Ensure all tool definitions strictly declare type: "object"
        for tool in manifest["tools"]:
            params = tool.get("parameters", {})
            self.assertEqual(params.get("type"), "object", f"Tool {tool['name']} missing type: object")
            self.assertIn("properties", params)

    async def test_post_tweet_missing_required_fields(self):
        # Missing uid
        res_no_uid = await app.tool_post_tweet(MockRequest({"text": "Hello"}))
        self.assertEqual(res_no_uid.error, "User ID is required")

        # Missing text
        res_no_text = await app.tool_post_tweet(MockRequest({"uid": "u1"}))
        self.assertEqual(res_no_text.error, "Tweet text is required")

        # Text over 280 chars
        res_too_long = await app.tool_post_tweet(MockRequest({"uid": "u1", "text": "x" * 281}))
        self.assertIn("too long", res_too_long.error)

    async def test_post_tweet_unauthenticated(self):
        with patch.object(app, "get_valid_access_token", return_value=None):
            res = await app.tool_post_tweet(MockRequest({"uid": "u1", "text": "Valid tweet"}))
            self.assertIn("connect your Twitter account", res.error)

    async def test_post_tweet_success(self):
        mock_resp = {
            "data": {
                "id": "tweet_999",
                "text": "Valid tweet text",
            }
        }
        with patch.object(app, "get_valid_access_token", return_value="token123"), \
             patch.object(app, "twitter_api_request", return_value=mock_resp):
            res = await app.tool_post_tweet(MockRequest({"uid": "u1", "text": "Valid tweet text"}))
            self.assertIsNone(res.error)
            self.assertIn("Tweet Posted!", res.result)
            self.assertIn("ID: `tweet_999`", res.result)

    async def test_get_timeline_null_max_results_does_not_crash(self):
        # Regression: body.get("max_results") being None previously crashed with TypeError in min()
        with patch.object(app, "get_valid_access_token", return_value="token123"), \
             patch.object(app, "get_user_id", return_value="user123"), \
             patch.object(app, "twitter_api_request", return_value={"data": []}):
            res = await app.tool_get_timeline(MockRequest({"uid": "u1", "max_results": None}))
            self.assertIsNone(res.error)
            self.assertEqual(res.result, "No tweets in your timeline.")

    async def test_get_my_tweets_null_max_results_does_not_crash(self):
        with patch.object(app, "get_valid_access_token", return_value="token123"), \
             patch.object(app, "get_user_id", return_value="user123"), \
             patch.object(app, "twitter_api_request", return_value={"data": []}):
            res = await app.tool_get_my_tweets(MockRequest({"uid": "u1", "max_results": None}))
            self.assertIsNone(res.error)
            self.assertEqual(res.result, "You haven't posted any tweets yet.")

    async def test_get_mentions_null_max_results_does_not_crash(self):
        with patch.object(app, "get_valid_access_token", return_value="token123"), \
             patch.object(app, "get_user_id", return_value="user123"), \
             patch.object(app, "twitter_api_request", return_value={"data": []}):
            res = await app.tool_get_mentions(MockRequest({"uid": "u1", "max_results": None}))
            self.assertIsNone(res.error)
            self.assertEqual(res.result, "No mentions found.")

    async def test_search_tweets_null_max_results_does_not_crash(self):
        with patch.object(app, "get_valid_access_token", return_value="token123"), \
             patch.object(app, "twitter_api_request", return_value={"data": []}):
            res = await app.tool_search_tweets(MockRequest({"uid": "u1", "query": "Omi", "max_results": None}))
            self.assertIsNone(res.error)
            self.assertIn("No tweets found", res.result)

    async def test_get_user_profile_null_metrics_does_not_crash(self):
        mock_user = {
            "data": {
                "name": "Aditya",
                "username": "1234adi1234",
                "public_metrics": None,
                "created_at": None,
            }
        }
        with patch.object(app, "get_valid_access_token", return_value="token123"), \
             patch.object(app, "twitter_api_request", return_value=mock_user):
            res = await app.tool_get_user_profile(MockRequest({"uid": "u1"}))
            self.assertIsNone(res.error)
            self.assertIn("@1234adi1234", res.result)
            self.assertIn("**Followers:** 0", res.result)


if __name__ == "__main__":
    unittest.main()
