"""Hermetic regression: the Twitter app must not reflect client-controlled
strings into HTML without escaping.

Three sinks in main.py interpolated client-controlled text straight into the
response body:

1. GET /auth/twitter/callback?error=... is unauthenticated and renders
   <p>{error}</p>.  Opening

       /auth/twitter/callback?error=%22%3E%3Cscript%3Ealert(1)%3C%2Fscript%3E

   returned markup whose paragraph contained a live script tag, so the script
   ran on the plugin's origin (reflected XSS, no preconditions - the
   "if error:" branch is the first thing the handler does).

2. GET / (home page, connected state) renders <p>Connected as @{username}</p>.

3. GET /auth/twitter/callback (success state) renders
   <p>Your Twitter account @{username} is now linked to Omi</p>.

username is persisted from the X API response and rendered on later requests,
so a malicious or malformed handle is a stored sink.

This suite imports the production module with framework-only stubs and drives
the real handlers, so it fails against main and passes on the fix.  No network,
credentials, or third-party packages required.

Run: python3 plugins/omi-twitter-chat-tools-app/test_html_escaping.py
"""

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

MAIN_PATH = Path(__file__).resolve().parent / "main.py"

BREAKOUT = '"' + ">" + "<script>alert(1)</script>"
QUOTE_BREAKER = '"' + "'" + "&<>"
BENIGN_USER = "jack"
BENIGN_ERROR = "access_denied"
SCRIPT_TAG = "<script>alert(1)</script>"


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

    class Response:
        """Minimal stand-in: keeps the rendered body reachable for assertions."""

        def __init__(self, content=None, **kwargs):
            self.content = content if content is not None else ""

        def __str__(self):
            return self.content

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
        "fastapi": module("fastapi", FastAPI=FastAPI, Request=object,
                          Query=lambda *a, **k: None, HTTPException=Exception),
        "fastapi.responses": module("fastapi.responses", HTMLResponse=Response,
                                    RedirectResponse=Response, JSONResponse=dict),
        "dotenv": module("dotenv", load_dotenv=lambda *a, **k: None),
        "requests": module("requests"),
        "db": db,
        "models": module("models", ChatToolResponse=ChatToolResponse),
    }
    spec = importlib.util.spec_from_file_location("twitter_chat_tools_escaping", MAIN_PATH)
    loaded = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(loaded)
    return loaded


app = load_app()


def drive(coro):
    """Run an async route handler to completion and return its rendered string."""
    return asyncio.run(coro)


class CallbackErrorEscaped(unittest.TestCase):
    """error from the query string must be escaped before it lands in the page."""

    def render(self, error):
        return str(drive(app.twitter_callback(code=None, state=None, error=error)))

    def test_breakout_payload_not_reflected_raw(self):
        self.assertNotIn(BREAKOUT, self.render(BREAKOUT))

    def test_no_live_script_tag(self):
        self.assertNotIn(SCRIPT_TAG, self.render(BREAKOUT))

    def test_benign_error_still_renders(self):
        self.assertIn(BENIGN_ERROR, self.render(BENIGN_ERROR))

    def test_none_error_does_not_crash(self):
        """The escape call is guarded so a missing parameter is still safe."""
        self.assertIn("Authorization Failed", self.render(None))


class UsernameSinkEscaped(unittest.TestCase):
    """username is persisted then re-rendered, so it must be escaped."""

    def render_connected(self, username):
        patcher = patch.object(app, "get_twitter_tokens",
                               lambda uid: {"username": username, "access_token": "t"})
        patcher.start()
        self.addCleanup(patcher.stop)
        return str(drive(app.root(uid="user-1")))

    def test_connected_page_escapes_username(self):
        page = self.render_connected(BREAKOUT)
        self.assertNotIn(BREAKOUT, page)
        self.assertNotIn(SCRIPT_TAG, page)

    def test_connected_page_keeps_benign_username(self):
        self.assertIn("@" + BENIGN_USER, self.render_connected(BENIGN_USER))

    def test_quote_breaker_entities_present(self):
        page = self.render_connected(QUOTE_BREAKER)
        para = page[page.index("Connected as"):]
        para = para[: para.index("</p>")]
        for raw in ('"', "'", "<", ">"):
            self.assertNotIn(raw, para,
                             "raw character must not appear in the username paragraph")

    def test_none_username_does_not_crash(self):
        self.assertIn("Connected as", self.render_connected(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
