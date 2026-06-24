import importlib.util
import json
import os
import re
from pathlib import Path

SCRIPT_NAME = "p1_3_v3_runtime_config_source_readiness.py"
EXPECTED_ROUTE_SCOPE = "GET /v3/memories"
EXPECTED_CONFIG_PATHS = ["memory_control/global_read_gate", "memory_control/write_convergence_gate"]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("p1_3_v3_runtime_config_source_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / SCRIPT_NAME)


def test_runtime_config_source_runner_exists_and_is_fail_safe_not_run_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / SCRIPT_NAME
    assert script_path.exists(), "missing server-owned runtime config source-selection readiness runner"

    report = _module().build_report(execute=False, env={})

    assert report["artifact"] == "p1_3_v3_runtime_config_source_readiness"
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

    proof = report["source_selection_proof"]
    assert proof["route_scope"] == EXPECTED_ROUTE_SCOPE
    assert [source["path"] for source in proof["selected_sources"]] == EXPECTED_CONFIG_PATHS
    assert proof["backend_service_principal_read_proven"] is False
    assert proof["production_config_sources_exist"] is False
    assert proof["production_config_sources_valid"] is False
    assert proof["client_override_allowed"] is False
    assert proof["route_scoped_without_user_dimensions"] is False
    assert report["summary"]["missing_prerequisite_count"] >= 5


def test_execute_missing_env_is_blocked_not_run_with_exact_prerequisites(monkeypatch):
    for key in list(os.environ):
        if key.startswith("MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_") or key in {
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
    missing = set(report["source_selection_proof"]["missing_prerequisites"])
    assert {
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_ALLOW=1",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_PROJECT_ID or GOOGLE_CLOUD_PROJECT",
        "GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_JSON",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_SERVICE_ACCOUNT_EMAIL",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_CONFIG_PATHS",
    }.issubset(missing)
    assert report["summary"]["backend_service_principal_read_proven"] is False
    assert report["summary"]["production_config_sources_exist"] is False
    assert report["summary"]["production_config_sources_valid"] is False


def test_injected_config_read_proves_route_scoped_source_selection_but_does_not_approve_rollout():
    module = _module()
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

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "PROVEN_READ_ONLY"
    assert report["network_or_provider_calls_executed"] is True
    assert report["firestore_reads_executed"] is True
    assert report["firestore_writes_executed"] is False
    proof = report["source_selection_proof"]
    assert proof["backend_service_principal_read_proven"] is True
    assert proof["production_config_sources_exist"] is True
    assert proof["production_config_sources_valid"] is True
    assert proof["config_validation_reason"] == "config_valid"
    assert proof["route_scoped_without_user_dimensions"] is True
    assert proof["client_override_allowed"] is False
    assert proof["fail_closed_on_missing_stale_malformed"] is True
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False


def test_injected_missing_stale_or_invalid_config_fails_closed_without_runtime_change():
    module = _module()
    env = {
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_ALLOW": "1",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_PROJECT_ID": "omi-prod-example",
        "SERVICE_ACCOUNT_JSON": "{}",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_SERVICE_ACCOUNT_EMAIL": "backend-memory-read@omi-prod-example.iam.gserviceaccount.com",
        "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_CONFIG_PATHS": ",".join(EXPECTED_CONFIG_PATHS),
    }

    missing = module.build_report(execute=True, env=env, reader=lambda path: None)
    assert missing["proof_status"] == "BLOCKED"
    assert missing["source_selection_proof"]["production_config_sources_exist"] is False
    assert missing["source_selection_proof"]["config_validation_reason"] == "config_missing"
    assert missing["source_selection_proof"]["fail_closed_on_missing_stale_malformed"] is True

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
    assert invalid["proof_status"] == "BLOCKED"
    assert invalid["source_selection_proof"]["production_config_sources_valid"] is False
    assert invalid["source_selection_proof"]["config_validation_reason"] == "config_contains_forbidden_dimension"
    assert invalid["source_selection_proof"]["backend_service_principal_read_proven"] is True
    assert invalid["runtime_wiring_changed"] is False

    stale = module.build_report(
        execute=True,
        env=env,
        reader=lambda path: {
            "route_scope": "get_v3_memories",
            "purpose": "v3_runtime_enablement",
            "owner": "memory_platform",
            "config_schema_version": 1,
            "max_staleness_seconds": 3600,
        },
    )
    assert stale["proof_status"] == "BLOCKED"
    assert stale["source_selection_proof"]["config_validation_reason"] == "config_staleness_unbounded"


def test_static_no_mutation_no_route_import_no_secret_cursor_user_content_logging_and_docs_links():
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
    assert "secret_value" not in lowered
    assert "cursor_token" not in lowered
    assert "raw_memory" not in lowered
    assert "request_payload" in lowered  # only as a forbidden dimension, never as input
    assert "client_override_allowed" in lowered
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
        assert not re.search(pattern, script_text), f"forbidden mutating config code path: {pattern}"

    report_json = json.dumps(_module().build_report(execute=False, env={}), sort_keys=True)
    assert "production_rollout_approved\": false" in report_json
    assert "approval_claimed\": false" in report_json
    assert "fake-client-runtime-config" not in report_json

    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    runtime = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text(encoding="utf-8")

    assert "test_p1_3_v3_runtime_config_source_readiness.py" in test_sh
    assert "runtime_config_source_readiness_proof" in runtime
    assert "runtime_config_source_readiness_proof" in external
    assert SCRIPT_NAME in ticket_doc
    assert "server-owned runtime control/config source-selection readiness proof" in ticket_doc
    assert SCRIPT_NAME in oracle_doc
    assert "server-owned runtime control/config source-selection readiness proof" in oracle_doc
