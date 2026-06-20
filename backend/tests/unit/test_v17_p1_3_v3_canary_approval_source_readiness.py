import importlib.util
import json
from pathlib import Path

EXPECTED_OWNER_GROUPS = ["product_privacy_ops", "memory_platform_oncall"]
EXPECTED_REQUIRED_PROOF_IDS = [
    "artifact_source_selected_server_owned_only",
    "static_firestore_rules_emulator_harness_ready",
    "direct_client_read_write_denied_or_emulator_required",
    "backend_service_principal_read_required",
    "artifact_path_has_no_user_request_or_secret_dimensions",
    "production_artifact_source_missing_not_run",
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_canary_approval_source_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=False):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_canary_approval_source_readiness.py")
    return module.build_report(execute=execute)


def test_canary_approval_source_readiness_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "v17_p1_3_v3_canary_approval_source_readiness.py"
    assert script_path.exists(), "missing safe canary approval artifact source-selection readiness runner"

    report = _report(execute=False)

    assert report["artifact"] == "v17_p1_3_v3_canary_approval_source_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["routers_memories_modified"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False
    assert report["execute"] is False


def test_canary_approval_source_contract_pins_server_owned_path_owners_and_route_scope():
    report = _report(execute=True)

    assert report["proof_status"] == "BLOCKED"
    contract = report["source_selection_contract"]
    assert contract["route_scope"] == "GET /v3/memories"
    assert contract["future_artifact_source"] == "firestore:system/v17_v3_canary_approvals/routes/get_v3_memories"
    assert contract["server_owned_only"] is True
    assert contract["client_supplied_artifact_trusted"] is False
    assert contract["bounded_owner_groups"] == EXPECTED_OWNER_GROUPS
    assert contract["approval_ids_and_timestamps_are_metadata_only"] is True
    assert contract["production_approval_claimed"] is False
    assert contract["production_artifact_source_status"] == "MISSING_NOT_RUN"
    assert contract["runtime_wired_to_v3_get"] is False

    forbidden = {"uid", "session", "memory", "cursor", "token", "secret", "request", "payload"}
    source_lower = contract["future_artifact_source"].lower()
    assert all(fragment not in source_lower for fragment in forbidden)

    static_proof = report["static_iam_rules_emulator_readiness_proof"]
    assert static_proof["artifact_document_path"] == "system/v17_v3_canary_approvals/routes/get_v3_memories"
    assert static_proof["route_scope"] == "GET /v3/memories"
    assert static_proof["status"] == "STATIC_RULES_EMULATOR_HARNESS_READY_RUNTIME_BLOCKED"
    assert static_proof["direct_signed_in_client_read_denied"] is True
    assert static_proof["direct_signed_in_client_create_update_delete_denied"] is True
    assert static_proof["backend_admin_or_service_principal_read_required"] is True
    assert static_proof["backend_admin_or_service_principal_read_static_contract_present"] is True
    assert static_proof["client_supplied_artifact_trusted"] is False
    assert static_proof["production_firestore_read_executed"] is False
    assert static_proof["emulator_command"] == "npm run test:v17-v3-canary-approval-source:emulator"


def test_canary_approval_source_contract_requires_iam_rules_privacy_readiness_before_wiring():
    report = _report(execute=True)
    rules = {rule["proof_id"]: rule for rule in report["required_iam_rules_privacy_proofs"]}

    assert list(rules) == EXPECTED_REQUIRED_PROOF_IDS
    assert rules["artifact_source_selected_server_owned_only"]["status"] == "BLOCKED"
    assert rules["artifact_source_selected_server_owned_only"]["server_owned_only"] is True
    assert rules["artifact_source_selected_server_owned_only"]["client_supplied_artifact_trusted"] is False

    static_rules = rules["static_firestore_rules_emulator_harness_ready"]
    assert static_rules["status"] == "READY_FOR_LOCAL_EMULATOR"
    assert static_rules["firestore_rules_path"] == "firestore.rules"
    assert static_rules["rules_emulator_test"] == "backend/scripts/v17_firestore_rules_emulator_test.mjs"
    assert static_rules["direct_signed_in_client_read_denied_static"] is True
    assert static_rules["direct_signed_in_client_write_denied_static"] is True
    assert static_rules["backend_admin_read_harness_present"] is True
    assert static_rules["production_firestore_read_executed"] is False

    direct = rules["direct_client_read_write_denied_or_emulator_required"]
    assert direct["status"] == "READY_FOR_LOCAL_EMULATOR"
    assert direct["direct_client_read_allowed"] is False
    assert direct["direct_client_write_allowed"] is False
    assert direct["local_emulator_or_iam_evidence_required"] is True
    assert direct["static_rules_denial_contract_present"] is True
    assert direct["local_emulator_or_iam_evidence_present"] is True

    backend = rules["backend_service_principal_read_required"]
    assert backend["status"] == "BLOCKED"
    assert backend["backend_service_principal_read_required"] is True
    assert backend["backend_service_principal_read_static_contract_present"] is True
    assert backend["backend_service_principal_read_proven"] is False

    path = rules["artifact_path_has_no_user_request_or_secret_dimensions"]
    assert path["status"] == "READY_FOR_CONTRACT"
    assert path["artifact_path_contains_uid_session_memory_cursor_token_secret_or_payload"] is False
    assert path["high_cardinality_labels_allowed"] is False

    missing = rules["production_artifact_source_missing_not_run"]
    assert missing["status"] == "BLOCKED"
    assert missing["production_artifact_source_exists"] is False
    assert missing["production_artifact_source_read"] is False
    assert missing["approval_claimed"] is False


def test_canary_approval_source_failure_semantics_and_non_claims_are_fail_closed():
    report = _report(execute=True)

    semantics = {item["state"]: item for item in report["failure_semantics"]}
    assert semantics["source_missing"]["future_route_behavior"] == "fail_closed_before_v17_read"
    assert semantics["iam_denied_or_timeout"]["future_route_behavior"] == "fail_closed_before_v17_read"
    assert (
        semantics["client_supplied_artifact_present"]["future_route_behavior"]
        == "ignore_and_fail_closed_if_server_source_unavailable"
    )
    assert (
        semantics["path_or_artifact_contains_sensitive_dimensions"]["future_route_behavior"]
        == "reject_contract_and_do_not_wire"
    )
    assert all(item["legacy_fallback_allowed"] is False for item in semantics.values())

    non_claims = "\n".join(report["non_claims"])
    assert "No runtime /v3 behavior changed." in non_claims
    assert "No production rollout approval claimed." in non_claims
    assert "No production Firestore/cloud/provider/vector/network calls executed." in non_claims
    assert "No telemetry sink production call executed or claimed." in non_claims


def test_canary_approval_source_readiness_json_summary_and_parent_links_are_stable():
    decoded = json.loads(json.dumps(_report(execute=True), sort_keys=True))

    assert decoded["summary"] == {
        "status": "BLOCKED",
        "proof_status": "BLOCKED",
        "required_iam_rules_privacy_proof_count": 6,
        "blocked_required_proof_count": 3,
        "failure_semantics_count": 5,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "approval_claimed": False,
        "production_artifact_source_exists": False,
        "backend_service_principal_read_proven": False,
        "direct_client_access_proven_denied": True,
        "static_iam_rules_emulator_readiness_present": True,
    }

    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    observability_readiness = (root / "scripts" / "v17_p1_3_v3_observability_approval_readiness.py").read_text(
        encoding="utf-8"
    )
    runtime_readiness = (root / "scripts" / "v17_p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external_readiness = (root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py").read_text(
        encoding="utf-8"
    )
    rules_emulator_test = (root.parent / "backend" / "scripts" / "v17_firestore_rules_emulator_test.mjs").read_text(
        encoding="utf-8"
    )
    package_json = (root.parent / "package.json").read_text(encoding="utf-8")

    assert "test_v17_p1_3_v3_canary_approval_source_readiness.py" in test_sh
    assert "v17_p1_3_v3_canary_approval_source_readiness.py" in ticket_doc
    assert "canary/approval artifact source-selection and ownership/IAM readiness" in ticket_doc
    assert "v17_p1_3_v3_canary_approval_source_readiness.py" in oracle_doc
    assert "canary/approval artifact source-selection and ownership/IAM readiness" in oracle_doc
    assert "canary_approval_source_readiness_proof" in observability_readiness
    assert "canary_approval_source_readiness_proof" in runtime_readiness
    assert "canary_approval_source_readiness_proof" in external_readiness
    assert "assertClientDeniedForV3CanaryApprovalSource" in rules_emulator_test
    assert "assertAdminCanReadV3CanaryApprovalSource" in rules_emulator_test
    assert "test:v17-v3-canary-approval-source:emulator" in package_json
