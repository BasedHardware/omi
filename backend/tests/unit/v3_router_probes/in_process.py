"""In-process TestClient probes for the real memories router under stubs."""

from __future__ import annotations

from typing import Any
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit.v3_router_probes.stubs import import_memories_router, install_router_import_stubs

MEMORY_ADAPTER_MODULES = [
    "utils.memory.v3.request_adapter",
    "testing.memory.v3_route_planner",
    "utils.memory.v3.response_adapter",
]

_STUB_MODULE_PREFIXES = (
    "database",
    "models",
    "routers.memories",
    "utils",
)


def _snapshot_router_import_modules() -> dict[str, object]:
    return {
        name: module
        for name, module in sys.modules.items()
        if name == "routers.memories"
        or any(name == prefix or name.startswith(f"{prefix}.") for prefix in _STUB_MODULE_PREFIXES)
    }


def _restore_router_import_modules(previous: dict[str, object]) -> None:
    for name in list(sys.modules):
        if name == "routers.memories" or any(
            name == prefix or name.startswith(f"{prefix}.") for prefix in _STUB_MODULE_PREFIXES
        ):
            sys.modules.pop(name, None)
    sys.modules.update(previous)


def probe_real_router_get_testclient_under_stubs() -> dict[str, Any]:
    previous_modules = _snapshot_router_import_modules()
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
    observed_get_calls: list[dict[str, Any]] = []
    stubbed_uid = "stubbed-test-uid"

    try:
        install_router_import_stubs(
            observed_get_calls=observed_get_calls,
            mutation_flags=mutation_flags,
            stubbed_uid=stubbed_uid,
            auth_raises=True,
        )
        module = import_memories_router()
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

        loaded_adapters = [name for name in MEMORY_ADAPTER_MODULES if name in __import__("sys").modules]

        return {
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
            "mutation_flags": mutation_flags,
            "memory_adapter_modules_loaded": loaded_adapters,
        }
    except Exception as exc:
        return {"testclient_ok": False, "blocked_reason": f"in-process GET TestClient probe failed: {exc}"}
    finally:
        _restore_router_import_modules(previous_modules)


def probe_get_dependency_auth_under_stubs() -> dict[str, Any]:
    previous_modules = _snapshot_router_import_modules()
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
    observed_get_calls: list[dict[str, Any]] = []
    dependency_calls: list[str] = []
    rate_limit_calls: list[str] = []
    stubbed_uid = "stubbed-auth-uid"

    try:
        install_router_import_stubs(
            observed_get_calls=observed_get_calls,
            mutation_flags=mutation_flags,
            stubbed_uid=stubbed_uid,
            auth_raises=True,
        )
        endpoints = __import__("sys").modules["utils.other.endpoints"]

        def tracking_get_current_user_uid() -> str:
            dependency_calls.append("auth.get_current_user_uid")
            raise AssertionError("controlled proof blocks unauthenticated GET without override")

        endpoints.get_current_user_uid = tracking_get_current_user_uid

        module = import_memories_router()

        route_evidence = None
        for route in module.router.routes:
            if getattr(route, "path", None) == "/v3/memories" and "GET" in (getattr(route, "methods", set()) or set()):
                deps = getattr(getattr(route, "dependant", None), "dependencies", [])
                dependency_names = [getattr(getattr(dep, "call", None), "__name__", repr(dep.call)) for dep in deps]
                route_evidence = {
                    "route": "GET /v3/memories",
                    "handler": getattr(getattr(route, "endpoint", None), "__name__", None),
                    "dependency_names": dependency_names,
                    "auth_dependency": (
                        "utils.other.endpoints.get_current_user_uid"
                        if "get_current_user_uid" in dependency_names
                        else None
                    ),
                    "auth_dependency_equivalent": (
                        "routers.memories.auth.get_current_user_uid"
                        if module.auth.get_current_user_uid is endpoints.get_current_user_uid
                        else None
                    ),
                    "uses_expected_auth_dependency": module.auth.get_current_user_uid is endpoints.get_current_user_uid
                    and "get_current_user_uid" in dependency_names,
                    "rate_limit_dependency": next((name for name in dependency_names if "rate_limit" in name), None),
                    "has_rate_limit_dependency": any("rate_limit" in name for name in dependency_names),
                }
                break

        app_without_override = FastAPI()
        app_without_override.include_router(module.router)
        without_auth_response = TestClient(app_without_override, raise_server_exceptions=False).get("/v3/memories")
        observed_after_without = list(observed_get_calls)

        app_with_override = FastAPI()
        app_with_override.dependency_overrides[module.auth.get_current_user_uid] = lambda: stubbed_uid
        app_with_override.include_router(module.router)
        with_auth_response = TestClient(app_with_override).get("/v3/memories")

        loaded_adapters = [name for name in MEMORY_ADAPTER_MODULES if name in __import__("sys").modules]

        return {
            "testclient_ok": with_auth_response.status_code == 200,
            "minimal_fastapi_app_created": True,
            "real_router_included_under_stubs": True,
            "route_dependency_evidence": route_evidence,
            "without_auth_override": {
                "status_code": without_auth_response.status_code,
                "blocked": without_auth_response.status_code >= 400 and len(observed_after_without) == 0,
                "stubbed_auth_call_count": len(dependency_calls),
                "legacy_get_call_count": len(observed_after_without),
            },
            "with_auth_override": {
                "status_code": with_auth_response.status_code,
                "body": with_auth_response.json(),
                "observed_legacy_call": observed_get_calls[-1] if observed_get_calls else None,
            },
            "dependency_calls": dependency_calls,
            "rate_limit_call_count": len(rate_limit_calls),
            "observed_get_memories_calls": observed_get_calls,
            "stubbed_legacy_get_memories_call_count": len(observed_get_calls),
            "mutation_flags": mutation_flags,
            "memory_control_dependency_present": False,
            "memory_control_dependency_invoked": False,
            "memory_adapter_modules_loaded": loaded_adapters,
        }
    except Exception as exc:
        return {"testclient_ok": False, "blocked_reason": f"in-process GET dependency/auth probe failed: {exc}"}
    finally:
        _restore_router_import_modules(previous_modules)


def probe_real_router_import_under_stubs() -> dict[str, Any]:
    previous_modules = _snapshot_router_import_modules()
    try:
        install_router_import_stubs(auth_raises=True)
        module = import_memories_router()
        pinned = []
        for route in module.router.routes:
            path = getattr(route, "path", None)
            methods = sorted(getattr(route, "methods", []) or [])
            method = next((candidate for candidate in ["GET", "POST", "DELETE"] if candidate in methods), None)
            if method and path in {"/v3/memories", "/v3/memories/{memory_id}"}:
                route_ref = f"{method} {path}"
                if route_ref in {"GET /v3/memories", "POST /v3/memories", "DELETE /v3/memories/{memory_id}"}:
                    response_model = getattr(route, "response_model", None)
                    pinned.append(
                        {
                            "route": route_ref,
                            "path": path,
                            "methods": [method],
                            "handler": getattr(getattr(route, "endpoint", None), "__name__", None),
                            "response_model": str(response_model).replace("typing.", "") if response_model else None,
                        }
                    )
        return {"import_ok": True, "pinned_routes": sorted(pinned, key=lambda item: item["route"])}
    except Exception as exc:
        return {"import_ok": False, "blocked_reason": f"in-process router import probe failed: {exc}"}
    finally:
        _restore_router_import_modules(previous_modules)
