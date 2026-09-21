"""Hermetic error handling and exception sanitization tests for Twitter Chat Tools App.

Verifies that internal exceptions, system paths, network addresses, and raw
tracebacks never leak into chat tool responses or OAuth callback HTML responses.
Runs under standard library unittest without external network dependencies.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


class Framework:
    def __init__(self, content="", status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.kwargs = kwargs

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class ChatToolResponseStub:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error


def make_module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


def load_twitter_module():
    stubs = {
        "requests": make_module(
            "requests",
            post=lambda *args, **kwargs: None,
            get=lambda *args, **kwargs: None,
            delete=lambda *args, **kwargs: None,
            RequestException=OSError,
        ),
        "dotenv": make_module("dotenv", load_dotenv=lambda *args, **kwargs: None),
        "fastapi": make_module(
            "fastapi",
            FastAPI=Framework,
            Request=Framework,
            Query=lambda default=None, **kw: default,
            HTTPException=Exception,
        ),
        "fastapi.responses": make_module(
            "fastapi.responses",
            HTMLResponse=Framework,
            RedirectResponse=Framework,
            JSONResponse=Framework,
        ),
        "db": make_module(
            "db",
            store_twitter_tokens=Mock(),
            get_twitter_tokens=Mock(),
            update_twitter_tokens=Mock(),
            delete_twitter_tokens=Mock(),
            store_oauth_state=Mock(),
            get_oauth_state=Mock(),
            delete_oauth_state=Mock(),
            store_user_setting=Mock(),
            get_user_setting=Mock(),
        ),
        "models": make_module("models", ChatToolResponse=ChatToolResponseStub),
    }

    spec = importlib.util.spec_from_file_location(
        "twitter_main_test", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_twitter_module()


class FakeChatRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class TwitterErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/twitter_key.json: connection reset by 192.168.1.99:443"

    def test_twitter_api_request_sanitizes_exception(self):
        with patch.object(app, "get_valid_access_token", return_value="fake_tok"):
            with patch.object(app.requests, "get", side_effect=RuntimeError(self.sensitive_leak)):
                res = app.twitter_api_request("user123", "GET", "/tweets")
                self.assertEqual(res, {"error": "Twitter API request failed"})
                self.assertNotIn(self.sensitive_leak, str(res))

    def test_twitter_api_request_sanitizes_upstream_body(self):
        with patch.object(app, "get_valid_access_token", return_value="fake_tok"):
            mock_resp = Mock()
            mock_resp.status_code = 500
            mock_resp.text = f"Internal Upstream Error: {self.sensitive_leak}"
            with patch.object(app.requests, "get", return_value=mock_resp):
                res = app.twitter_api_request("user123", "GET", "/tweets")
                self.assertEqual(res, {"error": "Twitter API error (HTTP 500)", "status_code": 500})
                self.assertNotIn(self.sensitive_leak, str(res))

    async def test_tool_post_tweet_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "text": "hello world"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_post_tweet(req)
            self.assertEqual(resp.error, "Failed to post tweet due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)

    async def test_tool_get_timeline_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_timeline(req)
            self.assertEqual(resp.error, "Failed to get timeline due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)

    async def test_tool_get_my_tweets_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_my_tweets(req)
            self.assertEqual(resp.error, "Failed to get tweets due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)

    async def test_tool_get_mentions_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_mentions(req)
            self.assertEqual(resp.error, "Failed to get mentions due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)

    async def test_tool_search_tweets_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "query": "python"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_search_tweets(req)
            self.assertEqual(resp.error, "Failed to search tweets due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)

    async def test_tool_like_tweet_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "tweet_id": "12345"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_like_tweet(req)
            self.assertEqual(resp.error, "Failed to like tweet due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)

    async def test_tool_unlike_tweet_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "tweet_id": "12345"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_unlike_tweet(req)
            self.assertEqual(resp.error, "Failed to unlike tweet due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)

    async def test_tool_retweet_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "tweet_id": "12345"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_retweet(req)
            self.assertEqual(resp.error, "Failed to retweet due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)

    async def test_tool_delete_tweet_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "tweet_id": "12345"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_delete_tweet(req)
            self.assertEqual(resp.error, "Failed to delete tweet due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)

    async def test_tool_get_user_profile_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "username": "jack"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_user_profile(req)
            self.assertEqual(resp.error, "Failed to get profile due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)

    async def test_twitter_callback_sanitizes_exception(self):
        with patch.object(app, "get_oauth_state", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.twitter_callback(code="auth_code", state="user123:state")
            self.assertEqual(resp.status_code, 500)
            self.assertIn("Authentication error", resp.content)
            self.assertNotIn(self.sensitive_leak, resp.content)


if __name__ == "__main__":
    unittest.main()
