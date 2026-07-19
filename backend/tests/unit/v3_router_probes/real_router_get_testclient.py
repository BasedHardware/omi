#!/usr/bin/env python3
"""Controlled Oracle P1-3 real-router TestClient GET-only proof for `/v3/memories`.

This proof creates a minimal FastAPI app, includes the real `routers.memories`
router only after explicit import stubs are installed, overrides auth, and
executes only GET `/v3/memories` through TestClient. It does not import
`backend/main.py`, start the production app, execute POST/DELETE, call real
Firestore/Pinecone/cloud/provider/network dependencies, mutate state, or claim
runtime cutover.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any


from tests.unit.v3_router_probes.real_router_dependency_map import (
    FUTURE_GET_WIRING_SEAM,
    REQUIRED_IMPORT_STUBS,
)
from tests.unit.v3_router_probes.stubs import legacy_memory_doc_factory_source, legacy_pin_stub_source

MEMORY_ADAPTER_MODULES = [
    "utils.memory.v3.request_adapter",
    "testing.memory.v3_route_planner",
    "utils.memory.v3.response_adapter",
]


REAL_ROUTER_GET_TESTCLIENT_PROOF = {
    "service": "backend/scripts/p1_3_v3_real_router_get_testclient.py",
    "test": "backend/tests/unit/test_p1_3_v3_real_router_get_testclient.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "get_only_testclient_under_stubs": True,
    "post_delete_unexecuted": True,
    "covered_defaults": [
        "minimal_fastapi_app_includes_real_memories_router_under_explicit_stubs",
        "get_v3_memories_calls_stubbed_legacy_memories_db_get_memories",
        "default_first_page_observes_current_offset_zero_limit_5000_override",
        "explicit_limit_offset_reach_stubbed_legacy_get_memories_when_offset_nonzero",
        "list_memorydb_response_model_serializes_legacy_compatible_items",
        "post_delete_unexecuted_and_mutation_flags_remain_false",
        "memory_request_adapter_route_planner_response_adapter_not_invoked_yet",
        "no_main_app_startup_no_external_calls_no_mutations_no_runtime_cutover",
    ],
}


def _repo_backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _probe_code() -> str:
    legacy_item_block = legacy_memory_doc_factory_source(stubbed_uid="stubbed-test-uid")
    pin_stub_block = legacy_pin_stub_source()
    template = textwrap.dedent(r'''
        import hashlib
        import importlib
        import json
        import sys
        import types

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        mutation_flags = {
            "create_memory": False,
            "save_memories": False,
            "delete_memory": False,
            "delete_all_memories": False,
            "upsert_memory_vector": False,
            "upsert_memory_vectors_batch": False,
            "delete_memory_vector": False,
            "delete_memory_vectors_batch": False,
            "update_personas_async": False,
            "executor_submit": False,
            "run_blocking": False,
        }
        observed_get_calls = []
        stubbed_uid = "stubbed-test-uid"

        def fail(name):
            def _inner(*args, **kwargs):
                raise AssertionError(f"stubbed unsafe dependency executed: {name}")
            return _inner

        def mark_mutation(name):
            def _inner(*args, **kwargs):
                mutation_flags[name] = True
                raise AssertionError(f"mutating stub unexpectedly executed: {name}")
            return _inner

        class StubExecutor:
            def submit(self, *args, **kwargs):
                mutation_flags["executor_submit"] = True
                raise AssertionError("stubbed executor submit executed")

__LEGACY_ITEM_BLOCK__

        database_pkg = types.ModuleType("database")
        database_pkg.__path__ = []
        sys.modules["database"] = database_pkg

        client_module = types.ModuleType("database._client")
        def document_id_from_seed(seed):
            return hashlib.sha1(str(seed).encode("utf-8")).hexdigest()[:20]
        client_module.document_id_from_seed = document_id_from_seed
        client_module.db = object()
        sys.modules["database._client"] = client_module
        setattr(database_pkg, "_client", client_module)

        memories = types.ModuleType("database.memories")
        def get_memories(uid, limit, offset, *args, **kwargs):
            observed = {"uid": uid, "limit": limit, "offset": offset}
            observed_get_calls.append(observed)
            if offset == 0:
                return [legacy_item("legacy-default", "legacy default page memory")]
            return [legacy_item("legacy-explicit", f"legacy explicit page limit={limit} offset={offset}", tags=["legacy", "explicit"])]
        memories.get_memories = get_memories
        memories.get_memory = fail("database.memories.get_memory")
        memories.create_memory = mark_mutation("create_memory")
        memories.save_memories = mark_mutation("save_memories")
        memories.delete_memory = mark_mutation("delete_memory")
        memories.delete_all_memories = mark_mutation("delete_all_memories")
        memories.review_memory = fail("database.memories.review_memory")
        memories.edit_memory = fail("database.memories.edit_memory")
        memories.change_memory_visibility = fail("database.memories.change_memory_visibility")
        sys.modules["database.memories"] = memories
        setattr(database_pkg, "memories", memories)

        review_queue = types.ModuleType("database.review_queue")
        review_queue.list_review_conflicts = fail("database.review_queue.list_review_conflicts")
        review_queue.resolve_review_conflict = fail("database.review_queue.resolve_review_conflict")
        sys.modules["database.review_queue"] = review_queue
        setattr(database_pkg, "review_queue", review_queue)

        vector_db = types.ModuleType("database.vector_db")
        vector_db.delete_memory_vector = mark_mutation("delete_memory_vector")
        vector_db.delete_memory_vectors_batch = mark_mutation("delete_memory_vectors_batch")
        vector_db.upsert_memory_vector = mark_mutation("upsert_memory_vector")
        vector_db.upsert_memory_vectors_batch = mark_mutation("upsert_memory_vectors_batch")
        sys.modules["database.vector_db"] = vector_db
        setattr(database_pkg, "vector_db", vector_db)

        utils_pkg = types.ModuleType("utils")
        utils_pkg.__path__ = []
        sys.modules["utils"] = utils_pkg

        memory_pkg = types.ModuleType("utils.memory")
        memory_pkg.__path__ = []
        sys.modules["utils.memory"] = memory_pkg
        setattr(utils_pkg, "memory", memory_pkg)

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

        memory_system_mod = types.ModuleType("utils.memory.memory_system")
        class MemorySystem:
            LEGACY = "legacy"
            CANONICAL = "canonical"
        def resolve_memory_system(uid, *, db_client=None):
            return MemorySystem.LEGACY
        memory_system_mod.MemorySystem = MemorySystem
        memory_system_mod.resolve_memory_system = resolve_memory_system
        sys.modules["utils.memory.memory_system"] = memory_system_mod
        setattr(memory_pkg, "memory_system", memory_system_mod)

        canonical_activation = types.ModuleType("utils.memory.canonical_activation")
        canonical_activation.canonical_read_enabled = lambda *args, **kwargs: False
        canonical_activation.canonical_write_enabled = lambda *args, **kwargs: False
        sys.modules["utils.memory.canonical_activation"] = canonical_activation
        setattr(memory_pkg, "canonical_activation", canonical_activation)

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
__PIN_STUB_BLOCK__        surface_routing.pin_memory_system = pin_memory_system
        sys.modules["utils.memory.surface_routing"] = surface_routing
        setattr(memory_pkg, "surface_routing", surface_routing)

        executors = types.ModuleType("utils.executors")
        executors.db_executor = StubExecutor()
        executors.postprocess_executor = StubExecutor()
        async def run_blocking(*args, **kwargs):
            mutation_flags["run_blocking"] = True
            raise AssertionError("stubbed run_blocking executed")
        executors.run_blocking = run_blocking
        executors.submit_with_context = fail("utils.executors.submit_with_context")
        sys.modules["utils.executors"] = executors
        setattr(utils_pkg, "executors", executors)

        apps = types.ModuleType("utils.apps")
        apps.update_personas_async = mark_mutation("update_personas_async")
        sys.modules["utils.apps"] = apps
        setattr(utils_pkg, "apps", apps)

        other_pkg = types.ModuleType("utils.other")
        other_pkg.__path__ = []
        sys.modules["utils.other"] = other_pkg
        setattr(utils_pkg, "other", other_pkg)
        endpoints = types.ModuleType("utils.other.endpoints")
        def get_current_user_uid():
            raise AssertionError("auth dependency must be overridden")
        def with_rate_limit(dependency, policy):
            def _dep():
                raise AssertionError(f"rate-limit dependency must not execute in GET-only proof: {policy}")
            return _dep
        endpoints.get_current_user_uid = get_current_user_uid
        endpoints.with_rate_limit = with_rate_limit
        sys.modules["utils.other.endpoints"] = endpoints
        setattr(other_pkg, "endpoints", endpoints)

        module = importlib.import_module("routers.memories")

        app = FastAPI()
        app.dependency_overrides[module.auth.get_current_user_uid] = lambda: stubbed_uid
        app.include_router(module.router)
        client = TestClient(app)

        default_response = client.get("/v3/memories")
        explicit_response = client.get("/v3/memories?limit=17&offset=3")

        route_refs = []
        for route in module.router.routes:
            path = getattr(route, "path", None)
            methods = sorted(getattr(route, "methods", []) or [])
            method = next((candidate for candidate in ["GET", "POST", "DELETE"] if candidate in methods), None)
            if method and path in {"/v3/memories", "/v3/memories/{memory_id}"}:
                route_refs.append(f"{method} {path}")

        memory_adapter_modules = [
            "utils.memory.v3.request_adapter",
            "testing.memory.v3_route_planner",
            "utils.memory.v3.response_adapter",
        ]
        loaded_adapters = [name for name in memory_adapter_modules if name in sys.modules]

        print(json.dumps({
            "testclient_ok": default_response.status_code == 200 and explicit_response.status_code == 200,
            "router_imported_under_stubs": True,
            "minimal_fastapi_app_created": True,
            "real_router_included_under_stubs": True,
            "auth_dependency_overridden": True,
            "available_pinned_routes": sorted(route_refs),
            "executed_routes": ["GET /v3/memories", "GET /v3/memories?limit=17&offset=3"],
            "unexecuted_mutating_routes": ["POST /v3/memories", "DELETE /v3/memories/{memory_id}"],
            "default_get": {
                "status_code": default_response.status_code,
                "body": default_response.json(),
                "observed_legacy_call": observed_get_calls[0],
            },
            "explicit_get": {
                "status_code": explicit_response.status_code,
                "body": explicit_response.json(),
                "observed_legacy_call": observed_get_calls[1],
            },
            "observed_get_memories_calls": observed_get_calls,
            "stubbed_legacy_get_memories_call_count": len(observed_get_calls),
            "current_first_page_limit_override": "offset=0 coerces limit to 5000 before legacy get_memories",
            "explicit_limit_offset_preserved_when_offset_nonzero": observed_get_calls[1] == {"uid": stubbed_uid, "limit": 17, "offset": 3},
            "mutation_flags": mutation_flags,
            "memory_adapter_modules_loaded": loaded_adapters,
            "runtime_cutover_claimed": False,
        }, sort_keys=True))
        ''')
    return template.replace("__LEGACY_ITEM_BLOCK__", legacy_item_block).replace("__PIN_STUB_BLOCK__", pin_stub_block)


def probe_real_router_get_testclient_under_stubs() -> dict[str, Any]:
    backend_root = _repo_backend_root()
    python = backend_root / 'venv' / 'bin' / 'python'
    if not python.exists():
        return {"testclient_ok": False, "blocked_reason": "repo-managed backend/venv/bin/python is unavailable"}
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
            "testclient_ok": False,
            "blocked_reason": "stubbed real-router GET TestClient probe failed",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr_tail": result.stderr[-2000:],
        }
    return json.loads(result.stdout)


def build_report(*, execute: bool = False) -> dict[str, Any]:
    probe = probe_real_router_get_testclient_under_stubs() if execute else {"testclient_ok": False}
    mutation_flags_raw = probe.get("mutation_flags", {})
    mutation_flags = mutation_flags_raw if isinstance(mutation_flags_raw, dict) else {}
    mutation_flags_clear = bool(mutation_flags) and not any(mutation_flags.values())
    post_delete_unexecuted = probe.get("unexecuted_mutating_routes") == [
        "POST /v3/memories",
        "DELETE /v3/memories/{memory_id}",
    ]
    testclient_ok = bool(probe.get("testclient_ok"))
    return {
        "artifact": "p1_3_v3_real_router_get_testclient",
        "status": "BLOCKED",
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "app_startup_executed": False,
        "production_app_imported": False,
        "minimal_fastapi_app_created": bool(probe.get("minimal_fastapi_app_created")) if execute else False,
        "real_router_target": "backend/routers/memories.py",
        "real_router_included_under_stubs": bool(probe.get("real_router_included_under_stubs")) if execute else False,
        "route_handlers_executed": ["GET /v3/memories"] if testclient_ok else [],
        "post_delete_executed": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "real_firestore_reads_executed": False,
        "stubbed_legacy_get_memories_executed": bool(probe.get("stubbed_legacy_get_memories_call_count")),
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "production_rollout_approved": False,
        "runtime_cutover_claimed": False,
        "memory_adapters_invoked": bool(probe.get("memory_adapter_modules_loaded")),
        "required_import_stubs": REQUIRED_IMPORT_STUBS,
        "dependency_overrides": ["routers.memories.auth.get_current_user_uid -> stubbed-test-uid"],
        "future_get_wiring_seam": FUTURE_GET_WIRING_SEAM,
        "probe": probe,
        "non_claims": [
            "No backend/main.py import or production app startup executed.",
            "Only GET /v3/memories was executed through TestClient; POST/DELETE remain unexecuted.",
            "No real Firestore, Pinecone, cloud, provider, or network calls executed.",
            "Current runtime still calls stubbed legacy memories_db.get_memories; no memory adapter/planner/response cutover is claimed.",
            "No runtime /v3 wiring, benchmark, telemetry sink integration, or rollout approval claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "testclient_ok": testclient_ok,
            "get_only": probe.get("executed_routes")
            == [
                "GET /v3/memories",
                "GET /v3/memories?limit=17&offset=3",
            ],
            "stubbed_legacy_get_memories_call_count": probe.get("stubbed_legacy_get_memories_call_count", 0),
            "post_delete_unexecuted": post_delete_unexecuted,
            "mutation_flags_clear": mutation_flags_clear,
            "memory_adapters_invoked": bool(probe.get("memory_adapter_modules_loaded")),
            "runtime_cutover_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="Run the controlled venv real-router GET TestClient probe"
    )
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
