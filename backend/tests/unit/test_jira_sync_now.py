"""Tests for the manual ``POST /v1/integrations/jira/sync-now`` affordance.

Two layers:

1. ``sync_user_jira_issues_with_timestamp`` — the wrapper that adds
   ``last_synced_at`` and persists it to Firestore via integration_prefs.
2. ``jira_sync_now`` router handler — the install-gate (400), the success
   shape (200), and the sanitized 502 path on plugin failure.

FastAPI / pydantic / jinja2 are not installed in the test venv; we stub the
exact surface area used by ``routers.integrations`` (APIRouter, Depends,
HTTPException, Query, Request, HTMLResponse, Jinja2Templates, BaseModel/Field)
so the module loads without pulling in the real framework.
"""

import asyncio
import importlib.util
import logging
import os
import sys
import types
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
# FastAPI / pydantic / jinja2 / httpx stubs
# ---------------------------------------------------------------------------


class _FakeHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class _FakeAPIRouter:
    def __init__(self, *args, **kwargs):
        self.routes = []

    # All decorators are identity functions — we call the raw handler
    # directly in tests.
    def _identity(self, *args, **kwargs):
        def deco(fn):
            return fn

        return deco

    def get(self, *args, **kwargs):
        return self._identity()

    def post(self, *args, **kwargs):
        return self._identity()

    def put(self, *args, **kwargs):
        return self._identity()

    def patch(self, *args, **kwargs):
        return self._identity()

    def delete(self, *args, **kwargs):
        return self._identity()

    def on_event(self, *args, **kwargs):
        return self._identity()


def _fake_depends(dependency=None):
    # Real FastAPI returns a Depends marker; for our direct-call tests we
    # never trigger DI, so any sentinel works.
    return dependency


def _fake_query(default=None, **kwargs):
    return default


# pydantic v2-ish: BaseModel that accepts kwargs and exposes them as attributes.
class _FakeBaseModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def model_dump(self, exclude_none=False):
        out = {}
        for k, v in self.__dict__.items():
            if exclude_none and v is None:
                continue
            out[k] = v
        return out


def _fake_field(default=None, **kwargs):
    return default


# fastapi — share the stub if test_jira_actions already installed one this
# session (collection order can put it first). Otherwise install ours and
# mark _TEST_STUB so test_jira_actions' guard reuses these classes.
if "fastapi" in sys.modules and getattr(sys.modules["fastapi"], "_TEST_STUB", False):
    fastapi_pkg = sys.modules["fastapi"]
    _FakeHTTPException = fastapi_pkg.HTTPException  # rebind for our local use
    _FakeAPIRouter = fastapi_pkg.APIRouter
else:
    fastapi_pkg = _stub_package("fastapi")
    fastapi_pkg.APIRouter = _FakeAPIRouter
    fastapi_pkg.Depends = _fake_depends
    fastapi_pkg.HTTPException = _FakeHTTPException
    fastapi_pkg.Query = _fake_query
    fastapi_pkg.Request = object  # never instantiated in our handler
    fastapi_pkg._TEST_STUB = True

# fastapi.responses
fastapi_responses = _stub_module("fastapi.responses")


class _FakeHTMLResponse:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


fastapi_responses.HTMLResponse = _FakeHTMLResponse

# fastapi.templating
fastapi_templating = _stub_module("fastapi.templating")


class _FakeJinja2Templates:
    def __init__(self, *args, **kwargs):
        pass

    def TemplateResponse(self, *args, **kwargs):  # noqa: N802 — match real API
        return _FakeHTMLResponse()


fastapi_templating.Jinja2Templates = _FakeJinja2Templates

# pydantic
pydantic_pkg = _stub_package("pydantic")
pydantic_pkg.BaseModel = _FakeBaseModel
pydantic_pkg.Field = _fake_field


# httpx — the real one is installed but we don't want network. The router
# imports `httpx` for OAuth callbacks; we provide a minimal stub so import
# succeeds in environments without it.
try:
    import httpx as _httpx_real  # noqa: F401  — verify real httpx is present
except ImportError:  # pragma: no cover — defensive
    httpx_pkg = _stub_module("httpx")
    httpx_pkg.AsyncClient = MagicMock
    httpx_pkg.RequestError = Exception


# ---------------------------------------------------------------------------
# database stubs
# ---------------------------------------------------------------------------

_stub_package("database")
sys.modules["database"].__path__ = [str(BACKEND_DIR / "database")]

users_db = _stub_module("database.users")
users_db.get_integration = MagicMock(return_value=None)
users_db.set_integration = MagicMock()
users_db.delete_integration = MagicMock(return_value=True)


class _FakeRedisClient:
    def __init__(self):
        self.kv = {}

    def get(self, k):
        return self.kv.get(k)

    def setex(self, k, ttl, v):
        self.kv[k] = v

    def delete(self, k):
        self.kv.pop(k, None)


redis_db_mod = _stub_module("database.redis_db")
redis_db_mod.r = _FakeRedisClient()
redis_db_mod.is_app_enabled = MagicMock(return_value=True)

action_items_db = _stub_module("database.action_items")
action_items_db.upsert_external_action_item = MagicMock(return_value="item-1")
# jira_sync deep-merges metadata by reading the prior doc; default-None so the
# wrapper tests don't need to set up a fake doc to exercise the timestamp path.
action_items_db._find_by_external_source = MagicMock(return_value=None)

apps_db = _stub_module("database.apps")
apps_db.get_app_by_id_db = MagicMock(return_value=None)

integration_prefs_db = _stub_module("database.integration_prefs")
integration_prefs_db.set_integration_pref = MagicMock(return_value={})
integration_prefs_db.get_integration_pref = MagicMock(return_value=None)

# ---------------------------------------------------------------------------
# utils stubs
# ---------------------------------------------------------------------------

_stub_package("utils")
sys.modules["utils"].__path__ = [str(BACKEND_DIR / "utils")]
_stub_package("utils.integrations")
sys.modules["utils.integrations"].__path__ = [str(BACKEND_DIR / "utils" / "integrations")]

log_san = _stub_module("utils.log_sanitizer")
log_san.sanitize = lambda v: str(v)
log_san.sanitize_pii = lambda v: str(v)

# utils.other.endpoints — DI dependency for routers (we never invoke it via DI)
_stub_package("utils.other")
sys.modules["utils.other"].__path__ = []
endpoints_mod = _stub_module("utils.other.endpoints")
endpoints_mod.get_current_user_uid = MagicMock(return_value="uid-test")


# ---------------------------------------------------------------------------
# Load real modules under test
# ---------------------------------------------------------------------------


def _load_module(dotted_name, file_path):
    spec = importlib.util.spec_from_file_location(dotted_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod


jira_sync = _load_module("utils.integrations.jira_sync", BACKEND_DIR / "utils" / "integrations" / "jira_sync.py")
integrations_router = _load_module("routers.integrations", BACKEND_DIR / "routers" / "integrations.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _reset():
    action_items_db.upsert_external_action_item.reset_mock()
    apps_db.get_app_by_id_db.reset_mock()
    apps_db.get_app_by_id_db.return_value = None
    integration_prefs_db.set_integration_pref.reset_mock()
    integration_prefs_db.set_integration_pref.return_value = {}
    redis_db_mod.is_app_enabled.reset_mock()
    redis_db_mod.is_app_enabled.return_value = True
    os.environ.pop("NOOTO_JIRA_PLUGIN_URL", None)
    yield


# ---------------------------------------------------------------------------
# Wrapper tests: sync_user_jira_issues_with_timestamp
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response
        self.posts = []
        self.closed = False

    async def post(self, url, json=None):
        self.posts.append({"url": url, "json": json})
        return self._response

    async def aclose(self):
        self.closed = True


class TestSyncUserJiraIssuesWithTimestamp:
    def test_adds_iso_timestamp_and_persists(self):
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"
        body = {
            "data": {
                "tasks": [
                    {"external_id": "PROJ-1", "title": "Task 1", "status_type": "todo"},
                ]
            }
        }
        client = _FakeAsyncClient(_FakeResponse(200, body))

        result = _run(jira_sync.sync_user_jira_issues_with_timestamp("uid-1", http_client=client))

        # Original keys preserved
        assert result["synced"] == 1
        assert result["errors"] == 0
        # New key: ISO8601 string with timezone
        assert isinstance(result["last_synced_at"], str)
        assert "T" in result["last_synced_at"]
        assert result["last_synced_at"].endswith("+00:00") or result["last_synced_at"].endswith("Z")
        # Persisted to Firestore via integration_prefs
        integration_prefs_db.set_integration_pref.assert_called_once()
        call_kwargs = integration_prefs_db.set_integration_pref.call_args
        assert call_kwargs.args[0] == "uid-1"
        assert call_kwargs.args[1] == "nooto-jira"
        assert call_kwargs.kwargs["last_synced_at"] == result["last_synced_at"]

    def test_returns_timestamp_even_on_zero_synced(self):
        # Plugin URL missing → wrapper still stamps the timestamp on the
        # error result so the UI can show "Last sync attempted N min ago"
        # without crashing on a missing key.
        apps_db.get_app_by_id_db.return_value = None
        client = _FakeAsyncClient(_FakeResponse(200, {"data": {"tasks": []}}))

        result = _run(jira_sync.sync_user_jira_issues_with_timestamp("uid-1", http_client=client))

        assert "last_synced_at" in result
        assert result["errors"] == 1  # carried through from underlying call

    def test_persistence_failure_does_not_mask_sync_result(self):
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"
        integration_prefs_db.set_integration_pref.side_effect = RuntimeError("firestore down")
        body = {"data": {"tasks": [{"external_id": "PROJ-1", "title": "x", "status_type": "todo"}]}}
        client = _FakeAsyncClient(_FakeResponse(200, body))

        # Must not raise — the sync itself succeeded.
        result = _run(jira_sync.sync_user_jira_issues_with_timestamp("uid-1", http_client=client))

        assert result["synced"] == 1
        assert "last_synced_at" in result


# ---------------------------------------------------------------------------
# Endpoint tests: jira_sync_now handler
# ---------------------------------------------------------------------------


class TestJiraSyncNowEndpoint:
    def test_200_path_returns_shape(self):
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"
        redis_db_mod.is_app_enabled.return_value = True
        # Patch the wrapper to skip the network and return a deterministic dict.
        original = integrations_router.sync_user_jira_issues_with_timestamp

        async def _fake_wrapper(uid):
            return {"synced": 3, "errors": 0, "skipped": 0, "last_synced_at": "2026-05-01T12:00:00+00:00"}

        integrations_router.sync_user_jira_issues_with_timestamp = _fake_wrapper
        try:
            resp = _run(integrations_router.jira_sync_now(uid="uid-1"))
        finally:
            integrations_router.sync_user_jira_issues_with_timestamp = original

        # FakeBaseModel exposes fields as attributes
        assert resp.synced == 3
        assert resp.errors == 0
        assert resp.last_synced_at == "2026-05-01T12:00:00+00:00"
        # Install-gate was checked
        redis_db_mod.is_app_enabled.assert_called_once_with("uid-1", "nooto-jira")

    def test_400_when_plugin_not_installed(self):
        redis_db_mod.is_app_enabled.return_value = False

        with pytest.raises(_FakeHTTPException) as excinfo:
            _run(integrations_router.jira_sync_now(uid="uid-1"))

        assert excinfo.value.status_code == 400
        assert excinfo.value.detail == "jira_not_installed"
        # Wrapper must NOT have been called when the gate fails.
        integration_prefs_db.set_integration_pref.assert_not_called()

    def test_502_on_unhandled_plugin_error_with_sanitized_log(self, caplog):
        redis_db_mod.is_app_enabled.return_value = True
        original = integrations_router.sync_user_jira_issues_with_timestamp

        async def _boom(uid):
            raise RuntimeError("plugin token=ABCDEFGH12345 leaked")

        integrations_router.sync_user_jira_issues_with_timestamp = _boom
        try:
            with caplog.at_level(logging.ERROR, logger=integrations_router.logger.name):
                with pytest.raises(_FakeHTTPException) as excinfo:
                    _run(integrations_router.jira_sync_now(uid="uid-7"))
        finally:
            integrations_router.sync_user_jira_issues_with_timestamp = original

        assert excinfo.value.status_code == 502
        assert excinfo.value.detail == "jira_plugin_error"
        # The error was logged through sanitize() (we stubbed it as str()),
        # so the log line exists but doesn't surface the raw exception in
        # the response detail. UID must remain visible for support triage.
        assert any("uid=uid-7" in rec.message for rec in caplog.records)

    def test_explicit_http_exception_is_not_double_wrapped(self):
        # If something downstream raises an HTTPException directly (e.g.
        # we ever decide to gate inside the wrapper), the handler must
        # propagate it as-is rather than collapsing to 502.
        redis_db_mod.is_app_enabled.return_value = True
        original = integrations_router.sync_user_jira_issues_with_timestamp

        async def _raise_404(uid):
            raise _FakeHTTPException(status_code=404, detail="missing")

        integrations_router.sync_user_jira_issues_with_timestamp = _raise_404
        try:
            with pytest.raises(_FakeHTTPException) as excinfo:
                _run(integrations_router.jira_sync_now(uid="uid-1"))
        finally:
            integrations_router.sync_user_jira_issues_with_timestamp = original

        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == "missing"


# ---------------------------------------------------------------------------
# Auth bypass — middleware-equivalent: the handler depends on
# auth.get_current_user_uid via FastAPI's Depends. With FastAPI stubbed,
# direct calls require the caller to pass uid explicitly. This test asserts
# the dependency wiring is in place (the function signature uses Depends on
# get_current_user_uid) — the real 401 behavior is handled by the FastAPI
# layer at runtime, identical to every other endpoint in this file.
# ---------------------------------------------------------------------------


class TestAuthDependency:
    def test_handler_uses_auth_dependency(self):
        import inspect

        sig = inspect.signature(integrations_router.jira_sync_now)
        params = list(sig.parameters.values())
        assert any(p.name == "uid" for p in params), "handler must take uid via Depends(get_current_user_uid)"
        # The default value of `uid` is the Depends marker (our fake_depends
        # returns the dependency itself). Confirm it points at our stub.
        uid_default = sig.parameters["uid"].default
        assert uid_default is endpoints_mod.get_current_user_uid
