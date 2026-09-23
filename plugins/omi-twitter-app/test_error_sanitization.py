"""Hermetic tests ensuring error sanitization across omi-twitter-app.

Tests verify that internal exceptions, system details, and unescaped values
are never leaked in HTTP responses or exceptions.
"""

import asyncio
import html
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

APP_ROOT = Path(__file__).resolve().parent


class _Captured:
    def __init__(self, content=None, status_code=200, url=None, **kwargs):
        self.body = content if content is not None else (url or "")
        self.status_code = status_code
        self.url = url


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _load_main():
    saved = {
        name: sys.modules.get(name)
        for name in (
            "requests",
            "dotenv",
            "fastapi",
            "fastapi.responses",
            "tweepy",
            "simple_storage",
            "twitter_client",
            "tweet_detector",
            "main_simple",
        )
    }

    requests_mod = types.ModuleType("requests")
    requests_mod.post = MagicMock()
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
    fastapi.HTTPException = HTTPException
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = _Captured
    responses.RedirectResponse = _Captured
    responses.JSONResponse = _Captured
    sys.modules["fastapi.responses"] = responses

    tweepy = types.ModuleType("tweepy")
    tweepy.TweepyException = Exception
    tweepy.Client = MagicMock()
    tweepy.OAuth2UserHandler = MagicMock()
    sys.modules["tweepy"] = tweepy

    storage = types.ModuleType("simple_storage")
    storage.SimpleUserStorage = MagicMock()
    storage.SimpleSessionStorage = MagicMock()
    storage.OAuthStateStorage = MagicMock()
    storage.users = {}
    storage.save_users = MagicMock()
    sys.modules["simple_storage"] = storage

    tclient = types.ModuleType("twitter_client")
    client_inst = MagicMock()
    tclient.TwitterClient = MagicMock(return_value=client_inst)
    sys.modules["twitter_client"] = tclient

    tdetector = types.ModuleType("tweet_detector")
    tdetector.TweetDetector = MagicMock()
    sys.modules["tweet_detector"] = tdetector

    main_path = APP_ROOT / "main_simple.py"
    with open(main_path, "r", encoding="utf-8") as f:
        code = compile(f.read(), str(main_path), "exec")

    mod = types.ModuleType("main_simple")
    mod.__file__ = str(main_path)
    sys.modules["main_simple"] = mod
    exec(code, mod.__dict__)

    return mod, client_inst, saved


class TestTwitterAppErrorSanitization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_mod, cls.client_inst, cls.saved_modules = _load_main()

    @classmethod
    def tearDownClass(cls):
        for name, mod in cls.saved_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def test_auth_start_sanitizes_exception(self):
        with patch.object(
            self.main_mod.twitter_client,
            "get_authorization_url",
            side_effect=RuntimeError("Sensitive AWS key leaked: AKIAIOSFODNN7EXAMPLE"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(self.main_mod.auth_start(uid="test_uid"))
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "OAuth initialization failed")
            self.assertNotIn("AKIAIOSFODNN7EXAMPLE", ctx.exception.detail)

    def test_webhook_sanitizes_json_parsing_exception(self):
        req = MagicMock()
        req.json = AsyncMock(side_effect=ValueError("Unexpected token at /etc/shadow:1"))
        with patch.object(
            self.main_mod.SimpleUserStorage, "get_user", return_value={"access_token": "token"}
        ), patch.object(self.main_mod.SimpleUserStorage, "is_token_expired", return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(self.main_mod.webhook(req, uid="test_uid"))
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertEqual(ctx.exception.detail, "Invalid JSON payload")
            self.assertNotIn("/etc/shadow", ctx.exception.detail)

    def test_auth_callback_escapes_error_uid(self):
        breakout = '"><script>alert(1)</script>'
        with patch.object(self.main_mod.OAuthStateStorage, "get_uid_by_state", side_effect=Exception("Database down")):
            req = MagicMock()
            resp = asyncio.run(self.main_mod.auth_callback(req, state=breakout, code="test_code"))
            self.assertEqual(resp.status_code, 500)
            self.assertNotIn('<script>alert(1)</script>', resp.body)
            self.assertIn('%22%3E%3Cscript%3Ealert%281%29%3C%2Fscript%3E', resp.body)


if __name__ == "__main__":
    unittest.main()
