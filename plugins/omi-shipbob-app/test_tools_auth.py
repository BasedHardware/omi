#!/usr/bin/env python3
"""
Regression tests for the shipbob chat-tool auth guard.

Hermetic: stdlib only, framework and sibling modules stubbed, drives the real
require_shipbob_tools_auth guard and inspects the real route handlers in main.py.

Before the fix (no shipbob_tools_auth.py, no Depends on the routes) every test
here is red. After the fix they pass. The uid these routes act on comes from the
request body, so the guard authenticates the calling service by a shared secret;
without it, anyone who knows a uid could act on that user's ShipBob account.
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
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    pydantic.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic

    sdk = types.ModuleType("omi_plugin_sdk")
    sdk_models = types.ModuleType("omi_plugin_sdk.models")
    for name in ("Conversation", "EndpointResponse", "Structured", "TranscriptSegment"):
        setattr(sdk_models, name, type(name, (), {}))
    sdk.models = sdk_models
    sys.modules["omi_plugin_sdk"] = sdk
    sys.modules["omi_plugin_sdk.models"] = sdk_models

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
    for name in ("HTMLResponse", "RedirectResponse", "JSONResponse"):
        responses.__dict__[name] = type(name, (), {"__init__": lambda self, *a, **k: None})
    sys.modules["fastapi.responses"] = responses

    staticfiles = types.ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = type("StaticFiles", (), {"__init__": lambda self, *a, **k: None})
    sys.modules["fastapi.staticfiles"] = staticfiles

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = type("Jinja2Templates", (), {"__init__": lambda self, *a, **k: None})
    sys.modules["fastapi.templating"] = templating

    exceptions = types.ModuleType("fastapi.exceptions")
    exceptions.RequestValidationError = type("RequestValidationError", (Exception,), {})
    sys.modules["fastapi.exceptions"] = exceptions

    requests = types.ModuleType("requests")
    for m in ("get", "post", "put", "delete"):
        setattr(requests, m, lambda *a, **k: None)
    sys.modules["requests"] = requests

    return fastapi.HTTPException


_HTTPException = _install_stubs()

import shipbob_tools_auth  # noqa: E402
import main  # noqa: E402


SECRET = "top-secret-shared-value"

# The eight routes that read uid from the body and act on the user's account.
GUARDED_HANDLERS = [
    "select_channel",
    "tool_get_inventory",
    "tool_get_products",
    "tool_create_wro",
    "tool_get_wros",
    "tool_cancel_wro",
    "tool_get_orders",
    "tool_get_fulfillment_centers",
]


class FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


class TestGuardBehavior(unittest.TestCase):
    def setUp(self):
        os.environ.pop("SHIPBOB_TOOLS_SECRET", None)

    def tearDown(self):
        os.environ.pop("SHIPBOB_TOOLS_SECRET", None)

    def test_unconfigured_secret_fails_closed_503(self):
        req = FakeRequest(headers={"Authorization": "Bearer anything"})
        with self.assertRaises(_HTTPException) as ctx:
            shipbob_tools_auth.require_shipbob_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_401(self):
        os.environ["SHIPBOB_TOOLS_SECRET"] = SECRET
        req = FakeRequest()
        with self.assertRaises(_HTTPException) as ctx:
            shipbob_tools_auth.require_shipbob_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_401(self):
        os.environ["SHIPBOB_TOOLS_SECRET"] = SECRET
        req = FakeRequest(headers={"Authorization": "Bearer wrong"})
        with self.assertRaises(_HTTPException) as ctx:
            shipbob_tools_auth.require_shipbob_tools_auth(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_correct_bearer_token_passes(self):
        os.environ["SHIPBOB_TOOLS_SECRET"] = SECRET
        req = FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})
        self.assertEqual(shipbob_tools_auth.require_shipbob_tools_auth(req), SECRET)

    def test_correct_query_token_passes(self):
        os.environ["SHIPBOB_TOOLS_SECRET"] = SECRET
        req = FakeRequest(query_params={"shipbob_tools_token": SECRET})
        self.assertEqual(shipbob_tools_auth.require_shipbob_tools_auth(req), SECRET)


class TestRoutesAreGuarded(unittest.TestCase):
    def test_all_eight_handlers_depend_on_the_guard(self):
        for name in GUARDED_HANDLERS:
            handler = getattr(main, name)
            deps = [
                p.default.dependency
                for p in inspect.signature(handler).parameters.values()
                if isinstance(p.default, _Dep)
            ]
            self.assertIn(
                shipbob_tools_auth.require_shipbob_tools_auth,
                deps,
                f"{name} is not guarded by require_shipbob_tools_auth",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
