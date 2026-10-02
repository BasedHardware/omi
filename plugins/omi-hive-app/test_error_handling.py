"""Hermetic error-handling regression suite for omi-hive-app.

Raw exception text must never reach a client. `hive_graphql_request` answered
request failures with `f"Request failed: {str(e)}"` / `f"Unexpected error: {str(e)}"`,
and the tool handlers surface that message verbatim
(`Failed to create task: Request failed: <raw exception>`), reflecting internal
socket errors, filesystem paths and provider details into the responses the OMI
backend hands to the model/client. The helper now logs the detail server-side and
answers with a fixed message; the handler assertions below pin that no handler can
reintroduce the leak through its own response path.

Standard library only: requests, dotenv, fastapi, pydantic, db, models, and the
Omi plugin SDK are stubbed before loading the module under test so the suite runs
under plain python3 (the manifest lane).

Run: python3 plugins/omi-hive-app/test_error_handling.py
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

APP_DIR = Path(__file__).parent

SECRET_TRACE = "/srv/app/.secrets/hive_credentials.json"
LEAK_MARKERS = (SECRET_TRACE, "RuntimeError", "RequestException", "Traceback")


class _RequestException(Exception):
    pass


_requests = types.ModuleType("requests")
_requests.RequestException = _RequestException
_requests.Timeout = type("Timeout", (_RequestException,), {})
_requests.get = _requests.post = _requests.put = _requests.delete = MagicMock(
    side_effect=_RequestException(SECRET_TRACE)
)
_requests.request = MagicMock(side_effect=_RequestException(SECRET_TRACE))

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
_db.get_hive_credentials = MagicMock(return_value={"workspace_id": "ws_1", "api_key": "key", "hive_user_id": "u1"})
_db.delete_hive_credentials = MagicMock()
_db.is_connected = MagicMock(return_value=True)
_db.store_default_project = MagicMock()
_db.get_default_project = MagicMock(return_value=None)
_db.get_user_settings = MagicMock(return_value={})

_spec_models = importlib.util.spec_from_file_location("models", APP_DIR / "models.py")
models = importlib.util.module_from_spec(_spec_models)
_spec_main = importlib.util.spec_from_file_location("main", APP_DIR / "main.py")
main = importlib.util.module_from_spec(_spec_main)

with patch.dict(
    sys.modules,
    {
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
    },
):
    _spec_models.loader.exec_module(models)
    _spec_main.loader.exec_module(main)


class FakeRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    async def json(self):
        return self._json_data


class HiveErrorHandlingTests(unittest.TestCase):
    def assert_no_leak(self, response):
        text = f"{getattr(response, 'result', None)} {getattr(response, 'error', None)}"
        for marker in LEAK_MARKERS:
            self.assertNotIn(marker, text, f"response leaked {marker!r}: {text!r}")

    def test_graphql_helper_answers_generically(self):
        result = main.hive_graphql_request("api-key", "query { me { id } }")

        message = result["errors"][0]["message"]
        for marker in LEAK_MARKERS:
            self.assertNotIn(marker, message, f"helper leaked {marker!r}: {message!r}")

    def test_get_projects_does_not_reflect_the_exception(self):
        with patch.object(main, "get_user_projects", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(main.tool_hive_get_projects(FakeRequest({"uid": "u1"})))

        self.assert_no_leak(response)

    def test_get_tasks_does_not_reflect_the_exception(self):
        with patch.object(main, "get_project_tasks", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(
                main.tool_hive_get_tasks(FakeRequest({"uid": "u1", "project_id": "p1"}))
            )

        self.assert_no_leak(response)

    def test_create_task_does_not_reflect_the_exception(self):
        with patch.object(main, "hive_rest_request", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(
                main.tool_hive_create_task(
                    FakeRequest({"uid": "u1", "task_name": "Ship it", "project_id": "p1"})
                )
            )

        self.assert_no_leak(response)

    def test_search_does_not_reflect_the_exception(self):
        with patch.object(main, "search_tasks", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(main.tool_hive_search(FakeRequest({"uid": "u1", "query": "budget"})))

        self.assert_no_leak(response)

    def test_update_task_status_does_not_reflect_the_exception(self):
        with patch.object(main, "hive_rest_request", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(
                main.tool_hive_update_task_status(
                    FakeRequest({"uid": "u1", "task_id": "t1", "status": "done"})
                )
            )

        self.assert_no_leak(response)

    def test_no_except_block_interpolates_the_exception_into_a_response(self):
        """Pin the class, not the string: `type(e).__name__` logging is fine."""
        import ast
        import re

        source = (APP_DIR / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        response_calls = {"ChatToolResponse", "JSONResponse", "HTMLResponse", "HTTPException"}
        offenders = []
        for handler in ast.walk(tree):
            if not isinstance(handler, ast.ExceptHandler):
                continue
            suspects = []
            for stmt in ast.walk(handler):
                if isinstance(stmt, (ast.Return, ast.Raise)):
                    suspects.append(stmt)
                elif isinstance(stmt, ast.Call):
                    func = stmt.func
                    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                    if name in response_calls:
                        suspects.append(stmt)
            for stmt in suspects:
                segment = ast.get_source_segment(source, stmt) or ""
                if re.search(r"str\((e|exc)\)|\{(e|exc)\}", segment):
                    offenders.append(stmt.lineno)
        self.assertEqual(offenders, [], f"exception text interpolated in a response at lines {offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
