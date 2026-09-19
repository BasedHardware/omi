#!/usr/bin/env python3
"""
Regression tests for the ms365 chat-tool auth guard.

Hermetic: stdlib only, framework, config, auth, and httpx stubbed, drives the
real require_ms365_tools_auth guard and inspects the real tool_dispatch route
in main.py.

Before the fix (no ms365_tools_auth.py, no Depends on the dispatch route) this
is red. After the fix it passes. The uid the tools act on comes from the
request body, and main.py's _auth_guard only proves the victim is connected;
this guard authenticates the calling service by a shared secret.
"""
import sys
import os
import types
import inspect
import unittest


APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class _Dep:
    """Stand-in for fastapi.Depends so we can inspect what a route depends on."""

    def __init__(self, dependency):
        self.dependency = dependency


def _install_stubs():
    fastapi = types.ModuleType("fastapi")

    class _App:
        def __init__(self, *a, **k):
            pass

        def _decorator(self, *a, **k):
            def wrap(fn):
                return fn
            return wrap

        get = post = put = delete = _decorator
        exception_handler = _decorator

        def mount(self, *a, **k):
            pass

    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi.FastAPI = _App
    fastapi.HTTPException = HTTPException
    fastapi.Request = object
    fastapi.Query = lambda default=None, **k: default
    fastapi.Depends = lambda dependency: _Dep(dependency)
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    for name in ("HTMLResponse", "JSONResponse", "RedirectResponse"):
        responses.__dict__[name] = type(name, (), {"__init__": lambda self, *a, **k: None})
    sys.modules["fastapi.responses"] = responses

    its = types.ModuleType("itsdangerous")
    its.BadSignature = type("BadSignature", (Exception,), {})

    class URLSafeSerializer:
        def __init__(self, *a, **k):
            pass

        def dumps(self, obj):
            return "state"

        def loads(self, s):
            return {}

    its.URLSafeSerializer = URLSafeSerializer
    sys.modules["itsdangerous"] = its

    config = types.ModuleType("config")
    config.GRAPH_SCOPES = ["User.Read"]

    class _Settings:
        log_level = "INFO"
        session_secret = "x"
        app_base_url = "http://localhost:8080"

    config.get_settings = lambda: _Settings()
    sys.modules["config"] = config

    auth = types.ModuleType("services.auth")

    class AuthError(Exception):
        pass

    async def get_access_token(user_id: str) -> str:
        return "token"

    auth.AuthError = AuthError
    auth.get_access_token = get_access_token
    sys.modules["services.auth"] = auth

    httpx = types.ModuleType("httpx")

    class AsyncClient:
        def __init__(self, *a, **k):
            pass

        async def request(self, *a, **k):
            raise AssertionError("network not expected in this test")

        async def aclose(self):
            pass

    httpx.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx

    return HTTPException


_HTTPException = _install_stubs()

import ms365_tools_auth  # noqa: E402
import main  # noqa: E402


SECRET = "top-secret-shared-value"


class FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestGuardBehavior(unittest.TestCase):
    def setUp(self):
        os.environ.pop("MS365_TOOLS_SECRET", None)

    def tearDown(self):
        os.environ.pop("MS365_TOOLS_SECRET", None)

    def test_unconfigured_secret_fails_closed_503(self):
        req = FakeRequest(headers={"Authorization": "Bearer anything"})
        with self.assertRaises(_HTTPException) as ctx:
            ms365_tools_auth.require_ms365_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_401(self):
        os.environ["MS365_TOOLS_SECRET"] = SECRET
        req = FakeRequest()
        with self.assertRaises(_HTTPException) as ctx:
            ms365_tools_auth.require_ms365_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_401(self):
        os.environ["MS365_TOOLS_SECRET"] = SECRET
        req = FakeRequest(headers={"Authorization": "Bearer wrong"})
        with self.assertRaises(_HTTPException) as ctx:
            ms365_tools_auth.require_ms365_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_correct_bearer_token_passes(self):
        os.environ["MS365_TOOLS_SECRET"] = SECRET
        req = FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
        self.assertEqual(ms365_tools_auth.require_ms365_tools_auth(req), SECRET)

    def test_correct_query_token_passes(self):
        os.environ["MS365_TOOLS_SECRET"] = SECRET
        req = FakeRequest(query_params={"ms365_tools_token": SECRET})
        self.assertEqual(ms365_tools_auth.require_ms365_tools_auth(req), SECRET)


class TestDispatchIsGuarded(unittest.TestCase):
    def test_tool_dispatch_depends_on_the_guard(self):
        deps = [
            p.default.dependency
            for p in inspect.signature(main.tool_dispatch).parameters.values()
            if isinstance(p.default, _Dep)
        ]
        self.assertIn(
            ms365_tools_auth.require_ms365_tools_auth,
            deps,
            "tool_dispatch is not guarded by require_ms365_tools_auth",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
