"""Hermetic regression tests for Whoop settings-page, callback and redirect encoding.

The settings page, OAuth callback and disconnect routes interpolated attacker
controllable `uid` and `error` text into HTML attribute, URL and inline-script
contexts without escaping, yielding reflected XSS. These tests load the
production module with framework-only doubles and assert the rendered output is
escaped and the disconnect redirect is percent-encoded.

fastapi, requests and dotenv are stubbed, so the suite runs in the hermetic
Hygiene lane that installs no third-party packages.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch


def load_app():
    class FastAPI:
        def __init__(self, *args, **kwargs):
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

    class Response:
        default_status = 200

        def __init__(self, content=None, status_code=None, url=None, **kwargs):
            if isinstance(content, bytes):
                self.body = content
            else:
                self.body = str("" if content is None else content).encode()
            self.status_code = self.default_status if status_code is None else status_code
            self.headers = {}
            if url is not None:
                self.headers["location"] = url

    class RedirectResponse(Response):
        default_status = 307

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
    responses.HTMLResponse = Response
    responses.RedirectResponse = RedirectResponse
    responses.JSONResponse = Response

    db = ModuleType("db")
    for name in (
        "store_whoop_tokens",
        "get_whoop_tokens",
        "update_whoop_tokens",
        "delete_whoop_tokens",
        "store_oauth_state",
        "get_uid_from_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
        "get_user_setting",
    ):
        setattr(db, name, lambda *args, **kwargs: None)

    models = ModuleType("models")
    models.ChatToolResponse = ChatToolResponse

    spec = importlib.util.spec_from_file_location(
        "whoop_app_encoding", Path(__file__).with_name("main.py")
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


main = load_app()


class TestWhoopSettingsPageEncoding(unittest.TestCase):
    def test_unauthenticated_root_page_escapes_uid(self):
        with patch.object(main, "get_whoop_tokens", return_value=None):
            response = asyncio.run(main.root(uid='user"123<script>'))
            self.assertEqual(response.status_code, 200)
            body = response.body.decode()
            self.assertIn('href="/auth/whoop?uid=user%22123%3Cscript%3E"', body)
            self.assertNotIn('href="/auth/whoop?uid=user"123<script>"', body)

    def test_authenticated_root_page_escapes_disconnect_link(self):
        with patch.object(
            main, "get_whoop_tokens", return_value={"access_token": "valid"}
        ):
            response = asyncio.run(main.root(uid='user"123<script>'))
            self.assertEqual(response.status_code, 200)
            body = response.body.decode()
            self.assertIn('href="/disconnect?uid=user%22123%3Cscript%3E"', body)
            self.assertNotIn('href="/disconnect?uid=user"123<script>"', body)

    def test_callback_error_is_escaped(self):
        response = asyncio.run(main.whoop_callback(error='<script>alert("xss")</script>'))
        self.assertEqual(response.status_code, 400)
        body = response.body.decode()
        self.assertIn("&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;", body)
        self.assertNotIn('<script>alert("xss")</script>', body)

    def test_callback_success_escapes_continue_link(self):
        from unittest.mock import MagicMock

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"access_token": "token123", "expires_in": 3600}

        with patch.object(
            main, "get_uid_from_oauth_state", return_value='user"123<script>'
        ), patch.object(main, "delete_oauth_state"), patch.object(
            main, "store_whoop_tokens"
        ), patch.object(
            main.requests, "post", return_value=fake_response
        ):
            response = asyncio.run(main.whoop_callback(code="code_123", state="state_123"))
            self.assertEqual(response.status_code, 200)
            body = response.body.decode()
            self.assertIn('href="/?uid=user%22123%3Cscript%3E"', body)
            self.assertNotIn('href="/?uid=user"123<script>"', body)

    def test_callback_exception_escapes_error_message(self):
        with patch.object(
            main, "get_uid_from_oauth_state", return_value="user123"
        ), patch.object(main, "delete_oauth_state"), patch.object(
            main.requests, "post", side_effect=Exception("<script>broken</script>")
        ):
            response = asyncio.run(main.whoop_callback(code="code_123", state="state_123"))
            self.assertEqual(response.status_code, 500)
            body = response.body.decode()
            self.assertIn("&lt;script&gt;broken&lt;/script&gt;", body)
            self.assertNotIn("<script>broken</script>", body)

    def test_disconnect_redirect_quotes_uid(self):
        with patch.object(main, "delete_whoop_tokens"):
            response = asyncio.run(main.disconnect(uid='user" 123&test=1'))
            self.assertEqual(response.status_code, 307)
            self.assertEqual(
                response.headers["location"], "/?uid=user%22%20123%26test%3D1"
            )


if __name__ == "__main__":
    unittest.main()