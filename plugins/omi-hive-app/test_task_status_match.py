"""Hermetic regression: hive_update_task_status must not mutate a task the user did not name.

The handler resolved a task name through search_tasks (substring match over the
workspace's recent actions, capped at five results) and, when no title matched
exactly, fell back to the first result. "mark deploy done" therefore completed
"Don't deploy on Friday" without saying so, and an exact match beyond the fifth
substring hit was never seen. The handler now resolves only an unambiguous
match and otherwise returns the candidates with ids.

Framework, HTTP and storage are stand ins; the production handler runs as is.

Run: python3 plugins/omi-hive-app/test_task_status_match.py
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get

    def mount(self, *args, **kwargs):
        pass


class Response:
    result = None
    error = None

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Task:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


stubs = {
    "requests": module("requests", get=Mock(), post=Mock(), put=Mock(), request=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module(
        "fastapi", FastAPI=Framework, HTTPException=Exception, Request=Framework, Query=Framework, Form=Framework
    ),
    "fastapi.responses": module(
        "fastapi.responses", HTMLResponse=Framework, RedirectResponse=Framework, JSONResponse=Framework
    ),
    "fastapi.staticfiles": module("fastapi.staticfiles", StaticFiles=Framework),
    "fastapi.templating": module("fastapi.templating", Jinja2Templates=Framework),
    "models": module("models", ChatToolResponse=Response, HiveProject=Task, HiveTask=Task, HiveAction=Task),
    "db": module(
        "db",
        **{
            name: Mock()
            for name in (
                "store_hive_credentials",
                "get_hive_credentials",
                "delete_hive_credentials",
                "is_connected",
                "store_default_project",
                "get_default_project",
                "get_user_settings",
            )
        },
    ),
}
spec = importlib.util.spec_from_file_location("hive_under_test", Path(__file__).with_name("main.py"))
hive = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(hive)


def task(id, name):
    return Task(id=id, name=name, status="todo", project_name="Ops")


class UpdateTaskStatusByName(unittest.TestCase):
    def update(self, task_name, found):
        request = Mock(json=AsyncMock(return_value={"uid": "u1", "task_name": task_name, "status": "done"}))
        with (
            patch.object(hive, "is_connected", return_value=True),
            patch.object(hive, "search_tasks", return_value=found) as search,
            patch.object(hive, "hive_rest_request", return_value={"ok": True}) as rest,
        ):
            result = asyncio.run(hive.tool_hive_update_task_status(request))
        return result, search, rest

    def test_partial_match_alone_is_never_used_when_several_tasks_match(self):
        result, _, rest = self.update("deploy", [task("a1", "Don't deploy on Friday"), task("a2", "Deploy staging")])
        rest.assert_not_called()
        self.assertIsNone(result.result)
        self.assertIn("More than one task matches 'deploy'", result.error)
        self.assertIn("`a1`", result.error)
        self.assertIn("`a2`", result.error)

    def test_exact_title_wins_over_earlier_partial_matches(self):
        found = [task("a1", "Deploy staging"), task("a2", "Deploy prod"), task("a3", "deploy")]
        result, search, rest = self.update("Deploy", found)
        self.assertGreaterEqual(search.call_args.kwargs.get("limit", 0), 50)
        rest.assert_called_once_with("u1", "PUT", "actions/a3", data={"status": "completed"})
        self.assertIn("**deploy**", result.result)

    def test_single_partial_match_is_used(self):
        result, _, rest = self.update("stag", [task("a1", "Deploy staging")])
        rest.assert_called_once_with("u1", "PUT", "actions/a1", data={"status": "completed"})
        self.assertIsNone(result.error)

    def test_two_exact_titles_are_ambiguous(self):
        result, _, rest = self.update("Deploy", [task("a1", "Deploy"), task("a2", "deploy")])
        rest.assert_not_called()
        self.assertIn("`a1`", result.error)
        self.assertIn("`a2`", result.error)

    def test_task_id_skips_the_name_lookup(self):
        request = Mock(json=AsyncMock(return_value={"uid": "u1", "task_id": "a9", "status": "in progress"}))
        with (
            patch.object(hive, "is_connected", return_value=True),
            patch.object(hive, "search_tasks") as search,
            patch.object(hive, "hive_rest_request", return_value={"ok": True}) as rest,
        ):
            result = asyncio.run(hive.tool_hive_update_task_status(request))
        search.assert_not_called()
        rest.assert_called_once_with("u1", "PUT", "actions/a9", data={"status": "in progress"})
        self.assertIsNone(result.error)


if __name__ == "__main__":
    unittest.main()
