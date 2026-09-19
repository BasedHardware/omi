"""Hermetic unit tests for omi-ms365-app setup page and OAuth callback HTML encoding.

Verifies that:
1. /setup/ms365 URL-encodes the uid query parameter into the OAuth start redirect link,
   preventing HTML attribute breakout and injection.
2. /auth/microsoft/callback HTML-escapes error and error_description query parameters,
   preventing reflected Cross-Site Scripting (XSS).
3. /auth/microsoft/callback validates code and state presence and rejects invalid signatures.
4. /auth/microsoft redirects with a cryptographically signed state token.

Zero external dependencies: FastAPI, itsdangerous, config, and services are stubbed
via sys.modules so tests run under pure standard library in CI.

Run: python3 plugins/omi-ms365-app/test_settings_page_encoding.py
"""

from __future__ import annotations

import asyncio
import html
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

MAIN_PATH = Path(__file__).resolve().parent / "main.py"


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class BadSignature(Exception):
    pass


class HTMLResponse:
    def __init__(self, content: str | bytes, status_code: int = 200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.body = content.encode("utf-8") if isinstance(content, str) else content
        self.__dict__.update(kwargs)


class RedirectResponse:
    def __init__(self, url: str, status_code: int = 307, **kwargs):
        self.url = url
        self.status_code = status_code
        self.headers = {"location": url}
        self.__dict__.update(kwargs)


class JSONResponse:
    def __init__(self, content: dict, status_code: int = 200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.__dict__.update(kwargs)


class MockSerializer:
    def __init__(self, secret: str, salt: str = ""):
        self.secret = secret
        self.salt = salt

    def dumps(self, obj: dict) -> str:
        return f"signed_{obj.get('uid', '')}"

    def loads(self, state: str) -> dict:
        if state == "invalid_state" or state.startswith("tampered"):
            raise BadSignature("Invalid signature")
        if state.startswith("signed_"):
            return {"uid": state[len("signed_"):]}
        return {"uid": state}


def _module(name: str, **attributes) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__dict__.update(attributes)
    return mod


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class AuthError(Exception):
        pass

    async def get_access_token(uid: str) -> str:
        return "mock_token"

    settings = types.SimpleNamespace(
        log_level="INFO",
        session_secret="mock_session_secret_12345",
        app_base_url="http://plugin",
    )

    class AnyHandlers(types.ModuleType):
        def __getattr__(self, name: str):
            async def handler(user_id: str, **kwargs):
                return {}
            return handler

    services = _module("services")
    for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
        sub = AnyHandlers(f"services.{name}")
        setattr(services, name, sub)

    services.auth.AuthError = AuthError
    services.auth.get_access_token = get_access_token
    services.auth.build_auth_url = MagicMock(
        side_effect=lambda state: f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state={state}"
    )
    services.auth.exchange_code_for_token = AsyncMock()
    services.auth.disconnect = AsyncMock()

    stubs = {
        "fastapi": _module(
            "fastapi",
            FastAPI=FastAPI,
            HTTPException=HTTPException,
            Query=lambda *a, **k: None,
            Request=object,
        ),
        "fastapi.responses": _module(
            "fastapi.responses",
            HTMLResponse=HTMLResponse,
            JSONResponse=JSONResponse,
            RedirectResponse=RedirectResponse,
        ),
        "itsdangerous": _module(
            "itsdangerous",
            BadSignature=BadSignature,
            URLSafeSerializer=MockSerializer,
        ),
        "config": _module("config", get_settings=lambda: settings),
        "services": services,
    }
    for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
        stubs[f"services.{name}"] = getattr(services, name)

    spec = importlib.util.spec_from_file_location("main_under_test", MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", stubs):
        spec.loader.exec_module(module)
    return module


main = load_app()


class TestMS365SettingsPageEncoding(unittest.TestCase):
    def test_setup_page_escapes_and_quotes_uid_against_attribute_breakout(self):
        evil_uid = 'user"123<script>alert(1)</script>'
        html_content = asyncio.run(main.setup_page(uid=evil_uid))
        expected_quoted = quote(evil_uid, safe="")
        self.assertIn(f'href="/auth/microsoft?uid={expected_quoted}"', html_content)
        self.assertNotIn('href="/auth/microsoft?uid=user"123<script>', html_content)

    def test_setup_page_normal_uid(self):
        html_content = asyncio.run(main.setup_page(uid="user_abc123"))
        self.assertIn('href="/auth/microsoft?uid=user_abc123"', html_content)

    def test_setup_page_uid_with_spaces_and_query_characters(self):
        uid_with_specials = "user & admin#frag?x=1"
        html_content = asyncio.run(main.setup_page(uid=uid_with_specials))
        expected_quoted = quote(uid_with_specials, safe="")
        self.assertIn(f'href="/auth/microsoft?uid={expected_quoted}"', html_content)
        self.assertNotIn("user & admin#frag?x=1", html_content)

    def test_auth_callback_escapes_error_and_description(self):
        evil_error = '<script>alert("err")</script>'
        evil_desc = '<b onmouseover=alert(1)>Fail</b>'
        response = asyncio.run(
            main.auth_callback(
                error=evil_error,
                error_description=evil_desc,
            )
        )
        self.assertEqual(response.status_code, 400)
        body = response.body.decode("utf-8")
        self.assertIn(html.escape(evil_error), body)
        self.assertIn(html.escape(evil_desc), body)
        self.assertNotIn(evil_error, body)
        self.assertNotIn(evil_desc, body)

    def test_auth_callback_escapes_error_without_description(self):
        evil_error = 'access_denied<img src=x onerror=alert(1)>'
        response = asyncio.run(
            main.auth_callback(
                error=evil_error,
                error_description=None,
            )
        )
        self.assertEqual(response.status_code, 400)
        body = response.body.decode("utf-8")
        self.assertIn(html.escape(evil_error), body)
        self.assertNotIn(evil_error, body)

    def test_auth_callback_missing_code_or_state_raises_400(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(main.auth_callback(code=None, state=None))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Missing code or state")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(main.auth_callback(code="valid_code", state=None))
        self.assertEqual(ctx.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(main.auth_callback(code=None, state="valid_state"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_auth_callback_invalid_state_signature_raises_400(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(main.auth_callback(code="valid_code", state="tampered_state"))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Invalid state")

    def test_auth_callback_successful_exchange(self):
        valid_state = "signed_user_123"
        main.auth.exchange_code_for_token.reset_mock()

        response = asyncio.run(main.auth_callback(code="auth_code_xyz", state=valid_state))
        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn("✓ Connected", body)
        main.auth.exchange_code_for_token.assert_awaited_once_with("auth_code_xyz", "user_123")

    def test_auth_start_redirects_with_signed_state(self):
        response = asyncio.run(main.auth_start(uid="user_999"))
        self.assertEqual(response.status_code, 307)
        self.assertIn("location", response.headers)
        self.assertTrue(
            response.headers["location"].startswith("https://login.microsoftonline.com/")
        )
        self.assertIn("state=signed_user_999", response.headers["location"])


if __name__ == "__main__":
    unittest.main()
