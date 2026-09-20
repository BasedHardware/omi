"""Hermetic test suite for HTML escaping in Twitter/X Integration App.

Verifies that OAuth callback error messages and connected usernames
are strictly HTML-escaped using standard library `html.escape(..., quote=True)`
to prevent reflected and stored cross-site scripting (XSS).

No network, credentials, or third-party packages required.

Run: python3 test_twitter_html_escaping.py
"""

import asyncio
import html
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch, MagicMock

MAIN_PATH = Path(__file__).resolve().parent / "main.py"


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class HTMLResponse:
        def __init__(self, content="", status_code=200):
            self.content = content
            self.status_code = status_code

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
        "fastapi.responses": module("fastapi.responses", HTMLResponse=HTMLResponse, RedirectResponse=str, JSONResponse=dict),
        "dotenv": module("dotenv", load_dotenv=lambda *a, **k: None),
        "requests": module("requests", post=lambda *a, **k: None, get=lambda *a, **k: None),
        "db": db,
        "models": module("models", ChatToolResponse=ChatToolResponse),
    }
    spec = importlib.util.spec_from_file_location("twitter_chat_tools_under_test", MAIN_PATH)
    loaded = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(loaded)
    return loaded


app = load_app()


class TestTwitterHtmlEscaping(unittest.TestCase):
    def setUp(self):
        # Silence Railway log calls during test runs
        patcher = patch.object(app, "log", lambda msg: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    # -------------------------------------------------------------------------
    # 1. OAuth Callback Error Reflected XSS Tests (Line 1091)
    # -------------------------------------------------------------------------

    def test_benign_error_renders(self):
        """A normal error code should render cleanly in the error box."""
        res = asyncio.run(app.twitter_callback(error="access_denied"))
        self.assertEqual(res.status_code, 400)
        self.assertIn("<p>access_denied</p>", res.content)

    def test_breakout_not_reflected_raw(self):
        """Malicious script tag in error parameter must not appear unescaped in HTML."""
        payload = '"><script>alert(1)</script>'
        res = asyncio.run(app.twitter_callback(error=payload))
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("<script>", res.content)
        self.assertNotIn(payload, res.content)
        self.assertIn(html.escape(payload, quote=True), res.content)

    def test_empty_error_safe(self):
        """Empty or falsy error string does not crash and renders safely."""
        res = asyncio.run(app.twitter_callback(error=""))
        # When error is empty string, function proceeds past `if error:`
        self.assertIsNotNone(res)

    def test_script_tag_absent(self):
        """Various XSS payloads must never produce raw HTML tags in error response."""
        payloads = [
            "<svg onload=alert(1)>",
            "<script src='evil.js'></script>",
            "<img src=x onerror=alert('xss')>",
            "';alert(String.fromCharCode(88,83,83))//",
        ]
        for p in payloads:
            with self.subTest(payload=p):
                res = asyncio.run(app.twitter_callback(error=p))
                self.assertNotIn("<script", res.content)
                self.assertNotIn("<svg", res.content)
                self.assertNotIn("<img", res.content)
                self.assertIn(html.escape(p, quote=True), res.content)

    def test_escaped_form_present(self):
        """Verify that HTML entity escaping correctly converts & < > \" and '."""
        complex_payload = '<div class="test" data-val=\'xyz\'>&"\'</div>'
        res = asyncio.run(app.twitter_callback(error=complex_payload))
        escaped = html.escape(complex_payload, quote=True)
        self.assertIn(escaped, res.content)
        self.assertNotIn(complex_payload, res.content)

    def test_quote_breaker_escaped(self):
        """Double and single quotes used to break out of attributes must be escaped."""
        payload = '" onload="alert(1)" \''
        res = asyncio.run(app.twitter_callback(error=payload))
        self.assertNotIn('" onload="', res.content)
        self.assertIn("&quot; onload=&quot;", res.content)

    # -------------------------------------------------------------------------
    # 2. Connected Page Username Stored/Reflected XSS Tests (Line 1027)
    # -------------------------------------------------------------------------

    def test_benign_username_renders(self):
        """Standard alphanumeric username renders normally as @handle."""
        with patch.object(app, "get_twitter_tokens", return_value={"username": "alice_dev"}):
            res = asyncio.run(app.root(uid="u123"))
            self.assertIn("<p>Connected as @alice_dev</p>", res.content)

    def test_malicious_username_not_raw(self):
        """Malicious username payload must be escaped and not rendered as raw HTML."""
        malicious_username = '"><script>alert("stored_xss")</script>'
        with patch.object(app, "get_twitter_tokens", return_value={"username": malicious_username}):
            res = asyncio.run(app.root(uid="u123"))
            self.assertNotIn("<script>", res.content)
            self.assertNotIn(malicious_username, res.content)
            self.assertIn(html.escape(malicious_username, quote=True), res.content)

    def test_none_username_handled_safely(self):
        """When tokens dict has None or empty username, it handles it safely without crashing."""
        with patch.object(app, "get_twitter_tokens", return_value={"username": None}):
            res = asyncio.run(app.root(uid="u123"))
            self.assertIn("<p>Connected as @</p>", res.content)

    # -------------------------------------------------------------------------
    # 3. OAuth Success Page Username Stored/Reflected XSS Tests (Line 1198)
    # -------------------------------------------------------------------------

    def test_success_page_benign_username(self):
        """Success page renders benign username correctly."""
        with patch.object(app, "get_oauth_state", return_value="u1:state123"), \
             patch.object(app, "get_user_setting", return_value="code_verifier_123"), \
             patch.object(app, "delete_oauth_state"), \
             patch.object(app, "store_twitter_tokens"):

            fake_token_resp = MagicMock()
            fake_token_resp.status_code = 200
            fake_token_resp.json.return_value = {"access_token": "acc123", "expires_in": 3600}

            fake_user_resp = MagicMock()
            fake_user_resp.status_code = 200
            fake_user_resp.json.return_value = {"data": {"username": "bob_contributor", "id": "12345"}}

            with patch.object(app.requests, "post", return_value=fake_token_resp), \
                 patch.object(app.requests, "get", return_value=fake_user_resp):
                res = asyncio.run(app.twitter_callback(code="valid_code", state="u1:state123"))
                self.assertIn("Your Twitter account @bob_contributor is now linked to Omi", res.content)

    def test_success_page_escapes_malicious_username(self):
        """Success page must escape malicious username received from Twitter API."""
        malicious = "<b>hacked</b><script>alert(1)</script>"
        with patch.object(app, "get_oauth_state", return_value="u1:state123"), \
             patch.object(app, "get_user_setting", return_value="code_verifier_123"), \
             patch.object(app, "delete_oauth_state"), \
             patch.object(app, "store_twitter_tokens"):

            fake_token_resp = MagicMock()
            fake_token_resp.status_code = 200
            fake_token_resp.json.return_value = {"access_token": "acc123", "expires_in": 3600}

            fake_user_resp = MagicMock()
            fake_user_resp.status_code = 200
            fake_user_resp.json.return_value = {"data": {"username": malicious, "id": "12345"}}

            with patch.object(app.requests, "post", return_value=fake_token_resp), \
                 patch.object(app.requests, "get", return_value=fake_user_resp):
                res = asyncio.run(app.twitter_callback(code="valid_code", state="u1:state123"))
                self.assertNotIn("<b>hacked</b>", res.content)
                self.assertNotIn("<script>", res.content)
                self.assertIn(html.escape(malicious, quote=True), res.content)


if __name__ == "__main__":
    unittest.main()
