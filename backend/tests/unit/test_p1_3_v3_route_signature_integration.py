import importlib.util
from pathlib import Path


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_route_signature_integration", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_signature_integration_is_static_read_only_and_no_fastapi_imports():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "p1_3_v3_route_signature_integration.py"
    assert script_path.exists(), "missing pure/static /v3 route-signature proof runner"
    source = script_path.read_text(encoding="utf-8")
    assert "from fastapi" not in source
    assert "import fastapi" not in source
    assert "routers.memories" not in source
    assert "import routers" not in source

    module = _load_module(script_path)
    report = module.build_report(execute=True)

    assert report["status"] == "BLOCKED"
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["app_startup_executed"] is False
    assert report["router_imported"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["runtime_cutover_claimed"] is False


def test_route_signature_integration_pins_current_v3_route_signatures_and_body_models():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_route_signature_integration.py")
    report = module.build_report(execute=True)
    routes = {route["route"]: route for route in report["route_signatures"]}

    get_route = routes["GET /v3/memories"]
    assert get_route["handler"] == "get_memories"
    assert get_route["is_async"] is False
    assert get_route["response_model"] == "List[MemoryDB]"
    assert get_route["body_model"] is None
    assert get_route["params"] == [
        {"name": "response", "annotation": "Response", "default": None, "dependency": None, "kind": "query"},
        {"name": "limit", "annotation": "int", "default": "100", "dependency": None, "kind": "query"},
        {"name": "offset", "annotation": "int", "default": "0", "dependency": None, "kind": "query"},
        {"name": "cursor", "annotation": "Optional[str]", "default": "None", "dependency": None, "kind": "query"},
        {
            "name": "uid",
            "annotation": "str",
            "default": "Depends(auth.get_current_user_uid)",
            "dependency": "auth.get_current_user_uid",
            "kind": "dependency",
        },
        {
            "name": "v17_runtime",
            "annotation": "V17V3GetRuntime",
            "default": "Depends(get_v17_v3_get_runtime)",
            "dependency": "get_v17_v3_get_runtime",
            "kind": "dependency",
        },
    ]

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


def test_route_signature_integration_pins_legacy_runtime_calls_and_no_cutover_claim():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_route_signature_integration.py")
    report = module.build_report(execute=True)
    routes = {route["route"]: route for route in report["route_signatures"]}

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
    assert report["runtime_cutover_claimed"] is False
    assert report["current_runtime_summary"] == (
        "GET /v3/memories now has a hard default-off V17 dependency branch: production/default and "
        "non-enrolled legacy-primary reads preserve legacy memories_db semantics, while TestClient-only "
        "V17 read-mode overrides can call the composed service without legacy fallback. POST/DELETE remain legacy mutation paths."
    )


def test_route_signature_integration_maps_get_params_to_adapter_contract_and_blocks_runtime():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_route_signature_integration.py")
    report = module.build_report(execute=True)

    mapping = {item["route_param"]: item for item in report["get_param_contract_mapping"]}
    assert mapping["limit"]["request_adapter_field"] == "limit"
    assert mapping["limit"]["safe_to_map"] is True
    assert mapping["limit"]["v17_constraint"] == "bounded V17 limit; never expanded to 5000 in V17 cursor mode"
    assert mapping["offset"]["safe_to_map"] is False
    assert (
        mapping["offset"]["blocked_reason"] == "offset is legacy-primary only; V17 cohort requires signed cursor mode"
    )
    assert mapping["cursor"]["current_route_param_present"] is True
    assert mapping["cursor"]["future_only"] is False
    assert mapping["include_archive"]["safe_to_map"] is False
    assert mapping["include_archive"]["blocked_reason"] == "Archive default-unavailable for /v3 default reads"

    assert report["future_wiring_seam"] == [
        "GET route query params -> adapt_v17_v3_request_parameters(...) without FastAPI-specific coupling",
        "adapted request + server-owned control/grant/projection/write evidence -> plan_v17_v3_memory_route(...) pure planner",
        "planner read envelope -> adapt_v17_v3_memory_response(...) List[MemoryDB] body plus additive headers",
    ]
    assert report["runtime_blockers"] == [
        "Do not wire while GET still lacks route-local server-owned V17 control/grant/projection evidence inputs.",
        "Do not wire while POST/DELETE still execute direct legacy DB/vector mutation paths for enrolled V17 accounts.",
        "Do not wire until FastAPI dependency/response-model behavior is proven with controlled stubs or production deps.",
    ]


def test_route_signature_integration_is_linked_from_readiness_test_runner_and_docs():
    root = Path(__file__).resolve().parents[2]
    readiness = _load_module(root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").build_report(
        execute=True
    )
    proof = readiness["route_signature_integration_proof"]
    assert proof["service"] == "backend/scripts/p1_3_v3_route_signature_integration.py"
    assert proof["test"] == "backend/tests/unit/test_p1_3_v3_route_signature_integration.py"
    assert proof["runtime_wired"] is False
    assert proof["production_rollout_approved"] is False
    assert proof["external_calls"] == []
    assert readiness["summary"]["route_signature_integration_proof_present"] is True

    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    assert "test_p1_3_v3_route_signature_integration.py" in test_sh
    assert "p1_3_v3_route_signature_integration.py" in ticket_doc
    assert "p1_3_v3_route_signature_integration.py" in oracle_doc
