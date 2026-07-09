"""Production-safe cursor secret metadata read proof (env-gated, no payload access)."""

from __future__ import annotations

import os

from tests.unit.v3_prod_read_probes import cursor_secret_production as module

EXPECTED_ROUTE_SCOPE = "GET /v3/memories"
EXPECTED_SECRET_ID = "memory-v3-get-cursor-signing-secret"


def test_fail_safe_not_run_without_env_gates():
    report = module.build_report(execute=False, env={})
    proof = report["production_read_proof"]
    assert proof["route_scope"] == EXPECTED_ROUTE_SCOPE
    assert proof["secret_id"] == EXPECTED_SECRET_ID
    assert proof["backend_service_principal_metadata_read_proven"] is False
    assert proof["production_secret_material_read"] is False
    assert report["secret_manager_metadata_reads_executed"] is False
    assert report["secret_manager_payload_reads_executed"] is False


def test_execute_missing_env_lists_prerequisites(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MEMORY_V3_CURSOR_SECRET_PROD_READ_") or key in {
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "SERVICE_ACCOUNT_JSON",
        }:
            monkeypatch.delenv(key, raising=False)

    report = module.build_report(execute=True, env={})
    missing = set(report["production_read_proof"]["missing_prerequisites"])
    assert {
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_ALLOW=1",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_PROJECT_ID or GOOGLE_CLOUD_PROJECT",
        "GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_JSON",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SERVICE_ACCOUNT_EMAIL",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SECRET_ID",
    }.issubset(missing)


def test_injected_metadata_read_proves_route_scoped_shape_without_secret_material():
    env = {
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_ALLOW": "1",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_PROJECT_ID": "omi-prod-example",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/non-secret-sa.json",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-memory-read@omi-prod-example.iam.gserviceaccount.com",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SECRET_ID": EXPECTED_SECRET_ID,
    }
    metadata = {
        "name": f"projects/omi-prod-example/secrets/{EXPECTED_SECRET_ID}",
        "labels": {
            "route_scope": "get_v3_memories",
            "purpose": "v3_cursor_signing",
            "owner": "memory_platform",
        },
        "replication": "automatic",
    }

    report = module.build_report(execute=True, env=env, reader=lambda: metadata)
    proof = report["production_read_proof"]
    assert proof["backend_service_principal_metadata_read_proven"] is True
    assert proof["production_secret_config_metadata_valid"] is True
    assert proof["production_secret_material_read"] is False
    assert proof["route_scoped_without_user_dimensions"] is True
    assert report["secret_manager_payload_reads_executed"] is False
    assert report["production_rollout_approved"] is False


def test_injected_missing_or_invalid_metadata_fails_closed():
    env = {
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_ALLOW": "1",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_PROJECT_ID": "omi-prod-example",
        "SERVICE_ACCOUNT_JSON": "{}",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-memory-read@omi-prod-example.iam.gserviceaccount.com",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SECRET_ID": EXPECTED_SECRET_ID,
    }

    missing = module.build_report(execute=True, env=env, reader=lambda: None)
    assert missing["production_read_proof"]["metadata_validation_reason"] == "metadata_missing"

    invalid = module.build_report(
        execute=True,
        env=env,
        reader=lambda: {"name": "projects/omi-prod-example/secrets/user-uid-scoped-secret"},
    )
    assert invalid["production_read_proof"]["metadata_validation_reason"] == "metadata_wrong_secret_id"
