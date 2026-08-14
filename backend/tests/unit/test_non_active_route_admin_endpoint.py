import os
import sys
import types
from datetime import datetime, timezone

import pytest

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

_STUB_NAMES = ("fastapi", "database._client", "database.vector_db", "utils.other.endpoints", "routers.memory_admin")


@pytest.fixture(scope="module", autouse=True)
def _router_import_isolation():
    saved = snapshot_sys_modules(_STUB_NAMES)
    sys.modules.pop("routers.memory_admin", None)
    install_memory_product_router_stubs(fastapi_stub, types.ModuleType("utils.other.endpoints"))
    from database.memory_non_active_routes import NonActiveRoute
    from utils.memory.non_active_route_audit import NonActiveRouteAuditReport
    import routers.memory_admin as memory_admin

    globals().update(
        NonActiveRoute=NonActiveRoute,
        NonActiveRouteAuditReport=NonActiveRouteAuditReport,
        memory_admin=memory_admin,
    )
    yield
    restore_sys_modules(saved)


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


def test_admin_router_registers_only_live_memory_admin_routes():
    routes = {(method, path) for method, path, _kwargs, _func in memory_admin.router.routes}
    assert ("GET", "/memory/admin/users/{uid}/non-active-route-report") in routes
    assert ("POST", "/memory/admin/users/{uid}/short-term-lifecycle/run") in routes
    assert not any("rollout" in path or "cohort" in path for _method, path in routes)


def test_non_active_report_requires_admin_key(monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "secret")
    with pytest.raises(_HTTPException) as exc:
        memory_admin.get_non_active_route_report("u1", secret_key="wrong")
    assert exc.value.status_code == 403


def test_non_active_report_delegates_without_memory_item_reads(monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "secret")
    monkeypatch.setattr(memory_admin, "fetch_non_active_route_audit_report", lambda *_a, **_k: _report())
    response = memory_admin.get_non_active_route_report("u1", secret_key="secret")
    assert response["uid"] == "u1"
    assert response["status"] == "green"
    assert response["total_accounted_outcomes"] == 6


def test_short_term_lifecycle_run_is_bounded(monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "secret")
    evaluated_at = datetime(2026, 8, 11, tzinfo=timezone.utc)
    report = types.SimpleNamespace(created_count=1, existing_count=2, skipped_count=3, skipped_memory_ids=("m4",))
    calls = []

    def _run(**kwargs):
        calls.append(kwargs)
        return report

    monkeypatch.setattr(memory_admin, "run_short_term_lifecycle_firestore", _run)
    response = memory_admin.post_short_term_lifecycle_run(
        "u1", run_id="run-1", evaluated_at=evaluated_at.isoformat(), limit=10, secret_key="secret"
    )
    assert response["transition_count"] == 3
    assert response["evaluated_count"] == 6
    assert calls[0]["uid"] == "u1"
    assert calls[0]["limit"] == 10


@pytest.mark.parametrize("run_id,limit", [("", 10), ("run", 0), ("run", 1001)])
def test_short_term_lifecycle_rejects_invalid_bounds(monkeypatch, run_id, limit):
    monkeypatch.setenv("ADMIN_KEY", "secret")
    with pytest.raises(_HTTPException) as exc:
        memory_admin.post_short_term_lifecycle_run("u1", run_id=run_id, limit=limit, secret_key="secret")
    assert exc.value.status_code == 400
