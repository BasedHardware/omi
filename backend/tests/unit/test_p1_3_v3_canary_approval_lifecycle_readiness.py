import importlib.util
import json
import re
from pathlib import Path

SCRIPT_NAME = "p1_3_v3_canary_approval_lifecycle_readiness.py"
EXPECTED_ROUTE_SCOPE = "GET /v3/memories"
EXPECTED_EVIDENCE_IDS = [
    "human_ops_approval_ticket_present",
    "bounded_owner_groups_and_approver_role_present",
    "issued_approved_expires_rotation_window_valid",
    "rollback_owner_and_steps_present",
    "monitoring_gate_ids_present",
    "production_read_proof_reference_present",
    "iam_emulator_proof_reference_present",
    "telemetry_runbook_reference_present",
    "explicit_route_scope_matches_get_v3_memories",
]
EXPECTED_FAILURE_STATES = [
    "approval_evidence_missing",
    "approval_evidence_stale_or_unrotated",
    "rollback_owner_or_steps_missing",
    "monitoring_gates_missing",
    "production_read_proof_missing",
    "iam_emulator_proof_missing",
    "route_scope_mismatch",
]
FORBIDDEN_EVIDENCE_FRAGMENTS = {
    "uid",
    "user_id",
    "session_id",
    "memory_id",
    "cursor",
    "cursor_token",
    "payload",
    "request_payload",
    "raw_memory",
    "memory_content",
    "transcript",
    "secret",
    "token",
}


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_canary_approval_lifecycle_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / SCRIPT_NAME)


def _report(execute=False):
    return _module().build_report(execute=execute)


def test_canary_approval_lifecycle_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / SCRIPT_NAME
    assert script_path.exists(), "missing safe canary approval lifecycle/evidence-bundle readiness runner"

    report = _report(execute=False)

    assert report["artifact"] == "v17_p1_3_v3_canary_approval_lifecycle_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
    assert report["execute"] is False
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["routers_memories_modified"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["telemetry_sink_calls_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False


def test_lifecycle_contract_defines_required_metadata_only_evidence_bundle():
    report = _report(execute=True)

    contract = report["approval_lifecycle_contract"]
    assert contract["route_scope"] == EXPECTED_ROUTE_SCOPE
    assert contract["artifact_source"] == "firestore:system/v17_v3_canary_approvals/routes/get_v3_memories"
    assert contract["evidence_bundle_required_before_production_use"] is True
    assert contract["approval_ids_and_timestamps_are_metadata_only"] is True
    assert contract["max_lifetime_hours"] == 24
    assert contract["rotation_required_before_expires_at"] is True
    assert contract["explicit_route_scope_required"] is True
    assert contract["runtime_wired_to_v3_get"] is False
    assert contract["production_rollout_approved"] is False
    assert contract["approval_claimed"] is False

    assert contract["owner_groups"] == ["product_privacy_ops", "memory_platform_oncall"]
    assert contract["approver_roles"] == ["product_privacy_ops"]
    assert contract["rollback_owner_groups"] == ["memory_platform_oncall", "product_privacy_ops"]
    assert contract["monitoring_gate_ids"] == [
        "fail_closed_rate",
        "p95_latency_ms",
        "error_rate",
        "projection_freshness_seconds",
    ]

    required = {item["evidence_id"]: item for item in report["required_evidence_bundle"]}
    assert list(required) == EXPECTED_EVIDENCE_IDS
    assert required["human_ops_approval_ticket_present"]["required_fields"] == ["approval_ticket_id", "approval_id"]
    assert required["bounded_owner_groups_and_approver_role_present"]["required_fields"] == [
        "owner_group",
        "approver_role",
    ]
    assert required["issued_approved_expires_rotation_window_valid"]["required_fields"] == [
        "issued_at",
        "approved_at",
        "expires_at",
    ]
    assert required["rollback_owner_and_steps_present"]["required_fields"] == ["rollback_owner", "rollback_steps"]
    assert required["monitoring_gate_ids_present"]["required_fields"] == ["monitoring_gate_ids"]
    assert required["production_read_proof_reference_present"]["reference"] == (
        "backend/scripts/p1_3_v3_canary_approval_production_readiness.py"
    )
    assert required["iam_emulator_proof_reference_present"]["reference"] == (
        "backend/scripts/p1_3_v3_canary_approval_source_readiness.py"
    )
    assert required["telemetry_runbook_reference_present"]["reference"] == (
        "backend/scripts/p1_3_v3_observability_approval_readiness.py"
    )
    assert required["explicit_route_scope_matches_get_v3_memories"]["expected_route_scope"] == EXPECTED_ROUTE_SCOPE


def test_lifecycle_fail_closed_semantics_inventory_missing_stale_route_and_proof_gaps():
    report = _report(execute=True)
    semantics = {item["state"]: item for item in report["fail_closed_semantics"]}

    assert list(semantics) == EXPECTED_FAILURE_STATES
    for state in EXPECTED_FAILURE_STATES:
        assert semantics[state]["future_route_behavior"] == "fail_closed_before_v17_read"
        assert semantics[state]["legacy_fallback_allowed"] is False
        assert semantics[state]["required_before_runtime_change"] is True
        assert semantics[state]["approval_claimed"] is False

    assert semantics["route_scope_mismatch"]["future_route_behavior"] == "fail_closed_before_v17_read"
    assert report["summary"]["fail_closed_semantics_count"] == len(EXPECTED_FAILURE_STATES)
    assert report["summary"]["blocked_required_evidence_count"] == len(EXPECTED_EVIDENCE_IDS)


def test_lifecycle_static_no_prod_calls_route_imports_telemetry_sink_or_pii_evidence_labels():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / SCRIPT_NAME
    script_text = script_path.read_text(encoding="utf-8")
    lowered = script_text.lower()

    assert "backend.routers" not in lowered
    assert "routers.memories" not in lowered
    assert "google.cloud" not in lowered
    assert "firebase" not in lowered
    assert "pinecone" not in lowered or "pinecone_calls_executed" in lowered
    assert "posthog" not in lowered
    assert "prometheus" not in lowered
    assert "requests." not in lowered
    assert "httpx" not in lowered
    assert "telemetry" not in lowered or "telemetry_sink_calls_executed" in lowered
    for pattern in [
        r"\.set\s*\(",
        r"\.update\s*\(",
        r"\.delete\s*\(",
        r"\.create\s*\(",
        r"\.commit\s*\(",
        r"\.add\s*\(",
    ]:
        assert not re.search(pattern, script_text), f"forbidden mutating code path: {pattern}"

    report = _report(execute=True)
    evidence_json = json.dumps(
        {
            "contract": report["approval_lifecycle_contract"],
            "required_evidence_bundle": report["required_evidence_bundle"],
            "fail_closed_semantics": report["fail_closed_semantics"],
        },
        sort_keys=True,
    ).lower()
    for fragment in FORBIDDEN_EVIDENCE_FRAGMENTS:
        assert fragment not in evidence_json


def test_lifecycle_readiness_links_into_ci_docs_and_parent_readiness():
    decoded = json.loads(json.dumps(_report(execute=True), sort_keys=True))
    assert decoded["summary"] == {
        "status": "BLOCKED",
        "proof_status": "BLOCKED",
        "required_evidence_count": 9,
        "blocked_required_evidence_count": 9,
        "fail_closed_semantics_count": 7,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "route_scope": EXPECTED_ROUTE_SCOPE,
    }

    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    source_readiness = (root / "scripts" / "p1_3_v3_canary_approval_source_readiness.py").read_text(
        encoding="utf-8"
    )
    production_readiness = (root / "scripts" / "p1_3_v3_canary_approval_production_readiness.py").read_text(
        encoding="utf-8"
    )
    observability = (root / "scripts" / "p1_3_v3_observability_approval_readiness.py").read_text(encoding="utf-8")
    runtime = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")

    assert "test_p1_3_v3_canary_approval_lifecycle_readiness.py" in test_sh
    assert "canary_approval_lifecycle_readiness_proof" in source_readiness
    assert "canary_approval_lifecycle_readiness_proof" in production_readiness
    assert "canary_approval_lifecycle_readiness_proof" in observability
    assert "canary_approval_lifecycle_readiness_proof" in runtime
    assert "canary_approval_lifecycle_readiness_proof" in external
    assert SCRIPT_NAME in ticket_doc
    assert "canary approval lifecycle/evidence-bundle readiness" in ticket_doc
    assert SCRIPT_NAME in oracle_doc
    assert "canary approval lifecycle/evidence-bundle readiness" in oracle_doc
