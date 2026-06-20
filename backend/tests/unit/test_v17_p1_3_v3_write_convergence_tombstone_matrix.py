import importlib.util
from pathlib import Path


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_write_convergence_tombstone_matrix", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=True):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_write_convergence_tombstone_matrix.py")
    return module.build_report(execute=execute)


def test_write_convergence_tombstone_matrix_is_safe_pre_runtime_only():
    report = _report(execute=True)

    assert report["artifact"] == "v17_p1_3_v3_write_convergence_tombstone_matrix"
    assert report["status"] == "BLOCKED"
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["routers_memories_modified"] is False
    assert report["production_app_imported"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["pinecone_calls_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False
    assert report["matrix_proof"]["proof_level"] == "pure_helper_route_planner_write_projection_seam_only"
    assert report["matrix_proof"]["fake_contexts_only"] is True
    assert report["matrix_proof"]["runtime_wired"] is False


def test_matrix_ready_case_requires_create_update_delete_and_all_projection_tombstone_fences():
    report = _report(execute=True)
    cases = {case["case_id"]: case for case in report["matrix_proof"]["cases"]}
    ready = cases["ready_create_update_delete_tombstone_projection_fences"]

    assert ready["http_status"] == 200
    assert ready["plan_kind"] == "v17_response_envelope"
    assert ready["read_decision"] == "v17_projection_ready"
    assert ready["legacy_calls"] == []
    assert ready["projection_calls"] == [{"uid": "uid-write-tombstone", "limit": 100, "cursor": None}]
    assert ready["body"] == [{"id": "projection-write-ready", "content": "projection memory"}]
    assert ready["write_decision_reasons"] == [
        "create_write_converged",
        "update_write_converged",
        "delete_write_converged",
    ]
    assert ready["projection_fence_summary"] == {
        "expected_account_generation": 11,
        "account_generation": 11,
        "projection_generation": 11,
        "tombstone_fence_present": True,
        "tombstone_fence_generation": 11,
        "freshness_fence_present": True,
        "freshness_fence_generation": 11,
    }
    assert ready["archive_default_available"] is False
    assert ready["stale_short_term_default_visible"] is False
    assert ready["legacy_fallback_allowed"] is False


def test_matrix_fail_closed_convergence_and_tombstone_delete_cases_never_fallback_or_merge():
    report = _report(execute=True)
    cases = {case["case_id"]: case for case in report["matrix_proof"]["cases"]}
    expected_reasons = {
        "create_convergence_false_fail_closed": "external_create_convergence_not_ready",
        "update_convergence_false_fail_closed": "external_update_convergence_not_ready",
        "delete_convergence_false_fail_closed": "external_delete_convergence_not_ready",
        "delete_tombstone_fence_missing_fail_closed": "tombstone_fence_missing",
        "delete_tombstone_generation_mismatch_fail_closed": "tombstone_fence_stale",
    }

    for case_id, reason in expected_reasons.items():
        case = cases[case_id]
        assert case["http_status"] == 503, case_id
        assert case["plan_kind"] == "fail_closed", case_id
        assert case["read_decision"] == reason, case_id
        assert case["legacy_calls"] == [], case_id
        assert case["projection_calls"] == [], case_id
        assert case["body"] is None, case_id
        assert case["legacy_fallback_allowed"] is False, case_id
        assert case["v17_legacy_merge_allowed"] is False, case_id
        assert case["archive_default_available"] is False, case_id
        assert case["stale_short_term_default_visible"] is False, case_id


def test_matrix_enabled_empty_only_when_all_write_projection_tombstone_fences_are_ready():
    report = _report(execute=True)
    cases = {case["case_id"]: case for case in report["matrix_proof"]["cases"]}

    allowed = cases["enabled_empty_all_fences_ready_allowed"]
    assert allowed["http_status"] == 200
    assert allowed["plan_kind"] == "v17_response_envelope"
    assert allowed["body"] == []
    assert allowed["legacy_calls"] == []
    assert allowed["projection_calls"] == []
    assert allowed["enabled_empty_allowed"] is True
    assert allowed["legacy_fallback_allowed"] is False

    blocked = cases["enabled_empty_missing_tombstone_fence_fail_closed"]
    assert blocked["http_status"] == 503
    assert blocked["plan_kind"] == "fail_closed"
    assert blocked["read_decision"] == "tombstone_fence_missing"
    assert blocked["body"] is None
    assert blocked["legacy_calls"] == []
    assert blocked["projection_calls"] == []
    assert blocked["enabled_empty_allowed"] is False
    assert blocked["legacy_fallback_allowed"] is False


def test_matrix_preserves_archive_and_stale_short_term_default_visibility_blocks():
    report = _report(execute=True)
    cases = {case["case_id"]: case for case in report["matrix_proof"]["cases"]}

    archive = cases["archive_default_visibility_denied"]
    assert archive["http_status"] == 403
    assert archive["plan_kind"] == "deny"
    assert archive["read_decision"] == "archive_not_allowed"
    assert archive["legacy_calls"] == []
    assert archive["projection_calls"] == []
    assert archive["archive_default_available"] is False
    assert archive["legacy_fallback_allowed"] is False

    stale = cases["stale_short_term_default_visibility_denied"]
    assert stale["http_status"] == 503
    assert stale["plan_kind"] == "fail_closed"
    assert stale["read_decision"] == "stale_short_term_default_visible"
    assert stale["legacy_calls"] == []
    assert stale["projection_calls"] == []
    assert stale["stale_short_term_default_visible"] is False
    assert stale["legacy_fallback_allowed"] is False


def test_write_convergence_tombstone_matrix_is_linked_from_readiness_and_docs():
    root = Path(__file__).resolve().parents[2]
    report = _report(execute=True)

    assert report["summary"] == {
        "status": "BLOCKED",
        "matrix_case_count": 10,
        "ready_case_count": 2,
        "fail_closed_or_denied_case_count": 8,
        "runtime_wiring_changed": False,
        "approval_claimed": False,
    }

    external = _load_module(root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py").build_report(
        execute=True
    )
    runtime = _load_module(root / "scripts" / "v17_p1_3_v3_get_runtime_wiring_readiness.py").build_report(execute=True)
    assert external["write_convergence_tombstone_matrix_proof"]["service"] == (
        "backend/scripts/v17_p1_3_v3_write_convergence_tombstone_matrix.py"
    )
    assert external["summary"]["write_convergence_tombstone_matrix_proof_present"] is True
    assert "write_convergence_tombstone_matrix_proof" in runtime["existing_local_proof_artifacts"]
    assert "write_convergence_tombstone_matrix_proof" in runtime["remaining_gates"][3]["existing_local_proofs"]
    assert "write_convergence_tombstone_matrix_proof" in runtime["remaining_gates"][8]["existing_local_proofs"]

    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    assert "test_v17_p1_3_v3_write_convergence_tombstone_matrix.py" in test_sh
    assert "v17_p1_3_v3_write_convergence_tombstone_matrix.py" in ticket_doc
    assert "v17_p1_3_v3_write_convergence_tombstone_matrix.py" in oracle_doc
