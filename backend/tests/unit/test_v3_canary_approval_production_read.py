"""Production-safe canary approval Firestore read proof (env-gated, injectable reader)."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from tests.unit.v3_prod_read_probes import canary_approval_production as module

EXPECTED_ARTIFACT_PATH = "system/v3_canary_approvals/routes/get_v3_memories"
EXPECTED_ROUTE_SCOPE = "GET /v3/memories"


def test_fail_safe_not_run_without_execute_or_env():
    report = module.build_report(execute=False, env={})
    proof = report["production_read_proof"]
    assert proof["artifact_document_path"] == EXPECTED_ARTIFACT_PATH
    assert proof["route_scope"] == EXPECTED_ROUTE_SCOPE
    assert proof["backend_service_principal_read_proven"] is False
    assert proof["production_artifact_source_exists"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False


def test_execute_missing_env_lists_exact_prerequisites(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MEMORY_V3_CANARY_APPROVAL_PROD_READ_") or key in {
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "SERVICE_ACCOUNT_JSON",
        }:
            monkeypatch.delenv(key, raising=False)

    report = module.build_report(execute=True, env={})
    missing = set(report["production_read_proof"]["missing_prerequisites"])
    assert {
        "MEMORY_V3_CANARY_APPROVAL_PROD_READ_ALLOW=1",
        "MEMORY_V3_CANARY_APPROVAL_PROD_READ_PROJECT_ID or GOOGLE_CLOUD_PROJECT",
        "GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_JSON",
        "MEMORY_V3_CANARY_APPROVAL_PROD_READ_SERVICE_ACCOUNT_EMAIL",
    }.issubset(missing)
    assert report["network_or_provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False


def test_injected_valid_artifact_proves_shape_but_not_rollout_approval():
    env = {
        "MEMORY_V3_CANARY_APPROVAL_PROD_READ_ALLOW": "1",
        "MEMORY_V3_CANARY_APPROVAL_PROD_READ_PROJECT_ID": "omi-prod-example",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/non-secret-sa.json",
        "MEMORY_V3_CANARY_APPROVAL_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-memory-read@omi-prod-example.iam.gserviceaccount.com",
    }
    artifact = {
        "schema_version": 1,
        "artifact_id": "memory-v3-get-canary-approval",
        "route_scope": EXPECTED_ROUTE_SCOPE,
        "owner": "product_privacy_ops",
        "status": "approved",
        "cohort": "canary_1",
        "issued_at": "2026-01-01T00:00:00+00:00",
        "expires_at": "2027-01-01T00:00:00+00:00",
        "approval": {
            "approval_id": "approval-memory-v3-get-001",
            "approved_at": "2026-01-01T00:01:00+00:00",
            "approved_by": "product_privacy_ops",
        },
        "rollback_plan": {
            "owner": "memory_platform_oncall",
            "disable_gate": "emergency_read_disable",
            "steps": ["disable_canary", "verify_fail_closed", "page_oncall"],
        },
        "monitoring_gates": [
            {"gate_id": "fail_closed_rate", "metric": "v3_fail_closed_rate", "max_threshold": 0.01},
            {"gate_id": "p95_latency_ms", "metric": "v3_get_p95_latency_ms", "max_threshold": 250},
        ],
    }

    report = module.build_report(
        execute=True,
        env=env,
        reader=lambda: artifact,
        now=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    proof = report["production_read_proof"]
    assert proof["backend_service_principal_read_proven"] is True
    assert proof["production_artifact_source_exists"] is True
    assert proof["production_artifact_valid"] is True
    assert proof["artifact_validation_reason"] == "approved"
    assert report["firestore_reads_executed"] is True
    assert report["firestore_writes_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False


def test_injected_missing_or_invalid_artifact_fails_closed():
    env = {
        "MEMORY_V3_CANARY_APPROVAL_PROD_READ_ALLOW": "1",
        "MEMORY_V3_CANARY_APPROVAL_PROD_READ_PROJECT_ID": "omi-prod-example",
        "SERVICE_ACCOUNT_JSON": "{}",
        "MEMORY_V3_CANARY_APPROVAL_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-memory-read@omi-prod-example.iam.gserviceaccount.com",
    }

    missing = module.build_report(execute=True, env=env, reader=lambda: None)
    assert missing["production_read_proof"]["production_artifact_source_exists"] is False
    assert missing["production_read_proof"]["artifact_validation_reason"] == "artifact_missing"

    invalid = module.build_report(execute=True, env=env, reader=lambda: {"route_scope": EXPECTED_ROUTE_SCOPE})
    assert invalid["production_read_proof"]["production_artifact_valid"] is False
    assert invalid["production_read_proof"]["artifact_validation_reason"] == "artifact_malformed"
