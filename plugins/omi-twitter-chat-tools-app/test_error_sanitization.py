"""Hermetic tests ensuring error sanitization across twitter-chat-tools-app.

Tests verify that internal exceptions and tracebacks are never leaked to users
or API callers.
"""

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

APP_ROOT = Path(__file__).resolve().parent


class _Captured:
    def __init__(self, content=None, status_code=200, url=None, **kwargs):
        self.body = content if content is not None else (url or "")
        self.status_code = status_code
        self.url = url


def _load_main():
    saved = {
        name: sys.modules.get(name)
        for name in ("requests", "dotenv", "fastapi", "fastapi.responses", "db", "models", "main")
    }

    requests_mod = types.ModuleType("requests")
    requests_mod.get = MagicMock()
    requests_mod.post = MagicMock()
    requests_mod.delete = MagicMock()
    sys.modules["requests"] = requests_mod

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    fastapi = types.ModuleType("fastapi")

    class _App:
        def __init__(self, *a, **k):
            pass

        def _decorator(self, *a, **k):
            def wrap(fn):
                return fn
            return wrap

        get = post = put = delete = on_event = middleware = _decorator

    fastapi.FastAPI = _App
    fastapi.Request = object
    fastapi.Query = lambda default=None, **k: default
    fastapi.HTTPException = Exception
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = _Captured
    responses.RedirectResponse = _Captured
    responses.JSONResponse = _Captured
    sys.modules["fastapi.responses"] = responses

    db = types.ModuleType("db")
    db.store_twitter_tokens = MagicMock()
    db.get_twitter_tokens = MagicMock()
    db.update_twitter_tokens = MagicMock()
    db.delete_twitter_tokens = MagicMock()
    db.store_oauth_state = MagicMock()
    db.get_oauth_state = MagicMock()
    db.delete_oauth_state = MagicMock()
    db.store_user_setting = MagicMock()
    db.get_user_setting = MagicMock()
    sys.modules["db"] = db

    models = types.ModuleType("models")

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    models.ChatToolResponse = ChatToolResponse
    sys.modules["models"] = models

    main_path = APP_ROOT / "main.py"
    with open(main_path, "r", encoding="utf-8") as f:
        code = compile(f.read(), str(main_path), "exec")

    mod = types.ModuleType("main")
    mod.__file__ = str(main_path)
    sys.modules["main"] = mod
    exec(code, mod.__dict__)

    return mod, saved


class TestTwitterErrorSanitization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_mod, cls.saved_modules = _load_main()

    @classmethod
    def tearDownClass(cls):
        for name, mod in cls.saved_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def test_twitter_api_request_sanitizes_exception(self):
        with patch.object(self.main_mod, "get_valid_access_token", return_value="test_token"), \
             patch.object(self.main_mod.requests, "get", side_effect=Exception("Sensitive twitter secret: token_xyz")):
            result = self.main_mod.twitter_api_request("test_uid", "GET", "/test")
            self.assertEqual(result, {"error": "API request failed"})

    def test_tool_post_tweet_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal tweet failure"))
        result = asyncio.run(self.main_mod.tool_post_tweet(req))
        self.assertEqual(result.error, "Failed to post tweet")
        self.assertNotIn("Internal tweet failure", result.error)

    def test_tool_get_timeline_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal timeline failure"))
        result = asyncio.run(self.main_mod.tool_get_timeline(req))
        self.assertEqual(result.error, "Failed to get timeline")
        self.assertNotIn("Internal timeline failure", result.error)

    def test_tool_get_my_tweets_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal tweets failure"))
        result = asyncio.run(self.main_mod.tool_get_my_tweets(req))
        self.assertEqual(result.error, "Failed to get tweets")
        self.assertNotIn("Internal tweets failure", result.error)

    def test_tool_get_mentions_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal mentions failure"))
        result = asyncio.run(self.main_mod.tool_get_mentions(req))
        self.assertEqual(result.error, "Failed to get mentions")
        self.assertNotIn("Internal mentions failure", result.error)

    def test_tool_search_tweets_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal search failure"))
        result = asyncio.run(self.main_mod.tool_search_tweets(req))
        self.assertEqual(result.error, "Search failed")
        self.assertNotIn("Internal search failure", result.error)

    def test_tool_like_tweet_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal like failure"))
        result = asyncio.run(self.main_mod.tool_like_tweet(req))
        self.assertEqual(result.error, "Failed to like tweet")
        self.assertNotIn("Internal like failure", result.error)

    def test_tool_unlike_tweet_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal unlike failure"))
        result = asyncio.run(self.main_mod.tool_unlike_tweet(req))
        self.assertEqual(result.error, "Failed to unlike tweet")
        self.assertNotIn("Internal unlike failure", result.error)

    def test_tool_retweet_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal retweet failure"))
        result = asyncio.run(self.main_mod.tool_retweet(req))
        self.assertEqual(result.error, "Failed to retweet")
        self.assertNotIn("Internal retweet failure", result.error)

    def test_tool_delete_tweet_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal delete failure"))
        result = asyncio.run(self.main_mod.tool_delete_tweet(req))
        self.assertEqual(result.error, "Failed to delete tweet")
        self.assertNotIn("Internal delete failure", result.error)

    def test_tool_get_user_profile_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal profile failure"))
        result = asyncio.run(self.main_mod.tool_get_user_profile(req))
        self.assertEqual(result.error, "Failed to get profile")
        self.assertNotIn("Internal profile failure", result.error)

    def test_twitter_callback_sanitizes_exception(self):
        with patch.object(self.main_mod, "get_oauth_state", return_value="auth_code:test_uid:verifier"), \
             patch.object(self.main_mod.requests, "post", side_effect=Exception("Sensitive OAuth secret leaked")):
            resp = asyncio.run(self.main_mod.twitter_callback(code="auth_code", state="auth_code:test_uid:verifier"))
            self.assertEqual(resp.status_code, 500)
            self.assertIn("Authentication error: Failed to complete authentication", resp.body)
            self.assertNotIn("Sensitive OAuth secret leaked", resp.body)


if __name__ == "__main__":
    unittest.main()
