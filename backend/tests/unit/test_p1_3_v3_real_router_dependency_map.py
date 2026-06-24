import importlib.util
from pathlib import Path


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_real_router_dependency_map", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_router_dependency_map_runner_exists_and_preserves_safety_flags():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "p1_3_v3_real_router_dependency_map.py"
    assert script_path.exists(), "missing controlled real-router dependency-map proof runner"

    module = _load_module(script_path)
    report = module.build_report(execute=True)

    assert report["status"] == "BLOCKED"
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["app_startup_executed"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["pinecone_calls_executed"] is False
    assert report["runtime_cutover_claimed"] is False
    assert report["production_rollout_approved"] is False


def test_real_router_dependency_map_pins_unsafe_imports_and_required_stubs():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_real_router_dependency_map.py")
    report = module.build_report(execute=True)

    assert report["real_router_target"] == "backend/routers/memories.py"
    assert report["production_app_imported"] is False
    assert report["router_import_attempted_under_stubs"] is True
    assert report["router_imported_under_stubs"] is True
    assert report["route_inclusion_attempted"] is False

    unsafe = {item["module"]: item for item in report["unsafe_import_dependencies"]}
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

    stubs = {stub["module"]: stub for stub in report["required_import_stubs"]}
    assert set(stubs) == set(unsafe)
    assert stubs["database._client"]["stubbed_attributes"] == ["document_id_from_seed"]
    assert "get_current_user_uid" in stubs["utils.other.endpoints"]["stubbed_attributes"]
    assert "with_rate_limit" in stubs["utils.other.endpoints"]["stubbed_attributes"]

    side_effects = report["import_side_effects_blocked_by_stubs"]
    assert "Firestore client/document-id helper construction blocked by database._client stub" in side_effects
    assert "Pinecone/vector provider import and mutation functions blocked by database.vector_db stub" in side_effects
    assert "Thread-pool/executor submission side effects blocked by utils.executors stub" in side_effects


def test_real_router_dependency_map_pins_v3_routes_and_future_get_seam_without_cutover():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_real_router_dependency_map.py")
    report = module.build_report(execute=True)
    routes = {route["route"]: route for route in report["pinned_routes"]}

    assert routes["GET /v3/memories"]["handler"] == "get_memories"
    assert routes["GET /v3/memories"]["methods"] == ["GET"]
    assert routes["GET /v3/memories"]["response_model"] == "List[MemoryDB]"
    assert routes["GET /v3/memories"]["dependency_overrides_required"] == ["auth.get_current_user_uid"]

    assert routes["POST /v3/memories"]["handler"] == "create_memory"
    assert routes["POST /v3/memories"]["methods"] == ["POST"]
    assert routes["POST /v3/memories"]["response_model"] == "MemoryDB"
    assert routes["POST /v3/memories"]["dependency_overrides_required"] == [
        "auth.with_rate_limit(auth.get_current_user_uid, 'memories:create')"
    ]

    assert routes["DELETE /v3/memories/{memory_id}"]["handler"] == "delete_memory"
    assert routes["DELETE /v3/memories/{memory_id}"]["methods"] == ["DELETE"]
    assert routes["DELETE /v3/memories/{memory_id}"]["dependency_overrides_required"] == [
        "auth.with_rate_limit(auth.get_current_user_uid, 'memories:delete')"
    ]

    assert report["future_get_wiring_seam"] == [
        "GET /v3/memories query params",
        "adapt_v17_v3_request_parameters(...) request adapter",
        "plan_v17_v3_memory_route(...) route planner",
        "adapt_v17_v3_memory_response(...) response adapter",
    ]
    assert report["runtime_cutover_claimed"] is False
    assert report["blocked_before_real_testclient"] == [
        "Replace import stubs with explicit FastAPI dependency_overrides and route-local V17 control/projection/write evidence seams.",
        "Prove GET does not call memories_db.get_memories for enrolled V17 projection-ready accounts before including the real router in TestClient.",
        "Prove POST/DELETE write convergence or keep enrolled V17 writes blocked before exercising mutating routes.",
    ]


def test_real_router_dependency_map_is_linked_from_readiness_test_runner_and_docs():
    root = Path(__file__).resolve().parents[2]
    readiness = _load_module(root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").build_report(
        execute=True
    )
    proof = readiness["real_router_dependency_map_proof"]
    assert proof["service"] == "backend/scripts/p1_3_v3_real_router_dependency_map.py"
    assert proof["test"] == "backend/tests/unit/test_p1_3_v3_real_router_dependency_map.py"
    assert proof["runtime_wired"] is False
    assert proof["production_rollout_approved"] is False
    assert proof["external_calls"] == []
    assert proof["imports_real_router_under_stubs"] is True
    assert readiness["summary"]["real_router_dependency_map_proof_present"] is True

    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    assert "test_p1_3_v3_real_router_dependency_map.py" in test_sh
    assert "p1_3_v3_real_router_dependency_map.py" in ticket_doc
    assert "p1_3_v3_real_router_dependency_map.py" in oracle_doc
