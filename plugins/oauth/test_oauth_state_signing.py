"""Hermetic regression tests for Notion CRM OAuth state signing.

Covers the login-CSRF class fixed by signing `state` with HMAC-SHA256:
- `get_oauth_url` emits `uid:<sig>` instead of the raw uid.
- `uid_from_state` round-trips server-issued states and rejects forged,
  tampered, unsigned, and empty ones.
- The `/auth/notion/callback` handler raises 400 before any token exchange
  when the state was not issued by this server.

Runs under pure standard library Python with zero external dependencies.
"""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock

_plugins_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugins_dir not in sys.path:
    sys.path.insert(0, _plugins_dir)


def _stub_requests():
    if "requests" in sys.modules:
        return
    req = types.ModuleType("requests")
    req_exc = types.ModuleType("requests.exceptions")

    class RequestException(Exception):
        pass

    req_exc.RequestException = RequestException
    req.RequestException = RequestException
    req.exceptions = req_exc
    req.Response = type("Response", (), {})
    req.post = MagicMock()
    req.get = MagicMock()
    utils = types.ModuleType("requests.utils")
    utils.quote = lambda s, safe="": s.replace(":", "%3A")
    req.utils = utils
    sys.modules["requests"] = req
    sys.modules["requests.exceptions"] = req_exc
    sys.modules["requests.utils"] = utils


def _stub_fastapi():
    if "fastapi" in sys.modules:
        return
    fa = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda fn: fn

        def post(self, *args, **kwargs):
            return lambda fn: fn

    class Request:
        pass

    fa.HTTPException = HTTPException
    fa.APIRouter = APIRouter
    fa.Request = Request
    sys.modules["fastapi"] = fa

    far = types.ModuleType("fastapi.responses")

    class HTMLResponse:
        pass

    far.HTMLResponse = HTMLResponse
    sys.modules["fastapi.responses"] = far

    fat = types.ModuleType("fastapi.templating")

    class Jinja2Templates:
        def __init__(self, *args, **kwargs):
            pass

        def TemplateResponse(self, name, context):
            return {"template": name, "context": context}

    fat.Jinja2Templates = Jinja2Templates
    sys.modules["fastapi.templating"] = fat


def _stub_db_and_models():
    if "db" not in sys.modules:
        sys.modules["db"] = MagicMock()
    if "models" not in sys.modules:
        models_mod = types.ModuleType("models")
        models_mod.Conversation = MagicMock()
        models_mod.EndpointResponse = MagicMock()
        sys.modules["models"] = models_mod


_stub_requests()
_stub_fastapi()
_stub_db_and_models()

from oauth.client import NotionClient
from oauth import conversation_created
from oauth.client import client as notion_client


def make_client(secret="test-secret-123"):
    return NotionClient(
        oauth_client_id="cid",
        oauth_client_secret=secret,
        oauth_redirect_uri="https://example.com/cb",
        auth_url="https://api.notion.com/v1/oauth/authorize?client_id=cid",
    )


class StateSigningTests(unittest.TestCase):
    def test_sign_state_binds_uid(self):
        c = make_client()
        state = c.sign_state("uid-abc")
        self.assertTrue(state.startswith("uid-abc:"))
        self.assertEqual(len(state.split(":")[-1]), 32)

    def test_uid_from_state_roundtrips(self):
        c = make_client()
        self.assertEqual(c.uid_from_state(c.sign_state("uid-abc")), "uid-abc")

    def test_uid_from_state_roundtrips_colon_in_uid(self):
        c = make_client()
        uid = "ns:uid-abc"
        self.assertEqual(c.uid_from_state(c.sign_state(uid)), uid)

    def test_raw_uid_state_is_rejected(self):
        """Legacy unsigned `state = uid` no longer validates."""
        c = make_client()
        self.assertIsNone(c.uid_from_state("victim-uid"))

    def test_tampered_signature_is_rejected(self):
        c = make_client()
        state = c.sign_state("victim-uid")
        forged = state[:-1] + ("0" if state[-1] != "0" else "1")
        self.assertIsNone(c.uid_from_state(forged))

    def test_foreign_secret_state_is_rejected(self):
        """A state signed under a different secret must not validate."""
        attacker = make_client(secret="attacker-known-secret")
        c = make_client()
        self.assertIsNone(c.uid_from_state(attacker.sign_state("victim-uid")))

    def test_empty_and_missing_state_rejected(self):
        c = make_client()
        self.assertIsNone(c.uid_from_state(""))
        self.assertIsNone(c.uid_from_state(None))
        self.assertIsNone(c.uid_from_state(":"))
        self.assertIsNone(c.uid_from_state("nosuffix:"))

    def test_oauth_url_carries_signed_state(self):
        c = make_client()
        url = c.get_oauth_url("uid-xyz")
        self.assertIn("state=uid-xyz%3A", url)


class CallbackStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_rejects_unsigned_state_before_token_exchange(self):
        """The real callback path: forged state -> 400, no code exchange."""
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            await conversation_created.callback_auth_notion_crm(
                MagicMock(), "victim-uid", "attacker-code"
            )
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_callback_rejects_tampered_state(self):
        from fastapi import HTTPException

        issued = notion_client.sign_state("victim-uid")
        forged = "attacker-uid" + issued[issued.rindex(":"):]
        with self.assertRaises(HTTPException) as ctx:
            await conversation_created.callback_auth_notion_crm(
                MagicMock(), forged, "attacker-code"
            )
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_callback_accepts_server_issued_state(self):
        """A signed state passes the gate and reaches the token exchange."""
        from fastapi import HTTPException

        issued = notion_client.sign_state("uid-abc")
        try:
            await conversation_created.callback_auth_notion_crm(
                MagicMock(), issued, "some-code"
            )
        except HTTPException as e:
            self.assertNotEqual(e.status_code, 400, "valid state must not hit the forgery gate")


if __name__ == "__main__":
    unittest.main()
