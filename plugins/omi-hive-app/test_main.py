"""
Hermetic test suite for the Hive integration app.

Exercises manifest schema compliance, project/task queries, and
tool endpoint flows without network or external services.
Runs cleanly under pure standard library Python (including under python3 -S).
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

        def mount(self, *args, **kwargs):
            pass

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class HTTPException(Exception):
        def __init__(self, status_code=400, detail=""):
            self.status_code = status_code
            self.detail = detail

    class Request:
        def __init__(self, json_data=None):
            self._json = json_data or {}

        async def json(self):
            return self._json

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.HTTPException = HTTPException
    fastapi.Query = lambda default=None, **kwargs: default
    fastapi.Form = lambda default=None, **kwargs: default

    staticfiles = ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = lambda **kwargs: None

    templating = ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda **kwargs: None

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.RedirectResponse = str
    responses.JSONResponse = dict

    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    requests = ModuleType("requests")
    requests.get = Mock()
    requests.post = Mock()

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    db = ModuleType("db")
    db.store_hive_credentials = Mock()
    db.get_hive_credentials = Mock(return_value=None)
    db.delete_hive_credentials = Mock()
    db.is_connected = Mock(return_value=False)
    db.store_default_project = Mock()
    db.get_default_project = Mock(return_value=None)
    db.get_user_settings = Mock(return_value={})

    models = ModuleType("models")

    class ChatToolResponse(BaseModel):
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    class HiveProject(BaseModel):
        def __init__(self, id="", name="", description=None, status=None, workspace_id=None):
            self.id = id
            self.name = name
            self.description = description
            self.status = status
            self.workspace_id = workspace_id

    class HiveTask(BaseModel):
        def __init__(self, id="", title="", name="", description=None, status="todo", deadline=None, project_id="", assignees=None):
            self.id = id
            self.title = title or name
            self.name = name or title
            self.description = description
            self.status = status
            self.deadline = deadline
            self.project_id = project_id
            self.assignees = assignees or []

    models.ChatToolResponse = ChatToolResponse
    models.HiveProject = HiveProject
    models.HiveTask = HiveTask
    models.HiveAction = BaseModel

    stubs = {
        "fastapi": fastapi,
        "fastapi.staticfiles": staticfiles,
        "fastapi.templating": templating,
        "fastapi.responses": responses,
        "pydantic": pydantic,
        "requests": requests,
        "dotenv": dotenv,
        "db": db,
        "models": models,
    }

    app_path = Path(__file__).resolve().parent / "main.py"
    spec = importlib.util.spec_from_file_location("hive_main", app_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module, stubs


app_module, stubs = load_app()


class HiveAppTests(unittest.TestCase):
    def test_manifest_schema_compliance(self):
        coro = app_module.get_omi_tools_manifest()
        manifest = asyncio.run(coro)
        self.assertIn("tools", manifest)
        self.assertEqual(len(manifest["tools"]), 5)

        for tool in manifest["tools"]:
            self.assertIn("name", tool)
            self.assertIn("parameters", tool)
            params = tool["parameters"]
            self.assertEqual(
                params.get("type"),
                "object",
                f"Tool {tool['name']} parameters missing 'type': 'object'",
            )
            self.assertIn("properties", params)
            self.assertIn("required", params)

    def test_get_projects_requires_uid(self):
        req = stubs["fastapi"].Request({})
        resp = asyncio.run(app_module.tool_hive_get_projects(req))
        self.assertIn("User ID is required", resp.error)

    def test_get_projects_not_connected(self):
        req = stubs["fastapi"].Request({"uid": "user123"})
        with patch.object(app_module, "is_connected", return_value=False):
            resp = asyncio.run(app_module.tool_hive_get_projects(req))
            self.assertIn("connect your Hive account first", resp.error)

    def test_get_projects_success_empty(self):
        req = stubs["fastapi"].Request({"uid": "user123"})
        with patch.object(app_module, "is_connected", return_value=True):
            with patch.object(app_module, "get_user_projects", return_value=[]):
                resp = asyncio.run(app_module.tool_hive_get_projects(req))
                self.assertIn("don't have any projects yet", resp.result)

    def test_get_projects_success_with_data(self):
        req = stubs["fastapi"].Request({"uid": "user123"})
        with patch.object(app_module, "is_connected", return_value=True):
            project = stubs["models"].HiveProject(id="p1", name="Engineering", description="Core dev", status="active")
            with patch.object(app_module, "get_user_projects", return_value=[project]):
                resp = asyncio.run(app_module.tool_hive_get_projects(req))
                self.assertIn("Engineering", resp.result)
                self.assertIn("active", resp.result)

    def test_create_task_requires_task_name(self):
        req = stubs["fastapi"].Request({"uid": "user123"})
        resp = asyncio.run(app_module.tool_hive_create_task(req))
        self.assertIn("Task name is required", resp.error)

    def test_create_task_success(self):
        req = stubs["fastapi"].Request({
            "uid": "user123",
            "task_name": "Implement Oauth",
            "project_name": "Backend",
        })
        project = stubs["models"].HiveProject(id="p_backend", name="Backend")
        with patch.object(app_module, "is_connected", return_value=True):
            with patch.object(app_module, "find_project_by_name", return_value=project):
                with patch.object(app_module, "get_hive_credentials", return_value={"workspace_id": "ws_1"}):
                    with patch.object(app_module, "hive_rest_request", return_value={"id": "t_1", "title": "Implement Oauth"}):
                        resp = asyncio.run(app_module.tool_hive_create_task(req))
                        self.assertIn("Created task", resp.result)
                        self.assertIn("Implement Oauth", resp.result)


if __name__ == "__main__":
    unittest.main()
