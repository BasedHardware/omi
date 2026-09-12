"""Hermetic regression for malformed `errors` payloads in Hive tool handlers.

tool_hive_create_task and tool_hive_update_task_status checked
`"errors" in result` then indexed `result["errors"][0]` - an empty list
or a non-list errors value crashed the error path itself, and the generic
except returned "list index out of range" instead of the API error.
The module's own get_graphql_error helper already encodes the correct
contract, so both handlers now use it.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


PLUGIN_DIR = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, PLUGIN_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ChatToolResponse:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error


class HiveProject:
    def __init__(self, id=None, name=None, **kw):
        self.id = id
        self.name = name
        for k, v in kw.items():
            setattr(self, k, v)


class HiveTask:
    def __init__(self, id=None, name=None, project_id=None, **kw):
        self.id = id
        self.name = name
        self.project_id = project_id
        for k, v in kw.items():
            setattr(self, k, v)


class ErrorsPayloadTests(unittest.TestCase):
    def setUp(self):
        fastapi = types.ModuleType("fastapi")
        app = Mock()
        for method in ("get", "post", "mount", "on_event"):
            getattr(app, method).side_effect = lambda *a, **k: lambda f: f
        fastapi.FastAPI = lambda **kwargs: app
        fastapi.Request = object
        fastapi.HTTPException = Exception
        fastapi.Query = fastapi.Form = lambda *a, **k: None
        responses = types.ModuleType("fastapi.responses")
        responses.HTMLResponse = responses.RedirectResponse = responses.JSONResponse = object
        staticfiles = types.ModuleType("fastapi.staticfiles")
        staticfiles.StaticFiles = Mock()
        templating = types.ModuleType("fastapi.templating")
        templating.Jinja2Templates = Mock()

        db = types.ModuleType("db")
        db.store_hive_credentials = db.delete_hive_credentials = Mock()
        db.get_hive_credentials = Mock(return_value={"workspace_id": "w1"})
        db.is_connected = Mock(return_value=True)
        db.store_default_project = Mock()
        db.get_default_project = Mock(return_value={"id": "p1", "name": "Default"})
        db.get_user_settings = Mock()

        models = types.ModuleType("models")
        models.ChatToolResponse = ChatToolResponse
        models.HiveProject = HiveProject
        models.HiveTask = HiveTask
        models.HiveAction = Mock

        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None

        modules = {
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "fastapi.staticfiles": staticfiles,
            "fastapi.templating": templating,
            "db": db,
            "models": models,
            "dotenv": dotenv,
            "requests": types.ModuleType("requests"),
        }
        originals = {name: sys.modules.get(name) for name in modules}
        sys.modules.update(modules)
        try:
            self.module = load("hive_main_under_test", "main.py")
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

    def run_tool(self, handler_name, body, rest_result):
        handler = getattr(self.module, handler_name)

        async def fake_json():
            return body

        request = Mock()
        request.json = fake_json
        with patch.object(
            self.module, "hive_rest_request", return_value=rest_result
        ):
            return asyncio.run(handler(request))

    def test_create_task_empty_errors_returns_clean_error(self):
        result = self.run_tool(
            "tool_hive_create_task",
            {"uid": "u1", "task_name": "t", "project_id": "p1"},
            {"errors": []},
        )
        self.assertIsNotNone(result.error)
        self.assertNotIn("list index", result.error)

    def test_create_task_non_list_errors(self):
        result = self.run_tool(
            "tool_hive_create_task",
            {"uid": "u1", "task_name": "t", "project_id": "p1"},
            {"errors": {"message": "boom"}},
        )
        self.assertIsNotNone(result.error)

    def test_create_task_populated_errors_surfaces_message(self):
        result = self.run_tool(
            "tool_hive_create_task",
            {"uid": "u1", "task_name": "t", "project_id": "p1"},
            {"errors": [{"message": "invalid project"}]},
        )
        self.assertIn("invalid project", result.error)

    def test_create_task_success_unchanged(self):
        result = self.run_tool(
            "tool_hive_create_task",
            {"uid": "u1", "task_name": "t", "project_id": "p1"},
            {"id": "a1"},
        )
        self.assertIsNone(result.error)
        self.assertIn("Created task", result.result)

    def test_update_task_empty_errors_returns_clean_error(self):
        result = self.run_tool(
            "tool_hive_update_task_status",
            {"uid": "u1", "task_name": "t", "task_id": "a1", "status": "completed"},
            {"errors": []},
        )
        self.assertIsNotNone(result.error)
        self.assertNotIn("list index", result.error)

    def test_update_task_populated_errors_surfaces_message(self):
        result = self.run_tool(
            "tool_hive_update_task_status",
            {"uid": "u1", "task_name": "t", "task_id": "a1", "status": "completed"},
            {"errors": [{"message": "not allowed"}]},
        )
        self.assertIn("not allowed", result.error)


if __name__ == "__main__":
    unittest.main()
