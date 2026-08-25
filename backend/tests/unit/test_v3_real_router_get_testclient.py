"""Real memories router GET /v3/memories TestClient behavior under stubs."""

from __future__ import annotations

import pytest

from tests.unit.v3_router_probes.in_process import probe_real_router_get_testclient_under_stubs
from tests.unit.v3_router_probes.real_router_dependency_map import FUTURE_GET_WIRING_SEAM

try:
    from fastapi.testclient import TestClient  # noqa: F401
except Exception as exc:  # pragma: no cover
    pytest.skip(f"FastAPI/TestClient required: {exc}", allow_module_level=True)


@pytest.fixture
def probe():
    result = probe_real_router_get_testclient_under_stubs()
    if not result.get("testclient_ok"):
        pytest.skip(result.get("blocked_reason", "real-router GET TestClient probe unavailable"))
    return result


def test_get_only_routes_execute_and_mutations_stay_blocked(probe):
    assert probe["executed_routes"] == ["GET /v3/memories", "GET /v3/memories?limit=17&offset=3"]
    assert probe["unexecuted_mutating_routes"] == ["POST /v3/memories", "DELETE /v3/memories/{memory_id}"]
    assert probe["mutation_flags"] == {
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
    assert probe["stubbed_legacy_get_memories_call_count"] == 2


def test_current_legacy_get_runtime_preserves_limit_offset_semantics(probe):
    assert probe["default_get"]["status_code"] == 200
    assert probe["explicit_get"]["status_code"] == 200
    assert probe["observed_get_memories_calls"] == [
        {"uid": "stubbed-test-uid", "limit": 5000, "offset": 0},
        {"uid": "stubbed-test-uid", "limit": 17, "offset": 3},
    ]
    assert probe["default_get"]["observed_legacy_call"] == {"uid": "stubbed-test-uid", "limit": 5000, "offset": 0}
    assert probe["explicit_get"]["observed_legacy_call"] == {"uid": "stubbed-test-uid", "limit": 17, "offset": 3}


def test_get_still_uses_legacy_db_not_runtime_adapter_pipeline(probe):
    assert probe["stubbed_legacy_get_memories_call_count"] == 2
    # Legacy GET routes through memories_db stub, not the v3 runtime adapter pipeline.
    assert probe["memory_adapter_modules_loaded"] == []
    assert FUTURE_GET_WIRING_SEAM == [
        "GET /v3/memories query params",
        "adapt_v3_request_parameters(...) request adapter",
        "plan_v3_memory_route(...) route planner",
        "adapt_v3_memory_response(...) response adapter",
    ]
