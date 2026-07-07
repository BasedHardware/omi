"""Static AST inspection of backend/routers/memories.py /v3 route signatures."""

from __future__ import annotations

from tests.unit.v3_router_probes.route_signature_integration import (
    CURRENT_RUNTIME_SUMMARY,
    FUTURE_WIRING_SEAM,
    GET_PARAM_CONTRACT_MAPPING,
    RUNTIME_BLOCKERS,
    inspect_route_signatures,
)


def test_pins_current_v3_route_signatures_and_body_models():
    routes = {route["route"]: route for route in inspect_route_signatures()}

    get_route = routes["GET /v3/memories"]
    assert get_route["handler"] == "get_memories"
    assert get_route["is_async"] is False
    assert get_route["response_model"] == "List[MemoryDB]"
    assert get_route["body_model"] is None
    param_names = [param["name"] for param in get_route["params"]]
    assert param_names[:4] == ["response", "limit", "offset", "cursor"]
    assert "uid" in param_names
    assert get_route["params"][param_names.index("uid")]["dependency"] == "auth.get_current_user_uid"
    assert "memory_runtime" in param_names
    assert get_route["params"][param_names.index("memory_runtime")]["dependency"] == "get_v3_get_runtime"

    post_route = routes["POST /v3/memories"]
    assert post_route["handler"] == "create_memory"
    assert post_route["is_async"] is True
    assert post_route["response_model"] == "MemoryDB"
    assert post_route["body_model"] == "Memory"

    delete_route = routes["DELETE /v3/memories/{memory_id}"]
    assert delete_route["handler"] == "delete_memory"
    assert delete_route["is_async"] is False
    assert delete_route["body_model"] is None
    assert [param["name"] for param in delete_route["params"]] == ["memory_id", "uid"]


def test_pins_legacy_runtime_calls_in_router_source():
    routes = {route["route"]: route for route in inspect_route_signatures()}

    assert routes["GET /v3/memories"]["legacy_runtime_calls"] == [
        "if offset == 0: limit = 5000",
        "memories_db.get_memories(uid, limit, offset)",
    ]
    assert routes["POST /v3/memories"]["legacy_runtime_calls"] == [
        "MemoryDB.from_memory(memory, uid, None, manually_added)",
        "memories_db.create_memory(uid, payload)",
        "upsert_memory_vector(uid, memory_db.id, memory_db.content, memory_db.category.value, memory_db.subject_entity_id)",
    ]
    assert routes["DELETE /v3/memories/{memory_id}"]["legacy_runtime_calls"] == [
        "_validate_memory(uid, memory_id)",
        "memories_db.delete_memory(uid, memory_id)",
        "delete_memory_vector(uid, memory_id)",
    ]
    assert CURRENT_RUNTIME_SUMMARY.startswith("GET /v3/memories now has a hard default-off memory dependency branch")


def test_maps_get_params_to_adapter_contract_and_future_seam():
    mapping = {item["route_param"]: item for item in GET_PARAM_CONTRACT_MAPPING}
    assert mapping["limit"]["request_adapter_field"] == "limit"
    assert mapping["limit"]["safe_to_map"] is True
    assert mapping["offset"]["safe_to_map"] is False
    assert mapping["cursor"]["current_route_param_present"] is True
    assert mapping["include_archive"]["safe_to_map"] is False

    assert FUTURE_WIRING_SEAM == [
        "GET route query params -> adapt_v3_request_parameters(...) without FastAPI-specific coupling",
        "adapted request + server-owned control/grant/projection/write evidence -> plan_v3_memory_route(...) pure planner",
        "planner read envelope -> adapt_v3_memory_response(...) List[MemoryDB] body plus additive headers",
    ]
    assert RUNTIME_BLOCKERS[0].startswith("Do not wire while GET still lacks route-local")
