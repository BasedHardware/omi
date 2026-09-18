"""
Hermetic regression tests for Notion OAuth state signing (#14444).

Verifies:
1. NotionClient produces cryptographically signed state parameters binding to UID.
2. NotionClient supports UIDs containing colons via rsplit.
3. NotionClient fails closed (raises ValueError on minting, returns None on verifying) when secret is unset.
4. response_setup_notion_crm_page successfully renders error messages even when UID is empty.
5. callback_auth_notion_crm renders the error page on tampered state without raising HTTPException 400.
6. setup_notion_crm fails closed (HTTP 503) if Notion OAuth secret is unconfigured.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Ensure plugins directory is in path
plugins_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if plugins_dir not in sys.path:
    sys.path.insert(0, plugins_dir)


def _stub_dependencies():
    if "requests" not in sys.modules:
        req = types.ModuleType("requests")
        req_exc = types.ModuleType("requests.exceptions")

        class RequestException(Exception):
            pass

        class HTTPError(RequestException):
            pass

        class Timeout(RequestException):
            pass

        class ConnectionError(RequestException):
            pass

        req_exc.RequestException = RequestException
        req_exc.HTTPError = HTTPError
        req_exc.Timeout = Timeout
        req_exc.ConnectionError = ConnectionError

        class Response:
            def __init__(self, status_code=200, text="{}", json_data=None):
                self.status_code = status_code
                self.text = text
                self._json_data = json_data if json_data is not None else {}

            def json(self):
                if isinstance(self._json_data, Exception):
                    raise self._json_data
                return self._json_data

        req.Response = Response
        req.exceptions = req_exc
        req.RequestException = RequestException
        req.post = MagicMock(return_value=Response(200))
        req.get = MagicMock(return_value=Response(200))

        sys.modules["requests"] = req
        sys.modules["requests.exceptions"] = req_exc

    if "fastapi" not in sys.modules:
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

    if "fastapi.responses" not in sys.modules:
        far = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            pass

        far.HTMLResponse = HTMLResponse
        sys.modules["fastapi.responses"] = far

    if "fastapi.templating" not in sys.modules:
        fat = types.ModuleType("fastapi.templating")

        class Jinja2Templates:
            def __init__(self, *args, **kwargs):
                pass

            def TemplateResponse(self, name, context):
                return {"template": name, "context": context}

        fat.Jinja2Templates = Jinja2Templates
        sys.modules["fastapi.templating"] = fat

    if "pydantic" not in sys.modules:
        pyd = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

            def model_dump(self, mode="json"):
                return self.__dict__.copy()

            def dict(self):
                return self.__dict__.copy()

        def Field(default=None, **kwargs):
            return default

        pyd.BaseModel = BaseModel
        pyd.Field = Field
        sys.modules["pydantic"] = pyd

    if "db" not in sys.modules:
        db_mod = types.ModuleType("db")
        db_mod.get_notion_crm_api_key = MagicMock(return_value="test_api_key")
        db_mod.get_notion_database_id = MagicMock(return_value="test_db_id")
        db_mod.store_notion_crm_api_key = MagicMock()
        db_mod.store_notion_database_id = MagicMock()
        sys.modules["db"] = db_mod

    if "models" not in sys.modules:
        models_mod = types.ModuleType("models")

        class Conversation:
            def __init__(
                self,
                id="conv_1",
                structured=None,
                transcript_segments=None,
                started_at=None,
                finished_at=None,
            ):
                self.id = id
                self.structured = structured
                self.transcript_segments = transcript_segments or []
                self.started_at = started_at
                self.finished_at = finished_at

        class Structured:
            def __init__(self, title="Test Title", overview="Test Overview", emoji="🧠", category="Work"):
                self.title = title
                self.overview = overview
                self.emoji = emoji
                self.category = category

        class TranscriptSegment:
            def __init__(self, speaker="Speaker 1", text="Hello world"):
                self.speaker = speaker
                self.text = text

        class EndpointResponse:
            def __init__(self, message=""):
                self.message = message

        models_mod.Conversation = Conversation
        models_mod.Structured = Structured
        models_mod.TranscriptSegment = TranscriptSegment
        models_mod.EndpointResponse = EndpointResponse
        sys.modules["models"] = models_mod


_stub_dependencies()

from oauth.client import NotionClient
from oauth.conversation_created import (
    response_setup_notion_crm_page,
    callback_auth_notion_crm,
    setup_notion_crm,
)
from fastapi import HTTPException, Request


class TestNotionOAuthState(unittest.TestCase):
    def setUp(self):
        self.client = NotionClient(
            oauth_client_id="test_client_id",
            oauth_client_secret="test_secret_key",
            oauth_redirect_uri="http://localhost:8000/auth/notion/callback",
            auth_url="https://api.notion.com/v1/oauth/authorize?owner=user",
        )

    def test_signed_state_valid_roundtrip(self):
        uid = "notion_user_456"
        state = self.client._signed_state(uid)
        recovered = self.client.uid_from_state(state)
        self.assertEqual(recovered, uid)

    def test_signed_state_supports_colons_in_uid(self):
        uid = "auth0|user:123:456"
        state = self.client._signed_state(uid)
        recovered = self.client.uid_from_state(state)
        self.assertEqual(recovered, uid)

    def test_signed_state_rejects_tampering(self):
        uid = "victim_uid"
        state = self.client._signed_state(uid)
        tampered = "attacker_uid:" + state.rsplit(":", 1)[1]
        self.assertIsNone(self.client.uid_from_state(tampered))

    def test_signed_state_rejects_unsigned_or_malformed(self):
        self.assertIsNone(self.client.uid_from_state("raw_unsigned_uid"))
        self.assertIsNone(self.client.uid_from_state(""))
        self.assertIsNone(self.client.uid_from_state(None))

    def test_signed_state_rejects_wrong_secret(self):
        uid = "test_user"
        state = self.client._signed_state(uid)
        other_client = NotionClient(oauth_client_secret="different_secret")
        self.assertIsNone(other_client.uid_from_state(state))

    def test_signed_state_fails_closed_when_secret_unset(self):
        unconfigured_client = NotionClient(oauth_client_secret="")
        with self.assertRaises(ValueError):
            unconfigured_client._signed_state("any_uid")

        valid_state = self.client._signed_state("any_uid")
        self.assertIsNone(unconfigured_client.uid_from_state(valid_state))

    def test_get_oauth_url_contains_signed_state(self):
        uid = "test_user_789"
        url = self.client.get_oauth_url(uid)
        self.assertIn("&state=", url)
        state_param = url.split("&state=")[1]
        import urllib.parse

        decoded_state = urllib.parse.unquote(state_param)
        self.assertEqual(self.client.uid_from_state(decoded_state), uid)


class TestNotionOAuthEndpoints(unittest.TestCase):
    def setUp(self):
        self.req = Request()

    def test_response_setup_page_with_empty_uid_and_error(self):
        # Must NOT raise HTTPException(400) when rendering error with empty uid
        resp = response_setup_notion_crm_page(
            self.req, "", "Invalid or tampered state parameter"
        )
        self.assertEqual(resp["template"], "setup_notion_crm.html")
        self.assertEqual(resp["context"]["error_message"], "Invalid or tampered state parameter")
        self.assertEqual(resp["context"]["uid"], "")
        self.assertEqual(resp["context"]["oauth_url"], "")

    def test_response_setup_page_raises_400_when_both_uid_and_error_empty(self):
        with self.assertRaises(HTTPException) as ctx:
            response_setup_notion_crm_page(self.req, "", "")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_callback_auth_rejects_tampered_state_with_error_page(self):
        resp = asyncio.run(callback_auth_notion_crm(self.req, "tampered:state", "some_code"))
        self.assertEqual(resp["template"], "setup_notion_crm.html")
        self.assertIn("Invalid or tampered state", resp["context"]["error_message"])

    def test_setup_notion_crm_fails_closed_when_secret_unset(self):
        from oauth.client import get_notion
        client = get_notion()
        orig_secret = client.oauth_client_secret
        try:
            client.oauth_client_secret = ""
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(setup_notion_crm(self.req, "uid123"))
            self.assertEqual(ctx.exception.status_code, 503)
        finally:
            client.oauth_client_secret = orig_secret


if __name__ == "__main__":
    unittest.main(verbosity=2)
