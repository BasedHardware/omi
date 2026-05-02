"""Tests for the Plan-screen direct dispatch helpers (transition + snooze).

Two layers exercised:

1. ``utils.integrations.jira_actions`` — the helpers that talk to the Jira
   plugin and update the local action item (metadata, completed flag,
   due_at). Covered: success paths, error mapping, status_type inference,
   plugin response sanitization in error logs.

2. ``routers.integrations`` — the two new POST endpoints
   (``/v1/integrations/jira/transition`` and ``/v1/integrations/jira/snooze``).
   Covered: 403 when two-way sync is OFF, 502 on plugin error, 404 on
   unknown action item.

Heavy deps (firebase, redis, FastAPI app) are stubbed; we only load the
two modules under test via importlib.
"""

import asyncio
import importlib.util
import logging
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

# database package
_stub_package("database")
sys.modules["database"].__path__ = [str(BACKEND_DIR / "database")]

action_items_db = _stub_module("database.action_items")
# Each test resets these mocks.
action_items_db.get_action_item = MagicMock()
action_items_db.update_action_item = MagicMock(return_value=True)

apps_db = _stub_module("database.apps")
apps_db.get_app_by_id_db = MagicMock(return_value=None)

# Real log_sanitizer (not stubbed) — we want to assert tokens get masked.
# Load the real one from disk.
_stub_package("utils")
sys.modules["utils"].__path__ = [str(BACKEND_DIR / "utils")]
_stub_package("utils.integrations")
sys.modules["utils.integrations"].__path__ = [str(BACKEND_DIR / "utils" / "integrations")]


def _load_from(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


log_san = _load_from("utils.log_sanitizer", BACKEND_DIR / "utils" / "log_sanitizer.py")


def _load_jira_actions():
    return _load_from(
        "utils.integrations.jira_actions",
        BACKEND_DIR / "utils" / "integrations" / "jira_actions.py",
    )


jira_actions = _load_jira_actions()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeResponse:
    def __init__(self, status_code, body, raw_text=None):
        self.status_code = status_code
        self._body = body
        self.text = raw_text if raw_text is not None else str(body)

    def json(self):
        return self._body


class _FakeAsyncClient:
    """Sequence-aware fake client — one or more `post()` calls match
    consecutive `_FakeResponse` instances. Use this when the helper does
    multiple HTTP calls within a single test."""

    def __init__(self, responses):
        if not isinstance(responses, list):
            responses = [responses]
        self._responses = list(responses)
        self.posts = []
        self.closed = False
        self.network_error: Exception | None = None

    async def post(self, url, json=None):
        self.posts.append({"url": url, "json": json})
        if self.network_error is not None:
            raise self.network_error
        return self._responses.pop(0)

    async def aclose(self):
        self.closed = True


def _action_item(
    *,
    item_id="ai-1",
    issue_key="PROJ-1",
    completed=False,
    metadata=None,
    due_at=None,
):
    return {
        "id": item_id,
        "description": "Ship",
        "completed": completed,
        "due_at": due_at,
        "external_source": {
            "source": "jira",
            "external_id": issue_key,
            "url": f"https://x/{issue_key}",
            **({"metadata": metadata} if metadata else {}),
        },
    }


@pytest.fixture(autouse=True)
def _reset():
    # reset_mock(side_effect=True) clears any leftover side_effect iterator
    # from a previous test (otherwise a leftover empty list raises
    # StopIteration the next time the mock is called).
    action_items_db.get_action_item.reset_mock(side_effect=True)
    action_items_db.get_action_item.return_value = None
    action_items_db.update_action_item.reset_mock(side_effect=True)
    action_items_db.update_action_item.return_value = True
    apps_db.get_app_by_id_db.reset_mock(side_effect=True)
    apps_db.get_app_by_id_db.return_value = None
    os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"
    yield
    os.environ.pop("NOOTO_JIRA_PLUGIN_URL", None)


# ===========================================================================
# transition_action_item
# ===========================================================================


class TestTransitionActionItem:

    def test_success_updates_metadata_and_completed_when_done(self):
        action_items_db.get_action_item.side_effect = [
            _action_item(metadata={"status": "To Do", "status_type": "todo", "priority": "High"}),
            # second read returns the "refreshed" item
            _action_item(
                completed=True,
                metadata={"status": "Done", "status_type": "done", "priority": "High"},
            ),
        ]
        plugin_body = {"result": "ok", "data": {"issue_key": "PROJ-1", "status": "Done"}}
        client = _FakeAsyncClient(_FakeResponse(200, plugin_body))

        result = _run(jira_actions.transition_action_item("uid-1", "ai-1", "Done", http_client=client))

        # Plugin was called with the right shape
        assert client.posts[0]["url"] == "https://plugin.example.com/tools/update_issue_status"
        assert client.posts[0]["json"] == {"uid": "uid-1", "issue_key": "PROJ-1", "new_status": "Done"}

        # update_action_item received metadata refresh + completed=True
        update_args = action_items_db.update_action_item.call_args
        uid_arg, item_id_arg, fields_arg = update_args.args
        assert uid_arg == "uid-1"
        assert item_id_arg == "ai-1"
        assert fields_arg["completed"] is True
        new_md = fields_arg["external_source"]["metadata"]
        assert new_md["status"] == "Done"
        assert new_md["status_type"] == "done"
        assert "status_changed_at" in new_md
        # Prior priority preserved
        assert new_md["priority"] == "High"

        assert result["completed"] is True

    def test_success_in_review_sets_status_type_indeterminate(self):
        action_items_db.get_action_item.side_effect = [
            _action_item(metadata={"status": "To Do", "status_type": "todo"}),
            _action_item(metadata={"status": "In Review", "status_type": "indeterminate"}),
        ]
        plugin_body = {"result": "ok", "data": {"issue_key": "PROJ-1", "status": "In Review"}}
        client = _FakeAsyncClient(_FakeResponse(200, plugin_body))

        _run(jira_actions.transition_action_item("uid-1", "ai-1", "In Review", http_client=client))

        fields_arg = action_items_db.update_action_item.call_args.args[2]
        new_md = fields_arg["external_source"]["metadata"]
        assert new_md["status"] == "In Review"
        assert new_md["status_type"] == "indeterminate"
        # Not completed — no `completed` flip when transitioning to in-progress
        assert "completed" not in fields_arg

    def test_reopening_completed_item_clears_completed(self):
        action_items_db.get_action_item.side_effect = [
            _action_item(completed=True, metadata={"status": "Done", "status_type": "done"}),
            _action_item(completed=False, metadata={"status": "To Do", "status_type": "todo"}),
        ]
        plugin_body = {"result": "ok", "data": {"issue_key": "PROJ-1", "status": "To Do"}}
        client = _FakeAsyncClient(_FakeResponse(200, plugin_body))

        _run(jira_actions.transition_action_item("uid-1", "ai-1", "To Do", http_client=client))

        fields_arg = action_items_db.update_action_item.call_args.args[2]
        assert fields_arg["completed"] is False

    def test_action_item_missing_raises_not_found(self):
        action_items_db.get_action_item.return_value = None
        client = _FakeAsyncClient(_FakeResponse(200, {}))

        with pytest.raises(jira_actions.JiraActionNotFound):
            _run(jira_actions.transition_action_item("uid-1", "ai-1", "Done", http_client=client))

        # Plugin must NOT have been called for a missing item.
        assert client.posts == []

    def test_action_item_not_jira_linked_raises_not_found(self):
        action_items_db.get_action_item.return_value = {
            "id": "ai-1",
            "description": "manual",
            "external_source": None,
        }
        client = _FakeAsyncClient(_FakeResponse(200, {}))

        with pytest.raises(jira_actions.JiraActionNotFound):
            _run(jira_actions.transition_action_item("uid-1", "ai-1", "Done", http_client=client))

        assert client.posts == []

    def test_plugin_5xx_raises_plugin_error(self):
        action_items_db.get_action_item.return_value = _action_item()
        client = _FakeAsyncClient(_FakeResponse(500, {}, raw_text="Internal Server Error"))

        with pytest.raises(jira_actions.JiraActionPluginError):
            _run(jira_actions.transition_action_item("uid-1", "ai-1", "Done", http_client=client))

        # Local doc must NOT have been mutated.
        assert action_items_db.update_action_item.called is False

    def test_plugin_error_payload_raises_plugin_error(self):
        action_items_db.get_action_item.return_value = _action_item()
        plugin_body = {"error": "Jira auth failed.", "oauth_url": "https://omi/auth"}
        client = _FakeAsyncClient(_FakeResponse(200, plugin_body))

        with pytest.raises(jira_actions.JiraActionPluginError):
            _run(jira_actions.transition_action_item("uid-1", "ai-1", "Done", http_client=client))

        assert action_items_db.update_action_item.called is False

    def test_plugin_network_error_raises_plugin_error(self):
        import httpx

        action_items_db.get_action_item.return_value = _action_item()
        client = _FakeAsyncClient([])
        client.network_error = httpx.RequestError("connection refused")

        with pytest.raises(jira_actions.JiraActionPluginError):
            _run(jira_actions.transition_action_item("uid-1", "ai-1", "Done", http_client=client))

    def test_invalid_transition_response_raises_plugin_error(self):
        # Plugin's update_issue_status returns 200 with `data.available` when
        # the named status isn't a valid transition. We surface that as
        # a plugin error so the router returns 502.
        action_items_db.get_action_item.return_value = _action_item()
        plugin_body = {
            "result": "Could not find status 'Quux'.",
            "data": {"issue_key": "PROJ-1", "available": ["To Do", "In Progress"]},
        }
        client = _FakeAsyncClient(_FakeResponse(200, plugin_body))

        with pytest.raises(jira_actions.JiraActionPluginError):
            _run(jira_actions.transition_action_item("uid-1", "ai-1", "Quux", http_client=client))

        assert action_items_db.update_action_item.called is False

    def test_empty_to_status_raises_plugin_error(self):
        with pytest.raises(jira_actions.JiraActionPluginError):
            _run(jira_actions.transition_action_item("uid-1", "ai-1", "  "))


# ===========================================================================
# snooze_action_item
# ===========================================================================


class TestSnoozeActionItem:

    def test_success_updates_due_at(self):
        action_items_db.get_action_item.side_effect = [
            _action_item(),
            _action_item(due_at=datetime(2026, 5, 4, tzinfo=timezone.utc)),
        ]
        plugin_body = {"result": "Set due", "data": {"issue_key": "PROJ-1", "due_date": "2026-05-04"}}
        client = _FakeAsyncClient(_FakeResponse(200, plugin_body))

        snooze_until = datetime(2026, 5, 4, tzinfo=timezone.utc)
        _run(jira_actions.snooze_action_item("uid-1", "ai-1", snooze_until, http_client=client))

        # Plugin called with YYYY-MM-DD
        assert client.posts[0]["url"] == "https://plugin.example.com/tools/update_issue_due_date"
        assert client.posts[0]["json"] == {"uid": "uid-1", "issue_key": "PROJ-1", "due_date": "2026-05-04"}

        # Local update — due_at set to the parsed datetime (UTC)
        update_args = action_items_db.update_action_item.call_args
        fields_arg = update_args.args[2]
        assert fields_arg["due_at"] == snooze_until

    def test_naive_datetime_treated_as_utc(self):
        action_items_db.get_action_item.side_effect = [_action_item(), _action_item()]
        plugin_body = {"result": "Set due", "data": {}}
        client = _FakeAsyncClient(_FakeResponse(200, plugin_body))

        # Naive datetime — helper coerces to UTC.
        naive = datetime(2026, 5, 4, 12, 0, 0)
        _run(jira_actions.snooze_action_item("uid-1", "ai-1", naive, http_client=client))

        assert client.posts[0]["json"]["due_date"] == "2026-05-04"

    def test_action_item_missing_raises_not_found(self):
        action_items_db.get_action_item.return_value = None
        client = _FakeAsyncClient(_FakeResponse(200, {}))

        with pytest.raises(jira_actions.JiraActionNotFound):
            _run(
                jira_actions.snooze_action_item(
                    "uid-1", "ai-1", datetime(2026, 5, 4, tzinfo=timezone.utc), http_client=client
                )
            )

    def test_plugin_5xx_raises_plugin_error(self):
        action_items_db.get_action_item.return_value = _action_item()
        client = _FakeAsyncClient(_FakeResponse(500, {}, raw_text="boom"))

        with pytest.raises(jira_actions.JiraActionPluginError):
            _run(
                jira_actions.snooze_action_item(
                    "uid-1", "ai-1", datetime(2026, 5, 4, tzinfo=timezone.utc), http_client=client
                )
            )
        assert action_items_db.update_action_item.called is False

    def test_plugin_error_payload_raises_plugin_error(self):
        action_items_db.get_action_item.return_value = _action_item()
        client = _FakeAsyncClient(_FakeResponse(200, {"error": "Issue not found."}))

        with pytest.raises(jira_actions.JiraActionPluginError):
            _run(
                jira_actions.snooze_action_item(
                    "uid-1", "ai-1", datetime(2026, 5, 4, tzinfo=timezone.utc), http_client=client
                )
            )
        assert action_items_db.update_action_item.called is False

    def test_non_datetime_raises(self):
        with pytest.raises(jira_actions.JiraActionPluginError):
            _run(jira_actions.snooze_action_item("uid-1", "ai-1", "2026-05-04"))


# ===========================================================================
# Plugin URL not configured → not_found
# ===========================================================================


class TestPluginNotConfigured:
    def test_no_plugin_url_raises_not_found(self):
        os.environ.pop("NOOTO_JIRA_PLUGIN_URL", None)
        apps_db.get_app_by_id_db.return_value = None
        action_items_db.get_action_item.return_value = _action_item()
        client = _FakeAsyncClient(_FakeResponse(200, {}))

        with pytest.raises(jira_actions.JiraActionNotFound):
            _run(jira_actions.transition_action_item("uid-1", "ai-1", "Done", http_client=client))

        # Restore for subsequent tests in the file.
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"


# ===========================================================================
# Logging sanitization — no raw token-shaped strings leak
# ===========================================================================


class TestLoggingSanitization:
    """When the plugin returns an error body that includes a token-shaped
    string (8+ chars with digits), the error log MUST mask it. We rely on
    ``utils.log_sanitizer.sanitize`` — this test exercises the path."""

    def test_token_in_5xx_response_body_is_masked(self, caplog):
        action_items_db.get_action_item.return_value = _action_item()
        # Token with digits → must be masked by sanitize().
        token_like = "abcd1234efgh5678zzzz"
        body_with_token = f"Internal error trace: token={token_like}"
        client = _FakeAsyncClient(_FakeResponse(500, {}, raw_text=body_with_token))

        with caplog.at_level(logging.WARNING):
            with pytest.raises(jira_actions.JiraActionPluginError):
                _run(jira_actions.transition_action_item("uid-1", "ai-1", "Done", http_client=client))

        # The full token must NOT appear verbatim in any log record.
        for record in caplog.records:
            assert token_like not in record.getMessage()

    def test_token_in_plugin_error_field_is_masked(self, caplog):
        action_items_db.get_action_item.return_value = _action_item()
        token_like = "secrettok1234567890ab"
        plugin_body = {"error": f"Auth failed with token {token_like}"}
        client = _FakeAsyncClient(_FakeResponse(200, plugin_body))

        with caplog.at_level(logging.INFO):
            with pytest.raises(jira_actions.JiraActionPluginError):
                _run(jira_actions.transition_action_item("uid-1", "ai-1", "Done", http_client=client))

        for record in caplog.records:
            assert token_like not in record.getMessage()


# ===========================================================================
# Status-type inference
# ===========================================================================


class TestInferStatusType:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Done", "done"),
            ("Closed", "done"),
            ("Resolved", "done"),
            ("Won't Do", "done"),
            ("To Do", "todo"),
            ("Open", "todo"),
            ("Backlog", "todo"),
            ("In Progress", "indeterminate"),
            ("In Review", "indeterminate"),
            ("Code Review", "indeterminate"),
            ("Some Custom Workflow Step", "indeterminate"),
            ("", "indeterminate"),
        ],
    )
    def test_mapping(self, name, expected):
        assert jira_actions._infer_status_type(name) == expected


# ===========================================================================
# Router endpoints — gating + status code mapping
# ===========================================================================
#
# We only test the gating + error mapping logic here. We don't spin up a
# FastAPI app; instead we call the route functions directly with stubs.
# The 403 path is the most important — it's the hard product rule.


def _stub_fastapi():
    """Provide just-enough fastapi / fastapi.responses / fastapi.templating
    stubs that ``routers.integrations`` can import. Pydantic is real (it
    ships with the venv), so request models still validate properly.

    Only callable surface used by the two routes under test is:
      - ``APIRouter`` — collects route handlers (we just call them directly)
      - ``HTTPException`` — raised by the gate; tests assert .status_code/.detail
      - ``Depends`` — passthrough decorator (not exercised here)
    """
    if "fastapi" in sys.modules and getattr(sys.modules["fastapi"], "_TEST_STUB", False):
        return  # already stubbed

    fastapi_mod = _stub_module("fastapi")
    fastapi_mod._TEST_STUB = True

    class _APIRouter:
        def __init__(self, *a, **kw):
            self.routes = []

        def _decorator(self, *a, **kw):
            def _wrap(fn):
                self.routes.append(fn)
                return fn

            return _wrap

        def get(self, *a, **kw):
            return self._decorator(*a, **kw)

        def post(self, *a, **kw):
            return self._decorator(*a, **kw)

        def put(self, *a, **kw):
            return self._decorator(*a, **kw)

        def patch(self, *a, **kw):
            return self._decorator(*a, **kw)

        def delete(self, *a, **kw):
            return self._decorator(*a, **kw)

        def on_event(self, *a, **kw):
            return self._decorator(*a, **kw)

    class _HTTPException(Exception):
        def __init__(self, status_code, detail=None):
            super().__init__(f"HTTP {status_code}: {detail}")
            self.status_code = status_code
            self.detail = detail

    def _Depends(dep=None):
        return dep

    def _Header(default=None):
        return default

    def _Query(default=None, **kw):
        return default

    class _Request:
        pass

    fastapi_mod.APIRouter = _APIRouter
    fastapi_mod.HTTPException = _HTTPException
    fastapi_mod.Depends = _Depends
    fastapi_mod.Header = _Header
    fastapi_mod.Query = _Query
    fastapi_mod.Request = _Request

    fastapi_responses = _stub_module("fastapi.responses")

    class _HTMLResponse:
        def __init__(self, content="", status_code=200):
            self.content = content
            self.status_code = status_code

    fastapi_responses.HTMLResponse = _HTMLResponse

    fastapi_templating = _stub_module("fastapi.templating")

    class _Jinja2Templates:
        def __init__(self, directory=None):
            self.directory = directory

        def TemplateResponse(self, *a, **kw):
            return _HTMLResponse()

    fastapi_templating.Jinja2Templates = _Jinja2Templates


def _load_routers_integrations():
    """Load the router module with the heavy deps stubbed."""
    _stub_fastapi()

    # Stub database submodules used by the router
    db_users = _stub_module("database.users")
    db_users.get_integration = MagicMock()
    db_users.set_integration = MagicMock()
    db_users.delete_integration = MagicMock()

    db_redis = _stub_module("database.redis_db")

    class _R:
        def get(self, *a, **kw):
            return None

        def setex(self, *a, **kw):
            pass

        def delete(self, *a, **kw):
            pass

    db_redis.r = _R()
    # is_app_enabled is imported by routers.integrations for the sync-now path;
    # default-True so the gating doesn't 400 in tests that don't need it.
    db_redis.is_app_enabled = MagicMock(return_value=True)

    db_prefs = _stub_module("database.integration_prefs")
    db_prefs.get_integration_pref = MagicMock(return_value=None)
    db_prefs.set_integration_pref = MagicMock(return_value={})
    db_prefs.is_two_way_sync_enabled = MagicMock(return_value=False)

    # utils.other.endpoints — auth shim
    _stub_package("utils.other")
    sys.modules["utils.other"].__path__ = [str(BACKEND_DIR / "utils" / "other")]
    auth_mod = _stub_module("utils.other.endpoints")
    auth_mod.get_current_user_uid = MagicMock(return_value="uid-1")

    # Pre-register the already-loaded jira_actions module so the router
    # picks up our stubbed instance instead of re-loading it.
    sys.modules["utils.integrations.jira_actions"] = jira_actions

    # Need a `routers` package on sys.path so the importlib spec resolves.
    _stub_package("routers")
    sys.modules["routers"].__path__ = [str(BACKEND_DIR / "routers")]

    mod = _load_from(
        "routers.integrations",
        BACKEND_DIR / "routers" / "integrations.py",
    )

    return mod, db_prefs, auth_mod


router_mod, prefs_mod, auth_mod = _load_routers_integrations()


class TestTransitionRoute:

    def test_returns_403_when_two_way_sync_off(self):
        prefs_mod.is_two_way_sync_enabled.return_value = False

        HTTPException = sys.modules["fastapi"].HTTPException

        with pytest.raises(HTTPException) as exc:
            _run(
                router_mod.jira_transition(
                    router_mod.JiraTransitionRequest(action_item_id="ai-1", to_status="Done"),
                    uid="uid-1",
                )
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == {"error": "two_way_sync_disabled"}

    def test_returns_502_on_plugin_error(self, monkeypatch):
        prefs_mod.is_two_way_sync_enabled.return_value = True

        async def boom(*a, **kw):
            raise jira_actions.JiraActionPluginError("plugin broke")

        monkeypatch.setattr(jira_actions, "transition_action_item", boom)

        HTTPException = sys.modules["fastapi"].HTTPException

        with pytest.raises(HTTPException) as exc:
            _run(
                router_mod.jira_transition(
                    router_mod.JiraTransitionRequest(action_item_id="ai-1", to_status="Done"),
                    uid="uid-1",
                )
            )

        assert exc.value.status_code == 502
        assert exc.value.detail == {"error": "jira_plugin_error"}

    def test_returns_404_on_missing_item(self, monkeypatch):
        prefs_mod.is_two_way_sync_enabled.return_value = True

        async def missing(*a, **kw):
            raise jira_actions.JiraActionNotFound("not found")

        monkeypatch.setattr(jira_actions, "transition_action_item", missing)

        HTTPException = sys.modules["fastapi"].HTTPException

        with pytest.raises(HTTPException) as exc:
            _run(
                router_mod.jira_transition(
                    router_mod.JiraTransitionRequest(action_item_id="ai-1", to_status="Done"),
                    uid="uid-1",
                )
            )

        assert exc.value.status_code == 404

    def test_success_returns_updated_item(self, monkeypatch):
        prefs_mod.is_two_way_sync_enabled.return_value = True

        async def ok(uid, ai_id, status, http_client=None):
            return {"id": ai_id, "completed": True, "external_source": {"source": "jira"}}

        monkeypatch.setattr(jira_actions, "transition_action_item", ok)

        result = _run(
            router_mod.jira_transition(
                router_mod.JiraTransitionRequest(action_item_id="ai-1", to_status="Done"),
                uid="uid-1",
            )
        )
        assert result["completed"] is True


class TestSnoozeRoute:

    def test_returns_403_when_two_way_sync_off(self):
        prefs_mod.is_two_way_sync_enabled.return_value = False

        HTTPException = sys.modules["fastapi"].HTTPException

        with pytest.raises(HTTPException) as exc:
            _run(
                router_mod.jira_snooze(
                    router_mod.JiraSnoozeRequest(
                        action_item_id="ai-1", snooze_until=datetime(2026, 5, 4, tzinfo=timezone.utc)
                    ),
                    uid="uid-1",
                )
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == {"error": "two_way_sync_disabled"}

    def test_returns_502_on_plugin_error(self, monkeypatch):
        prefs_mod.is_two_way_sync_enabled.return_value = True

        async def boom(*a, **kw):
            raise jira_actions.JiraActionPluginError("plugin broke")

        monkeypatch.setattr(jira_actions, "snooze_action_item", boom)

        HTTPException = sys.modules["fastapi"].HTTPException

        with pytest.raises(HTTPException) as exc:
            _run(
                router_mod.jira_snooze(
                    router_mod.JiraSnoozeRequest(
                        action_item_id="ai-1", snooze_until=datetime(2026, 5, 4, tzinfo=timezone.utc)
                    ),
                    uid="uid-1",
                )
            )

        assert exc.value.status_code == 502
        assert exc.value.detail == {"error": "jira_plugin_error"}

    def test_success_returns_updated_item(self, monkeypatch):
        prefs_mod.is_two_way_sync_enabled.return_value = True

        async def ok(uid, ai_id, snooze, http_client=None):
            return {"id": ai_id, "due_at": snooze, "external_source": {"source": "jira"}}

        monkeypatch.setattr(jira_actions, "snooze_action_item", ok)

        snooze = datetime(2026, 5, 4, tzinfo=timezone.utc)
        result = _run(
            router_mod.jira_snooze(
                router_mod.JiraSnoozeRequest(action_item_id="ai-1", snooze_until=snooze),
                uid="uid-1",
            )
        )
        assert result["due_at"] == snooze
