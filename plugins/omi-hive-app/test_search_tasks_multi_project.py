"""database `search_tasks` used a single `workspaces/{id}/actions?limit=50` call — a cap on
the 50 most recently *touched* actions across the whole workspace, not per project. A task
outside that window was silently unfindable by exact name no matter how small its own
project was, breaking `tool_hive_update_task_status`'s name lookup and
`tool_hive_create_task`'s parent-task lookup on any workspace with more than 50 actions in
flight, even though the caller only ever asked about one specific, existing task.

`search_tasks` now fetches per project (the same `projectId`-scoped request
`get_project_tasks` already uses), which is what these tests exercise directly: a match that
only exists in the workspace's second project, one project erroring without losing matches
from the others, and the exact-match early-exit not cutting the scan short while still
ambiguous.
"""

from pathlib import Path
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


TWO_PROJECTS = [{"id": "proj_1", "name": "Frontend"}, {"id": "proj_2", "name": "Backend"}]


class TestSearchTasksScansEveryProject(unittest.TestCase):
    def setUp(self):
        self.uid = "test_user_123"

    @patch.object(main, "get_hive_credentials", return_value={"workspace_id": "ws_1"})
    @patch.object(main, "hive_rest_request")
    def test_finds_an_exact_match_that_only_exists_in_the_second_project(self, mock_rest, mock_creds):
        mock_rest.side_effect = [
            TWO_PROJECTS,
            # proj_1: unrelated actions only
            [{"_id": "a1", "title": "Update README", "status": "todo"}],
            # proj_2: the task the caller actually asked about
            [{"_id": "a2", "title": "Rotate API keys", "status": "todo"}],
        ]

        results = main.search_tasks(self.uid, "Rotate API keys")

        self.assertEqual([t.id for t in results], ["a2"])
        # Both projects' actions endpoints were queried, correctly scoped.
        self.assertEqual(
            mock_rest.call_args_list[1].kwargs["params"],
            {"projectId": "proj_1", "limit": 50},
        )
        self.assertEqual(
            mock_rest.call_args_list[2].kwargs["params"],
            {"projectId": "proj_2", "limit": 50},
        )

    @patch.object(main, "get_hive_credentials", return_value={"workspace_id": "ws_1"})
    @patch.object(main, "hive_rest_request")
    def test_one_projects_error_does_not_lose_matches_from_another(self, mock_rest, mock_creds):
        mock_rest.side_effect = [
            TWO_PROJECTS,
            {"errors": [{"message": "project archived"}]},
            [{"_id": "a2", "title": "Rotate API keys", "status": "todo"}],
        ]

        results = main.search_tasks(self.uid, "Rotate API keys")

        self.assertEqual([t.id for t in results], ["a2"])

    @patch.object(main, "get_hive_credentials", return_value={"workspace_id": "ws_1"})
    @patch.object(main, "hive_rest_request")
    def test_ambiguous_partial_matches_across_projects_are_all_returned(self, mock_rest, mock_creds):
        """No exact match anywhere means every project must be scanned before returning."""
        mock_rest.side_effect = [
            TWO_PROJECTS,
            [{"_id": "a1", "title": "Deploy staging", "status": "todo"}],
            [{"_id": "a2", "title": "Deploy prod", "status": "todo"}],
        ]

        results = main.search_tasks(self.uid, "deploy")

        self.assertEqual({t.id for t in results}, {"a1", "a2"})
        self.assertEqual(mock_rest.call_count, 3)

    @patch.object(main, "get_hive_credentials", return_value=None)
    @patch.object(main, "hive_rest_request")
    def test_no_workspace_returns_empty_without_a_request(self, mock_rest, mock_creds):
        self.assertEqual(main.search_tasks(self.uid, "anything"), [])
        mock_rest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
