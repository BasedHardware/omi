"""Hermetic regression tests for plugins/omi-linear-app/main.py error handling.

Standard library only: requests, dotenv, fastapi, pydantic, and
omi_plugin_sdk are replaced with minimal stubs before importing the module
under test so the suite runs without site-packages (the manifest lane runs
plain python3). db.py is importable as-is (redis import is optional).

Covers the error-path crash in linear_graphql_request: `if "errors" in
result` indexed result["errors"][0] without checking the value's shape, so
`"errors": []` raised IndexError, `"errors": null` raised TypeError, and a
non-list errors payload raised TypeError — all inside the handler that
exists to produce clean error responses.
"""

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


class _Resp:
    def __init__(self, status_code=200, payload=None, content=b"x"):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = content
        self.text = "body"

    def json(self):
        return self._payload


def _call(payload):
    with mock.patch.object(main, "get_valid_access_token", return_value="tok"), mock.patch.object(
        main.requests, "post", return_value=_Resp(200, payload)
    ):
        return main.linear_graphql_request("u1", "query { x }")


class GraphqlErrorsShapeTests(unittest.TestCase):
    def test_errors_list_returns_first_message(self):
        result = _call({"errors": [{"message": "rate limited"}]})
        self.assertEqual(result, {"error": "rate limited"})

    def test_empty_errors_list_falls_through_to_data(self):
        result = _call({"errors": [], "data": {"viewer": {"id": "u1"}}})
        self.assertEqual(result, {"viewer": {"id": "u1"}})

    def test_null_errors_falls_through_to_data(self):
        result = _call({"errors": None, "data": {"a": 1}})
        self.assertEqual(result, {"a": 1})

    def test_non_list_errors_returns_generic_error(self):
        result = _call({"errors": {"message": "bad"}})
        self.assertEqual(result, {"error": "GraphQL error"})

    def test_errors_list_of_non_dicts_returns_generic_error(self):
        result = _call({"errors": ["boom"]})
        self.assertEqual(result, {"error": "GraphQL error"})

    def test_no_errors_returns_data(self):
        result = _call({"data": {"ok": True}})
        self.assertEqual(result, {"ok": True})


if __name__ == "__main__":
    unittest.main()
