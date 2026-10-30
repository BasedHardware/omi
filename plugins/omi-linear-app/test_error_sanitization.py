"""Hermetic error-sanitization tests for plugins/omi-linear-app/main.py.

Standard library only: requests, dotenv, fastapi, pydantic, and
omi_plugin_sdk are replaced with minimal stubs before importing the module
under test so the suite runs without site-packages (the manifest lane runs
plain python3). db.py is importable as-is (redis import is optional).

Covers the exception-text leak class: `linear_graphql_request` embedded
`str(e)` for transport failures, `tool_add_comment` echoed that error text
into the chat response, and all seven chat tools interpolated `str(e)` from
broad `except Exception` handlers. Now transport failures and unexpected
errors produce fixed, code-controlled messages; GraphQL server errors
(server-controlled text) still surface.
"""

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
    exceptions.ConnectionError = type("ConnectionError", (_RequestException,), {})
    requests.exceptions = exceptions
    # main.py references requests.RequestException at top level in its except clause
    requests.RequestException = _RequestException
    requests.Timeout = exceptions.Timeout
    requests.ConnectionError = exceptions.ConnectionError
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
        pass

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
    del _name, _original, _saved_modules

SCARY_TRANSPORT = (
    "HTTPSConnectionPool(host='api.linear.app', port=443): Max retries exceeded: "
    "[Errno -2] Name or service not known from host omi-plugins-7f9c via 10.0.2.15"
)


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def _patched_tool(payload, **extra_patches):
    """Call a chat tool with auth mocked and the GraphQL seam raising."""

    def _decorator(func):
        async def _run():
            with mock.patch.object(main, "get_linear_tokens", return_value={"access_token": "t"}), \
                 mock.patch.object(main, "linear_graphql_request",
                                   side_effect=RuntimeError(SCARY_TRANSPORT)):
                return await func(_FakeRequest(payload))
        return _run()
    return _decorator


class ToolSanitizationTests(unittest.TestCase):
    def _assert_clean(self, resp, expected):
        self.assertEqual(resp.error, expected)
        self.assertNotIn("Errno", resp.error)
        self.assertNotIn("10.0.2.15", resp.error)
        self.assertNotIn("omi-plugins-7f9c", resp.error)

    def test_create_issue(self):
        resp = _patched_tool({"uid": "u1", "title": "T"})(main.tool_create_issue)
        self._assert_clean(asyncio.run(resp), "Failed to create issue. Please try again later.")

    def test_list_my_issues(self):
        resp = _patched_tool({"uid": "u1"})(main.tool_list_my_issues)
        self._assert_clean(asyncio.run(resp), "Failed to list issues. Please try again later.")

    def test_list_recent_issues(self):
        resp = _patched_tool({"uid": "u1"})(main.tool_list_recent_issues)
        self._assert_clean(asyncio.run(resp), "Failed to list issues. Please try again later.")

    def test_update_issue_status(self):
        resp = _patched_tool({"uid": "u1", "issue_identifier": "ENG-1", "new_status": "Done"})(
            main.tool_update_issue_status)
        self._assert_clean(asyncio.run(resp), "Failed to update issue. Please try again later.")

    def test_search_issues(self):
        resp = _patched_tool({"uid": "u1", "query": "bug"})(main.tool_search_issues)
        self._assert_clean(asyncio.run(resp), "Search failed. Please try again later.")

    def test_get_issue(self):
        resp = _patched_tool({"uid": "u1", "issue_identifier": "ENG-1"})(main.tool_get_issue)
        self._assert_clean(asyncio.run(resp), "Failed to get issue. Please try again later.")

    def test_add_comment(self):
        resp = _patched_tool({"uid": "u1", "issue_identifier": "ENG-1", "comment": "hi"})(
            main.tool_add_comment)
        self._assert_clean(asyncio.run(resp), "Failed to add comment. Please try again later.")


class HelperSanitizationTests(unittest.TestCase):
    def test_transport_failure_returns_fixed_message(self):
        class _Resp:
            pass

        exc = main.requests.exceptions.Timeout(SCARY_TRANSPORT)
        with mock.patch.object(main, "get_valid_access_token", return_value="tok"), \
             mock.patch.object(main.requests, "post", side_effect=exc):
            result = main.linear_graphql_request("u1", "query { x }")
        self.assertEqual(
            result,
            {"error": "Linear API request failed: could not reach the API. Please try again later."})
        self.assertNotIn("Errno", result["error"])

    def test_graphql_server_errors_still_surface(self):
        """Server-controlled GraphQL messages are not host internals; they pass through."""
        with mock.patch.object(main, "get_linear_tokens", return_value={"access_token": "t"}), \
             mock.patch.object(main, "linear_graphql_request", return_value={"error": "rate limited"}), \
             mock.patch.object(main, "get_issue_by_identifier",
                               return_value={"issue": {"id": "abc", "identifier": "ENG-1", "title": "T"}}):
            resp = asyncio.run(main.tool_add_comment(_FakeRequest(
                {"uid": "u1", "issue_identifier": "ENG-1", "comment": "hi"})))
        self.assertIn("rate limited", resp.error)
        self.assertNotIn("Errno", resp.error)


class BehaviorPreservationTests(unittest.TestCase):
    def test_validation_messages_unchanged(self):
        resp = asyncio.run(main.tool_create_issue(_FakeRequest({"uid": "u1"})))
        self.assertEqual(resp.error, "Issue title is required")
        resp = asyncio.run(main.tool_create_issue(_FakeRequest({})))
        self.assertEqual(resp.error, "User ID is required")

    def test_auth_gate_unchanged(self):
        with mock.patch.object(main, "get_linear_tokens", return_value=None):
            resp = asyncio.run(main.tool_list_my_issues(_FakeRequest({"uid": "u1"})))
        self.assertIn("connect your Linear account", resp.error)


if __name__ == "__main__":
    unittest.main()
