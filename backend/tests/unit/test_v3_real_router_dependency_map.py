"""Real memories router import map and static /v3 route pins under explicit stubs."""

from __future__ import annotations

import pytest

from tests.unit.v3_router_probes.real_router_dependency_map import (
    REQUIRED_IMPORT_STUBS,
    UNSAFE_IMPORT_DEPENDENCIES,
    inspect_static_routes,
)
from tests.unit.v3_router_probes.in_process import probe_real_router_import_under_stubs

try:
    import routers.memories  # noqa: F401
except Exception:
    pass


@pytest.fixture
def import_probe():
    probe = probe_real_router_import_under_stubs()
    if not probe.get("import_ok"):
        pytest.skip(probe.get("blocked_reason", "real-router import probe unavailable"))
    return probe


def test_unsafe_imports_require_stubs_before_router_import():
    unsafe = {item["module"]: item for item in UNSAFE_IMPORT_DEPENDENCIES}
    for module_name in [
        "database.memories",
        "database.review_queue",
        "database.vector_db",
        "database._client",
        "utils.executors",
        "utils.apps",
        "utils.other.endpoints",
    ]:
        assert module_name in unsafe
        assert unsafe[module_name]["stub_required_before_import"] is True
        assert unsafe[module_name]["external_or_mutation_risk"] is True

    stubs = {stub["module"]: stub for stub in REQUIRED_IMPORT_STUBS}
    assert set(stubs) == set(unsafe)
    assert stubs["database._client"]["stubbed_attributes"] == ["document_id_from_seed"]
    assert "get_current_user_uid" in stubs["utils.other.endpoints"]["stubbed_attributes"]
    assert "with_rate_limit" in stubs["utils.other.endpoints"]["stubbed_attributes"]


def test_router_imports_under_stubs_without_route_execution(import_probe):
    assert import_probe["import_ok"] is True
    pinned = {route["route"]: route for route in import_probe["pinned_routes"]}
    assert pinned["GET /v3/memories"]["handler"] == "get_memories"
    assert pinned["POST /v3/memories"]["handler"] == "create_memory"
    assert pinned["DELETE /v3/memories/{memory_id}"]["handler"] == "delete_memory"


def test_static_ast_pins_v3_routes_handlers_and_dependency_overrides():
    routes = {route["route"]: route for route in inspect_static_routes()}
    assert routes["GET /v3/memories"]["handler"] == "get_memories"
    assert routes["GET /v3/memories"]["response_model"] == "List[MemoryDB]"
    assert routes["GET /v3/memories"]["dependency_overrides_required"] == ["auth.get_current_user_uid"]

    assert routes["POST /v3/memories"]["handler"] == "create_memory"
    assert routes["POST /v3/memories"]["response_model"] == "MemoryDB"
    assert routes["POST /v3/memories"]["dependency_overrides_required"] == [
        "auth.with_rate_limit(auth.get_current_user_uid, 'memories:create')"
    ]

    assert routes["DELETE /v3/memories/{memory_id}"]["handler"] == "delete_memory"
    assert routes["DELETE /v3/memories/{memory_id}"]["dependency_overrides_required"] == [
        "auth.with_rate_limit(auth.get_current_user_uid, 'memories:delete')"
    ]
