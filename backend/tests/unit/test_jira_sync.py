"""Tests for the Jira → Omi action items sync (read path / cron job).

Covers:
- ``sync_user_jira_issues`` calls upsert with the right shape per task
- Idempotency: second run with the same payload calls upsert again, but the
  upsert helper ensures only one doc per ``(source, external_id)`` (verified
  in test_action_items_external_source.py — here we just assert the same
  external_source key is reused)
- Plugin URL resolution (env var wins over Firestore lookup)
- Skipping tasks without ``external_id``
"""

import asyncio
import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
# Stubs for heavy deps
# ---------------------------------------------------------------------------

# database
_stub_package("database")
sys.modules["database"].__path__ = [str(BACKEND_DIR / "database")]

action_items_db = _stub_module("database.action_items")
action_items_db.upsert_external_action_item = MagicMock(return_value="item-1")
# Default: no prior doc — sync builds metadata from scratch. Tests that
# exercise the deep-merge path override this with a snapshot stub.
action_items_db._find_by_external_source = MagicMock(return_value=None)
action_items_db.action_items_collection = "action_items"

apps_db = _stub_module("database.apps")
apps_db.get_app_by_id_db = MagicMock(return_value=None)

integration_prefs_db = _stub_module("database.integration_prefs")
integration_prefs_db.set_integration_pref = MagicMock(return_value={})
integration_prefs_db.get_integration_pref = MagicMock(return_value=None)


class _FakeRedis:
    def __init__(self):
        self.keys = []
        self.enabled = {}

    def scan_iter(self, pattern, count=None):
        for k in self.keys:
            yield k.encode() if isinstance(k, str) else k

    def sismember(self, key, value):
        return value in self.enabled.get(key, set())


fake_redis = _FakeRedis()
redis_mod = _stub_module("database.redis_db")
redis_mod.r = fake_redis


def _is_app_enabled(uid, app_id):
    return app_id in fake_redis.enabled.get(f"users:{uid}:enabled_plugins", set())


redis_mod.is_app_enabled = _is_app_enabled

# utils
_stub_package("utils")
sys.modules["utils"].__path__ = [str(BACKEND_DIR / "utils")]
_stub_package("utils.integrations")
sys.modules["utils.integrations"].__path__ = [str(BACKEND_DIR / "utils" / "integrations")]

log_san = _stub_module("utils.log_sanitizer")
log_san.sanitize = lambda v: str(v)
log_san.sanitize_pii = lambda v: str(v)


def _load_jira_sync():
    spec = importlib.util.spec_from_file_location(
        "utils.integrations.jira_sync",
        str(BACKEND_DIR / "utils" / "integrations" / "jira_sync.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["utils.integrations.jira_sync"] = mod
    spec.loader.exec_module(mod)
    return mod


jira_sync = _load_jira_sync()


@pytest.fixture(autouse=True)
def _reset():
    action_items_db.upsert_external_action_item.reset_mock()
    action_items_db.upsert_external_action_item.return_value = "item-1"
    action_items_db._find_by_external_source.reset_mock()
    action_items_db._find_by_external_source.return_value = None
    apps_db.get_app_by_id_db.reset_mock()
    apps_db.get_app_by_id_db.return_value = None
    fake_redis.keys = []
    fake_redis.enabled = {}
    os.environ.pop("NOOTO_JIRA_PLUGIN_URL", None)
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


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

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPluginUrlResolution:
    def test_env_var_wins(self):
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://jira-plugin.example.com/"
        assert jira_sync._resolve_plugin_base_url() == "https://jira-plugin.example.com"

    def test_firestore_fallback(self):
        apps_db.get_app_by_id_db.return_value = {
            "external_integration": {"app_home_url": "https://from-firestore.example.com/"}
        }
        assert jira_sync._resolve_plugin_base_url() == "https://from-firestore.example.com"

    def test_returns_none_when_unconfigured(self):
        apps_db.get_app_by_id_db.return_value = None
        assert jira_sync._resolve_plugin_base_url() is None


class TestNormalizeTaskToActionItem:
    def test_basic_mapping(self):
        task = {
            "external_id": "PROJ-1",
            "title": "Ship the thing",
            "status_type": "todo",
            "due_at": "2025-12-01",
            "url": "https://x/browse/PROJ-1",
        }
        fields = jira_sync._normalize_task_to_action_item(task)
        assert fields["description"] == "Ship the thing"
        assert fields["completed"] is False
        assert fields["due_at"] is not None
        assert fields["conversation_id"] is None

    def test_done_status_marks_completed(self):
        task = {"external_id": "PROJ-1", "title": "Done thing", "status_type": "done"}
        assert jira_sync._normalize_task_to_action_item(task)["completed"] is True

    def test_invalid_due_date_falls_back_to_none(self):
        task = {"external_id": "PROJ-1", "title": "x", "due_at": "not-a-date"}
        assert jira_sync._normalize_task_to_action_item(task)["due_at"] is None

    def test_external_source_shape(self):
        task = {"external_id": "PROJ-1", "url": "https://x/browse/PROJ-1"}
        ext = jira_sync._build_external_source(task)
        # No metadata-shaped fields in the task → no metadata key emitted at all.
        assert ext == {"source": "jira", "external_id": "PROJ-1", "url": "https://x/browse/PROJ-1"}


class TestExternalSourceMetadata:
    """Plan-screen metadata population: status / status_type / project_key /
    priority / status_changed_at — all under ``external_source.metadata``."""

    def test_full_metadata_emitted_when_task_has_all_fields(self):
        task = {
            "external_id": "PROJ-7",
            "url": "https://x/PROJ-7",
            "status": "In Review",
            "status_type": "in_progress",  # plugin's chat-tool vocabulary
            "priority": "High",
            "project_key": "PROJ",
            "status_changed_at": "2026-04-28T14:00:00.000+0000",
        }
        ext = jira_sync._build_external_source(task)
        md = ext["metadata"]
        assert md["status"] == "In Review"
        # status_type is translated from "in_progress" → canonical "indeterminate"
        assert md["status_type"] == "indeterminate"
        assert md["priority"] == "High"
        assert md["project_key"] == "PROJ"
        assert md["status_changed_at"] == "2026-04-28T14:00:00.000+0000"

    def test_status_type_done_passes_through(self):
        task = {"external_id": "P-1", "status_type": "done"}
        ext = jira_sync._build_external_source(task)
        assert ext["metadata"]["status_type"] == "done"

    def test_status_type_todo_passes_through(self):
        task = {"external_id": "P-1", "status_type": "todo"}
        ext = jira_sync._build_external_source(task)
        assert ext["metadata"]["status_type"] == "todo"

    def test_legacy_project_key_falls_back_to_project(self):
        # Plugin used to emit only `project`. Sync still recognizes it.
        task = {"external_id": "P-1", "project": "LEGACY"}
        ext = jira_sync._build_external_source(task)
        assert ext["metadata"]["project_key"] == "LEGACY"

    def test_missing_fields_are_omitted_not_nulled(self):
        task = {"external_id": "P-1", "status": "Open"}
        ext = jira_sync._build_external_source(task)
        # Only `status` should be present in metadata — no `priority: None`
        # leaking through and lying to the Plan card.
        assert ext["metadata"] == {"status": "Open"}

    def test_deep_merge_preserves_prior_metadata_when_field_missing(self):
        # Prior sync had every field. New sync only returned `status`.
        prior = {
            "source": "jira",
            "external_id": "P-1",
            "url": "https://x/P-1",
            "metadata": {
                "status": "To Do",
                "status_type": "todo",
                "priority": "High",
                "project_key": "PROJ",
                "status_changed_at": "2026-04-01T00:00:00Z",
            },
        }
        task = {"external_id": "P-1", "status": "In Review", "status_type": "in_progress"}
        ext = jira_sync._build_external_source(task, prior_external_source=prior)
        md = ext["metadata"]
        # Refreshed fields use the new values
        assert md["status"] == "In Review"
        assert md["status_type"] == "indeterminate"
        # Untouched fields preserved verbatim
        assert md["priority"] == "High"
        assert md["project_key"] == "PROJ"
        assert md["status_changed_at"] == "2026-04-01T00:00:00Z"

    def test_deep_merge_no_prior_metadata(self):
        prior = {"source": "jira", "external_id": "P-1", "url": "https://x"}
        task = {"external_id": "P-1", "status": "Open"}
        ext = jira_sync._build_external_source(task, prior_external_source=prior)
        assert ext["metadata"] == {"status": "Open"}


class TestSyncUserJiraIssues:
    def test_calls_upsert_per_task(self):
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"
        body = {
            "data": {
                "tasks": [
                    {"external_id": "PROJ-1", "title": "Task 1", "status_type": "todo", "url": "https://x/PROJ-1"},
                    {"external_id": "PROJ-2", "title": "Task 2", "status_type": "done", "url": "https://x/PROJ-2"},
                ]
            }
        }
        client = _FakeAsyncClient(_FakeResponse(200, body))

        result = _run(jira_sync.sync_user_jira_issues("uid-1", http_client=client))

        assert result == {"synced": 2, "errors": 0, "skipped": 0}
        assert action_items_db.upsert_external_action_item.call_count == 2

        # Verify the first call shape
        first = action_items_db.upsert_external_action_item.call_args_list[0]
        uid_arg, ext_arg, fields_arg = first.args
        assert uid_arg == "uid-1"
        assert ext_arg["source"] == "jira"
        assert ext_arg["external_id"] == "PROJ-1"
        assert fields_arg["description"] == "Task 1"
        assert fields_arg["completed"] is False

        # Second task is "done"
        second = action_items_db.upsert_external_action_item.call_args_list[1]
        assert second.args[2]["completed"] is True

    def test_idempotent_second_run_calls_upsert_with_same_key(self):
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"

        # Re-run with fresh body each time — the sync helper intentionally
        # ``.clear()``s the tasks list after consumption (memory hygiene),
        # which would zap a shared body in subsequent iterations.
        for _ in range(2):
            body = {"data": {"tasks": [{"external_id": "PROJ-1", "title": "T1", "status_type": "todo"}]}}
            client = _FakeAsyncClient(_FakeResponse(200, body))
            _run(jira_sync.sync_user_jira_issues("uid-1", http_client=client))

        # Two upsert calls — both with the same external_source key. The
        # upsert layer dedupes by querying first; here we just assert the key
        # is identical so the dedupe contract holds.
        assert action_items_db.upsert_external_action_item.call_count == 2
        keys = [c.args[1]["external_id"] for c in action_items_db.upsert_external_action_item.call_args_list]
        assert keys == ["PROJ-1", "PROJ-1"]

    def test_skips_task_without_external_id(self):
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"
        body = {
            "data": {
                "tasks": [
                    {"external_id": "", "title": "no key"},
                    {"external_id": "PROJ-1", "title": "ok"},
                ]
            }
        }
        client = _FakeAsyncClient(_FakeResponse(200, body))
        result = _run(jira_sync.sync_user_jira_issues("uid-1", http_client=client))
        assert result["synced"] == 1
        assert result["skipped"] == 1
        assert action_items_db.upsert_external_action_item.call_count == 1

    def test_plugin_error_returns_errors(self):
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"
        client = _FakeAsyncClient(_FakeResponse(500, {"error": "boom"}))
        result = _run(jira_sync.sync_user_jira_issues("uid-1", http_client=client))
        assert result == {"synced": 0, "errors": 1, "skipped": 0}
        assert action_items_db.upsert_external_action_item.call_count == 0

    def test_no_plugin_url_returns_error(self):
        # No env var, no firestore doc
        apps_db.get_app_by_id_db.return_value = None
        client = _FakeAsyncClient(_FakeResponse(200, {"data": {"tasks": []}}))
        result = _run(jira_sync.sync_user_jira_issues("uid-1", http_client=client))
        assert result["errors"] == 1
        # We didn't even attempt the POST
        assert client.posts == []

    def test_sync_metadata_populated_on_create(self):
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"
        body = {
            "data": {
                "tasks": [
                    {
                        "external_id": "PROJ-1",
                        "title": "Ship",
                        "status_type": "in_progress",
                        "status": "In Review",
                        "priority": "High",
                        "project_key": "PROJ",
                        "status_changed_at": "2026-04-28T14:00:00Z",
                        "url": "https://x/PROJ-1",
                    }
                ]
            }
        }
        client = _FakeAsyncClient(_FakeResponse(200, body))
        _run(jira_sync.sync_user_jira_issues("uid-1", http_client=client))

        ext_arg = action_items_db.upsert_external_action_item.call_args.args[1]
        md = ext_arg["metadata"]
        assert md["status"] == "In Review"
        assert md["status_type"] == "indeterminate"  # translated
        assert md["priority"] == "High"
        assert md["project_key"] == "PROJ"
        assert md["status_changed_at"] == "2026-04-28T14:00:00Z"

    def test_sync_deep_merges_with_prior_external_source(self):
        os.environ["NOOTO_JIRA_PLUGIN_URL"] = "https://plugin.example.com"

        # Prior doc has a complete metadata block. Stub _find_by_external_source
        # to return a snapshot whose to_dict() exposes that prior state.
        class _Snap:
            def to_dict(self):
                return {
                    "external_source": {
                        "source": "jira",
                        "external_id": "PROJ-1",
                        "url": "https://x/PROJ-1",
                        "metadata": {
                            "status": "To Do",
                            "status_type": "todo",
                            "priority": "High",
                            "project_key": "PROJ",
                            "status_changed_at": "2026-04-01T00:00:00Z",
                        },
                    }
                }

        action_items_db._find_by_external_source.return_value = _Snap()

        # New sync returns only `status` + `status_type` (sparse).
        body = {
            "data": {
                "tasks": [
                    {
                        "external_id": "PROJ-1",
                        "title": "Ship",
                        "status_type": "in_progress",
                        "status": "In Review",
                        "url": "https://x/PROJ-1",
                    }
                ]
            }
        }
        client = _FakeAsyncClient(_FakeResponse(200, body))
        _run(jira_sync.sync_user_jira_issues("uid-1", http_client=client))

        ext_arg = action_items_db.upsert_external_action_item.call_args.args[1]
        md = ext_arg["metadata"]
        # Refreshed
        assert md["status"] == "In Review"
        assert md["status_type"] == "indeterminate"
        # Preserved from prior
        assert md["priority"] == "High"
        assert md["project_key"] == "PROJ"
        assert md["status_changed_at"] == "2026-04-01T00:00:00Z"


class TestIterUidsWithJiraEnabled:
    def test_yields_only_jira_enabled(self):
        fake_redis.keys = ["users:uid-1:enabled_plugins", "users:uid-2:enabled_plugins"]
        fake_redis.enabled = {
            "users:uid-1:enabled_plugins": {"nooto-jira", "other-app"},
            "users:uid-2:enabled_plugins": {"other-app"},
        }
        uids = list(jira_sync._iter_uids_with_jira_enabled())
        assert uids == ["uid-1"]

    def test_handles_malformed_keys(self):
        fake_redis.keys = ["bad-key", "users:uid-3:enabled_plugins"]
        fake_redis.enabled = {"users:uid-3:enabled_plugins": {"nooto-jira"}}
        uids = list(jira_sync._iter_uids_with_jira_enabled())
        assert uids == ["uid-3"]
