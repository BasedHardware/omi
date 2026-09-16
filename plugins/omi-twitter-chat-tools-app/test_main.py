"""Hermetic unit tests for Omi Twitter Chat Tools App."""

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Provide lightweight stubs for external dependencies if not present in environment
if "dotenv" not in sys.modules:
    try:
        import dotenv  # type: ignore
    except ImportError:
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda *args, **kwargs: None
        sys.modules["dotenv"] = dotenv

if "requests" not in sys.modules:
    try:
        import requests  # type: ignore
    except ImportError:
        requests = types.ModuleType("requests")
        requests.get = lambda *args, **kwargs: None
        requests.post = lambda *args, **kwargs: None
        requests.delete = lambda *args, **kwargs: None
        sys.modules["requests"] = requests

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.exceptions  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.routes = []

            def get(self, path, **kwargs):
                def decorator(func):
                    self.routes.append({"method": "GET", "path": path, "func": func})
                    return func
                return decorator

            def post(self, path, **kwargs):
                def decorator(func):
                    self.routes.append({"method": "POST", "path": path, "func": func})
                    return func
                return decorator

            def exception_handler(self, exc_class):
                return lambda f: f

        class Request:
            pass

        def Query(default=None, **kwargs):
            return default

        class HTTPException(Exception):
            def __init__(self, status_code: int, detail: str = None):
                self.status_code = status_code
                self.detail = detail

        fastapi.FastAPI = FastAPI
        fastapi.Request = Request
        fastapi.Query = Query
        fastapi.HTTPException = HTTPException
        sys.modules["fastapi"] = fastapi

        exceptions = types.ModuleType("fastapi.exceptions")

        class RequestValidationError(Exception):
            def __init__(self, errors=None):
                super().__init__("Validation error")
                self._errors = errors or []

            def errors(self):
                return self._errors

        exceptions.RequestValidationError = RequestValidationError
        sys.modules["fastapi.exceptions"] = exceptions
        fastapi.exceptions = exceptions

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content=None, status_code=200):
                self.content = content
                self.status_code = status_code

        class RedirectResponse:
            def __init__(self, url, status_code=307):
                self.url = url
                self.status_code = status_code

        class JSONResponse:
            def __init__(self, content=None, status_code=200):
                self.content = content
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.RedirectResponse = RedirectResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

            def model_dump(self):
                return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

# Add plugin directory to path so models and main can be loaded hermetically
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main
import models


class DummyRequest:
    """Helper mock for FastAPI request with json support."""
    def __init__(self, payload=None, raise_json=False):
        self._payload = payload
        self._raise_json = raise_json

    async def json(self):
        if self._raise_json:
            raise ValueError("Invalid JSON")
        return self._payload


class TwitterChatToolsHardeningTests(unittest.TestCase):
    """Test suite verifying input validation, guards, and normalization."""

    def run_async(self, coro):
        """Helper to run coroutines in synchronous tests."""
        return asyncio.run(coro)

    # -------------------------------------------------------------
    # 1. Helper function tests
    # -------------------------------------------------------------
    def test_safe_dict(self):
        self.assertEqual(main._safe_dict(None), {})
        self.assertEqual(main._safe_dict("string"), {})
        self.assertEqual(main._safe_dict([1, 2]), {})
        self.assertEqual(main._safe_dict({"key": "val"}), {"key": "val"})

    def test_clean_str(self):
        self.assertEqual(main._clean_str(None), "")
        self.assertEqual(main._clean_str("  hello  "), "hello")
        self.assertEqual(main._clean_str(12345), "12345")

    def test_clean_tweet_id(self):
        self.assertEqual(main._clean_tweet_id(None), "")
        self.assertEqual(main._clean_tweet_id("  12345  "), "12345")
        self.assertEqual(main._clean_tweet_id("#12345"), "12345")
        self.assertEqual(main._clean_tweet_id("  #98765  "), "98765")

    def test_clean_username(self):
        self.assertIsNone(main._clean_username(None))
        self.assertIsNone(main._clean_username(""))
        self.assertIsNone(main._clean_username("   "))
        self.assertIsNone(main._clean_username("@"))
        self.assertEqual(main._clean_username("@jack"), "jack")
        self.assertEqual(main._clean_username("  @elonmusk  "), "elonmusk")
        self.assertEqual(main._clean_username("sama"), "sama")

    def test_coerce_int_bounds(self):
        self.assertEqual(main._coerce_int_bounds(None, default=10, min_val=1, max_val=100), 10)
        self.assertEqual(main._coerce_int_bounds("invalid", default=10, min_val=1, max_val=100), 10)
        self.assertEqual(main._coerce_int_bounds(-5, default=10, min_val=1, max_val=100), 1)
        self.assertEqual(main._coerce_int_bounds(500, default=10, min_val=1, max_val=100), 100)
        self.assertEqual(main._coerce_int_bounds("25", default=10, min_val=1, max_val=100), 25)

    def test_format_count(self):
        self.assertEqual(main._format_count(None), "0")
        self.assertEqual(main._format_count(0), "0")
        self.assertEqual(main._format_count(1500), "1,500")
        self.assertEqual(main._format_count("2000000"), "2,000,000")
        self.assertEqual(main._format_count("N/A"), "N/A")

    # -------------------------------------------------------------
    # 2. format_tweet tests
    # -------------------------------------------------------------
    def test_format_tweet_standard(self):
        tweet = {
            "id": "1001",
            "text": "Hello world!",
            "author_id": "u1",
            "created_at": "2024-01-15T12:00:00Z",
            "public_metrics": {"like_count": 42, "retweet_count": 5, "reply_count": 2}
        }
        includes = {
            "users": [{"id": "u1", "name": "Jack", "username": "jack"}]
        }
        formatted = main.format_tweet(tweet, includes)
        self.assertIn("**@jack** (Jack)", formatted)
        self.assertIn("Hello world!", formatted)
        self.assertIn("Likes: 42 | Retweets: 5 | Replies: 2", formatted)
        self.assertIn("ID: `1001`", formatted)

    def test_format_tweet_defensive_nulls_and_empty(self):
        # Empty and non-dict tweet must not crash
        self.assertEqual(main.format_tweet({}, None), "ID: ``")
        self.assertEqual(main.format_tweet(None, None), "ID: ``")

    def test_format_tweet_malformed_users_includes(self):
        tweet = {"id": "1002", "text": "Test", "author_id": "u1"}
        # includes is not dict or users has non-dict item
        formatted = main.format_tweet(tweet, {"users": [None, "invalid", {"id": "u1", "username": "user1"}]})
        self.assertIn("**@user1**", formatted)

    def test_format_tweet_invalid_timestamp(self):
        tweet = {"id": "1003", "text": "Test", "created_at": "not-iso-timestamp-long"}
        formatted = main.format_tweet(tweet)
        self.assertIn("*not-iso-ti*", formatted)

    # -------------------------------------------------------------
    # 3. tool_post_tweet tests
    # -------------------------------------------------------------
    def test_post_tweet_validation(self):
        # Missing uid
        res = self.run_async(main.tool_post_tweet(DummyRequest({})))
        self.assertEqual(res.error, "User ID is required")

        # Missing text
        res = self.run_async(main.tool_post_tweet(DummyRequest({"uid": "user1"})))
        self.assertEqual(res.error, "Tweet text is required")

        # Text exceeds 280 chars
        long_text = "a" * 281
        res = self.run_async(main.tool_post_tweet(DummyRequest({"uid": "user1", "text": long_text})))
        self.assertIn("Tweet is too long", res.error)

    @patch("main.get_valid_access_token", return_value=None)
    def test_post_tweet_unauthenticated(self, mock_token):
        res = self.run_async(main.tool_post_tweet(DummyRequest({"uid": "user1", "text": "Hello"})))
        self.assertIn("Please connect your Twitter account", res.error)

    @patch("main.get_valid_access_token", return_value="valid_token")
    @patch("main.twitter_api_request", return_value={"error": "Rate limit exceeded"})
    def test_post_tweet_api_error(self, mock_req, mock_token):
        res = self.run_async(main.tool_post_tweet(DummyRequest({"uid": "user1", "text": "Hello"})))
        self.assertIn("Rate limit exceeded", res.error)

    @patch("main.get_valid_access_token", return_value="valid_token")
    @patch("main.twitter_api_request", return_value={"data": {"id": "999", "text": "Hello"}})
    def test_post_tweet_success_with_reply_id_clean(self, mock_req, mock_token):
        res = self.run_async(main.tool_post_tweet(DummyRequest({
            "uid": "user1",
            "text": "Hello",
            "reply_to": " #12345 "
        })))
        self.assertIsNone(res.error)
        self.assertIn("**Tweet Posted!**", res.result)
        self.assertIn("ID: `999`", res.result)
        # Check that reply_to was cleaned and passed without '#'
        mock_req.assert_called_once()
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs["json_data"]["reply"]["in_reply_to_tweet_id"], "12345")

    # -------------------------------------------------------------
    # 4. tool_get_timeline tests
    # -------------------------------------------------------------
    def test_get_timeline_missing_uid(self):
        res = self.run_async(main.tool_get_timeline(DummyRequest({})))
        self.assertEqual(res.error, "User ID is required")

    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.get_user_id", return_value=None)
    def test_get_timeline_no_user_id(self, mock_uid, mock_token):
        res = self.run_async(main.tool_get_timeline(DummyRequest({"uid": "u1"})))
        self.assertEqual(res.error, "Could not get your Twitter user ID.")

    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.get_user_id", return_value="tw_u1")
    @patch("main.twitter_api_request", return_value={"data": []})
    def test_get_timeline_empty(self, mock_req, mock_uid, mock_token):
        res = self.run_async(main.tool_get_timeline(DummyRequest({"uid": "u1"})))
        self.assertIsNone(res.error)
        self.assertEqual(res.result, "No tweets in your timeline.")

    # -------------------------------------------------------------
    # 5. tool_get_my_tweets tests
    # -------------------------------------------------------------
    def test_get_my_tweets_missing_uid(self):
        res = self.run_async(main.tool_get_my_tweets(DummyRequest({})))
        self.assertEqual(res.error, "User ID is required")

    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.get_user_id", return_value="tw_u1")
    @patch("main.twitter_api_request", return_value={"data": [{"id": "t1", "text": "My first tweet", "public_metrics": {"like_count": 10}}]})
    def test_get_my_tweets_success(self, mock_req, mock_uid, mock_token):
        res = self.run_async(main.tool_get_my_tweets(DummyRequest({"uid": "u1", "max_results": 20})))
        self.assertIsNone(res.error)
        self.assertIn("Your Tweets (1)", res.result)
        self.assertIn("My first tweet", res.result)

    # -------------------------------------------------------------
    # 6. tool_get_mentions tests
    # -------------------------------------------------------------
    def test_get_mentions_missing_uid(self):
        res = self.run_async(main.tool_get_mentions(DummyRequest({})))
        self.assertEqual(res.error, "User ID is required")

    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.get_user_id", return_value="tw_u1")
    @patch("main.twitter_api_request", return_value={"data": []})
    def test_get_mentions_empty(self, mock_req, mock_uid, mock_token):
        res = self.run_async(main.tool_get_mentions(DummyRequest({"uid": "u1"})))
        self.assertIsNone(res.error)
        self.assertEqual(res.result, "No mentions found.")

    # -------------------------------------------------------------
    # 7. tool_search_tweets tests
    # -------------------------------------------------------------
    def test_search_tweets_missing_fields(self):
        res = self.run_async(main.tool_search_tweets(DummyRequest({})))
        self.assertEqual(res.error, "User ID is required")

        res = self.run_async(main.tool_search_tweets(DummyRequest({"uid": "u1"})))
        self.assertEqual(res.error, "Search query is required")

    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.twitter_api_request", return_value={"data": []})
    def test_search_tweets_empty_results(self, mock_req, mock_token):
        res = self.run_async(main.tool_search_tweets(DummyRequest({"uid": "u1", "query": "python"})))
        self.assertIsNone(res.error)
        self.assertIn("No tweets found for 'python'.", res.result)

    # -------------------------------------------------------------
    # 8. tool_like_tweet & unlike_tweet tests
    # -------------------------------------------------------------
    def test_like_tweet_missing_fields(self):
        res = self.run_async(main.tool_like_tweet(DummyRequest({})))
        self.assertEqual(res.error, "User ID is required")

        res = self.run_async(main.tool_like_tweet(DummyRequest({"uid": "u1"})))
        self.assertEqual(res.error, "Tweet ID is required")

    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.get_user_id", return_value="tw_u1")
    @patch("main.twitter_api_request", return_value={"data": {"liked": True}})
    def test_like_tweet_success_hash_cleaned(self, mock_req, mock_uid, mock_token):
        res = self.run_async(main.tool_like_tweet(DummyRequest({"uid": "u1", "tweet_id": " #12345 "})))
        self.assertIsNone(res.error)
        self.assertIn("Liked!", res.result)
        self.assertIn("12345", res.result)
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs["json_data"]["tweet_id"], "12345")

    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.get_user_id", return_value="tw_u1")
    @patch("main.twitter_api_request", return_value={"data": {"liked": False}})
    def test_unlike_tweet_success(self, mock_req, mock_uid, mock_token):
        res = self.run_async(main.tool_unlike_tweet(DummyRequest({"uid": "u1", "tweet_id": "#12345"})))
        self.assertIsNone(res.error)
        self.assertIn("Unliked!", res.result)

    # -------------------------------------------------------------
    # 9. tool_retweet & delete_tweet tests
    # -------------------------------------------------------------
    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.get_user_id", return_value="tw_u1")
    @patch("main.twitter_api_request", return_value={"data": {"retweeted": True}})
    def test_retweet_success(self, mock_req, mock_uid, mock_token):
        res = self.run_async(main.tool_retweet(DummyRequest({"uid": "u1", "tweet_id": " 555 "})))
        self.assertIsNone(res.error)
        self.assertIn("Retweeted!", res.result)

    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.twitter_api_request", return_value={"data": {"deleted": True}})
    def test_delete_tweet_success(self, mock_req, mock_token):
        res = self.run_async(main.tool_delete_tweet(DummyRequest({"uid": "u1", "tweet_id": "#555"})))
        self.assertIsNone(res.error)
        self.assertIn("Tweet Deleted!", res.result)

    # -------------------------------------------------------------
    # 10. tool_get_user_profile tests (Leading @ stripping, None metrics)
    # -------------------------------------------------------------
    def test_get_user_profile_missing_uid(self):
        res = self.run_async(main.tool_get_user_profile(DummyRequest({})))
        self.assertEqual(res.error, "User ID is required")

    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.twitter_api_request")
    def test_get_user_profile_strips_leading_at(self, mock_req, mock_token):
        mock_req.return_value = {
            "data": {
                "name": "Jack Dorsey",
                "username": "jack",
                "description": "Building stuff",
                "verified": True,
                "public_metrics": {"followers_count": 6500000, "following_count": 4500, "tweet_count": 30000},
                "created_at": "2006-03-21T20:50:14.000Z"
            }
        }
        res = self.run_async(main.tool_get_user_profile(DummyRequest({"uid": "u1", "username": "  @jack  "})))
        self.assertIsNone(res.error)
        self.assertIn("**Jack Dorsey** (Verified)", res.result)
        self.assertIn("@jack", res.result)
        self.assertIn("**Followers:** 6,500,000", res.result)
        self.assertIn("**Joined:** 2006-03-21", res.result)
        # Check endpoint called had username 'jack' without '@'
        args, _ = mock_req.call_args
        self.assertEqual(args[2], "/users/by/username/jack")

    @patch("main.get_valid_access_token", return_value="token")
    @patch("main.twitter_api_request")
    def test_get_user_profile_me_fallback(self, mock_req, mock_token):
        mock_req.return_value = {
            "data": {
                "name": "Self User",
                "username": "self",
                "description": "",
                "created_at": None,
                "public_metrics": None
            }
        }
        # When username is empty or whitespace or '@'
        res = self.run_async(main.tool_get_user_profile(DummyRequest({"uid": "u1", "username": " @ " })))
        self.assertIsNone(res.error)
        self.assertIn("**Self User**", res.result)
        self.assertIn("**Followers:** 0", res.result)
        # Called /users/me
        args, _ = mock_req.call_args
        self.assertEqual(args[2], "/users/me")

    # -------------------------------------------------------------
    # 11. System Health & Pydantic Models
    # -------------------------------------------------------------
    def test_health_endpoint(self):
        res = self.run_async(main.health_check())
        self.assertEqual(res["status"], "healthy")

    def test_models_instantiation(self):
        post_req = models.PostTweetRequest(uid="u1", text="Hello")
        self.assertEqual(post_req.uid, "u1")
        self.assertEqual(post_req.text, "Hello")

        prof_req = models.GetUserProfileRequest(uid="u1", username="@jack")
        self.assertEqual(prof_req.uid, "u1")
        self.assertEqual(prof_req.username, "@jack")


if __name__ == "__main__":
    unittest.main()
