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
