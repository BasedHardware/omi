import importlib.util
import json
import re
from pathlib import Path

SCRIPT_NAME = "v17_p1_3_v3_canary_approval_aggregate_readiness.py"
EXPECTED_ROUTE_SCOPE = "GET /v3/memories"
EXPECTED_GATE_IDS = [
    "local_schema_validator_present",
    "source_iam_emulator_client_deny_readiness_present",
    "production_read_proof_missing_not_run",
    "lifecycle_evidence_bundle_missing_blocked",
    "observability_telemetry_approval_blocked",
    "runtime_wiring_blocked",
    "external_compatibility_blocked",
]
EXPECTED_REMAINING_BLOCKERS = [
    "real_production_backend_service_principal_read_proof_missing",
    "production_artifact_existence_and_validity_missing",
    "human_approval_evidence_bundle_missing",
    "telemetry_sink_and_runbook_proof_missing",
    "runtime_route_wiring_gates_blocked",
]
FORBIDDEN_LABEL_FRAGMENTS = {
    "uid",
    "user_id",
    "session_id",
    "memory_id",
    "raw_memory",
    "memory_content",
    "transcript",
    "cursor_token",
    "secret",
    "token",
    "payload",
    "request_payload",
    "high_cardinality",
}


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_canary_approval_aggregate_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / SCRIPT_NAME)


def _report(execute=False):
    return _module().build_report(execute=execute)


def test_aggregate_runner_exists_and_is_no_go_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / SCRIPT_NAME
    assert script_path.exists(), "missing final local canary approval aggregate readiness runner"

    report = _report(execute=False)

    assert report["artifact"] == "v17_p1_3_v3_canary_approval_aggregate_readiness"
    assert report["status"] == "BLOCKED"
    assert report["decision"] == "NO_GO"
    assert report["proof_status"] == "NOT_RUN"
    assert report["execute"] is False
    assert report["route_scope"] == EXPECTED_ROUTE_SCOPE
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["route_wiring"] is True
    assert report["runtime_wiring_changed"] is True
    assert report["effective_runtime_behavior_changed"] is False
    assert report["routers_memories_modified"] is True
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["pinecone_calls_executed"] is False
    assert report["telemetry_sink_calls_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False


def test_aggregate_execute_remains_local_no_go_without_production_calls_or_route_wiring():
    report = _report(execute=True)

    assert report["status"] == "BLOCKED"
    assert report["decision"] == "NO_GO"
    assert report["proof_status"] == "BLOCKED"
    assert report["execute"] is True
    assert report["route_wiring"] is True
    assert report["runtime_wiring_changed"] is True
    assert report["effective_runtime_behavior_changed"] is False
    assert report["routers_memories_modified"] is True
    assert report["network_or_provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["telemetry_sink_calls_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False

    summary = report["summary"]
    assert summary == {
        "status": "BLOCKED",
        "decision": "NO_GO",
        "proof_status": "BLOCKED",
        "route_scope": EXPECTED_ROUTE_SCOPE,
        "gate_count": 7,
        "ready_gate_count": 2,
        "blocked_gate_count": 5,
        "remaining_blocker_count": 5,
        "route_wiring": True,
        "runtime_wiring_changed": True,
        "effective_runtime_behavior_changed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
    }


def test_aggregate_gate_rows_consolidate_schema_source_production_lifecycle_observability_runtime_external():
    report = _report(execute=True)
    gates = {gate["gate_id"]: gate for gate in report["gate_rows"]}

    assert list(gates) == EXPECTED_GATE_IDS
    assert gates["local_schema_validator_present"]["status"] == "READY_LOCAL_CONTRACT"
    assert (
        gates["local_schema_validator_present"]["source_artifact"] == "backend/utils/memory/v17_v3_canary_approval.py"
    )
    assert gates["source_iam_emulator_client_deny_readiness_present"]["status"] == "READY_LOCAL_CONTRACT"
    assert gates["source_iam_emulator_client_deny_readiness_present"]["direct_client_access_proven_denied"] is True
    assert gates["production_read_proof_missing_not_run"]["status"] == "BLOCKED"
    assert gates["production_read_proof_missing_not_run"]["backend_service_principal_read_proven"] is False
    assert gates["production_read_proof_missing_not_run"]["production_artifact_source_exists"] is False
    assert gates["lifecycle_evidence_bundle_missing_blocked"]["status"] == "BLOCKED"
    assert gates["lifecycle_evidence_bundle_missing_blocked"]["blocked_required_evidence_count"] == 9
    assert gates["observability_telemetry_approval_blocked"]["status"] == "BLOCKED"
    assert gates["observability_telemetry_approval_blocked"]["telemetry_sink_calls_executed"] is False
    assert gates["runtime_wiring_blocked"]["status"] == "BLOCKED"
    assert gates["runtime_wiring_blocked"]["route_wiring"] is True
    assert gates["runtime_wiring_blocked"]["runtime_wiring_changed"] is True
    assert gates["runtime_wiring_blocked"]["effective_runtime_behavior_changed"] is False
    assert gates["external_compatibility_blocked"]["status"] == "BLOCKED"
    assert gates["external_compatibility_blocked"]["gap_count"] == 7

    for gate in gates.values():
        assert gate["route_scope"] == EXPECTED_ROUTE_SCOPE
        assert gate["required_before_go"] is True
        assert gate["approval_claimed"] is False


def test_aggregate_remaining_blockers_and_non_claims_preserve_no_go_boundaries():
    report = _report(execute=True)

    assert [blocker["blocker_id"] for blocker in report["remaining_blockers"]] == EXPECTED_REMAINING_BLOCKERS
    for blocker in report["remaining_blockers"]:
        assert blocker["status"] == "BLOCKED"
        assert blocker["required_before_go"] is True

    non_claims = set(report["non_claims"])
    assert (
        "Default-off backend/routers/memories.py GET seam exists, but no effective runtime /v3 behavior change."
        in non_claims
    )
    assert "No runtime /v3 behavior change." in non_claims
    assert "No production rollout approval." in non_claims
    assert (
        "No production Firestore writes/cloud/provider/vector/network calls by default or with --execute." in non_claims
    )
    assert "No telemetry sink production call." in non_claims
    assert "No PII/raw memory content telemetry." in non_claims
    assert "No secret/cursor token logging." in non_claims
    assert "No legacy fallback/merge for V17 failures." in non_claims
    assert "No Archive default visibility or stale Short-term default visibility." in non_claims


def test_aggregate_static_no_route_imports_mutation_prod_calls_telemetry_sink_or_sensitive_labels():
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
        r"\.batch\s*\(",
        r"\.add\s*\(",
        r"transaction\s*\(",
    ]:
        assert not re.search(pattern, script_text), f"forbidden mutating code path: {pattern}"

    labels_json = json.dumps(_report(execute=True)["telemetry_privacy_label_contract"], sort_keys=True).lower()
    for fragment in FORBIDDEN_LABEL_FRAGMENTS:
        assert fragment not in labels_json


def test_aggregate_links_into_ci_and_readiness_docs_without_claiming_go():
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    observability = (root / "scripts" / "v17_p1_3_v3_observability_approval_readiness.py").read_text(encoding="utf-8")
    runtime = (root / "scripts" / "v17_p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external = (root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")

    assert "test_v17_p1_3_v3_canary_approval_aggregate_readiness.py" in test_sh
    assert "canary_approval_aggregate_readiness_proof" in observability
    assert "canary_approval_aggregate_readiness_proof" in runtime
    assert "canary_approval_aggregate_readiness_proof" in external
    assert SCRIPT_NAME in ticket_doc
    assert "final local canary approval GO/NO-GO aggregate readiness" in ticket_doc
    assert SCRIPT_NAME in oracle_doc
    assert "final local canary approval GO/NO-GO aggregate readiness" in oracle_doc
    assert "decision=NO_GO" in ticket_doc
    assert "decision=NO_GO" in oracle_doc
