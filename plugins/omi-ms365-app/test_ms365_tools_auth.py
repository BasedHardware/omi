"""Hermetic regression tests for the MS365 chat-tool shared-secret guard.

`POST /tools/{tool_name}` dispatches to handlers that act on the stored
Microsoft Graph token of whatever `uid` the body names — `read_email`,
`send_email`, `send_chat_message`, `read_file_text` and `upload_text_file`
among them. The route carried no caller authentication, so any client that
could reach the deployment and name a uid could read and send that user's mail.

Covers the `ms365_tools_auth` dependency (fail-closed 503 when unconfigured,
401 on missing/wrong/non-Bearer token, accept on Bearer header or
`ms365_tools_token` query param) and asserts the chat-tool route is wired to
it, so the guard cannot be dropped from the decorator unnoticed.

Standard library only: stubs fastapi, itsdangerous, config and the service
modules before import, so the suite runs with no credentials, network, or
third-party packages.

Run: python3 plugins/omi-ms365-app/test_ms365_tools_auth.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

MAIN_PATH = APP_DIR / "main.py"
SECRET_ENV = "MS365_TOOLS_SECRET"
TEST_SECRET = "test-ms365-tools-secret"
TOOLS_ROUTE = "/tools/{tool_name}"


class _StubHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _module(name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    return module


def _fastapi_stub_if_missing():
    """Provide the fastapi surface the guard needs when fastapi is absent."""
    try:
        import fastapi  # noqa: F401

        return None
    except ImportError:
        return _module(
            "fastapi",
            HTTPException=_StubHTTPException,
            Request=object,
            Depends=lambda dependency: dependency,
            FastAPI=object,
            Query=lambda *a, **k: None,
        )


_FASTAPI_STUB = _fastapi_stub_if_missing()
if _FASTAPI_STUB is not None:
    sys.modules["fastapi"] = _FASTAPI_STUB

from fastapi import HTTPException  # noqa: E402

import ms365_tools_auth as guard  # noqa: E402


class _FakeRequest:
    """Minimal stand-in for a FastAPI Request: headers + query_params only."""

    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class MS365ToolsAuthUnitTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get(SECRET_ENV)

    def tearDown(self):
        if self._old is None:
            os.environ.pop(SECRET_ENV, None)
        else:
            os.environ[SECRET_ENV] = self._old

    def test_fails_closed_when_unconfigured(self):
        os.environ.pop(SECRET_ENV, None)
        with self.assertRaises(HTTPException) as ctx:
            guard.require_ms365_tools_auth(
                _FakeRequest(headers={"Authorization": f"Bearer {TEST_SECRET}"})
            )
        self.assertEqual(ctx.exception.status_code, 503)

    def test_blank_secret_is_treated_as_unconfigured(self):
        os.environ[SECRET_ENV] = "   "
        with self.assertRaises(HTTPException) as ctx:
            guard.require_ms365_tools_auth(
                _FakeRequest(query_params={"ms365_tools_token": "   "})
            )
        self.assertEqual(ctx.exception.status_code, 503)

    def test_401_when_no_token(self):
        os.environ[SECRET_ENV] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            guard.require_ms365_tools_auth(_FakeRequest())
        self.assertEqual(ctx.exception.status_code, 401)

    def test_401_on_wrong_bearer_token(self):
        os.environ[SECRET_ENV] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            guard.require_ms365_tools_auth(
                _FakeRequest(headers={"Authorization": "Bearer wrong"})
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_401_on_wrong_query_token(self):
        os.environ[SECRET_ENV] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            guard.require_ms365_tools_auth(
                _FakeRequest(query_params={"ms365_tools_token": "wrong"})
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_401_on_non_bearer_scheme(self):
        os.environ[SECRET_ENV] = TEST_SECRET
        with self.assertRaises(HTTPException) as ctx:
            guard.require_ms365_tools_auth(
                _FakeRequest(headers={"Authorization": f"Basic {TEST_SECRET}"})
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_accepts_bearer_token(self):
        os.environ[SECRET_ENV] = TEST_SECRET
        self.assertIsNone(
            guard.require_ms365_tools_auth(
                _FakeRequest(headers={"Authorization": f"Bearer {TEST_SECRET}"})
            )
        )

    def test_accepts_bearer_token_case_insensitively(self):
        os.environ[SECRET_ENV] = TEST_SECRET
        self.assertIsNone(
            guard.require_ms365_tools_auth(
                _FakeRequest(headers={"Authorization": f"bearer {TEST_SECRET}"})
            )
        )

    def test_accepts_query_token(self):
        os.environ[SECRET_ENV] = TEST_SECRET
        self.assertIsNone(
            guard.require_ms365_tools_auth(
                _FakeRequest(query_params={"ms365_tools_token": TEST_SECRET})
            )
        )


def _load_main_recording_routes():
    """Import the real main.py against stubs, recording route registrations.

    Mirrors ``test_tool_dispatch.load_app`` but keeps the decorator keyword
    arguments so the wiring of the shared-secret dependency is observable.
    """
    registrations: list[tuple[str, dict]] = []

    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, path, **kwargs):
            registrations.append((path, kwargs))
            return lambda handler: handler

        post = get

    class Serializer:
        def __init__(self, *args, **kwargs):
            pass

    class AuthError(Exception):
        pass

    async def get_access_token(uid):
        return "token"

    class AnyHandlers(ModuleType):
        """A service module whose every attribute is a placeholder handler."""

        def __getattr__(self, name):
            async def handler(user_id, **kwargs):
                raise AssertionError(f"placeholder handler {name} called")

            return handler

    services = _module("services")
    for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
        setattr(services, name, AnyHandlers(f"services.{name}"))
    services.auth.AuthError = AuthError
    services.auth.get_access_token = get_access_token

    settings = SimpleNamespace(log_level="INFO", session_secret="s", app_base_url="http://plugin")
    stubs = {
        "fastapi": _module(
            "fastapi",
            FastAPI=FastAPI,
            HTTPException=_StubHTTPException,
            Query=lambda *a, **k: None,
            Request=object,
            Depends=lambda dependency: dependency,
        ),
        "fastapi.responses": _module(
            "fastapi.responses", HTMLResponse=str, JSONResponse=dict, RedirectResponse=str
        ),
        "itsdangerous": _module("itsdangerous", BadSignature=Exception, URLSafeSerializer=Serializer),
        "config": _module("config", get_settings=lambda: settings),
        "services": services,
    }
    for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
        stubs[f"services.{name}"] = getattr(services, name)

    spec = importlib.util.spec_from_file_location("main_for_wiring", MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    # The guard imports fastapi itself; load it against the same stub.
    stubs.pop("ms365_tools_auth", None)
    with patch.dict("sys.modules", stubs):
        sys.modules.pop("ms365_tools_auth", None)
        spec.loader.exec_module(module)
    sys.modules.pop("ms365_tools_auth", None)
    return registrations


def _dependency_names(kwargs):
    names = set()
    for dep in kwargs.get("dependencies") or []:
        callable_ = getattr(dep, "dependency", dep)
        name = getattr(callable_, "__name__", "")
        if name:
            names.add(name)
    return names


class MS365RouteAuthWiringTests(unittest.TestCase):
    """The chat-tool route must carry the shared-secret dependency."""

    @classmethod
    def setUpClass(cls):
        cls.registrations = _load_main_recording_routes()

    def test_chat_tool_route_is_registered(self):
        self.assertIn(TOOLS_ROUTE, [path for path, _ in self.registrations])

    def test_chat_tool_route_requires_the_shared_secret(self):
        guarded = {
            path
            for path, kwargs in self.registrations
            if "require_ms365_tools_auth" in _dependency_names(kwargs)
        }
        self.assertEqual(guarded, {TOOLS_ROUTE})


if __name__ == "__main__":
    unittest.main()
