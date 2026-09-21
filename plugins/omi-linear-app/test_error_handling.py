"""Hermetic regression tests for sensitive exception leak prevention in Linear app."""
import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = (
    "requests",
    "requests.exceptions",
    "dotenv",
    "fastapi",
    "fastapi.responses",
    "fastapi.staticfiles",
    "fastapi.templating",
    "pydantic",
    "omi_plugin_sdk",
    "omi_plugin_sdk.models",
)


def _install_module_stubs():
    requests = types.ModuleType("requests")

    class _RequestException(Exception):
        pass

    exceptions = types.ModuleType("requests.exceptions")
    exceptions.RequestException = _RequestException
    exceptions.Timeout = type("Timeout", (_RequestException,), {})
    requests.exceptions = exceptions
    requests.RequestException = _RequestException
    requests.post = lambda *a, **k: None
    requests.get = lambda *a, **k: None
    sys.modules["requests"] = requests
    sys.modules["requests.exceptions"] = exceptions

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

        def mount(self, *args, **kwargs):
            pass

    class HTTPException(Exception):
        pass

    class Request:
        def __init__(self, json_data=None):
            self._json = json_data or {}

        async def json(self):
            return self._json

    def Query(default=None, **kwargs):
        return default

    fastapi.FastAPI = FastAPI
    fastapi.HTTPException = HTTPException
    fastapi.Request = Request
    fastapi.Query = Query
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")

    class _Resp:
        def __init__(self, *args, **kwargs):
            pass

    responses.HTMLResponse = _Resp
    responses.RedirectResponse = _Resp
    responses.JSONResponse = _Resp
    sys.modules["fastapi.responses"] = responses

    staticfiles = types.ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = lambda *a, **k: None
    sys.modules["fastapi.staticfiles"] = staticfiles

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda *a, **k: types.SimpleNamespace(TemplateResponse=lambda *a, **k: None)
    sys.modules["fastapi.templating"] = templating

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    pydantic.BaseModel = BaseModel
    pydantic.Field = lambda *a, **k: (k["default_factory"]() if "default_factory" in k else k.get("default"))
    sys.modules["pydantic"] = pydantic

    sdk_pkg = types.ModuleType("omi_plugin_sdk")
    sdk_models = types.ModuleType("omi_plugin_sdk.models")

    class _Model:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    for name in ("Conversation", "EndpointResponse", "Structured", "TranscriptSegment"):
        setattr(sdk_models, name, type(name, (_Model,), {}))
    sdk_pkg.models = sdk_models
    sys.modules["omi_plugin_sdk"] = sdk_pkg
    sys.modules["omi_plugin_sdk.models"] = sdk_models


_saved_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
_install_module_stubs()
try:
    import main  # noqa: E402
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original


def _run(coro):
    return asyncio.run(coro)


class LinearErrorSanitizationTests(unittest.TestCase):
    def test_graphql_request_exception_sanitization(self):
        sensitive_msg = "ConnectTimeout to https://api.linear.app/graphql?token=lin_api_secret_123"
        err = main.requests.RequestException(sensitive_msg)

        with mock.patch.object(main, "get_valid_access_token", return_value="valid-token"), \
             mock.patch.object(main.requests, "post", side_effect=err):
            result = main.linear_graphql_request("user1", "query { viewer { id } }")

        self.assertIn("error", result)
        self.assertEqual(result["error"], "Request failed")
        self.assertNotIn("lin_api_secret_123", result["error"])
        self.assertNotIn("https://api.linear.app", result["error"])

    def test_tool_create_issue_unexpected_exception_sanitization(self):
        sensitive_msg = "RuntimeError: Database conn dropped at postgres://user:secret@10.0.0.99:5432"
        req = main.Request({"uid": "user1", "title": "Test Issue"})

        with mock.patch.object(main, "get_linear_tokens", side_effect=RuntimeError(sensitive_msg)):
            resp = _run(main.tool_create_issue(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to create issue")
        self.assertNotIn("10.0.0.99", resp.error)
        self.assertNotIn("secret", resp.error)

    def test_tool_list_my_issues_unexpected_exception_sanitization(self):
        sensitive_msg = "KeyError: /var/secrets/tokens.json: 'private_key'"
        req = main.Request({"uid": "user1"})

        with mock.patch.object(main, "get_linear_tokens", side_effect=KeyError(sensitive_msg)):
            resp = _run(main.tool_list_my_issues(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to list issues")
        self.assertNotIn("/var/secrets", resp.error)

    def test_tool_list_recent_issues_unexpected_exception_sanitization(self):
        sensitive_msg = "MemoryError: Linear worker thread pool exhausted at 0x7fffbeef"
        req = main.Request({"uid": "user1"})

        with mock.patch.object(main, "get_linear_tokens", side_effect=MemoryError(sensitive_msg)):
            resp = _run(main.tool_list_recent_issues(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to list issues")
        self.assertNotIn("0x7fffbeef", resp.error)

    def test_tool_update_issue_status_unexpected_exception_sanitization(self):
        sensitive_msg = "ConnectionResetError: peer closed socket at 192.168.1.55"
        req = main.Request({"uid": "user1", "issue_identifier": "LIN-101", "new_status": "Done"})

        with mock.patch.object(main, "get_linear_tokens", side_effect=ConnectionResetError(sensitive_msg)):
            resp = _run(main.tool_update_issue_status(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to update issue")
        self.assertNotIn("192.168.1.55", resp.error)

    def test_tool_search_issues_unexpected_exception_sanitization(self):
        sensitive_msg = "ValueError: Bad internal state at /etc/ssl/certs/internal.crt"
        req = main.Request({"uid": "user1", "query": "login bug"})

        with mock.patch.object(main, "get_linear_tokens", side_effect=ValueError(sensitive_msg)):
            resp = _run(main.tool_search_issues(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Search failed")
        self.assertNotIn("/etc/ssl", resp.error)

    def test_tool_get_issue_unexpected_exception_sanitization(self):
        sensitive_msg = "Timeout accessing proxy http://gateway.corp:3128 with auth=secret"
        req = main.Request({"uid": "user1", "issue_identifier": "LIN-101"})

        with mock.patch.object(main, "get_linear_tokens", side_effect=TimeoutError(sensitive_msg)):
            resp = _run(main.tool_get_issue(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get issue")
        self.assertNotIn("gateway.corp", resp.error)

    def test_tool_add_comment_unexpected_exception_sanitization(self):
        sensitive_msg = "Exception: Internal token lin_oauth_sec_888 leaked in stack"
        req = main.Request({"uid": "user1", "issue_identifier": "LIN-101", "comment": "Reviewing now"})

        with mock.patch.object(main, "get_linear_tokens", side_effect=Exception(sensitive_msg)):
            resp = _run(main.tool_add_comment(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to add comment")
        self.assertNotIn("lin_oauth_sec_888", resp.error)


if __name__ == "__main__":
    unittest.main()
