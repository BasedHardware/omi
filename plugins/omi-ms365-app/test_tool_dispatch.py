"""Hermetic regression: /tools/{tool_name} must hand the handler the parameters
the Omi backend sends.

The backend posts a chat tool call as one flat JSON object: the tool's own
parameters next to the envelope keys uid, app_id, tool_name and geolocation
(backend/utils/retrieval/tools/app_tools.py, _call_tool_endpoint). The
dispatcher used to read body["args"], which the backend never sends, so every
tool with a required parameter answered HTTP 400 "Bad arguments" and optional
parameters were silently dropped.

Import the production module with framework, config and service stubs, then
exercise the real dispatcher. No network, credentials, or third-party packages.

Run: python3 plugins/omi-ms365-app/test_tool_dispatch.py
"""

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
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
        return "token"

    settings = SimpleNamespace(log_level="INFO", session_secret="s", app_base_url="http://plugin")
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

    stubs = {
        "fastapi": _module("fastapi", FastAPI=FastAPI, HTTPException=HTTPException, Query=lambda *a, **k: None, Request=object),
        "fastapi.responses": _module("fastapi.responses", HTMLResponse=str, JSONResponse=dict, RedirectResponse=str),
        "itsdangerous": _module("itsdangerous", BadSignature=Exception, URLSafeSerializer=Serializer),
        "config": _module("config", get_settings=lambda: settings),
        "services": services,
    }
    for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
        stubs[f"services.{name}"] = getattr(services, name)

    spec = importlib.util.spec_from_file_location("ms365_main_under_test", MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_app()


def _request(body, query=None):
    class _Request:
        query_params = query or {}

        async def json(self):
            if isinstance(body, Exception):
                raise body
            return body

    return _Request()


def _omi_call(tool_name, **params):
    """The exact envelope the Omi backend posts for a chat tool call."""
    return {
        **params,
        "uid": "user-1",
        "app_id": "app-1",
        "tool_name": tool_name,
        "geolocation": {"latitude": 1.0, "longitude": 2.0},
    }


class DispatchPassesOmiParameters(unittest.TestCase):
    def setUp(self):
        self.received = []

        async def search(user_id, query, limit=10):
            self.received.append((user_id, query, limit))
            return {"ok": True}

        async def get_me(user_id):
            self.received.append((user_id,))
            return {"ok": True}

        patcher = patch.dict(app._TOOLS, {"search_emails": search, "get_me": get_me})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_required_and_optional_parameters_reach_the_handler(self):
        result = asyncio.run(app.tool_dispatch("search_emails", _request(_omi_call("search_emails", query="invoice", limit=5))))
        self.assertEqual(result, {"ok": True})
        self.assertEqual(self.received, [("user-1", "invoice", 5)])

    def test_envelope_keys_are_not_forwarded_as_parameters(self):
        result = asyncio.run(app.tool_dispatch("get_me", _request(_omi_call("get_me"))))
        self.assertEqual(result, {"ok": True})
        self.assertEqual(self.received, [("user-1",)])

    def test_missing_required_parameter_is_a_bad_request_not_a_crash(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(app.tool_dispatch("search_emails", _request(_omi_call("search_emails"))))
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(self.received, [])

    def test_unknown_tool_is_reported_after_uid_check(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(app.tool_dispatch("no_such_tool", _request(_omi_call("no_such_tool"))))
        self.assertEqual(raised.exception.status_code, 404)

    def test_non_object_body_still_requires_uid(self):
        for body in (ValueError("not json"), [1, 2], "text"):
            with self.subTest(body=body):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(app.tool_dispatch("get_me", _request(body)))
                self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
