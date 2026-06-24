import importlib.util
import json
from pathlib import Path

REQUIRED_REQUIREMENT_IDS = [
    "canonical_control_source_path_api",
    "server_owned_control_reads_only",
    "fake_injectable_control_reader_interface",
    "fail_closed_decision_matrix",
    "non_enrolled_legacy_path_preservation",
    "enrolled_no_legacy_fallback_on_gate_failure",
    "proof_chain_dependencies",
    "real_evidence_blockers",
]

REQUIRED_FAIL_CLOSED_REASONS = [
    "missing_control_doc",
    "control_read_failed",
    "malformed_control_doc",
    "uid_mismatch",
    "unsupported_control_schema",
    "global_read_gate_closed",
    "stale_generation",
    "no_default_memory_grant",
    "projection_not_ready",
    "write_convergence_not_ready",
    "invalid_or_missing_cursor_secret",
    "archive_not_allowed",
]

REQUIRED_PROOF_KEYS = {
    "decision_service_proof",
    "cursor_service_proof",
    "projection_readiness_proof",
    "memory_read_service_proof",
    "write_convergence_proof",
    "response_adapter_proof",
    "request_adapter_proof",
    "route_planner_proof",
    "fastapi_route_contract_proof",
    "get_dependency_auth_readiness_proof",
    "projection_store_readiness_proof",
    "control_reader_contract_proof",
    "control_reader_emulator_readiness_proof",
    "get_runtime_wiring_readiness_proof",
}


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("p1_3_v3_control_reader_readiness", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=False):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_control_reader_readiness.py")
    return module.build_report(execute=execute)


def test_control_reader_readiness_runner_exists_and_is_safe_by_default():
    report = _report(execute=False)

    assert report["artifact"] == "p1_3_v3_control_reader_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] in {"NOT_RUN", "BLOCKED"}
    assert report["execute"] is False
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["production_control_reader_implemented"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["cloud_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["pinecone_calls_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False


def test_control_reader_readiness_inventories_exact_requirements():
    report = _report(execute=True)

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "BLOCKED"
    requirements = {item["requirement_id"]: item for item in report["control_reader_requirements"]}
    assert list(requirements) == REQUIRED_REQUIREMENT_IDS

    for requirement_id, requirement in requirements.items():
        assert requirement["status"] in {"BLOCKED", "READY_LOCAL_ADAPTER_PROVEN"}, requirement_id
        assert requirement["required_before_runtime_change"] is True
        assert requirement["runtime_wired"] is False
        assert requirement["approval_claimed"] is False
        if requirement_id == "canonical_control_source_path_api":
            assert requirement["missing_real_firestore_api_emulator_rules_iam_evidence"] is False
        else:
            assert requirement["missing_real_firestore_api_emulator_rules_iam_evidence"] is True
        assert requirement["evidence_sources"], requirement_id

    assert requirements["canonical_control_source_path_api"]["canonical_path"] == "users/{uid}/memory_control/state"
    assert requirements["canonical_control_source_path_api"]["explicit_blocker"] is None
    assert requirements["canonical_control_source_path_api"]["candidate_paths"] == ["users/{uid}/memory_control/state"]
    assert requirements["server_owned_control_reads_only"]["direct_client_control_reads_allowed"] is False
    assert requirements["fake_injectable_control_reader_interface"]["runtime_route_wiring_now"] is False
    assert requirements["fail_closed_decision_matrix"]["fail_closed_reasons"] == REQUIRED_FAIL_CLOSED_REASONS
    assert (
        requirements["non_enrolled_legacy_path_preservation"]["offset_zero_limit_5000_preserved_for_legacy_only"]
        is True
    )
    assert (
        requirements["enrolled_no_legacy_fallback_on_gate_failure"][
            "legacy_fallback_allowed_for_enrolled_gate_failures"
        ]
        is False
    )


def test_control_reader_readiness_defines_fake_injectable_interface_without_route_wiring():
    report = _report(execute=True)
    interface = report["fake_injectable_control_reader_interface"]

    assert interface == {
        "interface_name": "V3ControlReader",
        "method": "read_v3_control",
        "input_fields": ["uid", "db_client", "rollout_config", "consumer"],
        "output_fields": [
            "cohort_enrolled",
            "source_path",
            "uid",
            "schema_version",
            "configured_mode",
            "persisted_mode",
            "effective_mode",
            "mode_epoch",
            "cutover_epoch",
            "default_memory_grant",
            "account_generation",
            "projection_ready",
            "rollout_write_ready",
            "global_read_gate_open",
            "write_convergence_ready",
            "archive_allowed",
            "decision",
            "fail_closed_reason",
        ],
        "fake_injectable": True,
        "production_firestore_reader_implemented": True,
        "canonical_source_path": "users/{uid}/memory_control/state",
        "runtime_route_wiring_now": False,
    }


def test_control_reader_readiness_pins_fail_closed_semantics_and_legacy_boundaries():
    report = _report(execute=True)
    matrix = {item["reason"]: item for item in report["fail_closed_decision_matrix"]}

    assert list(matrix) == REQUIRED_FAIL_CLOSED_REASONS
    for reason, entry in matrix.items():
        assert entry["enrolled_decision"] in {"FAIL_CLOSED", "DENY", "HIDE"}, reason
        assert entry["legacy_fallback_allowed"] is False
        assert entry["required_before_runtime_change"] is True

    assert matrix["no_default_memory_grant"]["http_status"] == 403
    assert matrix["archive_not_allowed"]["archive_default_available"] is False

    legacy = report["legacy_boundary_contract"]
    assert legacy["non_enrolled_read_path"] == "legacy_primary"
    assert legacy["non_enrolled_offset_zero_limit_5000_preserved"] is True
    assert legacy["enrolled_gate_failure_legacy_fallback_allowed"] is False
    assert legacy["legacy_memory_result_merge_allowed"] is False


def test_control_reader_readiness_links_required_local_proofs_and_marks_real_evidence_missing():
    report = _report(execute=True)
    proofs = report["existing_local_proof_artifacts"]

    assert set(proofs) == REQUIRED_PROOF_KEYS
    for proof in proofs.values():
        assert proof["runtime_wired"] is False
        assert proof["production_rollout_approved"] is False
        assert proof["external_calls"] == []
        assert proof["missing_real_firestore_api_emulator_rules_iam_evidence"] is True

    assert proofs["projection_store_readiness_proof"]["service"] == (
        "backend/scripts/p1_3_v3_projection_store_readiness.py"
    )
    assert proofs["get_runtime_wiring_readiness_proof"]["service"] == (
        "backend/scripts/p1_3_v3_get_runtime_wiring_readiness.py"
    )
    assert proofs["get_dependency_auth_readiness_proof"]["service"] == (
        "backend/scripts/p1_3_v3_get_dependency_auth_readiness.py"
    )


def test_control_reader_readiness_records_safe_next_steps_and_non_claims():
    report = _report(execute=True)

    assert [step["step_id"] for step in report["proposed_next_safe_steps"]] == [
        "choose_canonical_control_source_and_security_contract",
        "add_fake_control_reader_contract_tests",
        "add_firestore_emulator_control_reader_proof",
        "prove_security_rules_and_iam_no_client_control_reads",
        "wire_route_only_after_all_control_projection_write_cursor_gates_pass",
    ]
    assert all(step["implements_runtime_wiring_now"] is False for step in report["proposed_next_safe_steps"])
    assert "No production server-side control reader implemented." in report["non_claims"]
    assert "No real Firestore/API/emulator/security rules/IAM evidence collected." in report["non_claims"]
    assert "No `/v3` route wiring changed." in report["non_claims"]


def test_control_reader_readiness_json_summary_is_stable():
    decoded = json.loads(json.dumps(_report(execute=True), sort_keys=True))

    assert decoded["summary"] == {
        "status": "BLOCKED",
        "proof_status": "BLOCKED",
        "requirement_count": 8,
        "blocked_requirement_count": 7,
        "fail_closed_reason_count": 12,
        "existing_local_proof_count": 14,
        "missing_real_evidence_requirement_count": 7,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "production_control_reader_implemented": False,
        "approval_claimed": False,
        "safe_next_step_count": 5,
        "control_reader_contract_proof_present": True,
    }


def test_control_reader_readiness_is_registered_in_test_runner_docs_and_parent_readiness():
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    runtime_readiness = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external_readiness = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")

    assert "test_p1_3_v3_control_reader_readiness.py" in test_sh
    assert "p1_3_v3_control_reader_readiness.py" in ticket_doc
    assert "control reader readiness" in ticket_doc
    assert "p1_3_v3_control_reader_readiness.py" in oracle_doc
    assert "control reader readiness" in oracle_doc
    assert "control_reader_readiness_proof" in runtime_readiness
    assert "control_reader_readiness_proof" in external_readiness
