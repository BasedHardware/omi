import importlib.util
import json
from pathlib import Path

REQUIRED_ROUTE_REFERENCES = {
    "GET /v3/memories": "list_default_memories",
    "POST /v3/memories": "create_memory",
    "POST /v3/memories/batch": "batch_create_memory",
    "PATCH /v3/memories/{memory_id}": "edit_memory",
    "DELETE /v3/memories/{memory_id}": "delete_memory",
    "GET /v3/memories/{memory_id}": "missing_read_endpoint_gap",
    "GET /v3/memories/search": "missing_search_endpoint_gap",
}

REQUIRED_GAPS = {
    "disabled_malformed_no_grant_semantics",
    "enabled_empty_semantics",
    "response_shape_source_metadata",
    "archive_default_unavailable",
    "category_filter_compatibility",
    "unsafe_legacy_fallback_after_v17_writes",
    "cursor_pagination_stability",
}


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_external_compatibility_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v3_external_compatibility_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py"
    assert script_path.exists(), "missing safe /v3 external compatibility readiness runner"

    module = _load_module(script_path)
    report = module.build_report(execute=False)

    assert report["status"] == "BLOCKED"
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["benchmark_evidence_collected"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False
    assert report["execute"] is False


def test_v3_external_compatibility_inventory_pins_exact_route_gaps_and_non_claims():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)

    assert report["execute"] is True
    assert report["status"] == "BLOCKED"
    routes = {surface["route"]: surface for surface in report["v3_surfaces"]}
    for route, expected_id in REQUIRED_ROUTE_REFERENCES.items():
        assert route in routes
        assert routes[route]["surface_id"] == expected_id
        assert routes[route]["source_file"] == "backend/routers/memories.py"
        assert routes[route]["evidence"] == []

    gaps = {gap["gap_id"]: gap for gap in report["remaining_gaps"]}
    assert REQUIRED_GAPS.issubset(gaps)
    for gap in gaps.values():
        assert gap["status"] in {"BLOCKED", "NOT_RUN"}
        assert gap["evidence"] == []
        assert gap["approval_claimed"] is False


def test_v3_readiness_pins_code_route_evidence_for_runtime_decision_blockers():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)

    list_surface = {surface["surface_id"]: surface for surface in report["v3_surfaces"]}["list_default_memories"]
    assert (
        list_surface["route_decorator"]
        == "@router.get('/v3/memories', tags=['memories'], response_model=List[MemoryDB])"
    )
    assert list_surface["handler_signature"] == (
        "def get_memories(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):"
    )
    assert list_surface["db_call"] == "memories_db.get_memories(uid, limit, offset)"
    assert list_surface["first_page_limit_override"] == "if offset == 0: limit = 5000"
    assert list_surface["supported_query_params"] == ["limit", "offset"]
    assert list_surface["unsupported_query_params"] == ["category", "cursor", "include_archive", "source"]
    assert list_surface["response_model"] == "List[MemoryDB]"
    assert list_surface["source_metadata_contract"] == "absent"

    create_surface = {surface["surface_id"]: surface for surface in report["v3_surfaces"]}["create_memory"]
    assert create_surface["db_write_call"] == "memories_db.create_memory(uid, payload)"
    assert create_surface["vector_write_call"] == "upsert_memory_vector(...)"
    assert create_surface["v17_write_convergence"] == "absent"

    delete_surface = {surface["surface_id"]: surface for surface in report["v3_surfaces"]}["delete_memory"]
    assert delete_surface["validation_call"] == "_validate_memory(uid, memory_id)"
    assert delete_surface["db_write_call"] == "memories_db.delete_memory(uid, memory_id)"
    assert delete_surface["v17_tombstone_convergence"] == "absent"


def test_v3_readiness_pins_decision_matrix_and_product_dependencies():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)

    decisions = {decision["state"]: decision for decision in report["runtime_decision_matrix"]}
    for state in ["disabled", "malformed", "missing", "no_default_memory_grant"]:
        assert decisions[state]["required_behavior"] == "fail_closed_or_explicit_legacy_safe_product_decision"
        assert decisions[state]["unsafe_legacy_fallback_allowed"] is False
    assert decisions["enabled_empty"]["required_behavior"] == "return_empty_v17_result_without_legacy_fallback"
    assert decisions["enabled_empty"]["unsafe_legacy_fallback_allowed"] is False
    assert (
        decisions["archive_default"]["required_behavior"] == "default_unavailable_without_explicit_archive_capability"
    )
    assert (
        decisions["cursor_pagination"]["required_behavior"] == "stable_cursor_contract_required_before_runtime_cutover"
    )

    dependencies = {dependency["dependency_id"]: dependency for dependency in report["product_decision_dependencies"]}
    for dependency_id in [
        "v3_disabled_malformed_no_grant_policy",
        "v3_enabled_empty_policy",
        "v3_response_shape_source_metadata",
        "v3_cursor_pagination_contract",
        "v3_write_convergence_before_read_cutover",
    ]:
        assert dependencies[dependency_id]["status"] == "BLOCKED"
        assert dependencies[dependency_id]["approval_claimed"] is False


def test_v3_readiness_json_round_trips_and_command_summary_is_stable():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py")
    report = module.build_report(execute=True)
    encoded = json.dumps(report, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["summary"] == {
        "status": "BLOCKED",
        "surface_count": 7,
        "gap_count": 7,
        "decision_state_count": 8,
        "product_dependency_count": 5,
        "read_only": True,
        "mutation_allowed": False,
        "approval_claimed": False,
    }


def test_v3_readiness_is_registered_in_test_runner_and_oracle_docs():
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")

    assert "test_v17_p1_3_v3_external_compatibility_readiness.py" in test_sh
    assert "v17_p1_3_v3_external_compatibility_readiness.py" in ticket_doc
    assert "Oracle P1-3 `/v3` external compatibility readiness slice" in ticket_doc
    assert "v17_p1_3_v3_external_compatibility_readiness.py" in oracle_doc
    assert "local `/v3` external compatibility readiness slice" in oracle_doc
