"""Hermetic regression: hive_create_task must never write to a project or
under a parent task it could not uniquely resolve.

find_project_by_name and the parent task lookup inside tool_hive_create_task
both picked the first candidate that matched a name, without checking that
match was unique. A project name like "Q3" in a workspace with both "Q3
Marketing" and "Q3 Sales" created the task in whichever project
get_user_projects happened to list first; a parent task name that matched
more than one task in the target project, or matched only a task in a
different project, silently attached the new task there instead of
refusing.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock


class ChatToolResponse:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error


class App:
    def __init__(self, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get

    def mount(self, *args, **kwargs):
        pass


def load_app():
    modules = {}
    definitions = {
        "fastapi": dict(FastAPI=App, HTTPException=Exception, Request=object, Query=Mock(), Form=Mock()),
        "fastapi.responses": dict(HTMLResponse=object, RedirectResponse=Mock(), JSONResponse=Mock()),
        "fastapi.staticfiles": dict(StaticFiles=Mock()),
        "fastapi.templating": dict(Jinja2Templates=Mock()),
        "dotenv": dict(load_dotenv=lambda: None),
        "requests": dict(post=Mock(side_effect=AssertionError("Unexpected HTTP")), get=Mock(side_effect=AssertionError("Unexpected HTTP"))),
        "db": {name: Mock(side_effect=AssertionError(f"Unexpected storage call: {name}")) for name in (
            "store_hive_credentials", "get_hive_credentials", "delete_hive_credentials", "is_connected",
            "store_default_project", "get_default_project", "get_user_settings")},
        "models": {name: ChatToolResponse if name == "ChatToolResponse" else types.SimpleNamespace for name in (
            "ChatToolResponse", "HiveProject", "HiveTask", "HiveAction")},
    }
    for name, values in definitions.items():
        modules[name] = types.ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location("hive_create_task_under_test", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    originals = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
    return module


def project(id_, name):
    return types.SimpleNamespace(id=id_, name=name)


def task(id_, name, project_id):
    return types.SimpleNamespace(id=id_, name=name, project_id=project_id)


class CreateTaskAmbiguousProjectTests(unittest.TestCase):
    def setUp(self):
        self.module = load_app()
        self.module.is_connected = lambda uid: True
        self.module.get_hive_credentials = lambda uid: {"workspace_id": "ws-1"}
        self.module.hive_rest_request = Mock(side_effect=AssertionError("Task must not be created for an ambiguous target"))

    def run_create(self, **body):
        payload = dict(uid="u1", task_name="Ship it")
        payload.update(body)

        async def json():
            return payload

        return asyncio.run(self.module.tool_hive_create_task(types.SimpleNamespace(json=json)))

    def test_ambiguous_project_name_refuses_and_does_not_create(self):
        self.module.get_user_projects = Mock(return_value=[project("p1", "Q3 Marketing"), project("p2", "Q3 Sales")])
        response = self.run_create(project_name="Q3")
        self.assertIsNotNone(response.error)
        self.assertIn("Q3 Marketing", response.error)
        self.assertIn("Q3 Sales", response.error)
        self.module.hive_rest_request.assert_not_called()

    def test_unambiguous_project_name_creates(self):
        self.module.get_user_projects = Mock(return_value=[project("p1", "Q3 Marketing"), project("p2", "Website")])
        self.module.hive_rest_request = Mock(return_value={"_id": "task-1"})
        response = self.run_create(project_name="Website")
        self.assertIsNone(response.error)
        _, kwargs = self.module.hive_rest_request.call_args
        self.assertEqual(kwargs["data"]["projectId"], "p2")

    def test_exact_name_wins_over_a_coincidental_substring(self):
        self.module.get_user_projects = Mock(return_value=[project("p1", "Q3"), project("p2", "Q3 Extended")])
        self.module.hive_rest_request = Mock(return_value={"_id": "task-1"})
        response = self.run_create(project_name="Q3")
        self.assertIsNone(response.error)
        self.assertEqual(self.module.hive_rest_request.call_args.kwargs["data"]["projectId"], "p1")


class CreateTaskAmbiguousParentTests(unittest.TestCase):
    def setUp(self):
        self.module = load_app()
        self.module.is_connected = lambda uid: True
        self.module.get_hive_credentials = lambda uid: {"workspace_id": "ws-1"}
        self.module.get_user_projects = Mock(return_value=[project("p1", "Website")])
        self.module.hive_rest_request = Mock(side_effect=AssertionError("Task must not be created for an ambiguous parent"))

    def run_create(self, **body):
        payload = dict(uid="u1", task_name="Sub task", project_name="Website")
        payload.update(body)

        async def json():
            return payload

        return asyncio.run(self.module.tool_hive_create_task(types.SimpleNamespace(json=json)))

    def test_two_matching_tasks_in_the_same_project_refuse(self):
        self.module.search_tasks = Mock(return_value=[task("t1", "Design review", "p1"), task("t2", "Design handoff", "p1")])
        response = self.run_create(parent_task_name="Design")
        self.assertIsNotNone(response.error)
        self.assertIn("Design review", response.error)
        self.assertIn("Design handoff", response.error)
        self.module.hive_rest_request.assert_not_called()

    def test_match_in_a_different_project_is_not_used_as_a_fallback(self):
        # Regression: the old code fell through to found_tasks[0] from any
        # project when nothing matched in the target project.
        self.module.search_tasks = Mock(return_value=[task("t9", "Design review", "p2")])
        response = self.run_create(parent_task_name="Design review")
        self.assertIsNotNone(response.error)
        self.assertIn("Website", response.error)
        self.module.hive_rest_request.assert_not_called()

    def test_single_match_in_project_is_used(self):
        self.module.search_tasks = Mock(return_value=[task("t1", "Design review", "p1"), task("t9", "Design review", "p2")])
        self.module.hive_rest_request = Mock(return_value={"_id": "task-1"})
        response = self.run_create(parent_task_name="Design review")
        self.assertIsNone(response.error)
        self.assertEqual(self.module.hive_rest_request.call_args.kwargs["data"]["parentId"], "t1")


if __name__ == "__main__":
    unittest.main()
