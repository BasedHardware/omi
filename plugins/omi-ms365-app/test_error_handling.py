"""Hermetic unit tests for error sanitization in plugins/omi-ms365-app.

Verifies that:
1. Microsoft authentication errors do not leak internal tenant IDs, tokens, or
   OAuth exchange details in HTTP 401 responses.
2. Argument type/binding errors do not leak Python runtime function signatures or
   internal parameter definitions in HTTP 400 responses.
3. Unexpected handler execution errors return sanitized HTTP 500 responses without
   exposing internal stack traces or server file paths.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

MAIN_PATH = Path(__file__).resolve().parent / "main.py"


class HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _module(name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    return module


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class Serializer:
        def __init__(self, *args, **kwargs):
            pass

    class AuthError(Exception):
        pass

    async def get_access_token(uid):
        return "token"

    settings = SimpleNamespace(log_level="INFO", session_secret="s", app_base_url="http://plugin")

    class AnyHandlers(ModuleType):
        def __getattr__(self, name):
            async def handler(user_id, **kwargs):
                raise AssertionError(f"placeholder handler {name} called")

            return handler

    services = _module("services")
    for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
        setattr(services, name, AnyHandlers(f"services.{name}"))
    services.auth.AuthError = AuthError
    services.auth.get_access_token = get_access_token

    class HTMLResponseStub:
        def __init__(self, content, status_code=200):
            self.content = content
            self.body = content.encode() if isinstance(content, str) else content
            self.status_code = status_code

    stubs = {
        "fastapi": _module(
            "fastapi", FastAPI=FastAPI, HTTPException=HTTPException, Query=lambda *a, **k: None, Request=object
        ),
        "fastapi.responses": _module(
            "fastapi.responses", HTMLResponse=HTMLResponseStub, JSONResponse=dict, RedirectResponse=str
        ),
        "itsdangerous": _module("itsdangerous", BadSignature=Exception, URLSafeSerializer=Serializer),
        "config": _module("config", get_settings=lambda: settings),
        "services": services,
    }
    for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
        stubs[f"services.{name}"] = getattr(services, name)

    spec = importlib.util.spec_from_file_location("main", MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", stubs):
        spec.loader.exec_module(module)
    return module


app = load_app()


def _request(json_payload, query=None):
    class Request:
        query_params = query or {}

        async def json(self):
            if isinstance(json_payload, Exception):
                raise json_payload
            return json_payload

    return Request()


def _omi_call(tool_name, **params):
    payload = {"uid": "user-1", "app_id": "ms365", "tool_name": tool_name}
    payload.update(params)
    return payload


SENSITIVE_LEAKS = [
    "tenant_id=72f988bf",
    "client_secret=secret123",
    "missing 1 required positional argument",
    "/var/data/ms365.db",
    "Traceback",
]


class ErrorSanitizationTests(unittest.TestCase):
    def test_auth_guard_sanitizes_internal_auth_errors(self):
        with patch.object(
            app.auth,
            "get_access_token",
            AsyncMock(
                side_effect=app.auth.AuthError("Token exchange failed: tenant_id=72f988bf client_secret=secret123")
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(app._auth_guard("user-1"))

            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "Microsoft not connected. Please complete authentication.")
            for leak in SENSITIVE_LEAKS:
                self.assertNotIn(leak, str(ctx.exception.detail))

    def test_tool_dispatch_sanitizes_type_errors(self):
        async def mock_handler(uid, **kwargs):
            raise TypeError("search() missing 1 required positional argument: 'query'")

        with patch.dict(app._TOOLS, {"search_emails": mock_handler}):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    app.tool_dispatch(
                        "search_emails",
                        _request(_omi_call("search_emails")),
                    )
                )

            self.assertEqual(ctx.exception.status_code, 400)
            self.assertEqual(ctx.exception.detail, "Bad arguments for search_emails.")
            for leak in SENSITIVE_LEAKS:
                self.assertNotIn(leak, str(ctx.exception.detail))

    def test_tool_dispatch_sanitizes_unexpected_handler_exceptions(self):
        async def mock_crashing_handler(uid, **kwargs):
            raise RuntimeError("Corrupted database at /var/data/ms365.db: connection pool exhausted")

        with patch.dict(app._TOOLS, {"search_emails": mock_crashing_handler}):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    app.tool_dispatch(
                        "search_emails",
                        _request(_omi_call("search_emails", query="urgent")),
                    )
                )

            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to execute tool search_emails. Please try again.")
            for leak in SENSITIVE_LEAKS:
                self.assertNotIn(leak, str(ctx.exception.detail))


if __name__ == "__main__":
    unittest.main()
