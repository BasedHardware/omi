import importlib.util
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_NAME = "p1_3_v3_canary_approval_production_readiness.py"
EXPECTED_ARTIFACT_PATH = "system/v17_v3_canary_approvals/routes/get_v3_memories"
EXPECTED_ROUTE_SCOPE = "GET /v3/memories"


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_canary_approval_production_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / SCRIPT_NAME)


def test_production_readiness_runner_exists_and_is_fail_safe_not_run_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / SCRIPT_NAME
    assert script_path.exists(), "missing production-safe canary approval read-proof runner"

    report = _module().build_report(execute=False, env={})

    assert report["artifact"] == "v17_p1_3_v3_canary_approval_production_readiness"
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
    assert report["production_read_proof"]["artifact_document_path"] == EXPECTED_ARTIFACT_PATH
    assert report["production_read_proof"]["route_scope"] == EXPECTED_ROUTE_SCOPE
    assert report["production_read_proof"]["backend_service_principal_read_proven"] is False
    assert report["production_read_proof"]["production_artifact_source_exists"] is False
    assert report["summary"]["missing_prerequisite_count"] >= 3


def test_execute_missing_env_is_blocked_not_run_with_exact_prerequisites(monkeypatch):
    for key in list(os.environ):
        if key.startswith("V17_V3_CANARY_APPROVAL_PROD_READ_") or key in {
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "SERVICE_ACCOUNT_JSON",
        }:
            monkeypatch.delenv(key, raising=False)

    report = _module().build_report(execute=True, env={})

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
    assert report["execute"] is True
    assert report["network_or_provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    missing = set(report["production_read_proof"]["missing_prerequisites"])
    assert {
        "V17_V3_CANARY_APPROVAL_PROD_READ_ALLOW=1",
        "V17_V3_CANARY_APPROVAL_PROD_READ_PROJECT_ID or GOOGLE_CLOUD_PROJECT",
        "GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_JSON",
        "V17_V3_CANARY_APPROVAL_PROD_READ_SERVICE_ACCOUNT_EMAIL",
    }.issubset(missing)
    assert report["summary"]["backend_service_principal_read_proven"] is False
    assert report["summary"]["production_artifact_source_exists"] is False
    assert report["summary"]["production_artifact_valid"] is False
    assert report["summary"]["approval_claimed"] is False


def test_injected_valid_artifact_read_proves_existence_and_shape_but_not_approval():
    module = _module()
    env = {
        "V17_V3_CANARY_APPROVAL_PROD_READ_ALLOW": "1",
        "V17_V3_CANARY_APPROVAL_PROD_READ_PROJECT_ID": "omi-prod-example",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/non-secret-sa.json",
        "V17_V3_CANARY_APPROVAL_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-v17-read@omi-prod-example.iam.gserviceaccount.com",
    }
    artifact = {
        "schema_version": 1,
        "artifact_id": "v17-v3-get-canary-approval",
        "route_scope": EXPECTED_ROUTE_SCOPE,
        "owner": "product_privacy_ops",
        "status": "approved",
        "cohort": "canary_1",
        "issued_at": "2026-01-01T00:00:00+00:00",
        "expires_at": "2027-01-01T00:00:00+00:00",
        "approval": {
            "approval_id": "approval-v17-v3-get-001",
            "approved_at": "2026-01-01T00:01:00+00:00",
            "approved_by": "product_privacy_ops",
        },
        "rollback_plan": {
            "owner": "memory_platform_oncall",
            "disable_gate": "emergency_read_disable",
            "steps": ["disable_canary", "verify_fail_closed", "page_oncall"],
        },
        "monitoring_gates": [
            {"gate_id": "fail_closed_rate", "metric": "v17_v3_fail_closed_rate", "max_threshold": 0.01},
            {"gate_id": "p95_latency_ms", "metric": "v17_v3_get_p95_latency_ms", "max_threshold": 250},
        ],
    }

    report = module.build_report(
        execute=True,
        env=env,
        reader=lambda: artifact,
        now=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "PROVEN_READ_ONLY"
    assert report["network_or_provider_calls_executed"] is True
    assert report["firestore_reads_executed"] is True
    assert report["firestore_writes_executed"] is False
    proof = report["production_read_proof"]
    assert proof["backend_service_principal_read_proven"] is True
    assert proof["production_artifact_source_exists"] is True
    assert proof["production_artifact_valid"] is True
    assert proof["artifact_validation_reason"] == "approved"
    assert proof["route_scope"] == EXPECTED_ROUTE_SCOPE
    assert proof["bounded_owners_and_cohorts_valid"] is True
    assert proof["approval_metadata_only"] is True
    assert proof["no_high_cardinality_or_sensitive_fields"] is True
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False
    assert report["summary"]["production_rollout_approved"] is False


def test_injected_missing_or_invalid_artifact_fails_closed_without_claiming_failure():
    module = _module()
    env = {
        "V17_V3_CANARY_APPROVAL_PROD_READ_ALLOW": "1",
        "V17_V3_CANARY_APPROVAL_PROD_READ_PROJECT_ID": "omi-prod-example",
        "SERVICE_ACCOUNT_JSON": "{}",
        "V17_V3_CANARY_APPROVAL_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-v17-read@omi-prod-example.iam.gserviceaccount.com",
    }

    missing = module.build_report(execute=True, env=env, reader=lambda: None)
    assert missing["proof_status"] == "BLOCKED"
    assert missing["production_read_proof"]["production_artifact_source_exists"] is False
    assert missing["production_read_proof"]["artifact_validation_reason"] == "artifact_missing"
    assert missing["approval_claimed"] is False

    invalid = module.build_report(execute=True, env=env, reader=lambda: {"route_scope": EXPECTED_ROUTE_SCOPE})
    assert invalid["proof_status"] == "BLOCKED"
    assert invalid["production_read_proof"]["production_artifact_valid"] is False
    assert invalid["production_read_proof"]["artifact_validation_reason"] == "artifact_malformed"
    assert invalid["production_read_proof"]["backend_service_principal_read_proven"] is True
    assert invalid["production_rollout_approved"] is False


def test_static_no_mutation_no_route_import_no_telemetry_sink_and_docs_links():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / SCRIPT_NAME
    script_text = script_path.read_text(encoding="utf-8")
    lowered = script_text.lower()

    assert "backend.routers" not in lowered
    assert "routers.memories" not in lowered
    assert "posthog" not in lowered
    assert "prometheus" not in lowered
    assert "telemetry" not in lowered or "telemetry_sink_calls_executed" in lowered
    forbidden_mutators = [
        r"\.set\s*\(",
        r"\.update\s*\(",
        r"\.delete\s*\(",
        r"\.create\s*\(",
        r"\.commit\s*\(",
        r"\.batch\s*\(",
        r"\.add\s*\(",
        r"transaction\s*\(",
    ]
    for pattern in forbidden_mutators:
        assert not re.search(pattern, script_text), f"forbidden mutating Firestore code path: {pattern}"

    report_json = json.dumps(_module().build_report(execute=False, env={}), sort_keys=True)
    assert "production_rollout_approved\": false" in report_json
    assert "approval_claimed\": false" in report_json

    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    source_readiness = (root / "scripts" / "p1_3_v3_canary_approval_source_readiness.py").read_text(
        encoding="utf-8"
    )
    observability = (root / "scripts" / "p1_3_v3_observability_approval_readiness.py").read_text(encoding="utf-8")
    runtime = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")

    assert "test_p1_3_v3_canary_approval_production_readiness.py" in test_sh
    assert SCRIPT_NAME in source_readiness
    assert "canary_approval_production_readiness_proof" in observability
    assert "canary_approval_production_readiness_proof" in runtime
    assert "canary_approval_production_readiness_proof" in external
    assert SCRIPT_NAME in ticket_doc
    assert "production-safe backend service-principal read proof" in ticket_doc
    assert SCRIPT_NAME in oracle_doc
    assert "production-safe backend service-principal read proof" in oracle_doc
