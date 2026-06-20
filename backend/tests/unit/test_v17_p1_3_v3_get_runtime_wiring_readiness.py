import importlib.util
import json
from pathlib import Path

REQUIRED_GATE_IDS = [
    "real_v17_control_read_fail_closed",
    "real_trusted_account_generation_source",
    "real_v17_compatibility_projection_read_api_store",
    "real_external_write_convergence_source_of_truth",
    "real_cursor_secret_validation_integration",
    "real_route_dependency_auth_rate_limit_testclient",
    "non_enrolled_legacy_backward_compatibility",
    "enrolled_fail_closed_no_fallback_states",
    "archive_unavailable_short_term_not_default_visible",
    "observability_telemetry_and_approval",
]

REQUIRED_EXISTING_PROOF_KEYS = {
    "decision_service_proof",
    "cursor_service_proof",
    "projection_readiness_proof",
    "memory_read_service_proof",
    "write_convergence_proof",
    "response_adapter_proof",
    "request_adapter_proof",
    "route_planner_proof",
    "route_signature_integration_proof",
    "fastapi_route_contract_proof",
    "real_router_dependency_map_proof",
    "real_router_get_testclient_proof",
    "get_dependency_auth_readiness_proof",
    "route_dependency_contract_readiness_proof",
    "get_dependency_seam_readiness_proof",
    "projection_store_readiness_proof",
    "projection_read_source_readiness_proof",
    "projection_write_convergence_readiness_proof",
    "archive_short_term_visibility_readiness_proof",
    "control_reader_readiness_proof",
    "control_reader_contract_proof",
    "control_reader_emulator_readiness_proof",
    "account_generation_readiness_proof",
    "real_router_fail_closed_matrix_proof",
    "write_convergence_tombstone_matrix_proof",
    "cursor_secret_readiness_proof",
    "cursor_secret_production_readiness_proof",
    "runtime_config_source_readiness_proof",
    "observability_approval_readiness_proof",
    "canary_approval_source_readiness_proof",
    "canary_approval_production_readiness_proof",
    "canary_approval_lifecycle_readiness_proof",
    "canary_approval_aggregate_readiness_proof",
}


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_get_runtime_wiring_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=False):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_get_runtime_wiring_readiness.py")
    return module.build_report(execute=execute)


def test_get_runtime_wiring_readiness_runner_exists_and_is_safe_by_default():
    report = _report(execute=False)

    assert report["artifact"] == "v17_p1_3_v3_get_runtime_wiring_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] in {"NOT_RUN", "BLOCKED"}
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["route_wiring"] is True
    assert report["runtime_wiring_changed"] is True
    assert report["effective_runtime_behavior_changed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False
    assert report["execute"] is False


def test_get_runtime_wiring_readiness_inventories_exact_remaining_gates():
    report = _report(execute=True)

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "BLOCKED"
    gates = {gate["gate_id"]: gate for gate in report["remaining_gates"]}
    assert list(gates) == REQUIRED_GATE_IDS
    for gate_id, gate in gates.items():
        assert gate["status"] == "BLOCKED"
        assert gate["approval_claimed"] is False
        assert gate["runtime_wired"] is False
        assert gate["missing_real_service_runtime_evidence"] is True
        assert gate["required_before_runtime_change"] is True
        assert gate["route_refs"] == ["GET /v3/memories"]
        assert gate["existing_local_proofs"], gate_id
        assert set(gate["existing_local_proofs"]).issubset(REQUIRED_EXISTING_PROOF_KEYS)

    assert "server-side" in gates["real_v17_control_read_fail_closed"]["required_evidence"]
    assert "without client-side direct control reads" in gates["real_v17_control_read_fail_closed"]["required_evidence"]
    assert "expected_account_generation" in gates["real_trusted_account_generation_source"]["required_evidence"]
    assert (
        "trusted == control == projection == cursor"
        in gates["real_trusted_account_generation_source"]["required_evidence"]
    )
    assert "MemoryDB-compatible" in gates["real_v17_compatibility_projection_read_api_store"]["required_evidence"]
    assert "empty projection state" in gates["real_v17_compatibility_projection_read_api_store"]["required_evidence"]
    assert "create/update/delete" in gates["real_external_write_convergence_source_of_truth"]["required_evidence"]
    assert "signing secret" in gates["real_cursor_secret_validation_integration"]["required_evidence"]
    assert "auth/rate-limit" in gates["real_route_dependency_auth_rate_limit_testclient"]["required_evidence"]
    assert "offset=0 -> limit=5000" in gates["non_enrolled_legacy_backward_compatibility"]["required_evidence"]
    assert "no legacy fallback" in gates["enrolled_fail_closed_no_fallback_states"]["required_evidence"]
    assert "stale Short-term" in gates["archive_unavailable_short_term_not_default_visible"]["required_evidence"]
    assert "approval" in gates["observability_telemetry_and_approval"]["required_evidence"]


def test_get_runtime_wiring_readiness_links_current_proofs_and_marks_runtime_evidence_missing():
    report = _report(execute=True)
    proofs = report["existing_local_proof_artifacts"]

    assert set(proofs) == REQUIRED_EXISTING_PROOF_KEYS
    assert (
        "legacy memories_db.get_memories"
        in proofs["real_router_get_testclient_proof"]["current_runtime_behavior_proven"]
    )
    assert proofs["real_router_get_testclient_proof"]["runtime_wired"] is False
    assert proofs["real_router_get_testclient_proof"]["missing_real_service_runtime_evidence"] is True
    assert proofs["get_dependency_auth_readiness_proof"]["controlled_testclient_under_stubs"] is True
    assert proofs["get_dependency_auth_readiness_proof"]["runtime_wired"] is False
    assert proofs["route_dependency_contract_readiness_proof"]["service"] == (
        "backend/scripts/v17_p1_3_v3_route_dependency_contract_readiness.py"
    )
    assert proofs["route_dependency_contract_readiness_proof"]["runtime_wired"] is False
    assert proofs["projection_store_readiness_proof"]["service"] == (
        "backend/scripts/v17_p1_3_v3_projection_store_readiness.py"
    )
    assert proofs["projection_store_readiness_proof"]["runtime_wired"] is False
    assert proofs["control_reader_readiness_proof"]["service"] == (
        "backend/scripts/v17_p1_3_v3_control_reader_readiness.py"
    )
    assert proofs["control_reader_readiness_proof"]["runtime_wired"] is False
    assert proofs["account_generation_readiness_proof"]["service"] == (
        "backend/scripts/v17_p1_3_v3_account_generation_readiness.py"
    )
    assert proofs["account_generation_readiness_proof"]["runtime_wired"] is False
    assert proofs["real_router_dependency_map_proof"]["imports_real_router_under_stubs"] is True
    assert proofs["route_planner_proof"]["runtime_wired"] is False
    assert proofs["memory_read_service_proof"]["runtime_wired"] is False
    assert proofs["cursor_service_proof"]["runtime_wired"] is False
    for proof in proofs.values():
        assert proof["external_calls"] == []
        assert proof["production_rollout_approved"] is False


def test_get_runtime_wiring_readiness_pins_safe_future_cutover_sequence_without_implementation():
    report = _report(execute=True)
    sequence = report["proposed_safe_cutover_sequence"]

    assert [step["step_id"] for step in sequence] == [
        "wire_server_side_control_reader",
        "wire_projection_store_read_api",
        "prove_write_convergence_source_of_truth",
        "configure_cursor_secret_and_validation",
        "add_route_dependency_testclient_proofs",
        "wire_get_route_behind_fail_closed_planner",
        "observe_shadow_then_canary",
        "approval_gate_before_rollout",
    ]
    assert all(step["implements_runtime_wiring_now"] is False for step in sequence)
    assert sequence[5]["must_preserve"] == [
        "non_enrolled_legacy_primary_current_limit_offset_behavior",
        "offset_zero_limit_5000_only_for_legacy_primary",
        "enrolled_fail_closed_no_legacy_fallback",
        "archive_default_unavailable",
        "stale_short_term_not_default_visible",
    ]


def test_get_runtime_wiring_readiness_json_summary_is_stable():
    decoded = json.loads(json.dumps(_report(execute=True), sort_keys=True))

    assert decoded["summary"] == {
        "status": "BLOCKED",
        "proof_status": "BLOCKED",
        "remaining_gate_count": 10,
        "blocked_gate_count": 10,
        "existing_local_proof_count": 33,
        "missing_real_service_runtime_evidence_count": 10,
        "read_only": True,
        "mutation_allowed": False,
        "route_wiring": True,
        "runtime_wiring_changed": True,
        "effective_runtime_behavior_changed": False,
        "approval_claimed": False,
        "safe_cutover_step_count": 8,
    }


def test_get_runtime_wiring_readiness_is_registered_in_test_runner_and_docs():
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")

    assert "test_v17_p1_3_v3_get_runtime_wiring_readiness.py" in test_sh
    assert "test_v17_p1_3_v3_get_dependency_auth_readiness.py" in test_sh
    assert "test_v17_p1_3_v3_route_dependency_contract_readiness.py" in test_sh
    assert "test_v17_p1_3_v3_account_generation_readiness.py" in test_sh
    assert "test_v17_v3_account_generation_source.py" in test_sh
    assert "v17_p1_3_v3_get_runtime_wiring_readiness.py" in ticket_doc
    assert "v17_p1_3_v3_get_dependency_auth_readiness.py" in ticket_doc
    assert "v17_p1_3_v3_route_dependency_contract_readiness.py" in ticket_doc
    assert "v17_p1_3_v3_account_generation_readiness.py" in ticket_doc
    assert "GET runtime-wiring remaining-gates readiness" in ticket_doc
    assert "v17_p1_3_v3_get_runtime_wiring_readiness.py" in oracle_doc
    assert "v17_p1_3_v3_get_dependency_auth_readiness.py" in oracle_doc
    assert "v17_p1_3_v3_route_dependency_contract_readiness.py" in oracle_doc
    assert "v17_p1_3_v3_account_generation_readiness.py" in oracle_doc
    assert "GET runtime-wiring remaining-gates readiness" in oracle_doc
    assert "v17_p1_3_v3_get_runtime_wiring_readiness.py" in (
        root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py"
    ).read_text(encoding="utf-8")
