"""Hermetic regression tests: omi-twitter-chat-tools-app must not reflect
``error`` or ``username`` values into HTML without escaping.

Tests exercise the production handler routes directly in main.py via
standard library unittest and hermetic stubs, ensuring templates cannot drift.

Run: python3 plugins/omi-twitter-chat-tools-app/test_twitter_html_escaping.py
"""

import asyncio
import html
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

BREAKOUT = '"><script>alert(1)</script>'
QUOTE_BREAKER = '"\'&<>'
BENIGN_ERROR = "access_denied"
BENIGN_USERNAME = "elonmusk"
MALICIOUS_USERNAME = '<script>alert("xss_via_username")</script>'


def load_twitter_app():
    """Load plugins/omi-twitter-chat-tools-app/main.py hermetically."""
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    def Query(default=None, **kwargs):
        return default

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _Response:
        def __init__(self, content="", status_code=200, **kwargs):
            self.content = content
            self.status_code = status_code
            self.kwargs = kwargs

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    requests = ModuleType("requests")
    requests.get = lambda *args, **kwargs: None
    requests.post = lambda *args, **kwargs: None

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = object
    fastapi.Query = Query
    fastapi.HTTPException = HTTPException

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = _Response
    responses.RedirectResponse = _Response
    responses.JSONResponse = _Response

    db = ModuleType("db")
    for name in (
        "store_twitter_tokens",
        "update_twitter_tokens",
        "delete_twitter_tokens",
        "store_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
    ):
        setattr(db, name, lambda *args, **kwargs: None)
    for name in ("get_twitter_tokens", "get_oauth_state", "get_user_setting"):
        setattr(db, name, lambda *args, **kwargs: None)

    models = ModuleType("models")
    models.ChatToolResponse = ChatToolResponse

    main_py_path = Path(__file__).with_name("main.py")
    spec = importlib.util.spec_from_file_location("twitter_main_app", main_py_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "requests": requests,
            "dotenv": dotenv,
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "db": db,
            "models": models,
        },
    ):
        spec.loader.exec_module(module)
    return module


class TestTwitterHtmlEscaping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_twitter_app()

    def test_error_callback_escapes_script_breakout(self):
        """Unauthenticated GET /auth/twitter/callback?error=<payload> must escape script tags."""
        resp = asyncio.run(self.app.twitter_callback(error=BREAKOUT))
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("<script>", resp.content)
        self.assertIn(html.escape(BREAKOUT, quote=True), resp.content)

    def test_error_callback_escapes_html_entities(self):
        """Quote characters and angle brackets must be encoded as entities."""
        resp = asyncio.run(self.app.twitter_callback(error=QUOTE_BREAKER))
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("'<", resp.content)
        self.assertIn("&quot;&#x27;&amp;&lt;&gt;", resp.content)

    def test_error_callback_benign_value_passes_through(self):
        """Standard OAuth error codes pass through undamaged."""
        resp = asyncio.run(self.app.twitter_callback(error=BENIGN_ERROR))
        self.assertEqual(resp.status_code, 400)
        self.assertIn(BENIGN_ERROR, resp.content)

    def test_error_callback_none_does_not_crash(self):
        """When error is None, callback proceeds past error branch without TypeError."""
        resp = asyncio.run(self.app.twitter_callback(code=None, state=None, error=None))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Missing authorization code or state", resp.content)

    def test_root_page_escapes_stored_username_xss(self):
        """GET / (connected page) must escape malicious username from tokens."""
        with patch.object(self.app, "get_twitter_tokens", return_value={"username": MALICIOUS_USERNAME, "access_token": "tok"}):
            resp = asyncio.run(self.app.root(uid="user123"))
            self.assertNotIn("<script>", resp.content)
            self.assertIn(html.escape(MALICIOUS_USERNAME, quote=True), resp.content)

    def test_root_page_handles_benign_username(self):
        """GET / renders normal alphanumeric handle."""
        with patch.object(self.app, "get_twitter_tokens", return_value={"username": BENIGN_USERNAME, "access_token": "tok"}):
            resp = asyncio.run(self.app.root(uid="user123"))
            self.assertIn(f"@{BENIGN_USERNAME}", resp.content)

    def test_root_page_handles_none_username_safely(self):
        """GET / handles tokens with missing or None username without crashing."""
        with patch.object(self.app, "get_twitter_tokens", return_value={"username": None, "access_token": "tok"}):
            resp = asyncio.run(self.app.root(uid="user123"))
            self.assertNotIn("<script>", resp.content)
            self.assertIn("Twitter Connected", resp.content)

    def test_success_callback_escapes_twitter_api_username(self):
        """GET /auth/twitter/callback success branch escapes username from Twitter user profile."""
        fake_token_resp = Mock(status_code=200)
        fake_token_resp.json.return_value = {"access_token": "at", "refresh_token": "rt", "expires_in": 7200}
        fake_user_resp = Mock(status_code=200)
        fake_user_resp.json.return_value = {"data": {"id": "12345", "username": MALICIOUS_USERNAME}}

        def mock_post(*args, **kwargs):
            return fake_token_resp

        def mock_get(*args, **kwargs):
            return fake_user_resp

        with patch.object(self.app.requests, "post", side_effect=mock_post), \
             patch.object(self.app.requests, "get", side_effect=mock_get), \
             patch.object(self.app, "get_oauth_state", return_value="user123:valid_token"), \
             patch.object(self.app, "get_user_setting", return_value="test_verifier"), \
             patch.object(self.app, "store_twitter_tokens"):
            resp = asyncio.run(self.app.twitter_callback(code="valid_code", state="user123:valid_token", error=None))
            self.assertNotIn("<script>", resp.content)
            self.assertIn(html.escape(MALICIOUS_USERNAME, quote=True), resp.content)


if __name__ == "__main__":
    unittest.main()
