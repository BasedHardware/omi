import importlib.util
from pathlib import Path


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("p1_3_v3_real_router_fail_closed_matrix", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=True):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_real_router_fail_closed_matrix.py")
    return module.build_report(execute=execute)


def test_fail_closed_matrix_runner_is_safe_and_honest_about_current_real_router_behavior():
    report = _report(execute=True)

    assert report["artifact"] == "p1_3_v3_real_router_fail_closed_matrix"
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
    assert report["current_real_router_baseline"]["behavior"] == "legacy_only_under_stubs"
    assert report["current_real_router_baseline"]["runtime_fail_closed_matrix_wired"] is False
    assert report["future_dispatcher_matrix_proof"]["proof_level"] == "pure_helper_route_planner_seam_only"
    assert report["future_dispatcher_matrix_proof"]["runtime_behavior_changed"] is False


def test_current_real_router_still_preserves_legacy_limit_offset_and_does_not_invoke_memory_adapters():
    report = _report(execute=True)
    baseline = report["current_real_router_baseline"]

    assert baseline["observed_get_memories_calls"] == [
        {"uid": "stubbed-test-uid", "limit": 5000, "offset": 0},
        {"uid": "stubbed-test-uid", "limit": 17, "offset": 3},
    ]
    assert baseline["memory_adapters_invoked"] is False
    assert baseline["stubbed_legacy_get_memories_call_count"] == 2
    assert baseline["mutation_flags_clear"] is True


def test_future_dispatcher_matrix_calls_only_the_selected_reader_or_no_reader():
    report = _report(execute=True)
    cases = {case["case_id"]: case for case in report["future_dispatcher_matrix_proof"]["cases"]}

    assert cases["non_enrolled_offset_zero_legacy_primary"]["http_status"] == 200
    assert cases["non_enrolled_offset_zero_legacy_primary"]["body"] == [{"id": "legacy-5000", "source": "legacy"}]
    assert cases["non_enrolled_offset_zero_legacy_primary"]["legacy_calls"] == [
        {"uid": "uid-matrix", "limit": 5000, "offset": 0}
    ]
    assert cases["non_enrolled_offset_zero_legacy_primary"]["projection_calls"] == []

    assert cases["non_enrolled_explicit_limit_offset_legacy_primary"]["legacy_calls"] == [
        {"uid": "uid-matrix", "limit": 17, "offset": 3}
    ]
    assert cases["non_enrolled_explicit_limit_offset_legacy_primary"]["projection_calls"] == []

    assert cases["enrolled_projection_success_projection_only"]["http_status"] == 200
    assert cases["enrolled_projection_success_projection_only"]["body"] == [
        {"id": "projection-1", "content": "projection memory"}
    ]
    assert cases["enrolled_projection_success_projection_only"]["legacy_calls"] == []
    assert cases["enrolled_projection_success_projection_only"]["projection_calls"] == [
        {"uid": "uid-matrix", "limit": 100, "cursor": None}
    ]

    assert cases["enrolled_enabled_empty_no_legacy_fallback"]["http_status"] == 200
    assert cases["enrolled_enabled_empty_no_legacy_fallback"]["body"] == []
    assert cases["enrolled_enabled_empty_no_legacy_fallback"]["legacy_calls"] == []
    assert cases["enrolled_enabled_empty_no_legacy_fallback"]["projection_calls"] == []


def test_future_dispatcher_matrix_fail_closed_and_denied_states_never_call_legacy_or_projection():
    report = _report(execute=True)
    cases = {case["case_id"]: case for case in report["future_dispatcher_matrix_proof"]["cases"]}
    expected_status = {
        "enrolled_missing_control_fail_closed": 503,
        "enrolled_malformed_control_fail_closed": 503,
        "enrolled_projection_not_ready_fail_closed": 503,
        "enrolled_write_convergence_not_ready_fail_closed": 503,
        "enrolled_account_generation_mismatch_fail_closed": 503,
        "enrolled_cursor_mismatch_fail_closed": 400,
        "enrolled_no_grant_denied": 403,
        "enrolled_archive_denied": 403,
    }

    for case_id, status in expected_status.items():
        case = cases[case_id]
        assert case["http_status"] == status, case_id
        assert case["legacy_calls"] == [], case_id
        assert case["projection_calls"] == [], case_id
        assert case["legacy_fallback_allowed"] is False, case_id
        assert case["body"] is None, case_id
        assert case["plan_kind"] in {"fail_closed", "deny"}, case_id


def test_fail_closed_matrix_is_linked_from_readiness_test_runner_and_docs():
    root = Path(__file__).resolve().parents[2]
    report = _report(execute=True)

    assert report["summary"] == {
        "status": "BLOCKED",
        "current_real_router_legacy_only": True,
        "future_matrix_case_count": 12,
        "future_matrix_fail_closed_or_denied_case_count": 8,
        "future_matrix_runtime_wired": False,
        "runtime_wiring_changed": False,
        "approval_claimed": False,
    }

    external = _load_module(root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").build_report(execute=True)
    runtime = _load_module(root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").build_report(execute=True)
    assert external["real_router_fail_closed_matrix_proof"]["service"] == (
        "backend/scripts/p1_3_v3_real_router_fail_closed_matrix.py"
    )
    assert external["summary"]["real_router_fail_closed_matrix_proof_present"] is True
    assert "real_router_fail_closed_matrix_proof" in runtime["existing_local_proof_artifacts"]

    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    assert "test_p1_3_v3_real_router_fail_closed_matrix.py" in test_sh
    assert "p1_3_v3_real_router_fail_closed_matrix.py" in ticket_doc
    assert "p1_3_v3_real_router_fail_closed_matrix.py" in oracle_doc
