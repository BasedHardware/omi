"""Hermetic regression tests verifying error sanitization in plugins/omi-linear-app.
Ensures internal exception details, network errors, and sensitive tokens are not leaked to users.
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
    requests.exceptions = exceptions
    requests.post = lambda *a, **k: None
    requests.get = lambda *a, **k: None
    requests.RequestException = _RequestException
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


class LinearErrorSanitizationTests(unittest.TestCase):
    """Verify that network exceptions and unexpected tool errors return sanitized messages."""

    def test_graphql_request_exception_sanitized(self):
        with mock.patch.object(main, "get_valid_access_token", return_value="secret-tok"):
            with mock.patch.object(main.requests, "post", side_effect=main.requests.RequestException("connection refused: 10.0.1.5:80")):
                res = main.linear_graphql_request("user1", "query { viewer { id } }")
                self.assertEqual(res, {"error": "Request failed"})
                self.assertNotIn("10.0.1.5", str(res))

    def test_tool_create_issue_exception_sanitized(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(side_effect=RuntimeError("internal crash in JSON parsing"))
        res = asyncio.run(main.tool_create_issue(req))
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to create issue")
        self.assertNotIn("internal crash", res.error)

    def test_tool_list_my_issues_exception_sanitized(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(side_effect=RuntimeError("internal crash in user resolution"))
        res = asyncio.run(main.tool_list_my_issues(req))
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to list issues")
        self.assertNotIn("internal crash", res.error)

    def test_tool_list_recent_issues_exception_sanitized(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(side_effect=RuntimeError("internal crash in team resolution"))
        res = asyncio.run(main.tool_list_recent_issues(req))
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to list issues")
        self.assertNotIn("internal crash", res.error)

    def test_tool_update_issue_status_exception_sanitized(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(side_effect=RuntimeError("internal crash in state resolution"))
        res = asyncio.run(main.tool_update_issue_status(req))
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to update issue")
        self.assertNotIn("internal crash", res.error)

    def test_tool_search_issues_exception_sanitized(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(side_effect=RuntimeError("internal crash in search query"))
        res = asyncio.run(main.tool_search_issues(req))
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Search failed")
        self.assertNotIn("internal crash", res.error)

    def test_tool_get_issue_exception_sanitized(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(side_effect=RuntimeError("internal crash in get issue"))
        res = asyncio.run(main.tool_get_issue(req))
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to get issue")
        self.assertNotIn("internal crash", res.error)

    def test_tool_add_comment_exception_sanitized(self):
        req = mock.Mock()
        req.json = mock.AsyncMock(side_effect=RuntimeError("internal crash in add comment"))
        res = asyncio.run(main.tool_add_comment(req))
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to add comment")
        self.assertNotIn("internal crash", res.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
