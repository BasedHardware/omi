"""Hermetic regression tests for constant-time, byte-encoded admin/metrics secret checks.

Covers:
1. `routers.apps._require_admin_key` and all 12 admin routes in `routers.apps`:
   - Constant-time comparison via `hmac.compare_digest` over UTF-8 bytes
   - Fails closed when `ADMIN_KEY` is unset, empty, or whitespace-only
   - Non-ASCII `secret-key` header returns HTTP 403 instead of raising `TypeError` (HTTP 500)
   - Preserves the route-specific 403 detail ('You are not authorized to perform this action' vs 'Forbidden')
2. `routers.memory_admin._require_admin_key`:
   - Constant-time bytewise comparison via `hmac.compare_digest`
   - Rejects whitespace-only `ADMIN_KEY` and non-ASCII headers with HTTP 403 instead of HTTP 500
3. `routers.client_telemetry._verify_admin`, `routers.device_diagnostics._admin_key`,
   `routers.fair_use_admin._verify_admin_key`, `routers.feedback_admin._verify_admin_key`,
   and `routers.metrics.metrics`:
   - Encode both operands to bytes before `hmac.compare_digest` so non-ASCII headers
     (e.g. Latin-1 `'wrong-\xe9'` or UTF-8 `'sécret'`) cleanly return 403/401 instead of
     raising `TypeError: comparing strings with non-ASCII characters is not supported`.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from unittest import mock

import pytest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from tests.unit.memory_import_isolation import (  # noqa: E402
    AutoMockModule,
    restore_sys_modules,
    snapshot_sys_modules,
)


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail=None, headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


class _APIRouter:
    def __init__(self, *args, **kwargs):
        self.routes = []

    def _decorator(self, method: str):
        def register(path: str, **kwargs):
            def wrap(func):
                self.routes.append((method, path, kwargs, func))
                return func

            return wrap

        return register

    def get(self, path: str, **kwargs):
        return self._decorator("GET")(path, **kwargs)

    def post(self, path: str, **kwargs):
        return self._decorator("POST")(path, **kwargs)

    def put(self, path: str, **kwargs):
        return self._decorator("PUT")(path, **kwargs)

    def patch(self, path: str, **kwargs):
        return self._decorator("PATCH")(path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self._decorator("DELETE")(path, **kwargs)


def _identity(default=None, **_kwargs):
    return default


def _load_router_isolated(module_name: str, rel_path: str, extra_stubs: dict[str, types.ModuleType] | None = None):
    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.APIRouter = _APIRouter
    fastapi_stub.Body = _identity
    fastapi_stub.Depends = _identity
    fastapi_stub.File = _identity
    fastapi_stub.Form = _identity
    fastapi_stub.Header = _identity
    fastapi_stub.HTTPException = _HTTPException
    fastapi_stub.Query = _identity
    fastapi_stub.Request = type("Request", (), {})
    fastapi_stub.Security = _identity
    fastapi_stub.UploadFile = type("UploadFile", (), {})

    responses_stub = types.ModuleType("fastapi.responses")
    responses_stub.HTMLResponse = type("HTMLResponse", (), {})
    responses_stub.JSONResponse = type("JSONResponse", (), {})

    routing_stub = types.ModuleType("fastapi.routing")
    routing_stub.APIRoute = type("APIRoute", (), {"get_route_handler": lambda self: lambda req: None})

    security_stub = types.ModuleType("fastapi.security")
    security_stub.HTTPAuthorizationCredentials = type("HTTPAuthorizationCredentials", (), {})
    security_stub.HTTPBearer = lambda **_kw: object()

    pydantic_stub = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self):
            return dict(self.__dict__)

    pydantic_stub.BaseModel = _BaseModel
    pydantic_stub.ConfigDict = lambda **kwargs: kwargs
    pydantic_stub.Field = lambda default=None, **_kwargs: default
    pydantic_stub.ValidationError = ValueError

    stubs: dict[str, types.ModuleType] = {
        "fastapi": fastapi_stub,
        "fastapi.responses": responses_stub,
        "fastapi.routing": routing_stub,
        "fastapi.security": security_stub,
        "pydantic": pydantic_stub,
    }
    if extra_stubs:
        stubs.update(extra_stubs)

    saved = snapshot_sys_modules([*stubs.keys(), module_name])
    try:
        for name, mod in stubs.items():
            sys.modules[name] = mod
        spec = importlib.util.spec_from_file_location(module_name, os.path.join(_BACKEND_DIR, rel_path))
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        restore_sys_modules(saved)


@pytest.fixture(scope="module")
def routers_bundle():
    common_AutoMocks = {
        name: AutoMockModule(name)
        for name in (
            "httpx",
            "ulid",
            "langchain_core",
            "langchain_core.messages",
            "utils.generated_compute",
            "utils.apps",
            "utils.executors",
            "utils.http_client",
            "utils.multipart",
            "utils.mcp_client",
            "utils.other",
            "utils.other.endpoints",
            "utils.other.storage",
            "utils.other.device_diagnostics_storage",
            "utils.llm",
            "utils.llm.persona",
            "utils.llm.app_generator",
            "utils.llm.app_generation_prompts",
            "utils.llm.usage_tracker",
            "utils.subscription",
            "utils.product_metrics",
            "utils.social",
            "utils.notifications",
            "utils.log_sanitizer",
            "utils.request_validation",
            "utils.client_telemetry_metrics",
            "utils.fair_use",
            "utils.feedback_context",
            "utils.metrics",
            "utils.memory",
            "utils.memory.non_active_route_audit",
            "database._client",
            "database.apps",
            "database.webhook_health",
            "database.memories",
            "database.auth",
            "database.redis_db",
            "database.chat",
            "database.fair_use",
            "database.feedback",
            "database.client_telemetry",
            "database.client_telemetry_ops",
            "database.serving_query_reads",
            "database.firestore_read_origin",
            "models.app",
            "models.other",
            "models.shared",
            "models.feedback",
            "models.memory_admin",
            "config.client_telemetry",
            "jobs.short_term_lifecycle_worker",
            "jobs.feedback_daily_report",
        )
    }
    common_AutoMocks["utils.multipart"].max_part_size = lambda _limit: (lambda fn: fn)
    common_AutoMocks["utils.other.endpoints"].with_rate_limit = lambda fn, *_a, **_k: fn
    common_AutoMocks["utils.other.endpoints"].rate_limit_dependency = lambda *_a, **_k: (lambda: None)
    common_AutoMocks["database.firestore_read_origin"].read_origin = lambda *_a, **_k: (lambda fn: fn)
    for _cls_name in ("App", "ActionType", "AppCreate", "AppUpdate", "AppBaseModel", "AppReview", "AppCatalogItem"):
        setattr(common_AutoMocks["models.app"], _cls_name, type(_cls_name, (), {}))
    for _cls_name in ("FeedbackContextHydrated", "FeedbackReport"):
        setattr(common_AutoMocks["models.feedback"], _cls_name, type(_cls_name, (), {}))
    setattr(common_AutoMocks["models.shared"], "StatusResponse", type("StatusResponse", (), {}))
    setattr(
        common_AutoMocks["models.memory_admin"],
        "ShortTermLifecycleRunResponse",
        type("ShortTermLifecycleRunResponse", (), {}),
    )
    setattr(
        common_AutoMocks["utils.memory.non_active_route_audit"],
        "NonActiveRouteAuditReport",
        type("NonActiveRouteAuditReport", (), {}),
    )

    return {
        "apps": _load_router_isolated("routers._test_apps", "routers/apps.py", common_AutoMocks),
        "memory_admin": _load_router_isolated(
            "routers._test_memory_admin", "routers/memory_admin.py", common_AutoMocks
        ),
        "client_telemetry": _load_router_isolated(
            "routers._test_client_telemetry", "routers/client_telemetry.py", common_AutoMocks
        ),
        "device_diagnostics": _load_router_isolated(
            "routers._test_device_diagnostics", "routers/device_diagnostics.py", common_AutoMocks
        ),
        "fair_use_admin": _load_router_isolated(
            "routers._test_fair_use_admin", "routers/fair_use_admin.py", common_AutoMocks
        ),
        "feedback_admin": _load_router_isolated(
            "routers._test_feedback_admin", "routers/feedback_admin.py", common_AutoMocks
        ),
        "metrics": _load_router_isolated("routers._test_metrics", "routers/metrics.py", common_AutoMocks),
    }


def test_apps_require_admin_key_constant_time_and_fail_closed(routers_bundle, monkeypatch):
    apps = routers_bundle["apps"]

    # Unset, empty, or whitespace-only ADMIN_KEY must never authenticate
    for configured in (None, "", "   "):
        if configured is None:
            monkeypatch.delenv("ADMIN_KEY", raising=False)
        else:
            monkeypatch.setenv("ADMIN_KEY", configured)
        for candidate in ("", "   ", "real-key"):
            with pytest.raises(_HTTPException) as exc:
                apps._require_admin_key(candidate)
            assert exc.value.status_code == 403
            assert exc.value.detail == "You are not authorized to perform this action"

    monkeypatch.setenv("ADMIN_KEY", "s3cr3t-admin-key")
    # Non-ASCII header (e.g. Latin-1 / UTF-8) must return 403, not raise TypeError (500)
    for bad in ("", "wrong", "wrong-\xe9", "sécret-ключ"):
        with pytest.raises(_HTTPException) as exc:
            apps._require_admin_key(bad)
        assert exc.value.status_code == 403

    # Summary-app-ids routes preserve their 'Forbidden' detail contract
    with pytest.raises(_HTTPException) as exc:
        apps.get_summary_app_ids(secret_key="wrong-\xe9")
    assert exc.value.status_code == 403
    assert exc.value.detail == "Forbidden"

    # Team/persona routes preserve 'You are not authorized to perform this action'
    with pytest.raises(_HTTPException) as exc:
        apps.get_unapproved_public_apps(secret_key="wrong-\xe9")
    assert exc.value.status_code == 403
    assert exc.value.detail == "You are not authorized to perform this action"

    # Behavioral seam: hmac.compare_digest is called with encoded bytes
    with mock.patch.object(apps.hmac, "compare_digest", wraps=apps.hmac.compare_digest) as spy:
        apps._require_admin_key("s3cr3t-admin-key")
        spy.assert_called_once_with(b"s3cr3t-admin-key", b"s3cr3t-admin-key")


def test_memory_admin_require_admin_key_constant_time_and_non_ascii(routers_bundle, monkeypatch):
    memory_admin = routers_bundle["memory_admin"]

    monkeypatch.setenv("ADMIN_KEY", "   ")
    with pytest.raises(_HTTPException) as exc:
        memory_admin._require_admin_key("   ")
    assert exc.value.status_code == 403

    monkeypatch.setenv("ADMIN_KEY", "mem-admin-secret")
    with pytest.raises(_HTTPException) as exc:
        memory_admin._require_admin_key("non-ascii-\xe9-ключ")
    assert exc.value.status_code == 403

    with mock.patch.object(memory_admin.hmac, "compare_digest", wraps=memory_admin.hmac.compare_digest) as spy:
        memory_admin._require_admin_key("mem-admin-secret")
        spy.assert_called_once_with(b"mem-admin-secret", b"mem-admin-secret")


def test_sibling_admin_and_metrics_verifiers_reject_non_ascii_without_type_error(routers_bundle, monkeypatch):
    client_telemetry = routers_bundle["client_telemetry"]
    device_diagnostics = routers_bundle["device_diagnostics"]
    fair_use_admin = routers_bundle["fair_use_admin"]
    feedback_admin = routers_bundle["feedback_admin"]
    metrics_router = routers_bundle["metrics"]

    monkeypatch.setenv("ADMIN_KEY", "expected-admin-key")
    monkeypatch.setenv("METRICS_SECRET", "expected-metrics-secret")
    monkeypatch.setattr(fair_use_admin, "ADMIN_KEY", "expected-admin-key")
    monkeypatch.setattr(feedback_admin, "ADMIN_KEY", "expected-admin-key")

    for non_ascii in ("wrong-\xe9", "sécret-ключ"):
        with pytest.raises(_HTTPException) as exc:
            client_telemetry._verify_admin(non_ascii)
        assert exc.value.status_code == 403

        with pytest.raises(_HTTPException) as exc:
            device_diagnostics._admin_key(x_admin_key=non_ascii, x_admin_user=None)
        assert exc.value.status_code == 403

        with pytest.raises(_HTTPException) as exc:
            fair_use_admin._verify_admin_key(x_admin_key=non_ascii)
        assert exc.value.status_code == 403

        with pytest.raises(_HTTPException) as exc:
            feedback_admin._verify_admin_key(x_admin_key=non_ascii, x_admin_user=None)
        assert exc.value.status_code == 403

        creds = types.SimpleNamespace(credentials=non_ascii)
        with pytest.raises(_HTTPException) as exc:
            metrics_router.metrics(credentials=creds)
        assert exc.value.status_code == 401

    # Valid keys still succeed
    client_telemetry._verify_admin("expected-admin-key")
    assert device_diagnostics._admin_key(x_admin_key="expected-admin-key", x_admin_user="alice").startswith("admin:")
    assert fair_use_admin._verify_admin_key(x_admin_key="expected-admin-key").startswith("admin:")
    assert feedback_admin._verify_admin_key(x_admin_key="expected-admin-key", x_admin_user="alice").startswith("admin:")
    metrics_router.metrics(credentials=types.SimpleNamespace(credentials="expected-metrics-secret"))
