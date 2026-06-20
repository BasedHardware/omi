import importlib.util
import json
from pathlib import Path

REQUIRED_SCHEMA_FIELDS = [
    "uid",
    "schema_version",
    "mode",
    "mode_epoch",
    "cutover_epoch",
    "account_generation",
    "fallback_projection_ready",
    "persistent_v17_writes_started",
    "writes_blocked",
    "stage_gates",
    "grants",
]

REQUIRED_PROOF_CASES = [
    "non_enrolled_legacy_allowed",
    "v17_projection_allowed",
    "missing_control_doc",
    "stale_generation",
    "no_default_memory_grant",
    "projection_not_ready",
    "write_convergence_not_ready",
    "invalid_or_missing_cursor_secret",
    "archive_not_allowed",
]

REQUIRED_LINKED_PROOFS = {
    "control_reader_contract_proof",
    "control_reader_readiness_proof",
    "get_runtime_wiring_readiness_proof",
    "get_dependency_auth_readiness_proof",
}


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_control_reader_emulator_readiness", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(*, execute=False, env=None):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_control_reader_emulator_readiness.py")
    return module.build_report(execute=execute, env={} if env is None else env)


def test_control_reader_emulator_readiness_is_safe_by_default_and_does_not_execute_services():
    report = _report(execute=False)

    assert report["artifact"] == "v17_p1_3_v3_control_reader_emulator_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
    assert report["execute"] is False
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["production_control_reader_implemented"] is False
    assert report["approval_claimed"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["cloud_calls_executed"] is False
    assert report["firestore_cloud_reads_executed"] is False
    assert report["firestore_cloud_writes_executed"] is False
    assert report["firestore_emulator_started"] is False
    assert report["firestore_emulator_reads_executed"] is False
    assert report["firestore_emulator_writes_executed"] is False


def test_control_reader_emulator_readiness_inventories_local_emulator_harness_without_starting_it():
    report = _report(execute=True, env={"FIRESTORE_EMULATOR_HOST": "127.0.0.1:8085"})
    inventory = report["local_emulator_harness_inventory"]

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] in {"BLOCKED", "NOT_RUN"}
    assert inventory["firebase_json_present"] is True
    assert inventory["firestore_rules_present"] is True
    assert inventory["firestore_emulator_configured"] is True
    assert inventory["firestore_emulator_port"] == 8085
    assert inventory["rules_emulator_harness_present"] is True
    assert inventory["control_reader_emulator_harness_present"] is False
    assert inventory["firestore_emulator_host_env_present"] is True
    assert inventory["safe_detection_only_no_service_start"] is True


def test_control_reader_emulator_readiness_pins_prerequisites_and_fixture_schema():
    report = _report(execute=True)
    prerequisites = {item["prerequisite_id"]: item for item in report["emulator_api_proof_prerequisites"]}

    assert list(prerequisites) == [
        "canonical_server_control_source_path_api",
        "firestore_emulator_config_and_cli",
        "control_reader_fixture_schema",
        "api_backed_server_reader_harness",
        "security_rules_and_iam_evidence_separation",
    ]
    assert prerequisites["canonical_server_control_source_path_api"]["status"] == "READY_LOCAL_ADAPTER_PROVEN"
    assert prerequisites["canonical_server_control_source_path_api"]["explicit_blocker"] is None
    assert (
        prerequisites["canonical_server_control_source_path_api"]["canonical_path"]
        == "users/{uid}/memory_control/state"
    )
    assert prerequisites["control_reader_fixture_schema"]["required_fields"] == REQUIRED_SCHEMA_FIELDS
    assert prerequisites["firestore_emulator_config_and_cli"]["requires_firestore_emulator_host"] is True
    assert prerequisites["api_backed_server_reader_harness"]["must_not_start_cloud_services"] is True
    assert prerequisites["security_rules_and_iam_evidence_separation"]["rules_static_proof_is_not_iam_proof"] is True


def test_control_reader_emulator_readiness_requires_security_iam_evidence_no_client_control_reads():
    report = _report(execute=True)
    evidence = {item["evidence_id"]: item for item in report["security_iam_evidence_requirements"]}

    assert list(evidence) == [
        "no_direct_client_control_reads_rules_static",
        "no_direct_client_control_reads_emulator",
        "server_principal_control_read_allowed_iam",
        "rules_static_emulator_iam_proof_separation",
    ]
    assert evidence["no_direct_client_control_reads_rules_static"]["direct_client_control_reads_allowed"] is False
    assert evidence["no_direct_client_control_reads_emulator"]["required_emulator_case"] == (
        "signed-in client getDoc(users/{uid}/memory_control/state) is denied"
    )
    assert evidence["server_principal_control_read_allowed_iam"]["cloud_credentials_required_now"] is False
    assert evidence["server_principal_control_read_allowed_iam"]["status"] == "BLOCKED"
    assert evidence["rules_static_emulator_iam_proof_separation"]["emulator_rules_proof_is_not_cloud_iam"] is True


def test_control_reader_emulator_readiness_maps_contract_decision_cases_and_boundaries():
    report = _report(execute=True)
    cases = {item["case_id"]: item for item in report["required_contract_proof_cases"]}

    assert list(cases) == REQUIRED_PROOF_CASES
    assert cases["non_enrolled_legacy_allowed"]["expected_route_family"] == "legacy_primary"
    assert cases["non_enrolled_legacy_allowed"]["legacy_fallback_allowed"] is True
    assert cases["v17_projection_allowed"]["expected_route_family"] == "v17_projection"
    assert cases["v17_projection_allowed"]["legacy_fallback_allowed"] is False
    for case_id in REQUIRED_PROOF_CASES[2:]:
        assert cases[case_id]["expected_route_family"] == "fail_closed", case_id
        assert cases[case_id]["legacy_fallback_allowed"] is False, case_id
    assert report["legacy_boundary_contract"]["enrolled_no_legacy_fallback_on_gate_failure"] is True
    assert report["legacy_boundary_contract"]["stale_short_term_control_state_absent"] is True
    assert report["legacy_boundary_contract"]["archive_default_available"] is False


def test_control_reader_emulator_readiness_links_readiness_chain_docs_and_summary():
    report = _report(execute=True)
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    control_readiness = (root / "scripts" / "v17_p1_3_v3_control_reader_readiness.py").read_text(encoding="utf-8")
    runtime_readiness = (root / "scripts" / "v17_p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external_readiness = (root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py").read_text(
        encoding="utf-8"
    )

    assert set(report["linked_readiness_proofs"]) == REQUIRED_LINKED_PROOFS
    assert "test_v17_p1_3_v3_control_reader_emulator_readiness.py" in test_sh
    assert "v17_p1_3_v3_control_reader_emulator_readiness.py" in ticket_doc
    assert "Firestore-emulator/security control reader readiness" in ticket_doc
    assert "v17_p1_3_v3_control_reader_emulator_readiness.py" in oracle_doc
    assert "Firestore-emulator/security control reader readiness" in oracle_doc
    assert "control_reader_emulator_readiness_proof" in control_readiness
    assert "control_reader_emulator_readiness_proof" in runtime_readiness
    assert "control_reader_emulator_readiness_proof" in external_readiness

    assert json.loads(json.dumps(report["summary"], sort_keys=True)) == {
        "status": "BLOCKED",
        "proof_status": "BLOCKED",
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "production_control_reader_implemented": False,
        "approval_claimed": False,
        "prerequisite_count": 5,
        "blocked_prerequisite_count": 4,
        "fixture_schema_field_count": 11,
        "required_contract_case_count": 9,
        "security_iam_evidence_requirement_count": 4,
        "linked_readiness_proof_count": 4,
        "control_reader_emulator_harness_present": False,
        "firestore_emulator_host_env_present": False,
    }
