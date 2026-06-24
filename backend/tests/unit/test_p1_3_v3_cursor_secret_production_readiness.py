import importlib.util
import json
import os
import re
from pathlib import Path

SCRIPT_NAME = "p1_3_v3_cursor_secret_production_readiness.py"
EXPECTED_ROUTE_SCOPE = "GET /v3/memories"
EXPECTED_SECRET_ID = "v17-v3-get-memories-cursor-signing-secret"


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_cursor_secret_production_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / SCRIPT_NAME)


def test_cursor_secret_production_runner_exists_and_is_fail_safe_not_run_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / SCRIPT_NAME
    assert script_path.exists(), "missing production-safe cursor secret/config read-proof runner"

    report = _module().build_report(execute=False, env={})

    assert report["artifact"] == "v17_p1_3_v3_cursor_secret_production_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
    assert report["execute"] is False
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["routers_memories_modified"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["secret_manager_metadata_reads_executed"] is False
    assert report["secret_manager_payload_reads_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["telemetry_sink_calls_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False

    proof = report["production_read_proof"]
    assert proof["route_scope"] == EXPECTED_ROUTE_SCOPE
    assert proof["secret_id"] == EXPECTED_SECRET_ID
    assert proof["backend_service_principal_metadata_read_proven"] is False
    assert proof["production_secret_config_source_exists"] is False
    assert proof["production_secret_material_read"] is False
    assert report["summary"]["missing_prerequisite_count"] >= 4


def test_execute_missing_env_is_blocked_not_run_with_exact_prerequisites(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MEMORY_V3_CURSOR_SECRET_PROD_READ_") or key in {
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
    assert report["secret_manager_metadata_reads_executed"] is False
    missing = set(report["production_read_proof"]["missing_prerequisites"])
    assert {
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_ALLOW=1",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_PROJECT_ID or GOOGLE_CLOUD_PROJECT",
        "GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_JSON",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SERVICE_ACCOUNT_EMAIL",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SECRET_ID",
    }.issubset(missing)
    assert report["summary"]["backend_service_principal_metadata_read_proven"] is False
    assert report["summary"]["production_secret_config_source_exists"] is False
    assert report["summary"]["production_secret_config_metadata_valid"] is False


def test_injected_metadata_read_proves_route_scoped_shape_but_never_reads_secret_material():
    module = _module()
    env = {
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_ALLOW": "1",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_PROJECT_ID": "omi-prod-example",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/non-secret-sa.json",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-v17-read@omi-prod-example.iam.gserviceaccount.com",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SECRET_ID": EXPECTED_SECRET_ID,
    }
    metadata = {
        "name": f"projects/omi-prod-example/secrets/{EXPECTED_SECRET_ID}",
        "labels": {
            "route_scope": "get_v3_memories",
            "purpose": "v17_v3_cursor_signing",
            "owner": "memory_platform",
        },
        "replication": "automatic",
    }

    report = module.build_report(execute=True, env=env, reader=lambda: metadata)

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "PROVEN_READ_ONLY"
    assert report["network_or_provider_calls_executed"] is True
    assert report["secret_manager_metadata_reads_executed"] is True
    assert report["secret_manager_payload_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    proof = report["production_read_proof"]
    assert proof["backend_service_principal_metadata_read_proven"] is True
    assert proof["production_secret_config_source_exists"] is True
    assert proof["production_secret_config_metadata_valid"] is True
    assert proof["metadata_validation_reason"] == "metadata_valid"
    assert proof["production_secret_material_read"] is False
    assert proof["client_supplied_secret_trusted"] is False
    assert proof["route_scoped_without_user_dimensions"] is True
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False


def test_injected_missing_or_invalid_metadata_fails_closed_without_production_failure():
    module = _module()
    env = {
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_ALLOW": "1",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_PROJECT_ID": "omi-prod-example",
        "SERVICE_ACCOUNT_JSON": "{}",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-v17-read@omi-prod-example.iam.gserviceaccount.com",
        "MEMORY_V3_CURSOR_SECRET_PROD_READ_SECRET_ID": EXPECTED_SECRET_ID,
    }

    missing = module.build_report(execute=True, env=env, reader=lambda: None)
    assert missing["proof_status"] == "BLOCKED"
    assert missing["production_read_proof"]["production_secret_config_source_exists"] is False
    assert missing["production_read_proof"]["metadata_validation_reason"] == "metadata_missing"
    assert missing["approval_claimed"] is False

    invalid = module.build_report(
        execute=True,
        env=env,
        reader=lambda: {"name": "projects/omi-prod-example/secrets/user-uid-scoped-secret"},
    )
    assert invalid["proof_status"] == "BLOCKED"
    assert invalid["production_read_proof"]["production_secret_config_metadata_valid"] is False
    assert invalid["production_read_proof"]["metadata_validation_reason"] == "metadata_wrong_secret_id"
    assert invalid["production_read_proof"]["backend_service_principal_metadata_read_proven"] is True
    assert invalid["production_rollout_approved"] is False


def test_static_no_mutation_no_payload_access_no_route_import_no_secret_or_token_logging_and_docs_links():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / SCRIPT_NAME
    script_text = script_path.read_text(encoding="utf-8")
    lowered = script_text.lower()

    assert "backend.routers" not in lowered
    assert "routers.memories" not in lowered
    assert "posthog" not in lowered
    assert "prometheus" not in lowered
    assert "telemetry" not in lowered or "telemetry_sink_calls_executed" in lowered
    assert "access_secret_version" not in lowered
    assert "payload" not in lowered or "secret_manager_payload_reads_executed" in lowered
    assert "cursor_token" not in lowered
    assert "secret_value" not in lowered
    forbidden_mutators = [
        r"\.set\s*\(",
        r"\.update\s*\(",
        r"\.delete\s*\(",
        r"\.create\s*\(",
        r"\.commit\s*\(",
        r"\.batch\s*\(",
        r"\.add\s*\(",
        r"transaction\s*\(",
        r"\.destroy_secret\s*\(",
        r"\.add_secret_version\s*\(",
        r"\.disable_secret_version\s*\(",
        r"\.enable_secret_version\s*\(",
    ]
    for pattern in forbidden_mutators:
        assert not re.search(pattern, script_text), f"forbidden mutating secret/config code path: {pattern}"

    report_json = json.dumps(_module().build_report(execute=False, env={}), sort_keys=True)
    assert "production_rollout_approved\": false" in report_json
    assert "approval_claimed\": false" in report_json
    assert "fake-server-owned-v17-v3-cursor-secret" not in report_json

    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    cursor_readiness = (root / "scripts" / "p1_3_v3_cursor_secret_readiness.py").read_text(encoding="utf-8")
    runtime = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")

    assert "test_p1_3_v3_cursor_secret_production_readiness.py" in test_sh
    assert SCRIPT_NAME in cursor_readiness
    assert "cursor_secret_production_readiness_proof" in runtime
    assert "cursor_secret_production_readiness_proof" in external
    assert SCRIPT_NAME in ticket_doc
    assert "production-safe cursor secret/config metadata read proof" in ticket_doc
    assert SCRIPT_NAME in oracle_doc
    assert "production-safe cursor secret/config metadata read proof" in oracle_doc
