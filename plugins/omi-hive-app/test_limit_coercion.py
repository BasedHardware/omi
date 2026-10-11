"""Hermetic regression tests for the Hive chat-tool limit coercion.

Standard library only: requests, dotenv, fastapi, pydantic, db, models, and the
Omi plugin SDK are stubbed before loading the module under test so the suite runs
under plain python3 (the manifest lane).

Covers the hive-app limit defect: ``tool_hive_get_projects``,
``tool_hive_get_tasks``, and ``tool_hive_search`` read the caller limit with
a raw ``body.get("limit", 10)``. dict.get returns None - not the default - when the key
is present with a JSON null, which is what the backend sends for an omitted
optional parameter, and ``items[:None]`` is a legal slice that silently returns
*every* row instead of the documented page size. A string limit reached the slice
uncoerced and raised TypeError, surfacing as "Failed to get projects: ...".
"""
from pathlib import Path
import asyncio
import importlib.util
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

_requests = types.ModuleType("requests")
_requests.get = _requests.post = _requests.put = _requests.delete = None

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
_db.get_hive_credentials = MagicMock(return_value={"workspace_id": "ws_1"})
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


class FakeRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    async def json(self):
        return self._json_data


def make_projects(n=25):
    return [main.HiveProject(id=f"p{i}", name=f"Project {i}") for i in range(1, n + 1)]


class TestCoerceLimit(unittest.TestCase):
    """The helper itself: null and junk must resolve to the documented default."""

    def test_null_and_absent_resolve_to_default(self):
        self.assertEqual(main.coerce_limit(None, default=10), 10)

    def test_non_numeric_falls_back_to_default(self):
        for bad in ("bogus", [1], {"x": 1}, object()):
            with self.subTest(value=repr(bad)):
                self.assertEqual(main.coerce_limit(bad, default=10), 10)

    def test_string_numerals_are_parsed(self):
        self.assertEqual(main.coerce_limit("7", default=10), 7)

    def test_clamping(self):
        self.assertEqual(main.coerce_limit(999, min_val=1, max_val=50), 50)
        self.assertEqual(main.coerce_limit(-4, min_val=1, max_val=50), 1)
        self.assertEqual(main.coerce_limit(0, min_val=1, max_val=50), 1)


class TestLimitNeverReachesASliceUncoerced(unittest.TestCase):
    """Each handler must page at the documented size, not dump every row."""

    def run_projects(self, payload):
        body = {"uid": "u1"}
        body.update(payload)
        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "get_user_projects", return_value=make_projects(25)):
            return asyncio.run(main.tool_hive_get_projects(FakeRequest(body)))

    def test_null_limit_returns_the_documented_page_not_every_row(self):
        response = self.run_projects({"limit": None})
        self.assertIsNone(response.error)
        # 10 rows by default; before the fix items[:None] returned all 25.
        self.assertIn("Project 10", response.result)
        self.assertNotIn("Project 11", response.result)

    def test_string_limit_is_honoured(self):
        response = self.run_projects({"limit": "3"})
        self.assertIsNone(response.error)
        self.assertIn("Project 3", response.result)
        self.assertNotIn("Project 4", response.result)

    def test_over_cap_limit_is_clamped(self):
        response = self.run_projects({"limit": 999})
        self.assertIsNone(response.error)
        self.assertIn("Project 25", response.result)

    def test_junk_limit_falls_back_instead_of_raising(self):
        response = self.run_projects({"limit": "5 } } { x"})
        self.assertIsNone(response.error, "a junk limit must not surface as an error")
        self.assertIn("Project 10", response.result)
        self.assertNotIn("Project 11", response.result)

    def test_search_handler_passes_a_coerced_int_downstream(self):
        """search_tasks does the slicing, so assert the value it receives."""
        body = {"uid": "u1", "query": "report", "limit": None}
        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[main.HiveTask(id="t1", name="Task 1")]) as mocked:
            response = asyncio.run(main.tool_hive_search(FakeRequest(body)))
        self.assertIsNone(response.error)
        passed = mocked.call_args[0][2]
        self.assertIsInstance(passed, int)
        self.assertEqual(passed, 10, "null limit must reach search_tasks as the documented default")

    def test_search_handler_clamps_a_junk_limit(self):
        body = {"uid": "u1", "query": "report", "limit": "not-a-number"}
        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[main.HiveTask(id="t1", name="Task 1")]) as mocked:
            response = asyncio.run(main.tool_hive_search(FakeRequest(body)))
        self.assertIsNone(response.error)
        self.assertEqual(mocked.call_args[0][2], 10)


if __name__ == "__main__":
    unittest.main()
