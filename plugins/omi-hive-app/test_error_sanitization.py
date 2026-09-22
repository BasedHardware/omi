"""Hermetic tests ensuring error sanitization across omi-hive-app.

Tests verify that internal exceptions, request details, and system errors
are never leaked in API response payloads or chat tool responses.
"""

from pathlib import Path
import asyncio
import importlib.util
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

# Stub external dependencies so the suite runs hermetically on pure stdlib
_requests = types.ModuleType("requests")
_requests.get = _requests.post = _requests.put = _requests.delete = _requests.request = MagicMock()
_requests.Timeout = type("Timeout", (Exception,), {})
_requests.RequestException = type("RequestException", (Exception,), {})

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *args, **kwargs: None

_fastapi = types.ModuleType("fastapi")


class _FastAPI:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda fn: fn

    def post(self, *args, **kwargs):
        return lambda fn: fn

    def mount(self, *args, **kwargs):
        pass


_fastapi.FastAPI = _FastAPI
_fastapi.HTTPException = Exception
_fastapi.Request = MagicMock
_fastapi.Query = lambda *args, **kwargs: None
_fastapi.Form = lambda *args, **kwargs: None

_fastapi_responses = types.ModuleType("fastapi.responses")
_fastapi_responses.HTMLResponse = MagicMock
_fastapi_responses.RedirectResponse = MagicMock
_fastapi_responses.JSONResponse = MagicMock

_fastapi_staticfiles = types.ModuleType("fastapi.staticfiles")
_fastapi_staticfiles.StaticFiles = MagicMock

_fastapi_templating = types.ModuleType("fastapi.templating")
_fastapi_templating.Jinja2Templates = MagicMock

_pydantic = types.ModuleType("pydantic")


class _BaseModel:
    def __init__(self, **data):
        for k, v in data.items():
            setattr(self, k, v)

    def dict(self, *args, **kwargs):
        return self.__dict__


_pydantic.BaseModel = _BaseModel
_pydantic.Field = lambda *args, **kwargs: None

_omi_sdk = types.ModuleType("omi_plugin_sdk")
_omi_sdk_models = types.ModuleType("omi_plugin_sdk.models")
_omi_sdk_models.Conversation = _BaseModel
_omi_sdk_models.EndpointResponse = _BaseModel
_omi_sdk_models.Structured = _BaseModel
_omi_sdk_models.TranscriptSegment = _BaseModel
_omi_sdk.models = _omi_sdk_models

_db = types.ModuleType("db")
_db.store_hive_credentials = MagicMock()
_db.get_hive_credentials = MagicMock(return_value={"api_key": "k", "hive_user_id": "u", "workspace_id": "ws_1"})
_db.delete_hive_credentials = MagicMock()
_db.is_connected = MagicMock(return_value=True)
_db.store_default_project = MagicMock()
_db.get_default_project = MagicMock(return_value=None)
_db.get_user_settings = MagicMock(return_value={})

_modules = {
    "requests": _requests,
    "dotenv": _dotenv,
    "fastapi": _fastapi,
    "fastapi.responses": _fastapi_responses,
    "fastapi.staticfiles": _fastapi_staticfiles,
    "fastapi.templating": _fastapi_templating,
    "pydantic": _pydantic,
    "omi_plugin_sdk": _omi_sdk,
    "omi_plugin_sdk.models": _omi_sdk_models,
    "db": _db,
}


def _load_module(name: str, path: Path):
    with patch.dict(sys.modules, _modules):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod


_app_dir = Path(__file__).resolve().parent
_models = _load_module("models", _app_dir / "models.py")
_modules["models"] = _models
_main = _load_module("main", _app_dir / "main.py")


class TestHiveErrorSanitization(unittest.TestCase):
    def test_make_graphql_request_sanitizes_request_exception(self):
        with patch.object(_main.requests, "post", side_effect=_requests.RequestException("Sensitive proxy leak 10.0.0.1")):
            res = _main.hive_graphql_request("test_key", "query {}")
            self.assertEqual(res, {"errors": [{"message": "API request failed"}]})
            self.assertNotIn("10.0.0.1", str(res))

    def test_make_graphql_request_sanitizes_unexpected_exception(self):
        with patch.object(_main.requests, "post", side_effect=Exception("Critical system error at 0xdeadbeef")):
            res = _main.hive_graphql_request("test_key", "query {}")
            self.assertEqual(res, {"errors": [{"message": "Unexpected error occurred"}]})
            self.assertNotIn("0xdeadbeef", str(res))

    def test_hive_rest_request_sanitizes_exception(self):
        with patch.object(_main, "get_hive_credentials", return_value={"api_key": "k", "hive_user_id": "u"}), \
             patch.object(_main.requests, "request", side_effect=Exception("Disk full on /var/log/hive")):
            res = _main.hive_rest_request("uid_1", "GET", "actions")
            self.assertEqual(res, {"errors": [{"message": "API request failed"}]})
            self.assertNotIn("/var/log", str(res))

    def test_tool_hive_get_projects_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal parse crash"))
        res = asyncio.run(_main.tool_hive_get_projects(req))
        self.assertEqual(res.error, "Failed to get projects. Please try again.")

    def test_tool_hive_get_tasks_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal tasks crash"))
        res = asyncio.run(_main.tool_hive_get_tasks(req))
        self.assertEqual(res.error, "Failed to get tasks. Please try again.")

    def test_tool_hive_create_task_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal create crash"))
        res = asyncio.run(_main.tool_hive_create_task(req))
        self.assertEqual(res.error, "Failed to create task. Please try again.")

    def test_tool_hive_search_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal search crash"))
        res = asyncio.run(_main.tool_hive_search(req))
        self.assertEqual(res.error, "Search failed. Please try again.")

    def test_tool_hive_update_task_status_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal update crash"))
        res = asyncio.run(_main.tool_hive_update_task_status(req))
        self.assertEqual(res.error, "Failed to update task. Please try again.")


if __name__ == "__main__":
    unittest.main()
