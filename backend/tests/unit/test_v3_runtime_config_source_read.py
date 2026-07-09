"""Production-safe runtime config source selection read proof."""

from __future__ import annotations

import os

from tests.unit.v3_prod_read_probes import runtime_config_source as module

EXPECTED_ROUTE_SCOPE = "GET /v3/memories"
EXPECTED_CONFIG_PATHS = ["memory_control/global_read_gate", "memory_control/write_convergence_gate"]


def test_fail_safe_not_run_without_env_gates():
    report = module.build_report(execute=False, env={})
    proof = report["source_selection_proof"]
    assert proof["route_scope"] == EXPECTED_ROUTE_SCOPE
    assert [source["path"] for source in proof["selected_sources"]] == EXPECTED_CONFIG_PATHS
    assert proof["backend_service_principal_read_proven"] is False
    assert proof["client_override_allowed"] is False
    assert report["firestore_reads_executed"] is False


def test_execute_missing_env_lists_prerequisites(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_") or key in {
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "SERVICE_ACCOUNT_JSON",
        }:
            monkeypatch.delenv(key, raising=False)

    report = module.build_report(execute=True, env={})
    missing = set(report["source_selection_proof"]["missing_prerequisites"])
    assert {
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_ALLOW=1",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_PROJECT_ID or GOOGLE_CLOUD_PROJECT",
        "GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_JSON",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_SERVICE_ACCOUNT_EMAIL",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_CONFIG_PATHS",
    }.issubset(missing)


def test_injected_config_read_proves_route_scoped_sources_without_rollout_approval():
    env = {
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_ALLOW": "1",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_PROJECT_ID": "omi-prod-example",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/non-secret-sa.json",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-memory-read@omi-prod-example.iam.gserviceaccount.com",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_CONFIG_PATHS": ",".join(EXPECTED_CONFIG_PATHS),
    }
    docs = {
        "memory_control/global_read_gate": {
            "route_scope": "get_v3_memories",
            "purpose": "v3_runtime_enablement",
            "owner": "memory_platform",
            "config_schema_version": 1,
            "max_staleness_seconds": 300,
            "memory_reads_enabled": False,
            "kill_switch_active": True,
        },
        "memory_control/write_convergence_gate": {
            "route_scope": "get_v3_memories",
            "purpose": "v3_write_convergence_gate",
            "owner": "memory_platform",
            "config_schema_version": 1,
            "max_staleness_seconds": 300,
            "durable_outbox_enabled": False,
            "dual_write_projection_ready": False,
            "delete_convergence_ready": False,
            "idempotency_contract_ready": False,
        },
    }

    report = module.build_report(execute=True, env=env, reader=lambda path: docs.get(path))
    proof = report["source_selection_proof"]
    assert proof["production_config_sources_valid"] is True
    assert proof["config_validation_reason"] == "config_valid"
    assert proof["route_scoped_without_user_dimensions"] is True
    assert report["production_rollout_approved"] is False


def test_injected_missing_or_forbidden_dimension_config_fails_closed():
    env = {
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_ALLOW": "1",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_PROJECT_ID": "omi-prod-example",
        "SERVICE_ACCOUNT_JSON": "{}",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-memory-read@omi-prod-example.iam.gserviceaccount.com",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_CONFIG_PATHS": ",".join(EXPECTED_CONFIG_PATHS),
    }

    missing = module.build_report(execute=True, env=env, reader=lambda path: None)
    assert missing["source_selection_proof"]["config_validation_reason"] == "config_missing"

    invalid = module.build_report(
        execute=True,
        env=env,
        reader=lambda path: {
            "route_scope": "get_v3_memories",
            "purpose": "v3_runtime_enablement",
            "owner": "memory_platform",
            "uid": "user-scoped-overrides-are-forbidden",
            "config_schema_version": 1,
            "max_staleness_seconds": 300,
        },
    )
    assert invalid["source_selection_proof"]["config_validation_reason"] == "config_contains_forbidden_dimension"
