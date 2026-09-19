"""Hermetic regression tests for reflected HTML / URL encoding in omi-dropbox-app.

#14892: ``plugins/omi-dropbox-app/main.py`` interpolated attacker-influenced values
straight into the HTML it returns and the URLs it redirects to:

* ``GET /auth/dropbox/callback?error=...&error_description=...`` is unauthenticated
  and reflected the ``error`` / ``error_description`` query parameters into
  ``<p>{error_description or error}</p>``, so a crafted link such as
  ``/auth/dropbox/callback?error=a&error_description=<script>alert(document.cookie)</script>``
  executed script on the plugin origin (reflected XSS).
* the settings page rendered ``display_name``, ``email`` and the stored
  ``folder_name`` into text nodes and a ``value="..."`` attribute, and the ``uid``
  query parameter into ``action``/``href`` targets, allowing attribute breakout and
  query-string corruption (stored XSS / parameter injection).
* the OAuth token-exchange failure body reflected the Dropbox error response verbatim.

The fix escapes every one of those boundaries with ``html.escape(..., quote=True)``
and ``quote(..., safe="")``.  This suite executes the real production functions from
``main.py`` with FastAPI, requests, and storage stubbed out — no network, no
database, no FastAPI runtime, standard library only.

Run: python3 plugins/omi-dropbox-app/test_settings_page_encoding.py
"""

import asyncio
import html
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import quote

BREAKOUT = '"><script>alert(1)</script>'  # attribute break-out + script injection
QUOTE_BREAKER = '"\'&<>'  # every character html.escape must handle
QUERY_BREAKER = "user&admin=1#frag"  # every character quote() must handle
SAFE_UID = "user-1"


# ─── framework / dependency doubles ──────────────────────────────────────────


class Framework:
    """Stand-in for ``fastapi.FastAPI`` and ``fastapi.Request``."""

    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = on_event = get


class Response:
    """Stand-in for ``fastapi.responses`` classes."""

    def __init__(self, content=None, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.__dict__.update(kwargs)


class FakeDropboxClient:
    """Minimal Dropbox client double used by the successful callback path."""

    def __init__(self, access_token):
        self.access_token = access_token

    def get_account(self):
        return ({"name": {"display_name": "Owner"}, "email": "owner@example.com"}, None)


class FakeRequest:
    """``Request`` double for the POST /settings handler."""

    async def form(self):
        return {"folder_name": "Omi Conversations"}


def _make_module(name, **attributes):
    mod = types.ModuleType(name)
    mod.__dict__.update(attributes)
    return mod


_oauth_states = {}
_settings = {}


def _store_oauth_state(uid, state):
    _oauth_states[uid] = state


def _get_oauth_state(uid):
    return _oauth_states.get(uid)


def _delete_oauth_state(uid):
    _oauth_states.pop(uid, None)


def _store_dropbox_tokens(**kwargs):
    _settings["tokens"] = kwargs


stubs = {
    "dotenv": _make_module("dotenv", load_dotenv=lambda: None),
    "fastapi": _make_module(
        "fastapi",
        FastAPI=Framework,
        Request=Framework,
        Query=lambda default=None, **kwargs: default,
    ),
    "fastapi.responses": _make_module(
        "fastapi.responses", HTMLResponse=Response, RedirectResponse=Response, JSONResponse=Response
    ),
    "requests": _make_module("requests", post=Mock()),
    "db": _make_module(
        "db",
        store_dropbox_tokens=_store_dropbox_tokens,
        get_dropbox_tokens=lambda uid: None,
        update_dropbox_tokens=lambda *a, **k: None,
        delete_dropbox_tokens=lambda uid: None,
        store_oauth_state=_store_oauth_state,
        get_oauth_state=_get_oauth_state,
        delete_oauth_state=_delete_oauth_state,
        get_user_settings=lambda uid: {},
        store_user_settings=lambda uid, settings: None,
    ),
    "models": _make_module("models", Conversation=Mock, EndpointResponse=Mock),
    "dropbox_client": _make_module("dropbox_client", DropboxClient=FakeDropboxClient),
}

_spec = importlib.util.spec_from_file_location(
    "dropbox_main_under_test", Path(__file__).with_name("main.py")
)
main = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, stubs):
    _spec.loader.exec_module(main)


def _ok_token_response():
    return Mock(
        status_code=200,
        json=lambda: {
            "access_token": "sl.abc",
            "refresh_token": "rt.abc",
            "expires_in": 14400,
            "account_id": "dbid:1",
        },
    )


# ─── tests ───────────────────────────────────────────────────────────────────


class ConnectUrlQuotingTest(unittest.TestCase):
    """The uid must be percent-encoded before it is placed in any URL."""

    def test_connect_link_quotes_uid(self):
        page = main.get_home_page_html(uid=QUERY_BREAKER, connected=False, settings={})
        self.assertEqual(page.count(f'/auth/dropbox?uid={quote(QUERY_BREAKER, safe="")}'), 1)
        self.assertNotIn(QUERY_BREAKER, page, "raw uid must not reach the markup")

    def test_query_breaker_cannot_corrupt_the_query_string(self):
        page = main.get_home_page_html(uid=QUERY_BREAKER, connected=False, settings={})
        self.assertNotIn("uid=user&admin=1", page)
        self.assertNotIn("#frag", page)


class UserInfoEscapingTest(unittest.TestCase):
    """Dropbox-supplied display name and e-mail are user controlled: escape them."""

    def test_display_name_and_email_are_escaped(self):
        page = main.get_home_page_html(
            uid=SAFE_UID,
            connected=True,
            display_name=BREAKOUT,
            email=QUOTE_BREAKER,
            settings={},
        )
        self.assertNotIn(BREAKOUT, page)
        self.assertNotIn("<script>", page)
        self.assertIn(html.escape(BREAKOUT, quote=True), page)
        self.assertIn(html.escape(QUOTE_BREAKER, quote=True), page)

    def test_none_display_name_does_not_crash(self):
        page = main.get_home_page_html(uid=SAFE_UID, connected=True, settings={})
        self.assertIn("Dropbox Connected", page)


class SettingsPageAttributeTest(unittest.TestCase):
    """Stored folder_name is rendered into a value attribute: no break-out."""

    def test_folder_name_attribute_breakout_is_prevented(self):
        page = main.get_home_page_html(
            uid=SAFE_UID, connected=True, settings={"folder_name": BREAKOUT}
        )
        self.assertNotIn(BREAKOUT, page, "payload must not appear raw inside value=\"...\"")
        self.assertIn(f'value="{html.escape(BREAKOUT, quote=True)}"', page)
        self.assertNotIn('value=""><script>', page)

    def test_settings_and_disconnect_urls_quote_uid(self):
        page = main.get_home_page_html(
            uid=QUERY_BREAKER, connected=True, settings={"folder_name": "Omi Conversations"}
        )
        safe = quote(QUERY_BREAKER, safe="")
        self.assertIn(f'action="/settings?uid={safe}"', page)
        self.assertIn(f'href="/disconnect?uid={safe}"', page)
        self.assertNotIn(f'uid={QUERY_BREAKER}"', page)


class CallbackErrorReflectionTest(unittest.TestCase):
    """GET /auth/dropbox/callback is unauthenticated and reflects `error`."""

    def test_error_description_is_escaped(self):
        response = asyncio.run(
            main.auth_callback(
                code=None, state=None, error="access_denied", error_description=BREAKOUT
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(BREAKOUT, response.content)
        self.assertNotIn("<script>alert(1)</script>", response.content)
        self.assertIn(html.escape(BREAKOUT, quote=True), response.content)

    def test_error_only_payload_is_escaped(self):
        response = asyncio.run(
            main.auth_callback(
                code=None, state=None, error=BREAKOUT, error_description=None
            )
        )
        self.assertNotIn(BREAKOUT, response.content)
        self.assertNotIn("<script>", response.content)
        self.assertIn("Authorization Failed", response.content)

    def test_benign_error_is_still_readable(self):
        response = asyncio.run(
            main.auth_callback(
                code=None, state=None, error="access_denied", error_description=None
            )
        )
        self.assertIn("access_denied", response.content)


class TokenExchangeErrorEscapingTest(unittest.TestCase):
    """The upstream Dropbox error body must not be reflected raw."""

    def test_token_exchange_error_is_escaped(self):
        payload = f'{{"error": {BREAKOUT}}}'
        _store_oauth_state(SAFE_UID, f"{SAFE_UID}:tok")
        with patch.object(main.requests, "post", return_value=Mock(status_code=400, text=payload)):
            response = asyncio.run(
                main.auth_callback(
                    code="code-1", state=f"{SAFE_UID}:tok", error=None, error_description=None
                )
            )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(BREAKOUT, response.content)
        self.assertIn(html.escape(payload, quote=True), response.content)


class RedirectQuotingTest(unittest.TestCase):
    """Redirect targets must percent-encode uid as well."""

    def test_disconnect_redirect_quotes_uid(self):
        response = asyncio.run(main.disconnect(uid=QUERY_BREAKER))
        self.assertEqual(response.url, f'/?uid={quote(QUERY_BREAKER, safe="")}')

    def test_settings_redirect_quotes_uid(self):
        response = asyncio.run(main.update_settings(request=FakeRequest(), uid=QUERY_BREAKER))
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, f'/?uid={quote(QUERY_BREAKER, safe="")}')

    def test_successful_callback_redirect_quotes_uid(self):
        uid = "user&admin=1"
        _store_oauth_state(uid, f"{uid}:tok")
        with patch.object(main.requests, "post", return_value=_ok_token_response()):
            response = asyncio.run(
                main.auth_callback(
                    code="code-1", state=f"{uid}:tok", error=None, error_description=None
                )
            )
        self.assertEqual(response.url, f'/?uid={quote(uid, safe="")}')
        self.assertEqual(
            _settings["tokens"]["display_name"], "Owner", "successful flow must still store tokens"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
