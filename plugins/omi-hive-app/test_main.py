from pathlib import Path
import asyncio
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

# Lightweight stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# requiring FastAPI, requests, pydantic, dotenv, or omi_plugin_sdk.

if "dotenv" not in sys.modules:
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv

if "requests" not in sys.modules:
    requests = types.ModuleType("requests")
    requests.get = lambda *args, **kwargs: None
    requests.post = lambda *args, **kwargs: None
    requests.put = lambda *args, **kwargs: None
    requests.delete = lambda *args, **kwargs: None
    sys.modules["requests"] = requests

if "omi_plugin_sdk" not in sys.modules:
    omi_sdk = types.ModuleType("omi_plugin_sdk")
    omi_sdk_models = types.ModuleType("omi_plugin_sdk.models")
    omi_sdk_models.Conversation = type("Conversation", (), {})
    omi_sdk_models.EndpointResponse = type("EndpointResponse", (), {})
    omi_sdk_models.Structured = type("Structured", (), {})
    omi_sdk_models.TranscriptSegment = type("TranscriptSegment", (), {})
    sys.modules["omi_plugin_sdk"] = omi_sdk
    sys.modules["omi_plugin_sdk.models"] = omi_sdk_models

if "fastapi" not in sys.modules:
    fastapi = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code, detail=None):
            self.status_code = status_code
            self.detail = detail

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass
        def get(self, *args, **kwargs):
            return lambda f: f
        def post(self, *args, **kwargs):
            return lambda f: f
        def mount(self, *args, **kwargs):
            pass

    class Request:
        def __init__(self, json_data=None):
            self._json_data = json_data or {}
        async def json(self):
            return self._json_data

    fastapi.FastAPI = FastAPI
    fastapi.HTTPException = HTTPException
    fastapi.Request = Request
    fastapi.Query = lambda default=None, **kwargs: default
    fastapi.Form = lambda default=None, **kwargs: default
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = type("HTMLResponse", (), {})
    responses.RedirectResponse = type("RedirectResponse", (), {})
    responses.JSONResponse = type("JSONResponse", (), {})
    sys.modules["fastapi.responses"] = responses

    staticfiles = types.ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = lambda *args, **kwargs: None
    sys.modules["fastapi.staticfiles"] = staticfiles

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda *args, **kwargs: None
    sys.modules["fastapi.templating"] = templating

if "pydantic" not in sys.modules:
    pydantic = types.ModuleType("pydantic")
    def Field(default=None, **kwargs):
        return default
    class BaseModel:
        def __init__(self, **kwargs):
            for cls in reversed(self.__class__.__mro__):
                for k, v in getattr(cls, "__dict__", {}).items():
                    if not k.startswith("_") and not callable(v):
                        setattr(self, k, None if v is ... else v)
            for k, v in kwargs.items():
                setattr(self, k, v)
        def dict(self, **kwargs):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    sys.modules["pydantic"] = pydantic

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main
from models import HiveTask, ChatToolResponse

class FakeRequest:
    def __init__(self, payload):
        self._payload = payload
    async def json(self):
        return self._payload

class HiveTaskResolutionTests(unittest.TestCase):
    def test_update_status_exact_match_resolves_and_mutates(self):
        task_exact = HiveTask(id="task-101", name="Deploy Staging", status="todo", project_name="Web")
        task_partial = HiveTask(id="task-102", name="Do Not Deploy Staging On Friday", status="todo", project_name="Web")

        req = FakeRequest({"uid": "u1", "task_name": "deploy staging", "status": "done"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[task_partial, task_exact]), \
             patch.object(main, "hive_rest_request", return_value={"status": "completed"}) as mock_rest:

            resp = asyncio.run(main.tool_hive_update_task_status(req))

            self.assertIsNone(resp.error)
            self.assertIn("Updated **Deploy Staging** (ID: `task-101`) status to **completed**", resp.result)
            mock_rest.assert_called_once_with("u1", "PUT", "actions/task-101", data={"status": "completed"})

    def test_update_status_whitespace_and_casing_resilience(self):
        # Input has leading/trailing whitespaces and multiple consecutive spaces
        task = HiveTask(id="task-103", name="Deploy Staging", status="todo")
        req = FakeRequest({"uid": "u1", "task_name": "   deploy    staging   ", "status": "finished"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[task]), \
             patch.object(main, "hive_rest_request", return_value={"status": "completed"}) as mock_rest:

            resp = asyncio.run(main.tool_hive_update_task_status(req))

            self.assertIsNone(resp.error)
            self.assertIn("Deploy Staging", resp.result)
            mock_rest.assert_called_once_with("u1", "PUT", "actions/task-103", data={"status": "completed"})

    def test_update_status_single_partial_match_resolves_and_mutates(self):
        task_single = HiveTask(id="task-201", name="Setup Prometheus Alerting", status="todo")
        req = FakeRequest({"uid": "u1", "task_name": "prometheus", "status": "completed"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[task_single]), \
             patch.object(main, "hive_rest_request", return_value={"status": "completed"}) as mock_rest:

            resp = asyncio.run(main.tool_hive_update_task_status(req))

            self.assertIsNone(resp.error)
            self.assertIn("Setup Prometheus Alerting", resp.result)
            mock_rest.assert_called_once_with("u1", "PUT", "actions/task-201", data={"status": "completed"})

    def test_update_status_multiple_partial_matches_aborts_without_mutation(self):
        task_a = HiveTask(id="task-301", name="Don't deploy on Friday", status="todo", project_name="Infra")
        task_b = HiveTask(id="task-302", name="Deploy staging services", status="todo", project_name="Infra")

        req = FakeRequest({"uid": "u1", "task_name": "deploy", "status": "completed"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[task_a, task_b]), \
             patch.object(main, "hive_rest_request") as mock_rest:

            resp = asyncio.run(main.tool_hive_update_task_status(req))

            mock_rest.assert_not_called()
            self.assertIsNotNone(resp.result)
            self.assertIn("Multiple tasks matched 'deploy'", resp.result)
            self.assertIn("task-301", resp.result)
            self.assertIn("task-302", resp.result)

    def test_update_status_multiple_exact_matches_aborts_without_mutation(self):
        task_1 = HiveTask(id="task-401", name="Review PR", status="todo", project_name="Frontend")
        task_2 = HiveTask(id="task-402", name="Review PR", status="in progress", project_name="Backend")

        req = FakeRequest({"uid": "u1", "task_name": "Review PR", "status": "done"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[task_1, task_2]), \
             patch.object(main, "hive_rest_request") as mock_rest:

            resp = asyncio.run(main.tool_hive_update_task_status(req))

            mock_rest.assert_not_called()
            self.assertIsNotNone(resp.result)
            self.assertIn("Multiple tasks found with the exact name 'Review PR'", resp.result)
            self.assertIn("task-401", resp.result)
            self.assertIn("task-402", resp.result)

    def test_update_status_with_explicit_task_id_only_never_returns_none(self):
        # Only task_id passed, task_name is None
        req = FakeRequest({"uid": "u1", "task_id": "act-888", "status": "in progress"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks") as mock_search, \
             patch.object(main, "hive_rest_request", return_value={"status": "in progress"}) as mock_rest:

            resp = asyncio.run(main.tool_hive_update_task_status(req))

            mock_search.assert_not_called()
            mock_rest.assert_called_once_with("u1", "PUT", "actions/act-888", data={"status": "in progress"})
            self.assertIsNone(resp.error)
            # Ensure literal '**None**' never appears in output
            self.assertNotIn("**None**", resp.result)
            self.assertIn("task (ID: `act-888`)", resp.result)

    def test_update_status_invalid_task_id_format(self):
        # Path traversal attack attempt in task_id
        req = FakeRequest({"uid": "u1", "task_id": "../workspaces/admin", "status": "done"})

        with patch.object(main, "is_connected", return_value=True):
            resp = asyncio.run(main.tool_hive_update_task_status(req))
            self.assertIsNotNone(resp.error)
            self.assertIn("Invalid task_id format", resp.error)

    def test_update_status_markdown_sanitization(self):
        # Task title contains markdown formatting characters that shouldn't break UI
        task = HiveTask(id="task-md-1", name="Fix [Critical] *Bug* in `auth`", status="todo")
        req = FakeRequest({"uid": "u1", "task_name": "Fix [Critical] *Bug* in `auth`", "status": "completed"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[task]), \
             patch.object(main, "hive_rest_request", return_value={"status": "completed"}):

            resp = asyncio.run(main.tool_hive_update_task_status(req))
            self.assertIsNone(resp.error)
            # Verify markdown control characters were sanitized
            self.assertIn("\\[Critical\\]", resp.result)

    def test_update_status_dirty_data_resilience(self):
        # search_tasks returns objects with None or malformed attributes
        task_valid = HiveTask(id="task-good", name="Normal Task", status="todo")
        dirty_obj = type("DirtyTask", (), {"name": None, "id": None, "status": None})()

        req = FakeRequest({"uid": "u1", "task_name": "Normal Task", "status": "todo"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[dirty_obj, task_valid]), \
             patch.object(main, "hive_rest_request", return_value={"status": "todo"}):

            resp = asyncio.run(main.tool_hive_update_task_status(req))
            self.assertIsNone(resp.error)
            self.assertIn("Normal Task", resp.result)

    def test_update_status_task_not_found(self):
        req = FakeRequest({"uid": "u1", "task_name": "Nonexistent Task 404", "status": "done"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[]):

            resp = asyncio.run(main.tool_hive_update_task_status(req))
            self.assertIsNotNone(resp.error)
            self.assertIn("Could not find task", resp.error)

    def test_search_tasks_output_includes_task_id(self):
        task = HiveTask(id="act-555", name="Prepare Q4 Roadmap", status="in progress", project_name="Planning")
        req = FakeRequest({"uid": "u1", "query": "Roadmap"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[task]):

            resp = asyncio.run(main.tool_hive_search(req))
            self.assertIsNone(resp.error)
            self.assertIn("**Prepare Q4 Roadmap** (ID: `act-555`)", resp.result)

    def test_get_tasks_output_includes_task_id(self):
        task = HiveTask(id="act-777", name="Fix memory leak", status="todo")
        req = FakeRequest({"uid": "u1", "project_name": "Core"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "find_project_by_name", return_value=main.HiveProject(id="p1", name="Core")), \
             patch.object(main, "get_project_tasks", return_value=[task]):

            resp = asyncio.run(main.tool_hive_get_tasks(req))
            self.assertIsNone(resp.error)
            self.assertIn("**Fix memory leak** (ID: `act-777`)", resp.result)

    def test_missing_required_fields(self):
        req_no_uid = FakeRequest({"task_id": "act-1"})
        resp = asyncio.run(main.tool_hive_update_task_status(req_no_uid))
        self.assertEqual(resp.error, "User ID is required")

        req_no_target = FakeRequest({"uid": "u1", "status": "completed"})
        resp = asyncio.run(main.tool_hive_update_task_status(req_no_target))
        self.assertEqual(resp.error, "Task name or ID is required")

        req_no_status = FakeRequest({"uid": "u1", "task_id": "act-1"})
        resp = asyncio.run(main.tool_hive_update_task_status(req_no_status))
        self.assertIn("Status is required", resp.error)

    def test_explicit_task_id_with_task_name_does_not_mislabel(self):
        # When task_id is explicitly passed, the unverified task_name must not be displayed
        req = FakeRequest({"uid": "u1", "task_id": "act-explicit", "task_name": "Unverified Name", "status": "done"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "hive_rest_request", return_value={"id": "act-explicit"}) as mock_rest:

            resp = asyncio.run(main.tool_hive_update_task_status(req))
            self.assertIsNone(resp.error)
            self.assertIn("task (ID: `act-explicit`)", resp.result)
            self.assertNotIn("Unverified Name", resp.result)
            mock_rest.assert_called_once_with("u1", "PUT", "actions/act-explicit", data={"status": "completed"})

    def test_robust_errors_handling_for_nonstandard_error_payload(self):
        req = FakeRequest({"uid": "u1", "task_id": "act-1", "status": "done"})

        # Case 1: errors is empty list
        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "hive_rest_request", return_value={"errors": []}):
            resp = asyncio.run(main.tool_hive_update_task_status(req))
            self.assertEqual(resp.error, "Failed to update task: Unknown error")

        # Case 2: errors is string
        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "hive_rest_request", return_value={"errors": "Rate limit exceeded"}):
            resp = asyncio.run(main.tool_hive_update_task_status(req))
            self.assertEqual(resp.error, "Failed to update task: Rate limit exceeded")

    def test_unicode_normalization_matching(self):
        # Fullwidth ASCII, decomposed characters, and multiple unicode spaces
        import unicodedata
        composed_name = "Café Menu"
        decomposed_input = unicodedata.normalize("NFD", "  Ｃａｆé \u3000 Menu  ")
        task = HiveTask(id="act-cafe", name=composed_name, status="todo")
        req = FakeRequest({"uid": "u1", "task_name": decomposed_input, "status": "done"})

        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "search_tasks", return_value=[task]), \
             patch.object(main, "hive_rest_request", return_value={"id": "act-cafe"}):

            resp = asyncio.run(main.tool_hive_update_task_status(req))
            self.assertIsNone(resp.error)
            self.assertIn("**Café Menu** (ID: `act-cafe`)", resp.result)

if __name__ == "__main__":
    unittest.main()
