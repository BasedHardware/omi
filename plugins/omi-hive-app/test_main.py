"""Hermetic regression tests for the Hive task-creation safety contract.

The plugin's production dependencies are intentionally stubbed so this check
can run in the repository's stdlib-only local/CI lanes.
"""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


def _install_stubs() -> None:
    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda function: function

        def post(self, *args, **kwargs):
            return lambda function: function

        def mount(self, *args, **kwargs):
            pass

    class HTTPException(Exception):
        pass

    fastapi.FastAPI = FastAPI
    fastapi.HTTPException = HTTPException
    fastapi.Request = object
    fastapi.Query = lambda default=None, **kwargs: default
    fastapi.Form = lambda default=None, **kwargs: default
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = type("HTMLResponse", (), {})
    responses.RedirectResponse = type("RedirectResponse", (), {})
    responses.JSONResponse = type("JSONResponse", (), {})
    sys.modules["fastapi.responses"] = responses
    fastapi.responses = responses

    staticfiles = types.ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = type("StaticFiles", (), {"__init__": lambda self, *a, **k: None})
    sys.modules["fastapi.staticfiles"] = staticfiles

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = type(
        "Jinja2Templates",
        (),
        {
            "__init__": lambda self, *a, **k: None,
            "TemplateResponse": lambda self, *a, **k: None,
        },
    )
    sys.modules["fastapi.templating"] = templating

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    pydantic.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic

    requests = types.ModuleType("requests")
    requests.post = lambda *a, **k: None
    requests.get = lambda *a, **k: None
    requests.request = lambda *a, **k: None
    requests.Timeout = type("Timeout", (Exception,), {})
    requests.RequestException = type("RequestException", (Exception,), {})
    sys.modules["requests"] = requests

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    sdk = types.ModuleType("omi_plugin_sdk")
    sdk_models = types.ModuleType("omi_plugin_sdk.models")
    for name in ("Conversation", "EndpointResponse", "Structured", "TranscriptSegment"):
        setattr(sdk_models, name, type(name, (), {}))
    sys.modules["omi_plugin_sdk"] = sdk
    sys.modules["omi_plugin_sdk.models"] = sdk_models

    db = types.ModuleType("db")
    for name in (
        "store_hive_credentials", "get_hive_credentials", "delete_hive_credentials",
        "is_connected", "store_default_project", "get_default_project", "get_user_settings",
    ):
        setattr(db, name, lambda *a, **k: None)
    sys.modules["db"] = db


_install_stubs()
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main  # noqa: E402


class _Request:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


def _project(project_id, name):
    return main.HiveProject(id=project_id, name=name)


def _task(task_id, name, project_id):
    return main.HiveTask(id=task_id, name=name, project_id=project_id)


class HiveNameResolutionTests(unittest.TestCase):
    def test_exact_unique_match_wins(self):
        projects = [_project("marketing", "Q3 Marketing"), _project("q3", "Q3")]
        with patch.object(main, "get_user_projects", return_value=projects):
            project, candidates = main.find_project_by_name("u", " q3 ")
        self.assertEqual(project.id, "q3")
        self.assertEqual([p.name for p in candidates], ["Q3"])

    def test_ambiguous_partial_match_fails_closed(self):
        projects = [_project("m", "Q3 Marketing"), _project("s", "Q3 Sales")]
        with patch.object(main, "get_user_projects", return_value=projects):
            project, candidates = main.find_project_by_name("u", "Q3")
        self.assertIsNone(project)
        self.assertEqual({p.id for p in candidates}, {"m", "s"})

    def test_empty_name_never_matches_every_project(self):
        with patch.object(main, "get_user_projects") as projects:
            project, candidates = main.find_project_by_name("u", "  ")
        projects.assert_not_called()
        self.assertIsNone(project)
        self.assertEqual(candidates, [])

    def test_malformed_project_payload_is_ignored(self):
        with patch.object(main, "get_user_projects", return_value=[object(), None]):
            project, candidates = main.find_project_by_name("u", "Q3")
        self.assertIsNone(project)
        self.assertEqual(candidates, [])


class HiveManifestSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_manifest_schema_compliance(self):
        manifest = await main.get_omi_tools_manifest()
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

class HiveCreateTaskSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.project = _project("target", "Target")
        self.credentials = {"workspace_id": "workspace"}

    def _patch_common(self, search_results, create_result=None):
        return patch.multiple(
            main,
            is_connected=lambda uid: True,
            get_hive_credentials=lambda uid: self.credentials,
            get_user_projects=lambda uid: [self.project],
            search_tasks=lambda uid, query, limit=10: search_results,
            hive_rest_request=lambda *args, **kwargs: create_result or {"id": "created"},
        )

    async def test_project_ambiguity_is_reported_without_mutation(self):
        candidates = [_project("a", "Q3 Marketing"), _project("b", "Q3 Sales")]
        with patch.object(main, "is_connected", return_value=True), \
             patch.object(main, "get_user_projects", return_value=candidates), \
             patch.object(main, "hive_rest_request") as create:
            response = await main.tool_hive_create_task(
                _Request({"uid": "u", "task_name": "Write report", "project_name": "Q3"})
            )
        self.assertIn("ambiguous", response.error.lower())
        self.assertIn("Q3 Marketing", response.error)
        create.assert_not_called()

    async def test_parent_only_found_in_other_project_is_rejected(self):
        outside = _task("outside", "Launch", "other-project")
        with self._patch_common([outside]) as mocks:
            response = await main.tool_hive_create_task(
                _Request({
                    "uid": "u", "task_name": "Subtask", "project_name": "Target",
                    "parent_task_name": "Launch",
                })
            )
        self.assertIn("unique parent task", response.error)
        self.assertIn("no matching task", response.error)

    async def test_blank_parent_name_is_rejected_without_search(self):
        with self._patch_common([]) as mocks:
            response = await main.tool_hive_create_task(
                _Request({
                    "uid": "u", "task_name": "Subtask", "project_name": "Target",
                    "parent_task_name": "   ",
                })
            )
        self.assertEqual(response.error, "Parent task name must not be empty.")

    async def test_duplicate_parent_names_are_rejected(self):
        matches = [_task("one", "Launch", "target"), _task("two", "Launch", "target")]
        with self._patch_common(matches) as mocks:
            response = await main.tool_hive_create_task(
                _Request({
                    "uid": "u", "task_name": "Subtask", "project_name": "Target",
                    "parent_task_name": "Launch",
                })
            )
        self.assertIn("multiple exact matches", response.error)

    async def test_unique_exact_parent_is_used_and_payload_is_scoped(self):
        parent = _task("parent", "Launch", "target")
        calls = []

        def create(*args, **kwargs):
            calls.append((args, kwargs))
            return {"id": "created"}

        with patch.multiple(
            main,
            is_connected=lambda uid: True,
            get_hive_credentials=lambda uid: self.credentials,
            get_user_projects=lambda uid: [self.project],
            search_tasks=lambda uid, query, limit=10: [parent],
            hive_rest_request=create,
        ):
            response = await main.tool_hive_create_task(
                _Request({
                    "uid": "u", "task_name": "Subtask", "project_name": "Target",
                    "parent_task_name": "Launch", "description": "details",
                })
            )
        self.assertIsNone(response.error)
        self.assertIn("created", response.result.lower())
        self.assertEqual(len(calls), 1)
        payload = calls[0][1]["data"]
        self.assertEqual(payload["projectId"], "target")
        self.assertEqual(payload["parentId"], "parent")

    async def test_api_failure_is_returned_without_exception(self):
        with self._patch_common([], {"errors": [{"message": "forbidden"}]}):
            response = await main.tool_hive_create_task(
                _Request({"uid": "u", "task_name": "Task", "project_name": "Target"})
            )
        self.assertIn("forbidden", response.error)


if __name__ == "__main__":
    unittest.main()
