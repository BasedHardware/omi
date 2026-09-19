"""Hermetic tests: Twitter chat tools plugin OAuth callback and UI templates must escape HTML and URL-encode query params.

Regression testing for Issue #14881:
- GET /auth/twitter/callback?error=... must HTML-escape the error query parameter.
- GET /?uid=... must URL-encode uid in authorization and disconnect links, and HTML-escape username.
- GET /auth/twitter/callback success page must HTML-escape username and URL-encode uid.
- GET /disconnect?uid=... must URL-encode uid in redirect URL.

Hermetic test requires no network access, credentials, or live Twitter API.
"""

import asyncio
import html
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

MAIN_PATH = Path(__file__).resolve().parent / "main.py"
BREAKOUT = '"><script>alert(1)</script>'
QUERY_BREAKER = 'a&b#c?d="1"'


class _CapturedResponse:
    def __init__(self, content=None, status_code=200, url=None, **kwargs):
        self.body = content if content is not None else (url or "")
        self.status_code = status_code
        self.url = url


def load_twitter_app():
    saved = {
        name: sys.modules.get(name)
        for name in ("requests", "dotenv", "fastapi", "fastapi.responses", "db", "models")
    }

    requests_mod = types.ModuleType("requests")
    requests_mod.post = lambda *a, **k: None
    requests_mod.get = lambda *a, **k: None
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
    fastapi.Query = lambda default=None, **k: default
    fastapi.Request = object
    fastapi.HTTPException = type("HTTPException", (Exception,), {})
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = _CapturedResponse
    responses.RedirectResponse = _CapturedResponse
    responses.JSONResponse = _CapturedResponse
    fastapi.responses = responses
    sys.modules["fastapi.responses"] = responses

    db = types.ModuleType("db")
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
        setattr(db, name, lambda *a, **k: None)
    sys.modules["db"] = db

    models = types.ModuleType("models")
    models.ChatToolResponse = type("ChatToolResponse", (), {"__init__": lambda self, **k: None})
    sys.modules["models"] = models

    spec = importlib.util.spec_from_file_location("twitter_chat_tools_under_test", MAIN_PATH)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)

    for name, original in saved.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original

    return loaded


APP = load_twitter_app()


def _body(coro):
    result = asyncio.run(coro)
    return getattr(result, "body", result)


class TwitterHtmlEscapingTest(unittest.TestCase):
    def test_error_param_is_escaped_in_callback(self):
        result = _body(APP.twitter_callback(code=None, state=None, error=BREAKOUT))
        self.assertNotIn(BREAKOUT, result)
        self.assertNotIn("<script>alert(1)</script>", result)
        self.assertIn(html.escape(BREAKOUT), result)

    def test_normal_error_message_rendered(self):
        result = _body(APP.twitter_callback(code=None, state=None, error="access_denied"))
        self.assertIn("access_denied", result)

    def test_disconnected_root_quotes_uid(self):
        with patch.object(APP, "get_twitter_tokens", return_value=None):
            result = _body(APP.root(uid=QUERY_BREAKER))
            self.assertNotIn(QUERY_BREAKER, result)
            self.assertNotIn('uid=a&b#c?d="1"', result)
            self.assertIn("uid=a%26b%23c%3Fd%3D%221%22", result)

    def test_connected_root_escapes_username_and_quotes_uid(self):
        fake_tokens = {"username": BREAKOUT, "access_token": "token123"}
        with patch.object(APP, "get_twitter_tokens", return_value=fake_tokens):
            result = _body(APP.root(uid=QUERY_BREAKER))
            self.assertNotIn(BREAKOUT, result)
            self.assertNotIn("<script>alert(1)</script>", result)
            self.assertIn(html.escape(BREAKOUT, quote=True), result)
            self.assertIn("/disconnect?uid=a%26b%23c%3Fd%3D%221%22", result)

    def test_disconnect_endpoint_quotes_uid(self):
        with patch.object(APP, "delete_twitter_tokens") as mock_delete:
            resp = asyncio.run(APP.disconnect(uid=QUERY_BREAKER))
            mock_delete.assert_called_once_with(QUERY_BREAKER)
            redirect_url = getattr(resp, "url", getattr(resp, "body", ""))
            self.assertEqual(redirect_url, "/?uid=a%26b%23c%3Fd%3D%221%22")

    def test_callback_success_page_escapes_username_and_quotes_uid(self):
        uid = "user123&action=hack"
        state = f"{uid}:randomstate"
        code = "oauth_code"

        with patch.object(APP, "get_oauth_state", return_value=state), \
             patch.object(APP, "get_user_setting", return_value="verifier123"), \
             patch.object(APP, "delete_oauth_state"), \
             patch.object(APP, "store_twitter_tokens"):

            mock_token_resp = MagicMock()
            mock_token_resp.status_code = 200
            mock_token_resp.json.return_value = {
                "access_token": "mock_access_token",
                "refresh_token": "mock_refresh_token",
                "expires_in": 7200,
            }

            mock_user_resp = MagicMock()
            mock_user_resp.status_code = 200
            mock_user_resp.json.return_value = {
                "data": {
                    "id": "12345",
                    "username": BREAKOUT,
                }
            }

            with patch.object(APP.requests, "post", return_value=mock_token_resp), \
                 patch.object(APP.requests, "get", return_value=mock_user_resp):

                result = _body(APP.twitter_callback(code=code, state=state, error=None))
                self.assertNotIn(BREAKOUT, result)
                self.assertNotIn("<script>alert(1)</script>", result)
                self.assertIn(html.escape(BREAKOUT, quote=True), result)
                self.assertIn("/?uid=user123%26action%3Dhack", result)


if __name__ == "__main__":
    unittest.main()
