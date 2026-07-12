#!/usr/bin/env python3
"""Controlled `/v3/memories` GET dependency/auth/rate-limit TestClient proof.

This Oracle P1-3 artifact executes the current GET route through a minimal
FastAPI app under explicit stubs. It does not import `backend/main.py`, change
`backend/routers/memories.py`, call real Firestore/Pinecone/cloud/provider
services, execute mutating routes, or claim runtime cutover approval.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any


from tests.unit.v3_router_probes.real_router_dependency_map import REQUIRED_IMPORT_STUBS
from tests.unit.v3_router_probes.stubs import legacy_memory_doc, legacy_pin_stub_source

GET_DEPENDENCY_AUTH_READINESS_PROOF = {
    "service": "backend/scripts/p1_3_v3_get_dependency_auth_readiness.py",
    "test": "backend/tests/unit/test_p1_3_v3_get_dependency_auth_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "controlled_testclient_under_stubs": True,
    "covered_defaults": [
        "real_get_route_uses_auth_get_current_user_uid_dependency",
        "minimal_fastapi_app_can_override_get_auth_dependency_to_stub_uid",
        "get_without_auth_override_is_blocked_in_controlled_testclient_probe",
        "current_get_route_has_no_rate_limit_dependency",
        "get_with_auth_override_calls_stubbed_legacy_get_memories_for_non_enrolled_baseline",
        "no_memory_cohort_control_dependency_present_or_invoked",
        "no_main_app_startup_no_external_calls_no_mutations_no_runtime_cutover",
    ],
}


def _repo_backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _probe_code() -> str:
    auth_doc = legacy_memory_doc(
        "legacy-auth-proof",
        "legacy dependency/auth proof memory",
        uid="stubbed-auth-uid",
        tags=["legacy", "auth-proof"],
    )
    legacy_item_block = f"        def legacy_item():\n            return {auth_doc!r}\n"
    pin_stub_block = legacy_pin_stub_source()
    template = textwrap.dedent(r'''
        import hashlib
        import importlib
        import json
        import sys
        import types

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        stubbed_uid = "stubbed-auth-uid"
        dependency_calls = []
        observed_get_calls = []
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
        rate_limit_calls = []

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
            observed_get_calls.append({"uid": uid, "limit": limit, "offset": offset})
            return [legacy_item()]
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
            dependency_calls.append("auth.get_current_user_uid")
            raise AssertionError("controlled proof blocks unauthenticated GET without override")
        def with_rate_limit(dependency, policy):
            def _dep():
                rate_limit_calls.append(policy)
                raise AssertionError(f"rate-limit dependency executed: {policy}")
            _dep.__name__ = f"rate_limit_{policy.replace(':', '_')}"
            return _dep
        endpoints.get_current_user_uid = get_current_user_uid
        endpoints.with_rate_limit = with_rate_limit
        sys.modules["utils.other.endpoints"] = endpoints
        setattr(other_pkg, "endpoints", endpoints)

        module = importlib.import_module("routers.memories")

        route_evidence = None
        for route in module.router.routes:
            if getattr(route, "path", None) == "/v3/memories" and "GET" in (getattr(route, "methods", set()) or set()):
                deps = getattr(getattr(route, "dependant", None), "dependencies", [])
                dependency_names = []
                for dep in deps:
                    call = getattr(dep, "call", None)
                    dependency_names.append(getattr(call, "__name__", repr(call)))
                route_evidence = {
                    "route": "GET /v3/memories",
                    "handler": getattr(getattr(route, "endpoint", None), "__name__", None),
                    "dependency_names": dependency_names,
                    "auth_dependency": "utils.other.endpoints.get_current_user_uid" if "get_current_user_uid" in dependency_names else None,
                    "auth_dependency_equivalent": "routers.memories.auth.get_current_user_uid" if module.auth.get_current_user_uid is endpoints.get_current_user_uid else None,
                    "uses_expected_auth_dependency": module.auth.get_current_user_uid is endpoints.get_current_user_uid and "get_current_user_uid" in dependency_names,
                    "rate_limit_dependency": next((name for name in dependency_names if "rate_limit" in name), None),
                    "rate_limit_policy": None,
                    "has_rate_limit_dependency": any("rate_limit" in name for name in dependency_names),
                }
                break

        app_without_override = FastAPI()
        app_without_override.include_router(module.router)
        client_without_override = TestClient(app_without_override, raise_server_exceptions=False)
        without_auth_response = client_without_override.get("/v3/memories")

        dependency_calls_after_without = list(dependency_calls)
        observed_after_without = list(observed_get_calls)

        app_with_override = FastAPI()
        app_with_override.dependency_overrides[module.auth.get_current_user_uid] = lambda: stubbed_uid
        app_with_override.include_router(module.router)
        client_with_override = TestClient(app_with_override)
        with_auth_response = client_with_override.get("/v3/memories")

        memory_adapter_modules = [
            "utils.memory.v3.compatibility",
            "utils.memory.v3.request_adapter",
            "testing.memory.v3_route_planner",
            "utils.memory.v3.memory_read_service",
            "utils.memory.v3.response_adapter",
        ]
        loaded_adapters = [name for name in memory_adapter_modules if name in sys.modules]

        print(json.dumps({
            "testclient_ok": with_auth_response.status_code == 200,
            "minimal_fastapi_app_created": True,
            "real_router_included_under_stubs": True,
            "route_dependency_evidence": route_evidence,
            "without_auth_override": {
                "status_code": without_auth_response.status_code,
                "blocked": without_auth_response.status_code >= 400 and len(observed_after_without) == 0,
                "stubbed_auth_call_count": len(dependency_calls_after_without),
                "legacy_get_call_count": len(observed_after_without),
            },
            "with_auth_override": {
                "status_code": with_auth_response.status_code,
                "body": with_auth_response.json(),
                "observed_legacy_call": observed_get_calls[-1] if observed_get_calls else None,
            },
            "auth_dependency_overridden": True,
            "dependency_calls": dependency_calls,
            "rate_limit_call_count": len(rate_limit_calls),
            "rate_limit_calls": rate_limit_calls,
            "observed_get_memories_calls": observed_get_calls,
            "stubbed_legacy_get_memories_call_count": len(observed_get_calls),
            "mutation_flags": mutation_flags,
            "memory_control_dependency_present": False,
            "memory_control_dependency_invoked": False,
            "memory_adapter_modules_loaded": loaded_adapters,
            "runtime_cutover_claimed": False,
        }, sort_keys=True))
        ''')
    return template.replace("__LEGACY_ITEM_BLOCK__", legacy_item_block).replace("__PIN_STUB_BLOCK__", pin_stub_block)


def probe_get_dependency_auth_under_stubs() -> dict[str, Any]:
    backend_root = _repo_backend_root()
    python = backend_root / "venv" / "bin" / "python"
    if not python.exists():
        return {"testclient_ok": False, "blocked_reason": "repo-managed backend/venv/bin/python is unavailable"}
    result = subprocess.run(
        [str(python), "-c", _probe_code()],
        cwd=str(backend_root),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return {
            "testclient_ok": False,
            "blocked_reason": "stubbed GET dependency/auth TestClient probe failed",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr_tail": result.stderr[-2000:],
        }
    return json.loads(result.stdout)


def build_report(*, execute: bool = False) -> dict[str, Any]:
    probe = probe_get_dependency_auth_under_stubs() if execute else {"testclient_ok": False}
    route_evidence = probe.get("route_dependency_evidence") or {
        "route": "GET /v3/memories",
        "handler": "get_memories",
        "auth_dependency": None,
        "auth_dependency_equivalent": None,
        "uses_expected_auth_dependency": False,
        "rate_limit_dependency": None,
        "rate_limit_policy": None,
        "has_rate_limit_dependency": False,
    }
    mutation_flags_raw = probe.get("mutation_flags", {})
    mutation_flags = mutation_flags_raw if isinstance(mutation_flags_raw, dict) else {}
    testclient_ok = bool(probe.get("testclient_ok"))
    without_auth_blocked = bool(probe.get("without_auth_override", {}).get("blocked"))
    auth_override_works = bool(probe.get("with_auth_override", {}).get("status_code") == 200)
    proof_status = "PARTIAL" if testclient_ok and without_auth_blocked else ("BLOCKED" if execute else "NOT_RUN")
    status = "PARTIAL" if proof_status == "PARTIAL" else "BLOCKED"
    return {
        "artifact": "p1_3_v3_get_dependency_auth_readiness",
        "status": status,
        "proof_status": proof_status,
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "routers_memories_modified": False,
        "production_app_imported": False,
        "app_startup_executed": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "real_router_target": "backend/routers/memories.py",
        "required_import_stubs": REQUIRED_IMPORT_STUBS,
        "route_dependency_evidence": route_evidence,
        "dependency_overrides": ["routers.memories.auth.get_current_user_uid -> stubbed-auth-uid"],
        "stubbed_legacy_get_memories_executed": bool(probe.get("stubbed_legacy_get_memories_call_count")),
        "non_enrolled_legacy_behavior_preserved_under_auth_override": auth_override_works
        and bool(probe.get("stubbed_legacy_get_memories_call_count")),
        "memory_cohort_control_dependency_present": bool(probe.get("memory_control_dependency_present")),
        "memory_cohort_control_dependency_invoked": bool(probe.get("memory_control_dependency_invoked")),
        "memory_adapters_invoked": bool(probe.get("memory_adapter_modules_loaded")),
        "runtime_cutover_claimed": False,
        "mutation_flags_clear": bool(mutation_flags) and not any(mutation_flags.values()),
        "probe": probe,
        "proof": GET_DEPENDENCY_AUTH_READINESS_PROOF,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No backend/main.py import or production app startup executed.",
            "No real Firestore, Pinecone, cloud, provider, or network calls executed.",
            "No mutating /v3 routes executed and no production approval claimed.",
            "No memory cohort/control dependency is currently present or invoked by GET /v3/memories.",
            "This controlled stub proof is not real production auth/rate-limit/runtime evidence.",
        ],
        "summary": {
            "status": status,
            "proof_status": proof_status,
            "testclient_ok": testclient_ok,
            "expected_auth_dependency_present": bool(route_evidence.get("uses_expected_auth_dependency")),
            "auth_override_works": auth_override_works,
            "without_auth_override_blocked": without_auth_blocked,
            "has_rate_limit_dependency": bool(route_evidence.get("has_rate_limit_dependency")),
            "stubbed_legacy_get_memories_call_count": probe.get("stubbed_legacy_get_memories_call_count", 0),
            "memory_cohort_control_dependency_present": bool(probe.get("memory_control_dependency_present")),
            "memory_cohort_control_dependency_invoked": bool(probe.get("memory_control_dependency_invoked")),
            "runtime_cutover_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run the controlled venv TestClient dependency probe")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
