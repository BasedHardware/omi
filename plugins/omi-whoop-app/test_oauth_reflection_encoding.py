"""Hermetic, stdlib-only regression tests for reflected XSS / parameter
injection in the Whoop Omi plugin (issue #14890).

The plugin builds its HTML with f-strings, so every attacker- or
upstream-controlled value has to be encoded for the context it lands in:

* ``uid`` is percent-encoded (``quote(uid, safe='')``) before it is placed in a
  query string, and the resulting URL is HTML-escaped before it lands in an
  ``href`` attribute.  Without it, ``/?uid="><script>alert(1)</script>`` breaks
  out of the attribute and executes script on the plugin origin.
* the OAuth ``error`` query parameter and the OAuth exception message are
  reflected into the page body and must be HTML-escaped: ``/auth/whoop/callback``
  is unauthenticated, so any crafted link is instant reflected XSS.

The production module is imported with framework-only stubs (the same seam used
by ``test_main.py``) and the storage/network functions are patched, so the suite
needs no FastAPI runtime, no Redis, no network and no HTTP server — only the
Python standard library.

Run: python3 plugins/omi-whoop-app/test_oauth_reflection_encoding.py
"""

import asyncio
import html
import importlib.util
import re
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from urllib.parse import quote


def load_app():
    """Import ``main.py`` with third-party imports replaced by stubs."""

    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class _QuerySentinel:
        """Stands in for FastAPI's ``Query`` default when a handler is called
        directly instead of through the HTTP layer."""

        def __init__(self, default=None):
            self.default = default

    def Query(default=None, **kwargs):
        return _QuerySentinel(default)

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class HTMLResponse:
        def __init__(self, content="", status_code=200, **kwargs):
            self.body = (content or "").encode("utf-8")
            self.status_code = status_code
            self.headers = {}

    class RedirectResponse:
        def __init__(self, url="", status_code=307, **kwargs):
            self.body = b""
            self.status_code = status_code
            self.headers = {"location": url}

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
    responses.HTMLResponse = HTMLResponse
    responses.RedirectResponse = RedirectResponse
    responses.JSONResponse = lambda *args, **kwargs: None

    db = ModuleType("db")
    for name in (
        "store_whoop_tokens",
        "update_whoop_tokens",
        "delete_whoop_tokens",
        "store_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
    ):
        setattr(db, name, lambda *args, **kwargs: None)
    for name in ("get_whoop_tokens", "get_uid_from_oauth_state", "get_user_setting"):
        setattr(db, name, lambda *args, **kwargs: None)

    models = ModuleType("models")
    models.ChatToolResponse = ChatToolResponse

    spec = importlib.util.spec_from_file_location(
        "whoop_app", Path(__file__).with_name("main.py")
    )
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


app = load_app()

# ``"><script>alert(1)</script>`` — attribute breakout plus a script tag.
PAYLOAD = '"><script>alert(1)</script>'
QUOTE_BREAKER = '"\'&<>'


def _body(response) -> str:
    body = getattr(response, "body", None)
    if body is None:
        return str(response)
    return body.decode("utf-8") if isinstance(body, bytes) else str(body)


def _hrefs(page: str):
    return re.findall(r'href="([^"]*)"', page)


class FakeUpstreamResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {
            "access_token": "tok",
            "refresh_token": "refresh",
            "expires_in": 3600,
        }

    def json(self):
        return self._json_data


class WhoopReflectionEncodingTest(unittest.IsolatedAsyncioTestCase):
    """Every reflected value must be encoded for its HTML context."""

    # ── root() / connect page ────────────────────────────────────────────
    async def test_connect_href_quotes_uid(self):
        """uid in the connect link must be percent-encoded and attribute-safe."""
        with patch.object(app, "get_whoop_tokens", lambda uid: None):
            page = _body(await app.root(uid=PAYLOAD))

        self.assertNotIn(PAYLOAD, page, "raw uid must never be reflected into HTML")
        self.assertNotIn("<script>", page)

        expected = "/auth/whoop?uid=" + quote(PAYLOAD, safe="")
        self.assertIn(expected, _hrefs(page))
        self.assertIn(html.escape(expected, quote=True), page)

    async def test_connect_href_leaves_benign_uid_intact(self):
        """A benign uid passes through unchanged (no double encoding)."""
        with patch.object(app, "get_whoop_tokens", lambda uid: None):
            page = _body(await app.root(uid="abc123"))

        self.assertIn("/auth/whoop?uid=abc123", _hrefs(page))

    # ── root() / connected page ──────────────────────────────────────────
    async def test_disconnect_href_quotes_uid(self):
        """The disconnect link on the connected page must quote + escape uid."""
        with patch.object(app, "get_whoop_tokens", lambda uid: {"access_token": "tok"}):
            page = _body(await app.root(uid=PAYLOAD))

        self.assertNotIn(PAYLOAD, page)
        self.assertNotIn("<script>", page)
        self.assertIn("/disconnect?uid=" + quote(PAYLOAD, safe=""), _hrefs(page))

    # ── /auth/whoop/callback ─────────────────────────────────────────────
    async def test_callback_error_is_escaped(self):
        """The reflected ``error`` query parameter must be HTML-escaped."""
        page = _body(await app.whoop_callback(error=PAYLOAD))

        self.assertNotIn(PAYLOAD, page, "raw OAuth error must not be reflected")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn(html.escape(PAYLOAD, quote=True), page)

    async def test_callback_error_escapes_quote_breakers(self):
        """Every character html.escape handles must be encoded inside <p>.</p>."""
        page = _body(await app.whoop_callback(error=QUOTE_BREAKER))

        self.assertNotIn(QUOTE_BREAKER, page)
        paragraph = page[page.index("<p>") + 3:page.index("</p>")]
        self.assertNotIn("<", paragraph)
        self.assertNotIn(">", paragraph)

    async def test_callback_success_href_quotes_uid(self):
        """The uid taken from the stored OAuth state must be quoted in the link."""
        with patch.object(app, "get_uid_from_oauth_state", lambda state: PAYLOAD), \
             patch.object(app, "store_whoop_tokens", lambda *a, **k: None), \
             patch.object(app.requests, "post", lambda *a, **k: FakeUpstreamResponse()):
            page = _body(await app.whoop_callback(code="code", state="state"))

        self.assertNotIn(PAYLOAD, page)
        self.assertNotIn("<script>", page)
        self.assertIn("/?uid=" + quote(PAYLOAD, safe=""), _hrefs(page))

    async def test_exception_message_is_escaped(self):
        """The OAuth failure page must escape the upstream exception message."""
        def boom(*args, **kwargs):
            raise RuntimeError(PAYLOAD)

        with patch.object(app, "get_uid_from_oauth_state", lambda state: "uid1"), \
             patch.object(app.requests, "post", boom):
            response = await app.whoop_callback(code="code", state="state")

        page = _body(response)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(PAYLOAD, page, "exception text must not be reflected raw")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn(html.escape(PAYLOAD, quote=True), page)

    # ── /disconnect ──────────────────────────────────────────────────────
    async def test_disconnect_redirect_quotes_uid(self):
        """The redirect Location must carry a percent-encoded uid."""
        response = await app.disconnect(uid=PAYLOAD)

        location = response.headers["location"]
        self.assertNotIn(PAYLOAD, location)
        self.assertEqual(location, "/?uid=" + quote(PAYLOAD, safe=""))

    # ── Query sentinel guards (handlers invoked directly) ────────────────
    async def test_root_without_uid_returns_service_info(self):
        """root() called with FastAPI's Query default must not raise."""
        page = await app.root()
        self.assertIsInstance(page, dict)
        self.assertEqual(page.get("app"), "Whoop Omi Integration")

    async def test_callback_without_params_reports_missing_code(self):
        """whoop_callback() with Query sentinels reports missing code, not crash."""
        response = await app.whoop_callback()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing authorization code", _body(response))


if __name__ == "__main__":
    unittest.main(verbosity=2)
