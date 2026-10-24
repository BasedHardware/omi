"""Hermetic regression test: MS365 tool dispatch and auth guard must not leak
internal exceptions, private IPs, credentials, or upstream Graph error payloads.

Standard library only: runs under python3 -S with zero external dependencies.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

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
        return "mock-token"

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

    class GraphError(Exception):
        def __init__(self, status: int, payload: object):
            super().__init__(f"Graph {status}: {payload}")
            self.status = status
            self.payload = payload

    services.graph_client = _module("services.graph_client", GraphError=GraphError)

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
        "services.graph_client": services.graph_client,
    }
    for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
        stubs[f"services.{name}"] = getattr(services, name)

    spec = importlib.util.spec_from_file_location("main_error_test", MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", stubs):
        spec.loader.exec_module(module)
    return module


app = load_app()

SENSITIVE_HOST = "10.0.12.88"
SENSITIVE_SECRET = "sec_oauth_client_secret_9999"
SENSITIVE_DETAIL = f"Token error at http://{SENSITIVE_HOST}/oauth?secret={SENSITIVE_SECRET}"


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


class TestMS365ErrorHandlingAndLeakPrevention(unittest.TestCase):
    def test_auth_guard_does_not_leak_auth_error_details(self):
        """_auth_guard must return fixed message without leaking internal token/host info."""
        with patch.object(app.auth, "get_access_token", side_effect=app.auth.AuthError(SENSITIVE_DETAIL)):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(app._auth_guard("user-1"))

            self.assertEqual(ctx.exception.status_code, 401)
            self.assertNotIn(SENSITIVE_HOST, ctx.exception.detail)
            self.assertNotIn(SENSITIVE_SECRET, ctx.exception.detail)
            self.assertEqual(ctx.exception.detail, "Microsoft not connected — please connect in settings.")

    def test_tool_dispatch_bad_arguments_does_not_leak_typeerror_trace(self):
        """tool_dispatch must not leak internal argument inspection details on TypeError."""

        async def failing_handler(user_id, **kwargs):
            raise TypeError(f"internal type failure at {SENSITIVE_HOST} path /etc/passwd")

        with patch.dict(app._TOOLS, {"search_emails": failing_handler}):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(app.tool_dispatch("search_emails", _request(_omi_call("search_emails", query="test"))))

            self.assertEqual(ctx.exception.status_code, 400)
            self.assertNotIn(SENSITIVE_HOST, ctx.exception.detail)
            self.assertNotIn("/etc/passwd", ctx.exception.detail)
            self.assertEqual(ctx.exception.detail, "Bad arguments for search_emails")

    def test_tool_dispatch_graph_4xx_error_does_not_leak_payload(self):
        """Graph 4xx errors should preserve status without leaking payload details."""

        class MockGraphError(Exception):
            def __init__(self):
                super().__init__(f"Graph 404: {SENSITIVE_DETAIL}")
                self.status = 404
                self.payload = {"secret": SENSITIVE_SECRET, "host": SENSITIVE_HOST}

        async def failing_handler(user_id, **kwargs):
            raise MockGraphError()

        with patch.dict(app._TOOLS, {"get_me": failing_handler}):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(app.tool_dispatch("get_me", _request(_omi_call("get_me"))))

            self.assertEqual(ctx.exception.status_code, 404)
            self.assertNotIn(SENSITIVE_HOST, ctx.exception.detail)
            self.assertNotIn(SENSITIVE_SECRET, ctx.exception.detail)
            self.assertEqual(ctx.exception.detail, "Request failed for get_me")

    def test_tool_dispatch_unexpected_exception_does_not_leak_stack(self):
        """Unexpected internal exceptions in tools return generic 502 without leaking details."""

        async def failing_handler(user_id, **kwargs):
            raise RuntimeError(f"Database connection pool exhausted: {SENSITIVE_DETAIL}")

        with patch.dict(app._TOOLS, {"list_recent_emails": failing_handler}):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(app.tool_dispatch("list_recent_emails", _request(_omi_call("list_recent_emails"))))

            self.assertEqual(ctx.exception.status_code, 502)
            self.assertNotIn(SENSITIVE_HOST, ctx.exception.detail)
            self.assertNotIn(SENSITIVE_SECRET, ctx.exception.detail)
            self.assertEqual(
                ctx.exception.detail, "Failed to execute list_recent_emails due to an upstream service error."
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
