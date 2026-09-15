"""Hermetic regressions for the Hive chat tools (#13976).

`tool_hive_update_task_status` resolved `task_name` — the only thing the model
could pass, since `hive_search` and `hive_get_tasks` never printed ids —
through `search_tasks`, a substring match over the workspace's recent actions
capped at five results. When no title matched exactly it mutated `tasks[0]`
("Use first result as fallback"): "mark deploy done" completed "Don't deploy
on Friday" without saying so, an exact title past the fifth substring hit was
never considered, and two identical titles were picked silently.

The handler now searches the whole fetched window, resolves only an
unambiguous match (a single exact title, or a single partial hit), and
otherwise returns the candidates with their ids so the model can retry with
`task_id`. `hive_search` and `hive_get_tasks` print ids.

Framework, HTTP, and storage are stand-ins; the production module, its real
models module, and the real handlers run unmodified. No network, no
credentials, no third-party packages.

Run: python3 plugins/omi-hive-app/test_main.py
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


class _FastAPI:
    """Stand-in for fastapi.FastAPI: route decorators return the handler."""

    def __init__(self, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda handler: handler

    post = get
    put = get
    delete = get

    def mount(self, *args, **kwargs):
        pass


class _BaseModel:
    """Stand-in for pydantic.BaseModel: keyword args become attributes."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Any:
    """Instantiable stand-in for framework classes used as decorators/responses."""

    def __init__(self, *args, **kwargs):
        pass


def _module(name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    return module


def load_app():
    """Import main.py with third-party deps stubbed; db.py/models.py stay real."""
    plugin_dir = Path(__file__).parent

    sdk_models = _module(
        "omi_plugin_sdk.models",
        **{
            name: type(name, (_BaseModel,), {})
            for name in ("Conversation", "EndpointResponse", "Structured", "TranscriptSegment")
        },
    )
    stubs = {
        "requests": _module(
            "requests",
            get=Mock(),
            post=Mock(),
            request=Mock(),
            Timeout=type("Timeout", (Exception,), {}),
            RequestException=type("RequestException", (Exception,), {}),
        ),
        "dotenv": _module("dotenv", load_dotenv=lambda: None),
        "fastapi": _module(
            "fastapi",
            FastAPI=_FastAPI,
            HTTPException=type("HTTPException", (Exception,), {}),
            Request=_Any,
            Query=_Any,
            Form=_Any,
        ),
        "fastapi.responses": _module(
            "fastapi.responses",
            HTMLResponse=_Any,
            RedirectResponse=_Any,
            JSONResponse=_Any,
        ),
        "fastapi.staticfiles": _module("fastapi.staticfiles", StaticFiles=_Any),
        "fastapi.templating": _module("fastapi.templating", Jinja2Templates=_Any),
        "pydantic": _module("pydantic", BaseModel=_BaseModel),
        "omi_plugin_sdk": _module("omi_plugin_sdk", models=sdk_models),
        "omi_plugin_sdk.models": sdk_models,
    }

    with patch.dict(sys.modules, stubs):
        # The real sibling modules: models.py under the pydantic/SDK stubs,
        # db.py (tolerates redis being absent, and is never called here).
        for name in ("models", "db"):
            spec = importlib.util.spec_from_file_location(name, plugin_dir / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)

        spec = importlib.util.spec_from_file_location("hive_app", plugin_dir / "main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


app = load_app()


class _Request:
    """Minimal stand-in for fastapi.Request carrying a JSON body."""

    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _task(task_id, name, status="todo", project_name="Ops"):
    return app.HiveTask(id=task_id, name=name, status=status, project_name=project_name)


class NormalizeTitleTests(unittest.TestCase):
    def test_collapses_whitespace_and_case(self):
        self.assertEqual(app._normalize_title("  Deploy\t Staging\n"), "deploy staging")
        self.assertEqual(app._normalize_title(None), "")


class FormatTaskLinesTests(unittest.TestCase):
    def test_lines_include_task_ids(self):
        lines = app._format_task_lines([_task("a1", "Deploy staging", status="in progress")])
        self.assertEqual(lines, ["1. **Deploy staging** [in progress] (in Ops) — id: `a1`"])

    def test_lines_omit_empty_status_and_project(self):
        lines = app._format_task_lines([app.HiveTask(id="a2", name="X")])
        self.assertEqual(lines, ["1. **X** — id: `a2`"])


class UpdateTaskStatusTests(unittest.IsolatedAsyncioTestCase):
    async def _update(self, body, *, tasks=None, connected=True, rest_result=None):
        with (
            patch.object(app, "is_connected", return_value=connected),
            patch.object(app, "search_tasks", return_value=tasks if tasks is not None else []) as search,
            patch.object(app, "hive_rest_request", return_value=rest_result or {"ok": True}) as rest,
        ):
            response = await app.tool_hive_update_task_status(_Request(body))
        return response, search, rest

    async def test_ambiguous_partial_names_never_mutate_the_first_hit(self):
        """#13976 headline case: 'deploy' must not complete 'Don't deploy on Friday'."""
        response, _, rest = await self._update(
            {"uid": "u1", "task_name": "deploy", "status": "done"},
            tasks=[_task("a1", "Don't deploy on Friday"), _task("a2", "Deploy staging")],
        )
        rest.assert_not_called()
        self.assertIsNone(response.error)
        self.assertIn("Multiple tasks match the name 'deploy'", response.result)
        self.assertIn("`a1`", response.result)
        self.assertIn("`a2`", response.result)
        self.assertIn("task_id", response.result)

    async def test_single_exact_match_updates_the_named_task(self):
        response, _, rest = await self._update(
            {"uid": "u1", "task_name": "Deploy staging", "status": "done"},
            tasks=[_task("a1", "Don't deploy on Friday"), _task("a2", "Deploy staging")],
        )
        rest.assert_called_once_with("u1", "PUT", "actions/a2", data={"status": "completed"})
        self.assertIn("**Deploy staging**", response.result)
        self.assertIn("**completed**", response.result)

    async def test_exact_match_is_case_and_whitespace_insensitive(self):
        response, _, rest = await self._update(
            {"uid": "u1", "task_name": "deploy staging", "status": "done"},
            tasks=[_task("a9", "Deploy window"), _task("a1", "Deploy  staging")],
        )
        rest.assert_called_once_with("u1", "PUT", "actions/a1", data={"status": "completed"})

    async def test_name_search_scans_the_whole_fetched_window(self):
        """An exact title past the fifth substring hit must be seen (#13976)."""
        _, search, _ = await self._update(
            {"uid": "u1", "task_name": "deploy", "status": "done"},
            tasks=[_task("a1", "deploy")],
        )
        search.assert_called_once_with("u1", "deploy", limit=50)

    async def test_duplicate_exact_titles_ask_for_task_id(self):
        response, _, rest = await self._update(
            {"uid": "u1", "task_name": "Ship it", "status": "done"},
            tasks=[_task("a1", "Ship it"), _task("a2", "Ship it")],
        )
        rest.assert_not_called()
        self.assertIn("share the exact title 'Ship it'", response.result)
        self.assertIn("`a1`", response.result)
        self.assertIn("`a2`", response.result)

    async def test_single_partial_match_still_updates(self):
        response, _, rest = await self._update(
            {"uid": "u1", "task_name": "deploy", "status": "done"},
            tasks=[_task("a1", "Deploy staging")],
        )
        rest.assert_called_once_with("u1", "PUT", "actions/a1", data={"status": "completed"})

    async def test_ambiguous_listing_is_capped_at_ten_candidates(self):
        tasks = [_task(f"a{i}", f"Deploy env {i}") for i in range(12)]
        response, _, rest = await self._update(
            {"uid": "u1", "task_name": "deploy", "status": "done"}, tasks=tasks
        )
        rest.assert_not_called()
        self.assertIn("... and 2 more", response.result)
        self.assertNotIn("`a11`", response.result)

    async def test_no_match_returns_not_found(self):
        response, _, rest = await self._update(
            {"uid": "u1", "task_name": "nope", "status": "done"}, tasks=[]
        )
        rest.assert_not_called()
        self.assertIn("Could not find task: nope", response.error)

    async def test_task_id_short_circuits_the_name_search(self):
        response, search, rest = await self._update(
            {"uid": "u1", "task_id": "a9", "status": "in progress"}
        )
        search.assert_not_called()
        rest.assert_called_once_with("u1", "PUT", "actions/a9", data={"status": "in progress"})
        self.assertIn("**a9**", response.result)

    async def test_status_words_map_to_hive_statuses(self):
        cases = {
            "done": "completed",
            "mark finished": "completed",
            "in progress": "in progress",
            "todo": "todo",
            "custom state": "custom state",
        }
        for spoken, expected in cases.items():
            with self.subTest(spoken=spoken):
                _, _, rest = await self._update(
                    {"uid": "u1", "task_name": "deploy", "status": spoken},
                    tasks=[_task("a1", "Deploy staging")],
                )
                rest.assert_called_once_with("u1", "PUT", "actions/a1", data={"status": expected})

    async def test_rest_failure_surfaces_the_error(self):
        response, _, _ = await self._update(
            {"uid": "u1", "task_name": "deploy", "status": "done"},
            tasks=[_task("a1", "Deploy staging")],
            rest_result={"errors": [{"message": "boom"}]},
        )
        self.assertIn("boom", response.error)

    async def test_missing_uid_is_rejected(self):
        response, search, rest = await self._update({"task_name": "deploy", "status": "done"})
        search.assert_not_called()
        rest.assert_not_called()
        self.assertIn("User ID is required", response.error)

    async def test_missing_status_is_rejected(self):
        response, _, rest = await self._update({"uid": "u1", "task_name": "deploy"})
        rest.assert_not_called()
        self.assertIn("Status is required", response.error)

    async def test_missing_name_and_id_is_rejected(self):
        response, _, rest = await self._update({"uid": "u1", "status": "done"})
        rest.assert_not_called()
        self.assertIn("Task name or ID is required", response.error)

    async def test_disconnected_user_is_rejected(self):
        response, search, rest = await self._update(
            {"uid": "u1", "task_name": "deploy", "status": "done"}, connected=False
        )
        search.assert_not_called()
        rest.assert_not_called()
        self.assertIn("connect your Hive account", response.error)


class SearchToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_results_print_task_ids(self):
        with (
            patch.object(app, "is_connected", return_value=True),
            patch.object(app, "search_tasks", return_value=[_task("a1", "Deploy staging")]),
        ):
            response = await app.tool_hive_search(_Request({"uid": "u1", "query": "deploy"}))
        self.assertIsNone(response.error)
        self.assertIn("id: `a1`", response.result)
        self.assertIn("**Deploy staging**", response.result)

    async def test_search_without_hits_says_so(self):
        with (
            patch.object(app, "is_connected", return_value=True),
            patch.object(app, "search_tasks", return_value=[]),
        ):
            response = await app.tool_hive_search(_Request({"uid": "u1", "query": "deploy"}))
        self.assertIn("No results found for 'deploy'", response.result)


class GetTasksToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_task_listing_prints_task_ids(self):
        with (
            patch.object(app, "is_connected", return_value=True),
            patch.object(app, "get_default_project", return_value={"id": "p1", "name": "Main"}),
            patch.object(app, "get_project_tasks", return_value=[_task("a1", "Deploy staging", project_name=None)]),
        ):
            response = await app.tool_hive_get_tasks(_Request({"uid": "u1"}))
        self.assertIsNone(response.error)
        self.assertIn("id: `a1`", response.result)
        self.assertIn("**Main**", response.result)

    async def test_no_project_and_no_default_is_rejected(self):
        with (
            patch.object(app, "is_connected", return_value=True),
            patch.object(app, "get_default_project", return_value=None),
        ):
            response = await app.tool_hive_get_tasks(_Request({"uid": "u1"}))
        self.assertIn("specify a project name or set a default", response.error)


if __name__ == "__main__":
    unittest.main()
