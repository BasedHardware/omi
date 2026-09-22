"""Hermetic tests: Hive app endpoints must never leak raw exception text."""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from pathlib import Path
import asyncio
import importlib.util
import types
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

_SENTINEL = "FATAL: /var/secrets/twitter_key.json: connection reset by 192.168.1.99:443"

# Stub external dependencies
_requests = types.ModuleType("requests")
_requests.get = _requests.post = _requests.put = _requests.delete = None

class RequestException(Exception):
    pass

class Timeout(RequestException):
    pass

_requests.RequestException = RequestException
_requests.Timeout = Timeout

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

# Stub db module functions
_db = types.ModuleType("db")
_db.store_hive_credentials = MagicMock()
_db.get_hive_credentials = MagicMock(return_value={"workspace_id": "ws_1", "api_key": "test_key", "hive_user_id": "u_1"})
_db.delete_hive_credentials = MagicMock()
_db.is_connected = MagicMock(return_value=True)
_db.store_default_project = MagicMock()
_db.get_default_project = MagicMock(return_value=None)
_db.get_user_settings = MagicMock(return_value={})

app_dir = Path(__file__).parent
models_file = app_dir / "models.py"
main_file = app_dir / "main.py"

spec_models = importlib.util.spec_from_file_location("models", models_file)
models = importlib.util.module_from_spec(spec_models)

spec_main = importlib.util.spec_from_file_location("main", main_file)
main = importlib.util.module_from_spec(spec_main)

modules_to_patch = {
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
    "models": models,
}

with patch.dict(sys.modules, modules_to_patch):
    spec_models.loader.exec_module(models)
    spec_main.loader.exec_module(main)


def _assert_no_leak(test_case, obj, context=""):
    text = str(obj)
    test_case.assertNotIn(_SENTINEL, text, f"Exception text leaked in {context}")
    test_case.assertNotIn("192.168.1.99", text, f"Internal IP leaked in {context}")
    test_case.assertNotIn("/var/secrets/", text, f"Internal path leaked in {context}")


class HiveErrorHandlingTests(unittest.TestCase):

    def test_hive_graphql_request_exception(self):
        with patch.object(_requests, "post", side_effect=RequestException(_SENTINEL)):
            res = main.hive_graphql_request("u1", "query { test }")
            self.assertIn("errors", res)
            err_msg = res["errors"][0]["message"]
            _assert_no_leak(self, err_msg, "hive_graphql_request")
            self.assertEqual(err_msg, "Request failed")

    def test_hive_graphql_unexpected_exception(self):
        with patch.object(_requests, "post", side_effect=RuntimeError(_SENTINEL)):
            res = main.hive_graphql_request("u1", "query { test }")
            self.assertIn("errors", res)
            err_msg = res["errors"][0]["message"]
            _assert_no_leak(self, err_msg, "hive_graphql_request unexpected")
            self.assertEqual(err_msg, "Unexpected error")

    def test_hive_rest_request_exception(self):
        with patch.object(_requests, "get", side_effect=RequestException(_SENTINEL)):
            res = main.hive_rest_request("u1", "GET", "test")
            self.assertIn("errors", res)
            err_msg = res["errors"][0]["message"]
            _assert_no_leak(self, err_msg, "hive_rest_request")
            self.assertEqual(err_msg, "Request failed")

    def test_tool_hive_create_task_handles_failure(self):
        async def run():
            with patch.object(main, "get_user_projects", return_value=[main.HiveProject(id="p1", name="Project 1")]):
                with patch.object(main, "hive_rest_request", return_value={"errors": [{"message": "Request failed"}]}):
                    mock_req = MagicMock()
                    mock_req.query_params = {"uid": "u1"}
                    mock_req.json = AsyncMock(return_value={"uid": "u1", "task_name": "Test", "project_name": "Project 1"})
                    resp = await main.tool_hive_create_task(mock_req)
                    self.assertIsNotNone(resp.error)
                    _assert_no_leak(self, resp.error, "tool_hive_create_task")
                    self.assertIn("Failed to create task", resp.error)
        asyncio.run(run())

    def test_tool_hive_update_task_status_handles_failure(self):
        async def run():
            with patch.object(main, "hive_rest_request", return_value={"errors": [{"message": "Request failed"}]}):
                mock_req = MagicMock()
                mock_req.query_params = {"uid": "u1"}
                mock_req.json = AsyncMock(return_value={"uid": "u1", "task_id": "t1", "status": "done"})
                resp = await main.tool_hive_update_task_status(mock_req)
                self.assertIsNotNone(resp.error)
                _assert_no_leak(self, resp.error, "tool_hive_update_task_status")
                self.assertIn("Failed to update task", resp.error)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
