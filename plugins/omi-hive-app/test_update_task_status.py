from pathlib import Path
import asyncio
import importlib.util
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

# Stub external dependencies so the suite runs hermetically on pure stdlib
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

# Stub db module functions
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


class TestHiveUpdateTaskStatus(unittest.TestCase):

    def setUp(self):
        self.uid = "test_user_123"

    @patch.object(main, "is_connected", return_value=True)
    @patch.object(main, "hive_rest_request")
    @patch.object(main, "get_hive_credentials", return_value={"workspace_id": "ws_1"})
    def test_update_exact_match_chosen_over_partials(self, mock_creds, mock_rest, mock_conn):
        """When an exact title match exists alongside partial matches, the exact match is updated."""
        mock_rest.side_effect = [
            # 1st call: search_tasks GET workspaces/ws_1/actions
            [
                {"_id": "act_1", "title": "Don't deploy on Friday", "status": "todo"},
                {"_id": "act_2", "title": "Deploy", "status": "todo"},
                {"_id": "act_3", "title": "Deploy staging", "status": "todo"},
            ],
            # 2nd call: PUT actions/act_2
            {"_id": "act_2", "status": "completed"}
        ]

        req = FakeRequest({"uid": self.uid, "task_name": "Deploy", "status": "done"})
        res = asyncio.run(main.tool_hive_update_task_status(req))

        self.assertIsNone(res.error)
        self.assertIn("Updated task **Deploy** status to **completed**", res.result)
        mock_rest.assert_called_with(self.uid, "PUT", "actions/act_2", data={"status": "completed"})

    @patch.object(main, "is_connected", return_value=True)
    @patch.object(main, "hive_rest_request")
    @patch.object(main, "get_hive_credentials", return_value={"workspace_id": "ws_1"})
    def test_update_ambiguous_partial_matches_rejected(self, mock_creds, mock_rest, mock_conn):
        """When multiple partial matches exist and no exact match, disambiguation is returned and no task is mutated."""
        mock_rest.return_value = [
            {"_id": "act_1", "title": "Don't deploy on Friday", "status": "todo"},
            {"_id": "act_3", "title": "Deploy staging", "status": "todo"},
        ]

        req = FakeRequest({"uid": self.uid, "task_name": "deploy", "status": "done"})
        res = asyncio.run(main.tool_hive_update_task_status(req))

        self.assertIsNotNone(res.error)
        self.assertIn("Multiple tasks matching 'deploy' found", res.error)
        self.assertIn("Don't deploy on Friday", res.error)
        self.assertIn("act_1", res.error)
        self.assertIn("Deploy staging", res.error)
        self.assertIn("act_3", res.error)
        self.assertEqual(mock_rest.call_count, 1)

    @patch.object(main, "is_connected", return_value=True)
    @patch.object(main, "hive_rest_request")
    @patch.object(main, "get_hive_credentials", return_value={"workspace_id": "ws_1"})
    def test_update_ambiguous_duplicate_exact_matches_rejected(self, mock_creds, mock_rest, mock_conn):
        """When multiple tasks share the exact same title, disambiguation is returned with IDs."""
        mock_rest.return_value = [
            {"_id": "act_10", "title": "Release v1.0", "status": "todo"},
            {"_id": "act_11", "title": "Release v1.0", "status": "todo"},
        ]

        req = FakeRequest({"uid": self.uid, "task_name": "Release v1.0", "status": "completed"})
        res = asyncio.run(main.tool_hive_update_task_status(req))

        self.assertIsNotNone(res.error)
        self.assertIn("Multiple tasks found with exact name 'Release v1.0'", res.error)
        self.assertIn("act_10", res.error)
        self.assertIn("act_11", res.error)
        self.assertEqual(mock_rest.call_count, 1)

    @patch.object(main, "is_connected", return_value=True)
    @patch.object(main, "hive_rest_request")
    @patch.object(main, "get_hive_credentials", return_value={"workspace_id": "ws_1"})
    def test_update_single_partial_match_resolves(self, mock_creds, mock_rest, mock_conn):
        """When exactly one partial match exists, it resolves and updates."""
        mock_rest.side_effect = [
            [{"_id": "act_42", "title": "Fix memory leak on login", "status": "todo"}],
            {"_id": "act_42", "status": "completed"}
        ]

        req = FakeRequest({"uid": self.uid, "task_name": "memory leak", "status": "done"})
        res = asyncio.run(main.tool_hive_update_task_status(req))

        self.assertIsNone(res.error)
        self.assertIn("Fix memory leak on login", res.result)
        mock_rest.assert_called_with(self.uid, "PUT", "actions/act_42", data={"status": "completed"})

    @patch.object(main, "is_connected", return_value=True)
    @patch.object(main, "hive_rest_request")
    def test_update_by_explicit_task_id(self, mock_rest, mock_conn):
        """When task_id is provided, it updates directly without searching."""
        mock_rest.return_value = {"_id": "act_99", "status": "completed"}

        req = FakeRequest({"uid": self.uid, "task_id": "act_99", "status": "in progress"})
        res = asyncio.run(main.tool_hive_update_task_status(req))

        self.assertIsNone(res.error)
        self.assertIn("act_99", res.result)
        self.assertIn("in progress", res.result)
        mock_rest.assert_called_once_with(self.uid, "PUT", "actions/act_99", data={"status": "in progress"})

    @patch.object(main, "is_connected", return_value=True)
    @patch.object(main, "hive_rest_request")
    @patch.object(main, "get_hive_credentials", return_value={"workspace_id": "ws_1"})
    def test_search_and_get_tasks_print_ids(self, mock_creds, mock_rest, mock_conn):
        """hive_search and hive_get_tasks include task IDs in their output."""
        # 1. Search
        mock_rest.return_value = [
            {"_id": "act_55", "title": "Audit auth logs", "status": "todo"}
        ]
        search_req = FakeRequest({"uid": self.uid, "query": "Audit"})
        search_res = asyncio.run(main.tool_hive_search(search_req))
        self.assertIsNone(search_res.error)
        self.assertIn("ID: `act_55`", search_res.result)

        # 2. Get tasks
        mock_rest.return_value = [
            {"_id": "act_77", "title": "Configure CI", "status": "in progress"}
        ]
        get_req = FakeRequest({"uid": self.uid, "project_id": "proj_1"})
        get_res = asyncio.run(main.tool_hive_get_tasks(get_req))
        self.assertIsNone(get_res.error)
        self.assertIn("ID: `act_77`", get_res.result)


if __name__ == "__main__":
    unittest.main()
