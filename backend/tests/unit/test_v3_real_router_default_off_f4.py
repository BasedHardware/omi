import importlib
import logging
import sys
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except Exception as exc:  # pragma: no cover - exercised by minimal system pytest env
    pytest.skip(f'real FastAPI/TestClient proof requires backend venv dependencies: {exc}', allow_module_level=True)

from utils.memory.v3.composed_get_service import V3ComposedResponse

SENSITIVE_SENTINELS = [
    "secret-uid-123",
    "Bearer secret-auth-token",
    "memory-secret-id",
    "sensitive memory content",
    "raw-filter-value",
    "cursor-token-signature",
    "cursor-secret-material",
    "grant-epoch-secret",
    "config-epoch-secret",
    "raw adapter exploded with sensitive details",
]


def _memory_item(memory_id="legacy-id", content="legacy content", uid="secret-uid-123", **extra):
    item = {
        "id": memory_id,
        "uid": uid,
        "content": content,
        "category": "system",
        "visibility": "private",
        "tags": ["compat"],
        "created_at": datetime(2026, 6, 20, tzinfo=timezone.utc).isoformat(),
        "updated_at": datetime(2026, 6, 20, tzinfo=timezone.utc).isoformat(),
        "reviewed": True,
        "manually_added": False,
        "edited": False,
        "is_locked": False,
        "kg_extracted": False,
        "evidence": [],
        "arguments": {},
        "subject_attribution": "legacy_assumed",
        "object_entity_ids": [],
        "qualifiers": {},
        "uncertainty_reasons": [],
    }
    item.update(extra)
    return item


@dataclass
class Counters:
    legacy_calls: list
    projection_calls: int = 0
    service_calls: int = 0
    mutation_calls: list = None

    def __post_init__(self):
        if self.mutation_calls is None:
            self.mutation_calls = []


def _install_router_stubs(monkeypatch, counters):
    for name in list(sys.modules):
        if name == "routers.memories":
            monkeypatch.delitem(sys.modules, name, raising=False)

    database_pkg = types.ModuleType("database")
    database_pkg.__path__ = [str(BACKEND_DIR / "database")]
    monkeypatch.setitem(sys.modules, "database", database_pkg)

    client_module = types.ModuleType("database._client")
    client_module.document_id_from_seed = lambda seed: "stubbed-document-id"
    client_module.db = object()
    monkeypatch.setitem(sys.modules, "database._client", client_module)
    setattr(database_pkg, "_client", client_module)

    memories = types.ModuleType("database.memories")

    def get_memories(uid, limit, offset):
        counters.legacy_calls.append({"uid": uid, "limit": limit, "offset": offset})
        return [_memory_item("legacy-id", f"legacy limit={limit} offset={offset}", uid=uid)]

    def mark_mutation(name):
        def _inner(*args, **kwargs):
            counters.mutation_calls.append(name)
            raise AssertionError(f"mutation executed: {name}")

        return _inner

    memories.get_memories = get_memories
    memories.get_memory = lambda *a, **k: None
    memories.create_memory = mark_mutation("create_memory")
    memories.save_memories = mark_mutation("save_memories")
    memories.delete_memory = mark_mutation("delete_memory")
    memories.delete_all_memories = mark_mutation("delete_all_memories")
    memories.review_memory = mark_mutation("review_memory")
    memories.edit_memory = mark_mutation("edit_memory")
    memories.change_memory_visibility = mark_mutation("change_memory_visibility")
    monkeypatch.setitem(sys.modules, "database.memories", memories)
    setattr(database_pkg, "memories", memories)

    review_queue = types.ModuleType("database.review_queue")
    review_queue.list_review_conflicts = mark_mutation("list_review_conflicts")
    review_queue.resolve_review_conflict = mark_mutation("resolve_review_conflict")
    setattr(
        review_queue,
        "purge_stale_review_conflicts_for_memories",
        mark_mutation("purge_stale_review_conflicts_for_memories"),
    )
    monkeypatch.setitem(sys.modules, "database.review_queue", review_queue)
    setattr(database_pkg, "review_queue", review_queue)

    vector_db = types.ModuleType("database.vector_db")
    vector_db.delete_memory_vector = mark_mutation("delete_memory_vector")
    vector_db.delete_memory_vectors_batch = mark_mutation("delete_memory_vectors_batch")
    vector_db.upsert_memory_vector = mark_mutation("upsert_memory_vector")
    vector_db.upsert_memory_vectors_batch = mark_mutation("upsert_memory_vectors_batch")
    monkeypatch.setitem(sys.modules, "database.vector_db", vector_db)
    setattr(database_pkg, "vector_db", vector_db)

    projection = types.ModuleType("database.memory_compatibility_projection")

    def read_v3_compatibility_projection_page(request):
        counters.projection_calls += 1
        raise AssertionError("projection reader should not run in this test path")

    projection.read_v3_compatibility_projection_page = read_v3_compatibility_projection_page
    monkeypatch.setitem(sys.modules, "database.memory_compatibility_projection", projection)
    setattr(database_pkg, "memory_compatibility_projection", projection)

    apps = types.ModuleType("utils.apps")
    apps.update_personas_async = mark_mutation("update_personas_async")
    monkeypatch.setitem(sys.modules, "utils.apps", apps)

    executors = types.ModuleType("utils.executors")
    executors.db_executor = object()
    executors.postprocess_executor = object()
    executors.run_blocking = mark_mutation("run_blocking")
    executors.submit_with_context = mark_mutation("submit_with_context")
    monkeypatch.setitem(sys.modules, "utils.executors", executors)

    endpoints = types.ModuleType("utils.other.endpoints")

    def get_current_user_uid():
        raise AssertionError("auth dependency should be overridden")

    def with_rate_limit(dependency, policy):
        return dependency

    endpoints.get_current_user_uid = get_current_user_uid
    endpoints.with_rate_limit = with_rate_limit
    monkeypatch.setitem(sys.modules, "utils.other.endpoints", endpoints)

    from utils.memory.memory_system import MemorySystem

    surface_routing = types.ModuleType("utils.memory.surface_routing")
    surface_routing.pin_memory_system = lambda uid, db_client=None: MemorySystem.LEGACY
    surface_routing.MemorySystem = MemorySystem
    monkeypatch.setitem(sys.modules, "utils.memory.surface_routing", surface_routing)


def _client(monkeypatch, runtime=None):
    counters = Counters(legacy_calls=[])
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    clear_canonical_cohort(monkeypatch)
    _install_router_stubs(monkeypatch, counters)
    module = importlib.import_module("routers.memories")

    app = FastAPI()
    app.dependency_overrides[module.auth.get_current_user_uid] = lambda: "secret-uid-123"
    if runtime is not None:
        app.dependency_overrides[module.get_v3_get_runtime] = lambda: runtime
    app.include_router(module.router)
    return TestClient(app), counters, module


class RecordingService:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, params, adapters):
        self.calls.append(params)
        return self.response


def _runtime(module, *, enabled=True, response=None):
    service = RecordingService(
        response or V3ComposedResponse.success(body=[], next_cursor=None, source="memory_compatibility_projection")
    )
    return module.V3GetRuntime(enabled=enabled, source_decision="memory_read", service=service)


def test_production_default_dependency_is_disabled_and_preserves_legacy_get_behavior(monkeypatch):
    client, counters, module = _client(monkeypatch)

    assert client.get("/v3/memories").status_code == 200
    assert client.get("/v3/memories?limit=17").status_code == 200
    assert client.get("/v3/memories?limit=17&offset=0").status_code == 200
    assert client.get("/v3/memories?limit=17&offset=3").status_code == 200

    assert counters.legacy_calls == [
        {"uid": "secret-uid-123", "limit": 5000, "offset": 0},
        {"uid": "secret-uid-123", "limit": 5000, "offset": 0},
        {"uid": "secret-uid-123", "limit": 5000, "offset": 0},
        {"uid": "secret-uid-123", "limit": 17, "offset": 3},
    ]
    assert module.get_v3_get_runtime(uid="secret-uid-123").enabled is False
    assert counters.mutation_calls == []


def test_test_enabled_non_enrolled_legacy_primary_calls_legacy_once_and_projection_zero(monkeypatch):
    client, counters, module = _client(monkeypatch)
    runtime = module.V3GetRuntime(
        enabled=True,
        source_decision="legacy_primary",
        service=RecordingService(V3ComposedResponse.error(503, "adapter_exception")),
    )
    client.app.dependency_overrides[module.get_v3_get_runtime] = lambda: runtime

    response = client.get("/v3/memories?limit=22&offset=0")

    assert response.status_code == 200
    assert counters.legacy_calls == [{"uid": "secret-uid-123", "limit": 5000, "offset": 0}]
    assert runtime.service.calls == []
    assert counters.projection_calls == 0


@pytest.mark.parametrize(
    "response,status",
    [
        (
            V3ComposedResponse.success(
                body=[_memory_item("memory-id", "memory body", memory_only="strip-me")],
                next_cursor="cursor-token-signature",
                source="memory_compatibility_projection",
            ),
            200,
        ),
        (V3ComposedResponse.error(403, "grant_denied"), 403),
        (V3ComposedResponse.error(400, "offset_invalid"), 400),
        (V3ComposedResponse.error(400, "cursor_invalid"), 400),
        (V3ComposedResponse.error(503, "adapter_contract"), 503),
        (V3ComposedResponse.error(503, "partial_projection"), 503),
        (V3ComposedResponse.error(504, "deadline_exhausted"), 504),
        (V3ComposedResponse.success(body=[], next_cursor=None, source="memory_compatibility_projection"), 200),
    ],
)
def test_enrolled_memory_never_calls_legacy_for_success_or_fail_closed_cases(monkeypatch, response, status):
    client, counters, module = _client(monkeypatch)
    runtime = _runtime(module, response=response)
    client.app.dependency_overrides[module.get_v3_get_runtime] = lambda: runtime

    result = client.get("/v3/memories?limit=100&offset=0&cursor=cursor-token-signature")

    assert result.status_code == status
    assert counters.legacy_calls == []
    assert len(runtime.service.calls) == 1
    if status == 200:
        for item in result.json():
            assert "memory_only" not in item
        assert "X-Omi-Memory-Read-Source" in result.headers
        assert "X-Omi-Memory-Read-Decision" in result.headers
        assert result.headers["Cache-Control"] == "no-store"
        assert "cursor-token-signature" not in result.text


@pytest.mark.parametrize("query", ["limit=0", "limit=-1", "limit=501", "limit=5000", "offset=1"])
def test_memory_pagination_rejections_happen_without_legacy_reads(monkeypatch, query):
    client, counters, module = _client(monkeypatch)
    runtime = _runtime(module, response=V3ComposedResponse.error(400, "bad_request"))
    client.app.dependency_overrides[module.get_v3_get_runtime] = lambda: runtime

    result = client.get(f"/v3/memories?{query}")

    assert result.status_code == 400
    assert counters.legacy_calls == []
    assert len(runtime.service.calls) == 1


def test_router_logs_are_sanitized_and_mutating_route_dependencies_unchanged(monkeypatch, caplog):
    client, counters, module = _client(monkeypatch)
    runtime = _runtime(module, response=V3ComposedResponse.error(503, "adapter_exception"))
    client.app.dependency_overrides[module.get_v3_get_runtime] = lambda: runtime

    with caplog.at_level(logging.INFO):
        response = client.get("/v3/memories?cursor=cursor-token-signature")

    assert response.status_code == 503
    assert counters.legacy_calls == []
    assert counters.mutation_calls == []
    logs = "\n".join(record.getMessage() for record in caplog.records if record.name.startswith("routers.memories"))
    for sentinel in SENSITIVE_SENTINELS:
        assert sentinel not in logs

    route_by_name = {route.name: route for route in module.router.routes if hasattr(route, "name")}
    assert "get_v3_get_runtime" not in repr(route_by_name["create_memory"].dependant.dependencies)
    assert "get_v3_get_runtime" not in repr(route_by_name["delete_memory"].dependant.dependencies)
