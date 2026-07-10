import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from config.memory_rollout import PASSED, MemoryRolloutMode, MemoryRolloutStageGate
from tests.unit.memory_import_isolation import (
    install_memory_product_router_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


class _HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _APIRouter:
    def __init__(self):
        self.routes = []

    def get(self, path, **kwargs):
        def decorator(func):
            self.routes.append(("GET", path, kwargs, func))
            return func

        return decorator

    def post(self, path, **kwargs):
        def decorator(func):
            self.routes.append(("POST", path, kwargs, func))
            return func

        return decorator


def _identity(default=None, **_kwargs):
    return default


fastapi_stub = types.ModuleType("fastapi")
fastapi_stub.APIRouter = _APIRouter
fastapi_stub.Header = _identity
fastapi_stub.HTTPException = _HTTPException
fastapi_stub.Query = _identity
fastapi_stub.Request = type("Request", (), {})

_ADMIN_ROUTER_STUB_NAMES = (
    "fastapi",
    "database._client",
    "database.vector_db",
    "utils.other.endpoints",
    "routers.memory_admin",
)


@pytest.fixture(scope="module", autouse=True)
def _memory_admin_router_import_isolation():
    saved = snapshot_sys_modules(_ADMIN_ROUTER_STUB_NAMES)
    sys.modules.pop("routers.memory_admin", None)
    install_memory_product_router_stubs(fastapi_stub, types.ModuleType("utils.other.endpoints"))
    from database.memory_non_active_routes import NonActiveRoute
    from utils.memory.non_active_route_audit import NonActiveRouteAuditReport

    import routers.memory_admin as memory_admin

    globals()["NonActiveRoute"] = NonActiveRoute
    globals()["NonActiveRouteAuditReport"] = NonActiveRouteAuditReport
    globals()["memory_admin"] = memory_admin
    yield
    restore_sys_modules(saved)
    sys.modules.pop("routers.memory_admin", None)
    globals()["memory_admin"] = None


NonActiveRoute = None
NonActiveRouteAuditReport = None
memory_admin = None


def _report(uid="u1"):
    return NonActiveRouteAuditReport(
        uid=uid,
        status="green",
        total_accounted_outcomes=6,
        counts_by_route={route.value: 1 for route in NonActiveRoute},
        evidence=[],
        missing_source_ids=[],
        red_reasons=[],
    )


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        if self._data is None:
            return None
        return dict(self._data)


class _DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def get(self):
        self._db_client.document_get_paths.append(self.path)
        if self.path not in self._db_client.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db_client.docs[self.path], exists=True)


class _FirestoreFake:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.document_get_paths = []
        self.collection_paths = []

    def document(self, path):
        return _DocumentRef(self, path)

    def collection(self, path):
        self.collection_paths.append(path)
        raise AssertionError(f"admin rollout inspection must not read collections: {path}")


def _enabled_rollout_doc(uid="u1"):
    return {
        "schema_version": 1,
        "uid": uid,
        "mode": MemoryRolloutMode.read.value,
        "mode_epoch": 7,
        "cutover_epoch": 7,
        "account_generation": 3,
        "fallback_projection_ready": True,
        "persistent_memory_writes_started": True,
        "writes_blocked": False,
        "stage_gates": {
            MemoryRolloutStageGate.shadow.value: PASSED,
            MemoryRolloutStageGate.write.value: PASSED,
            MemoryRolloutStageGate.read.value: PASSED,
        },
        "grants": {
            "mcp": {"default_memory": True, "archive": True},
            "developer_api": {"default_memory": True, "archive": True},
            "omi_chat": {"default_memory": True, "archive": True},
        },
    }


def test_admin_router_registers_memory_admin_routes():
    routes = {(method, path) for method, path, _kwargs, _func in memory_admin.router.routes}
    assert ("GET", "/memory/admin/users/{uid}/non-active-route-report") in routes
    assert ("GET", "/memory/admin/users/{uid}/read-rollout-decision") in routes
    assert ("POST", "/memory/admin/users/{uid}/short-term-lifecycle/run") in routes
    legacy_prefix = "/" + "v" + "17/"
    assert not any(isinstance(path, str) and path.startswith(legacy_prefix) for _method, path in routes)


def test_admin_read_rollout_decision_endpoint_reports_all_enabled_consumers_without_memory_item_reads(monkeypatch):
    os.environ["ADMIN_KEY"] = "secret"
    db_client = _FirestoreFake({"users/u1/memory_control/state": _enabled_rollout_doc()})
    monkeypatch.setattr(memory_admin, "db", db_client)

    response = memory_admin.get_memory_read_rollout_decision("u1", secret_key="secret")

    assert db_client.document_get_paths == ["users/u1/memory_control/state"]
    assert db_client.collection_paths == []
    assert response["uid"] == "u1"
    assert response["source_path"] == "users/u1/memory_control/state"
    assert response["archive_default_visible"] is False
    assert response["archive_capability"] is False
    assert response["decision_counters"] == {
        "total": {"enabled": 3, "fallback": 0},
        "by_consumer": {
            "mcp": {"enabled": 1, "fallback": 0, "fallback_reasons": {}},
            "developer_api": {"enabled": 1, "fallback": 0, "fallback_reasons": {}},
            "omi_chat": {"enabled": 1, "fallback": 0, "fallback_reasons": {}},
        },
    }
    assert response["decision_audit_events"] == [
        {
            "uid": "u1",
            "source_path": "users/u1/memory_control/state",
            "consumer": "mcp",
            "enabled": True,
            "outcome": "enabled",
            "read_decision": "USE_MEMORY",
            "fallback_reason": None,
            "default_memory_grant": True,
            "memory_reads_enabled": True,
            "archive_default_visible": False,
            "archive_capability": False,
        },
        {
            "uid": "u1",
            "source_path": "users/u1/memory_control/state",
            "consumer": "developer_api",
            "enabled": True,
            "outcome": "enabled",
            "read_decision": "USE_MEMORY",
            "fallback_reason": None,
            "default_memory_grant": True,
            "memory_reads_enabled": True,
            "archive_default_visible": False,
            "archive_capability": False,
        },
        {
            "uid": "u1",
            "source_path": "users/u1/memory_control/state",
            "consumer": "omi_chat",
            "enabled": True,
            "outcome": "enabled",
            "read_decision": "USE_MEMORY",
            "fallback_reason": None,
            "default_memory_grant": True,
            "memory_reads_enabled": True,
            "archive_default_visible": False,
            "archive_capability": False,
        },
    ]
    assert sorted(response["consumers"]) == ["developer_api", "mcp", "omi_chat"]
    for consumer in ("mcp", "developer_api", "omi_chat"):
        decision = response["consumers"][consumer]
        assert decision == {
            "consumer": consumer,
            "enabled": True,
            "reason": "ok",
            "read_decision": "USE_MEMORY",
            "mode": "read",
            "memory_reads_enabled": True,
            "legacy_reads_authoritative": False,
            "default_memory_grant": True,
            "archive_default_visible": False,
            "archive_capability": False,
            "fallback_reason": None,
            "capabilities": {
                "legacy_only": False,
                "shadow_artifacts_enabled": True,
                "memory_writes_enabled": True,
                "memory_reads_enabled": True,
                "legacy_reads_authoritative": False,
            },
        }


def test_admin_read_rollout_decision_endpoint_reports_disabled_consumers_for_missing_malformed_uid_mismatch_and_no_grants(
    monkeypatch,
):
    os.environ["ADMIN_KEY"] = "secret"
    cases = [
        (
            {},
            {
                "mcp": "missing_rollout_state",
                "developer_api": "missing_rollout_state",
                "omi_chat": "missing_rollout_state",
            },
        ),
        (
            {"users/u1/memory_control/state": {"schema_version": 1, "uid": "u1", "mode": "read", "stage_gates": "bad"}},
            {
                "mcp": "malformed_rollout_state",
                "developer_api": "malformed_rollout_state",
                "omi_chat": "malformed_rollout_state",
            },
        ),
        (
            {"users/u1/memory_control/state": _enabled_rollout_doc(uid="other")},
            {"mcp": "uid_mismatch", "developer_api": "uid_mismatch", "omi_chat": "uid_mismatch"},
        ),
        (
            {
                "users/u1/memory_control/state": _enabled_rollout_doc()
                | {"grants": {"mcp": {}, "developer_api": {}, "omi_chat": {}}}
            },
            {
                "mcp": "missing_mcp_default_memory_grant",
                "developer_api": "missing_developer_default_memory_grant",
                "omi_chat": "missing_chat_default_memory_grant",
            },
        ),
    ]

    for docs, expected_reasons in cases:
        db_client = _FirestoreFake(docs)
        monkeypatch.setattr(memory_admin, "db", db_client)

        response = memory_admin.get_memory_read_rollout_decision("u1", secret_key="secret")

        for consumer, reason in expected_reasons.items():
            decision = response["consumers"][consumer]
            assert decision["enabled"] is False
            assert decision["reason"] == reason
            assert decision["fallback_reason"] == reason
            assert decision["default_memory_grant"] is False
            assert decision["archive_default_visible"] is False
            assert decision["archive_capability"] is False
        assert response["archive_default_visible"] is False
        assert response["archive_capability"] is False
        assert db_client.document_get_paths == ["users/u1/memory_control/state"]
        assert db_client.collection_paths == []


def test_admin_read_rollout_decision_endpoint_rejects_invalid_admin_key(monkeypatch):
    os.environ["ADMIN_KEY"] = "secret"
    db_client = _FirestoreFake({"users/u1/memory_control/state": _enabled_rollout_doc()})
    monkeypatch.setattr(memory_admin, "db", db_client)

    try:
        memory_admin.get_memory_read_rollout_decision("u1", secret_key="wrong")
    except _HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("expected admin auth failure")

    assert db_client.document_get_paths == []
    assert db_client.collection_paths == []


def test_admin_endpoint_surfaces_non_active_route_report_counts_without_memory_items(monkeypatch):
    os.environ["ADMIN_KEY"] = "secret"
    calls = []

    def fake_fetch(uid, *, run_id=None, expected_source_ids=None):
        calls.append((uid, run_id, expected_source_ids))
        return _report(uid)

    monkeypatch.setattr(memory_admin, "fetch_non_active_route_audit_report", fake_fetch)

    response = memory_admin.get_non_active_route_report(
        "u1",
        run_id="run-1",
        expected_source_ids=" src-review,src-archive ,, src-hidden ",
        secret_key="secret",
    )

    assert calls == [("u1", "run-1", ["src-review", "src-archive", "src-hidden"])]
    assert response["status"] == "green"
    assert response["total_accounted_outcomes"] == 6
    assert response["counts_by_route"] == {
        "review": 1,
        "archive": 1,
        "context_only": 1,
        "reject": 1,
        "hidden": 1,
        "skip": 1,
    }


def test_admin_endpoint_rejects_missing_or_invalid_admin_key(monkeypatch):
    os.environ["ADMIN_KEY"] = "secret"
    monkeypatch.setattr(memory_admin, "fetch_non_active_route_audit_report", MagicMock(return_value=_report()))

    try:
        memory_admin.get_non_active_route_report("u1", secret_key="wrong")
    except _HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "You are not authorized to perform this action"
    else:
        raise AssertionError("expected admin auth failure")

    memory_admin.fetch_non_active_route_audit_report.assert_not_called()


def test_admin_endpoint_runs_short_term_lifecycle_with_bounded_inputs(monkeypatch):
    os.environ["ADMIN_KEY"] = "secret"
    calls = []

    class _Report:
        created_records = [MagicMock(), MagicMock()]
        existing_records = [MagicMock()]
        skipped_memory_ids = ["fresh-short-term"]
        created_count = 2
        existing_count = 1
        skipped_count = 1

    def fake_run(*, uid, db_client, run_id, now=None, limit=None, dispositions=None):
        calls.append((uid, db_client, run_id, now, limit, dispositions))
        return _Report()

    monkeypatch.setattr(memory_admin, "run_short_term_lifecycle_firestore", fake_run)

    response = memory_admin.post_short_term_lifecycle_run(
        "u1",
        run_id="manual-run-1",
        evaluated_at="2026-06-19T12:00:00+00:00",
        limit=25,
        secret_key="secret",
    )

    assert calls == [
        (
            "u1",
            memory_admin.db,
            "manual-run-1",
            datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
            25,
            None,
        )
    ]
    assert response == {
        "uid": "u1",
        "run_id": "manual-run-1",
        "evaluated_at": "2026-06-19T12:00:00+00:00",
        "evaluated_count": 4,
        "created_count": 2,
        "existing_count": 1,
        "skipped_count": 1,
        "transition_count": 3,
        "skipped_memory_ids": ["fresh-short-term"],
        "default_access_allowed": False,
        "archive_default_visible": False,
    }


def test_admin_endpoint_rejects_invalid_short_term_lifecycle_inputs(monkeypatch):
    os.environ["ADMIN_KEY"] = "secret"
    fake_run = MagicMock()
    monkeypatch.setattr(memory_admin, "run_short_term_lifecycle_firestore", fake_run)

    for kwargs in (
        {"run_id": "", "limit": 25, "evaluated_at": None},
        {"run_id": "run-1", "limit": 0, "evaluated_at": None},
        {"run_id": "run-1", "limit": 1001, "evaluated_at": None},
        {"run_id": "run-1", "limit": 25, "evaluated_at": "not-a-date"},
    ):
        try:
            memory_admin.post_short_term_lifecycle_run("u1", secret_key="secret", **kwargs)
        except _HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f"expected invalid input failure for {kwargs}")

    fake_run.assert_not_called()
