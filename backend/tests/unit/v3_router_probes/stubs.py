"""Minimal in-process stubs for importing ``routers.memories`` in unit probes."""

from __future__ import annotations

import hashlib
import importlib
import sys
import textwrap
import types
from typing import Any, Callable

LEGACY_MEMORY_DOC_FIELDS = (
    "id",
    "uid",
    "content",
    "category",
    "visibility",
    "tags",
    "created_at",
    "updated_at",
    "reviewed",
    "manually_added",
    "edited",
    "is_locked",
    "kg_extracted",
    "evidence",
    "arguments",
    "subject_attribution",
    "object_entity_ids",
    "qualifiers",
    "uncertainty_reasons",
)


def legacy_memory_doc(
    memory_id: str,
    content: str,
    *,
    uid: str = "stubbed-test-uid",
    category: str = "system",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Factory for legacy memory documents used by v3 router probe stubs."""
    return {
        "id": memory_id,
        "uid": uid,
        "content": content,
        "category": category,
        "visibility": "private",
        "tags": tags or ["legacy"],
        "created_at": "2026-06-19T12:00:00Z",
        "updated_at": "2026-06-19T12:00:00Z",
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


def legacy_pin_stub_source() -> str:
    """Return subprocess-safe source for pin_memory_system → LEGACY stub."""
    return "        def pin_memory_system(uid, *, db_client=None):\n" "            return MemorySystem.LEGACY\n"


def legacy_memory_doc_factory_source(*, stubbed_uid: str = "stubbed-test-uid") -> str:
    """Return subprocess-safe legacy_item factory used by router probe scripts."""
    return textwrap.dedent(f'''
        def legacy_item(memory_id, content, *, category="system", tags=None, uid=None):
            return {{
                "id": memory_id,
                "uid": uid or "{stubbed_uid}",
                "content": content,
                "category": category,
                "visibility": "private",
                "tags": tags or ["legacy"],
                "created_at": "2026-06-19T12:00:00Z",
                "updated_at": "2026-06-19T12:00:00Z",
                "reviewed": True,
                "manually_added": False,
                "edited": False,
                "is_locked": False,
                "kg_extracted": False,
                "evidence": [],
                "arguments": {{}},
                "subject_attribution": "legacy_assumed",
                "object_entity_ids": [],
                "qualifiers": {{}},
                "uncertainty_reasons": [],
            }}
        ''').strip()


def _fail(name: str) -> Callable[..., Any]:
    def _inner(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"stubbed unsafe dependency executed: {name}")

    return _inner


def _mark_mutation(flags: dict[str, bool], name: str) -> Callable[..., Any]:
    def _inner(*args: Any, **kwargs: Any) -> Any:
        flags[name] = True
        raise AssertionError(f"mutating stub unexpectedly executed: {name}")

    return _inner


def install_router_import_stubs(
    *,
    observed_get_calls: list[dict[str, Any]] | None = None,
    mutation_flags: dict[str, bool] | None = None,
    stubbed_uid: str = "stubbed-test-uid",
    auth_raises: bool = True,
) -> None:
    """Install stubs required before ``import routers.memories`` in probe tests."""
    for name in list(sys.modules):
        if name == "routers.memories":
            del sys.modules[name]

    flags = mutation_flags if mutation_flags is not None else {}
    get_calls = observed_get_calls if observed_get_calls is not None else []

    database_pkg = types.ModuleType("database")
    database_pkg.__path__ = []
    sys.modules["database"] = database_pkg

    client_module = types.ModuleType("database._client")

    def document_id_from_seed(seed: Any) -> str:
        return hashlib.sha1(str(seed).encode("utf-8")).hexdigest()[:20]

    client_module.document_id_from_seed = document_id_from_seed
    client_module.db = object()
    sys.modules["database._client"] = client_module
    setattr(database_pkg, "_client", client_module)

    memories = types.ModuleType("database.memories")

    def legacy_item(memory_id: str, content: str, *, uid: str | None = None) -> dict[str, Any]:
        return legacy_memory_doc(memory_id, content, uid=uid or stubbed_uid)

    def get_memories(uid: str, limit: int, offset: int, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        get_calls.append({"uid": uid, "limit": limit, "offset": offset})
        if offset == 0:
            return [legacy_item("legacy-default", "legacy default page memory")]
        return [legacy_item("legacy-explicit", f"legacy explicit page limit={limit} offset={offset}", uid=uid)]

    memories.get_memories = get_memories
    memories.get_memory = _fail("database.memories.get_memory")
    memories.create_memory = _mark_mutation(flags, "create_memory")
    memories.save_memories = _mark_mutation(flags, "save_memories")
    memories.delete_memory = _mark_mutation(flags, "delete_memory")
    memories.delete_all_memories = _mark_mutation(flags, "delete_all_memories")
    memories.review_memory = _fail("database.memories.review_memory")
    memories.edit_memory = _fail("database.memories.edit_memory")
    memories.change_memory_visibility = _fail("database.memories.change_memory_visibility")
    sys.modules["database.memories"] = memories
    setattr(database_pkg, "memories", memories)

    review_queue = types.ModuleType("database.review_queue")
    review_queue.list_review_conflicts = _fail("database.review_queue.list_review_conflicts")
    review_queue.resolve_review_conflict = _fail("database.review_queue.resolve_review_conflict")
    sys.modules["database.review_queue"] = review_queue
    setattr(database_pkg, "review_queue", review_queue)

    vector_db = types.ModuleType("database.vector_db")
    vector_db.delete_memory_vector = _mark_mutation(flags, "delete_memory_vector")
    vector_db.delete_memory_vectors_batch = _mark_mutation(flags, "delete_memory_vectors_batch")
    vector_db.upsert_memory_vector = _mark_mutation(flags, "upsert_memory_vector")
    vector_db.upsert_memory_vectors_batch = _mark_mutation(flags, "upsert_memory_vectors_batch")
    sys.modules["database.vector_db"] = vector_db
    setattr(database_pkg, "vector_db", vector_db)

    executors = types.ModuleType("utils.executors")

    class StubExecutor:
        def submit(self, *args: Any, **kwargs: Any) -> Any:
            flags["executor_submit"] = True
            raise AssertionError("stubbed executor submit executed")

    executors.db_executor = StubExecutor()
    executors.postprocess_executor = StubExecutor()

    async def run_blocking(*args: Any, **kwargs: Any) -> Any:
        flags["run_blocking"] = True
        raise AssertionError("stubbed run_blocking executed")

    executors.run_blocking = run_blocking
    executors.submit_with_context = _fail("utils.executors.submit_with_context")
    sys.modules["utils.executors"] = executors

    apps = types.ModuleType("utils.apps")
    apps.update_personas_async = _mark_mutation(flags, "update_personas_async")
    sys.modules["utils.apps"] = apps

    other_pkg = types.ModuleType("utils.other")
    other_pkg.__path__ = []
    sys.modules["utils.other"] = other_pkg
    endpoints = types.ModuleType("utils.other.endpoints")

    def get_current_user_uid() -> str:
        if auth_raises:
            raise AssertionError("auth dependency must be overridden")
        return stubbed_uid

    def with_rate_limit(dependency: Any, policy: str) -> Any:
        def _dep() -> Any:
            raise AssertionError(f"rate-limit dependency executed: {policy}")

        return _dep

    endpoints.get_current_user_uid = get_current_user_uid
    endpoints.with_rate_limit = with_rate_limit
    sys.modules["utils.other.endpoints"] = endpoints
    setattr(other_pkg, "endpoints", endpoints)

    utils_pkg = sys.modules.get("utils")
    if utils_pkg is None:
        utils_pkg = types.ModuleType("utils")
        utils_pkg.__path__ = []
        sys.modules["utils"] = utils_pkg

    memory_pkg = sys.modules.get("utils.memory")
    if memory_pkg is None:
        memory_pkg = types.ModuleType("utils.memory")
        memory_pkg.__path__ = []
        sys.modules["utils.memory"] = memory_pkg
        setattr(utils_pkg, "memory", memory_pkg)

    projection_db = types.ModuleType("database.memory_compatibility_projection")
    projection_db.read_v3_compatibility_projection_page = _fail(
        "database.memory_compatibility_projection.read_v3_compatibility_projection_page"
    )
    sys.modules["database.memory_compatibility_projection"] = projection_db
    setattr(database_pkg, "memory_compatibility_projection", projection_db)

    composed = types.ModuleType("utils.memory.v3.composed_get_service")

    class V3ComposedRequestParams:
        def __init__(self, limit=None, offset=None, cursor=None, include_archive=False, include_historical=False):
            self.limit = limit
            self.offset = offset
            self.cursor = cursor
            self.include_archive = include_archive
            self.include_historical = include_historical

    class V3ComposedResponse:
        def __init__(self, http_status=200, body=None, public_error=None, headers=None, source="none", decision="ok"):
            self.http_status = http_status
            self.body = body
            self.public_error = public_error
            self.headers = headers or {}
            self.source = source
            self.decision = decision

    composed.V3ComposedRequestParams = V3ComposedRequestParams
    composed.V3ComposedResponse = V3ComposedResponse
    sys.modules["utils.memory.v3.composed_get_service"] = composed
    setattr(memory_pkg, "v3_composed_get_service", composed)

    production_runtime = types.ModuleType("utils.memory.v3.production_runtime")

    class ProductionV3GetRuntime:
        def __init__(self, enabled=False, source_decision="disabled", service=None, adapters=None, **kwargs):
            self.enabled = enabled
            self.source_decision = source_decision
            self.service = service
            self.adapters = adapters
            for key, value in kwargs.items():
                setattr(self, key, value)

    def build_v3_production_runtime(*, uid, db_client, env=None):
        return ProductionV3GetRuntime(enabled=False, source_decision="disabled")

    production_runtime.V3GetRuntime = ProductionV3GetRuntime
    production_runtime.build_v3_production_runtime = build_v3_production_runtime
    sys.modules["utils.memory.v3.production_runtime"] = production_runtime
    setattr(memory_pkg, "v3_production_runtime", production_runtime)

    canonical_adapter = types.ModuleType("utils.memory.canonical_memory_adapter")
    canonical_adapter._read_canonical_memory_item = _fail(
        "utils.memory.canonical_memory_adapter._read_canonical_memory_item"
    )
    canonical_adapter.memory_item_to_memorydb = _fail("utils.memory.canonical_memory_adapter.memory_item_to_memorydb")
    sys.modules["utils.memory.canonical_memory_adapter"] = canonical_adapter
    setattr(memory_pkg, "canonical_memory_adapter", canonical_adapter)

    client_device = types.ModuleType("utils.client_device")
    client_device.resolve_client_device = lambda *args, **kwargs: (None, None)
    sys.modules["utils.client_device"] = client_device
    setattr(utils_pkg, "client_device", client_device)

    device_scope = types.ModuleType("utils.memory.device_scope_filter")
    device_scope.device_scope_validation_error = lambda *args, **kwargs: None
    device_scope.filter_items_by_device_scope = lambda items, **kwargs: items
    sys.modules["utils.memory.device_scope_filter"] = device_scope
    setattr(memory_pkg, "device_scope_filter", device_scope)

    memory_service_mod = types.ModuleType("utils.memory.memory_service")

    def fetch_memory_dict(uid, memory_id, *, db_client=None):
        raise AssertionError("stubbed fetch_memory_dict executed")

    class MemoryService:
        def __init__(self, *, db_client=None):
            self.db_client = db_client

    memory_service_mod.fetch_memory_dict = fetch_memory_dict
    memory_service_mod.MemoryService = MemoryService
    sys.modules["utils.memory.memory_service"] = memory_service_mod
    setattr(memory_pkg, "memory_service", memory_service_mod)

    surface_routing = types.ModuleType("utils.memory.surface_routing")

    class _MemorySystem:
        LEGACY = "legacy"
        CANONICAL = "canonical"

    def resolve_memory_system(uid, *, db_client=None):
        return _MemorySystem.LEGACY

    def pin_memory_system(uid, *, db_client=None):
        return _MemorySystem.LEGACY

    surface_routing.pin_memory_system = pin_memory_system
    sys.modules["utils.memory.surface_routing"] = surface_routing
    setattr(memory_pkg, "surface_routing", surface_routing)

    memory_system_mod = types.ModuleType("utils.memory.memory_system")
    memory_system_mod.MemorySystem = _MemorySystem
    memory_system_mod.resolve_memory_system = resolve_memory_system
    sys.modules["utils.memory.memory_system"] = memory_system_mod
    setattr(memory_pkg, "memory_system", memory_system_mod)

    canonical_activation = types.ModuleType("utils.memory.canonical_activation")
    canonical_activation.canonical_read_enabled = lambda *args, **kwargs: False
    canonical_activation.canonical_write_enabled = lambda *args, **kwargs: False
    sys.modules["utils.memory.canonical_activation"] = canonical_activation
    setattr(memory_pkg, "canonical_activation", canonical_activation)


def import_memories_router():
    return importlib.import_module("routers.memories")
