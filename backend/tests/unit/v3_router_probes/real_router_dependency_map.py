#!/usr/bin/env python3
"""Controlled Oracle P1-3 `/v3` real-router import/dependency-map proof.

This runner does not import `backend/main.py`, start the production app, call
Firestore/Pinecone/cloud/provider clients, or execute route handlers. In execute
mode it launches the repo-managed venv Python and imports `routers.memories`
only after installing explicit in-process stubs for import-time unsafe modules.
The result is a dependency map and BLOCKED handoff, not runtime cutover evidence.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from tests.unit.v3_router_probes.stubs import legacy_pin_stub_source

TARGET_ROUTES = {
    ('GET', '/v3/memories'),
    ('POST', '/v3/memories'),
    ('DELETE', '/v3/memories/{memory_id}'),
}

UNSAFE_IMPORT_DEPENDENCIES = [
    {
        "module": "database.memories",
        "reason": "Legacy Firestore memory CRUD module; route handlers call reads/writes/deletes.",
        "stub_required_before_import": True,
        "external_or_mutation_risk": True,
    },
    {
        "module": "database.review_queue",
        "reason": "Review queue persistence module imported by router and unsafe to execute in route proof.",
        "stub_required_before_import": True,
        "external_or_mutation_risk": True,
    },
    {
        "module": "database.vector_db",
        "reason": "Pinecone/vector provider mutation functions are imported at module top level.",
        "stub_required_before_import": True,
        "external_or_mutation_risk": True,
    },
    {
        "module": "database._client",
        "reason": "Firestore client module is reached by models.memories for document_id_from_seed.",
        "stub_required_before_import": True,
        "external_or_mutation_risk": True,
    },
    {
        "module": "utils.executors",
        "reason": "Executor globals/submission helpers can create runtime pools or schedule side effects.",
        "stub_required_before_import": True,
        "external_or_mutation_risk": True,
    },
    {
        "module": "utils.apps",
        "reason": "Persona/app post-processing helper imported by public-memory write path.",
        "stub_required_before_import": True,
        "external_or_mutation_risk": True,
    },
    {
        "module": "utils.other.endpoints",
        "reason": "Authentication/rate-limit dependencies must be overridden before TestClient route execution.",
        "stub_required_before_import": True,
        "external_or_mutation_risk": True,
    },
]

REQUIRED_IMPORT_STUBS = [
    {
        "module": "database.memories",
        "stubbed_attributes": [
            "get_memory",
            "get_memories",
            "create_memory",
            "save_memories",
            "delete_memory",
            "delete_all_memories",
            "review_memory",
            "edit_memory",
            "change_memory_visibility",
        ],
    },
    {"module": "database.review_queue", "stubbed_attributes": ["list_review_conflicts", "resolve_review_conflict"]},
    {
        "module": "database.vector_db",
        "stubbed_attributes": [
            "delete_memory_vector",
            "delete_memory_vectors_batch",
            "upsert_memory_vector",
            "upsert_memory_vectors_batch",
        ],
    },
    {"module": "database._client", "stubbed_attributes": ["document_id_from_seed"]},
    {
        "module": "utils.executors",
        "stubbed_attributes": ["db_executor", "postprocess_executor", "run_blocking", "submit_with_context"],
    },
    {"module": "utils.apps", "stubbed_attributes": ["update_personas_async"]},
    {"module": "utils.other.endpoints", "stubbed_attributes": ["get_current_user_uid", "with_rate_limit"]},
]

IMPORT_SIDE_EFFECTS_BLOCKED = [
    "Firestore client/document-id helper construction blocked by database._client stub",
    "Legacy memory Firestore CRUD execution blocked by database.memories stub",
    "Pinecone/vector provider import and mutation functions blocked by database.vector_db stub",
    "Thread-pool/executor submission side effects blocked by utils.executors stub",
    "Authentication/rate-limit dependency execution blocked by utils.other.endpoints stub",
    "Persona post-processing side effects blocked by utils.apps stub",
]

FUTURE_GET_WIRING_SEAM = [
    "GET /v3/memories query params",
    "adapt_v3_request_parameters(...) request adapter",
    "plan_v3_memory_route(...) route planner",
    "adapt_v3_memory_response(...) response adapter",
]

BLOCKED_BEFORE_REAL_TESTCLIENT = [
    "Replace import stubs with explicit FastAPI dependency_overrides and route-local memory control/projection/write evidence seams.",
    "Prove GET does not call memories_db.get_memories for enrolled memory projection-ready accounts before including the real router in TestClient.",
    "Prove POST/DELETE write convergence or keep enrolled memory writes blocked before exercising mutating routes.",
]

REAL_ROUTER_DEPENDENCY_MAP_PROOF = {
    "service": "backend/scripts/p1_3_v3_real_router_dependency_map.py",
    "test": "backend/tests/unit/test_p1_3_v3_real_router_dependency_map.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "imports_real_router_under_stubs": True,
    "covered_defaults": [
        "real_memories_router_imported_only_after_explicit_unsafe_dependency_stubs",
        "pins_import_side_effects_and_required_testclient_overrides_before_route_execution",
        "pins_get_post_delete_v3_route_functions_and_decorators_from_real_router",
        "future_get_seam_remains_request_adapter_to_route_planner_to_response_adapter",
        "no_main_app_startup_no_external_calls_no_mutations_no_runtime_cutover",
    ],
}


def _repo_backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _decorated_route(decorator: ast.expr) -> tuple[str, str, str | None] | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = ast.unparse(decorator.func)
    if not func.startswith('router.') or not decorator.args:
        return None
    method = func.split('.', 1)[1].upper()
    path_node = decorator.args[0]
    if not isinstance(path_node, ast.Constant) or not isinstance(path_node.value, str):
        return None
    response_model = None
    for keyword in decorator.keywords:
        if keyword.arg == 'response_model':
            response_model = ast.unparse(keyword.value)
    return method, path_node.value, response_model


def _dependency_override(route: str) -> list[str]:
    if route == 'GET /v3/memories':
        return ["auth.get_current_user_uid"]
    if route == 'POST /v3/memories':
        return ["auth.with_rate_limit(auth.get_current_user_uid, 'memories:create')"]
    if route == 'DELETE /v3/memories/{memory_id}':
        return ["auth.with_rate_limit(auth.get_current_user_uid, 'memories:delete')"]
    return []


def _normalize_response_model(response_model: str | None) -> str | None:
    if response_model is None:
        return None
    normalized = response_model.replace('models.memories.', '').replace('typing.', '')
    if normalized.startswith("<class '") and normalized.endswith("'>"):
        return normalized.removeprefix("<class '").removesuffix("'>")
    return normalized


def inspect_static_routes(router_source_path: Path | None = None) -> list[dict[str, Any]]:
    source_path = router_source_path or (_repo_backend_root() / 'routers' / 'memories.py')
    source = source_path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    routes: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            decorated = _decorated_route(decorator)
            if decorated is None:
                continue
            method, route_path, response_model = decorated
            if (method, route_path) not in TARGET_ROUTES:
                continue
            route = f'{method} {route_path}'
            routes.append(
                {
                    "route": route,
                    "methods": [method],
                    "path": route_path,
                    "handler": node.name,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "response_model": response_model,
                    "decorator": ast.get_source_segment(source, decorator),
                    "dependency_overrides_required": _dependency_override(route),
                    "source_file": "backend/routers/memories.py",
                }
            )
    return sorted(routes, key=lambda item: (item['route']))


def _probe_code() -> str:
    pin_stub_block = legacy_pin_stub_source()
    template = textwrap.dedent(r'''
        import hashlib
        import importlib
        import json
        import sys
        import types

        def fail(name):
            def _inner(*args, **kwargs):
                raise AssertionError(f"stubbed unsafe dependency executed: {name}")
            return _inner

        class StubExecutor:
            def submit(self, *args, **kwargs):
                raise AssertionError("stubbed executor submit executed")

        database_pkg = types.ModuleType("database")
        database_pkg.__path__ = []
        sys.modules["database"] = database_pkg

        client = types.ModuleType("database._client")
        def document_id_from_seed(seed):
            return hashlib.sha1(str(seed).encode("utf-8")).hexdigest()[:20]
        client.document_id_from_seed = document_id_from_seed
        client.db = object()
        sys.modules["database._client"] = client
        setattr(database_pkg, "_client", client)

        memories = types.ModuleType("database.memories")
        for name in ["get_memory", "get_memories", "create_memory", "save_memories", "delete_memory", "delete_all_memories", "review_memory", "edit_memory", "change_memory_visibility"]:
            setattr(memories, name, fail(f"database.memories.{name}"))
        sys.modules["database.memories"] = memories
        setattr(database_pkg, "memories", memories)

        review_queue = types.ModuleType("database.review_queue")
        for name in ["list_review_conflicts", "resolve_review_conflict"]:
            setattr(review_queue, name, fail(f"database.review_queue.{name}"))
        sys.modules["database.review_queue"] = review_queue
        setattr(database_pkg, "review_queue", review_queue)

        vector_db = types.ModuleType("database.vector_db")
        for name in ["delete_memory_vector", "delete_memory_vectors_batch", "upsert_memory_vector", "upsert_memory_vectors_batch"]:
            setattr(vector_db, name, fail(f"database.vector_db.{name}"))
        sys.modules["database.vector_db"] = vector_db
        setattr(database_pkg, "vector_db", vector_db)

        utils_pkg = types.ModuleType("utils")
        utils_pkg.__path__ = ["utils"]
        sys.modules["utils"] = utils_pkg

        memory_pkg = types.ModuleType("utils.memory")
        memory_pkg.__path__ = ["utils/memory"]
        sys.modules["utils.memory"] = memory_pkg
        setattr(utils_pkg, "memory", memory_pkg)
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

        memory_system_mod = types.ModuleType("utils.memory.memory_system")
        class MemorySystem:
            LEGACY = "legacy"
            CANONICAL = "canonical"
        memory_system_mod.MemorySystem = MemorySystem
        sys.modules["utils.memory.memory_system"] = memory_system_mod
        setattr(memory_pkg, "memory_system", memory_system_mod)

        memory_service_mod = types.ModuleType("utils.memory.memory_service")
        class MemoryService:
            def __init__(self, *, db_client=None):
                self.db_client = db_client
        memory_service_mod.MemoryService = MemoryService
        sys.modules["utils.memory.memory_service"] = memory_service_mod
        setattr(memory_pkg, "memory_service", memory_service_mod)

        surface_routing = types.ModuleType("utils.memory.surface_routing")
__PIN_STUB_BLOCK__        surface_routing.pin_memory_system = pin_memory_system
        sys.modules["utils.memory.surface_routing"] = surface_routing
        setattr(memory_pkg, "surface_routing", surface_routing)

        executors = types.ModuleType("utils.executors")
        executors.db_executor = StubExecutor()
        executors.postprocess_executor = StubExecutor()
        async def run_blocking(*args, **kwargs):
            raise AssertionError("stubbed run_blocking executed")
        executors.run_blocking = run_blocking
        executors.submit_with_context = fail("utils.executors.submit_with_context")
        sys.modules["utils.executors"] = executors
        setattr(utils_pkg, "executors", executors)

        apps = types.ModuleType("utils.apps")
        apps.update_personas_async = fail("utils.apps.update_personas_async")
        sys.modules["utils.apps"] = apps
        setattr(utils_pkg, "apps", apps)

        other_pkg = types.ModuleType("utils.other")
        other_pkg.__path__ = []
        sys.modules["utils.other"] = other_pkg
        setattr(utils_pkg, "other", other_pkg)
        endpoints = types.ModuleType("utils.other.endpoints")
        def get_current_user_uid():
            raise AssertionError("stubbed auth dependency executed")
        def with_rate_limit(dependency, policy):
            def _dep():
                raise AssertionError(f"stubbed rate-limit dependency executed: {policy}")
            return _dep
        endpoints.get_current_user_uid = get_current_user_uid
        endpoints.with_rate_limit = with_rate_limit
        sys.modules["utils.other.endpoints"] = endpoints
        setattr(other_pkg, "endpoints", endpoints)

        module = importlib.import_module("routers.memories")
        pinned = []
        for route in module.router.routes:
            path = getattr(route, "path", None)
            methods = sorted(getattr(route, "methods", []) or [])
            endpoint = getattr(route, "endpoint", None)
            method = next((candidate for candidate in ["GET", "POST", "DELETE"] if candidate in methods), None)
            if method and path in {"/v3/memories", "/v3/memories/{memory_id}"}:
                route_ref = f"{method} {path}"
                if route_ref in {"GET /v3/memories", "POST /v3/memories", "DELETE /v3/memories/{memory_id}"}:
                    response_model = getattr(route, "response_model", None)
                    pinned.append({
                        "route": route_ref,
                        "path": path,
                        "methods": [method],
                        "handler": getattr(endpoint, "__name__", None),
                        "response_model": str(response_model).replace("typing.", "") if response_model is not None else None,
                    })
        print(json.dumps({"import_ok": True, "pinned_routes": sorted(pinned, key=lambda item: item["route"])}))
        ''')
    return template.replace("__PIN_STUB_BLOCK__", pin_stub_block)


def probe_real_router_import_under_stubs() -> dict[str, Any]:
    backend_root = _repo_backend_root()
    python = backend_root / 'venv' / 'bin' / 'python'
    if not python.exists():
        return {"import_ok": False, "blocked_reason": "repo-managed backend/venv/bin/python is unavailable"}
    result = subprocess.run(
        [str(python), '-c', _probe_code()],
        cwd=str(backend_root),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return {
            "import_ok": False,
            "blocked_reason": "stubbed real-router import probe failed",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr_tail": result.stderr[-2000:],
        }
    return json.loads(result.stdout)


def build_report(*, execute: bool = False) -> dict[str, Any]:
    static_routes = inspect_static_routes()
    probe = probe_real_router_import_under_stubs() if execute else {"import_ok": False, "pinned_routes": []}
    imported_under_stubs = bool(probe.get("import_ok"))
    probe_routes = {route["route"]: route for route in probe.get("pinned_routes", [])}
    pinned_routes = []
    for route in static_routes:
        merged = dict(route)
        if route["route"] in probe_routes:
            merged.update({key: probe_routes[route["route"]][key] for key in ["methods", "handler", "response_model"]})
            merged["response_model"] = _normalize_response_model(merged["response_model"])
        pinned_routes.append(merged)
    return {
        "artifact": "p1_3_v3_real_router_dependency_map",
        "status": "BLOCKED",
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "app_startup_executed": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "production_rollout_approved": False,
        "runtime_cutover_claimed": False,
        "real_router_target": "backend/routers/memories.py",
        "production_app_imported": False,
        "router_import_attempted_under_stubs": execute,
        "router_imported_under_stubs": imported_under_stubs,
        "route_inclusion_attempted": False,
        "unsafe_import_dependencies": UNSAFE_IMPORT_DEPENDENCIES,
        "required_import_stubs": REQUIRED_IMPORT_STUBS,
        "import_side_effects_blocked_by_stubs": IMPORT_SIDE_EFFECTS_BLOCKED,
        "probe": probe,
        "pinned_routes": pinned_routes,
        "future_get_wiring_seam": FUTURE_GET_WIRING_SEAM,
        "blocked_before_real_testclient": BLOCKED_BEFORE_REAL_TESTCLIENT,
        "non_claims": [
            "No backend/main.py import or production app startup executed.",
            "No real route handler executed and no TestClient route inclusion attempted in this slice.",
            "No Firestore, Pinecone, cloud, provider, or network calls executed.",
            "No runtime /v3 wiring or rollout approval claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "read_only": True,
            "unsafe_dependency_count": len(UNSAFE_IMPORT_DEPENDENCIES),
            "required_stub_count": len(REQUIRED_IMPORT_STUBS),
            "pinned_route_count": len(pinned_routes),
            "router_imported_under_stubs": imported_under_stubs,
            "runtime_cutover_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run the controlled venv real-router import probe")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
