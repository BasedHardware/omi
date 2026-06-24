import importlib.util
import json
from pathlib import Path

REQUIRED_REQUIREMENT_IDS = [
    "route_scoped_server_owned_projection_source",
    "authenticated_subject_selector_only",
    "bounded_page_size_limit_contract",
    "deterministic_keyset_ordering_contract",
    "projection_metadata_freshness_fail_closed",
    "privacy_safe_telemetry_dimensions",
    "no_client_controlled_source_or_path",
    "no_legacy_fallback_or_merge_claim",
]

FORBIDDEN_STATIC_TOKENS = [
    ".set(",
    ".add(",
    ".update(",
    ".delete(",
    ".create(",
    "batch(",
    "commit(",
    "backend.routers.memories",
    "routers.memories",
    "upsert_memory_vector",
    "requests.",
    "httpx.",
    "telemetry_client",
    "posthog",
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("p1_3_v3_projection_read_source_readiness", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / "p1_3_v3_projection_read_source_readiness.py")


def _report(execute=False, env=None, reader=None):
    return _module().build_report(execute=execute, env={} if env is None else env, reader=reader)


def test_projection_read_source_readiness_is_safe_blocked_by_default():
    report = _report(execute=False)

    assert report["artifact"] == "p1_3_v3_projection_read_source_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
    assert report["execute"] is False
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["runtime_wiring_changed"] is False
    assert report["routers_memories_modified"] is False
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["pinecone_calls_executed"] is False
    assert report["telemetry_sink_calls_executed"] is False
    assert report["production_rollout_approved"] is False
    assert report["approval_claimed"] is False
    assert report["summary"]["status"] == "BLOCKED"
    assert report["summary"]["missing_prerequisite_count"] == 5


def test_projection_read_source_contract_inventories_required_source_shape():
    report = _report(execute=True)
    contract = report["projection_read_source_contract"]
    requirements = {item["requirement_id"]: item for item in report["read_source_requirements"]}

    assert list(requirements) == REQUIRED_REQUIREMENT_IDS
    assert contract["route_scope"] == "GET /v3/memories"
    assert contract["source_type"] == "firestore_compatibility_projection"
    assert contract["state_path_template"] == "users/{uid}/v3_compatibility_projection/state"
    assert contract["items_path_template"] == "users/{uid}/v3_compatibility_projection_items/{memory_id}"
    assert contract["client_override_allowed"] is False
    assert contract["uid_usage"] == "authenticated_subject_selector_only"
    assert contract["configuration_dimension_fields"] == []
    assert contract["limit_bounds"] == {"min": 1, "default": 100, "max": 500}
    assert contract["ordering"] == [
        {"field": "created_at", "direction": "DESC"},
        {"field": "__name__", "direction": "DESC"},
    ]
    assert set(contract["cursor_fields"]) == {
        "created_at",
        "memory_id",
        "account_generation",
        "projection_generation",
        "projection_commit_id",
    }
    assert contract["legacy_fallback_allowed"] is False
    assert contract["merge_legacy_and_memory_allowed"] is False
    assert contract["fail_closed_on_missing_stale_malformed_metadata"] is True

    assert requirements["route_scoped_server_owned_projection_source"]["server_owned"] is True
    assert requirements["authenticated_subject_selector_only"]["uid_as_config_dimension_allowed"] is False
    assert requirements["bounded_page_size_limit_contract"]["max_limit"] == 500
    assert requirements["deterministic_keyset_ordering_contract"]["offset_supported_for_memory"] is False
    assert requirements["projection_metadata_freshness_fail_closed"]["fail_closed"] is True
    assert requirements["privacy_safe_telemetry_dimensions"]["telemetry_sink_calls_executed"] is False
    assert requirements["no_client_controlled_source_or_path"]["client_source_path_override_allowed"] is False
    assert requirements["no_legacy_fallback_or_merge_claim"]["legacy_fallback_allowed"] is False


def test_projection_read_source_missing_env_execute_is_blocked_without_reads():
    report = _report(execute=True, env={})

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
    assert report["firestore_reads_executed"] is False
    proof = report["production_read_source_proof"]
    assert proof["missing_prerequisites"] == [
        "MEMORY_V3_PROJECTION_READ_SOURCE_PROD_READ_ALLOW=1",
        "MEMORY_V3_PROJECTION_READ_SOURCE_PROD_READ_PROJECT_ID or GOOGLE_CLOUD_PROJECT",
        "GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_JSON",
        "MEMORY_V3_PROJECTION_READ_SOURCE_PROD_READ_SERVICE_ACCOUNT_EMAIL",
        "MEMORY_V3_PROJECTION_READ_SOURCE_PROD_READ_UID",
    ]
    assert proof["production_projection_source_exists"] is False
    assert proof["production_projection_source_valid"] is False
    assert proof["source_validation_reason"] == "not_run"


def test_projection_read_source_gated_reader_validates_source_metadata_read_only():
    module = _module()
    env = {
        module.ALLOW_ENV: "1",
        module.PROJECT_ID_ENV: "omi-prod",
        module.SERVICE_ACCOUNT_EMAIL_ENV: "backend@omi-prod.iam.gserviceaccount.com",
        module.SERVICE_ACCOUNT_JSON_ENV: "{}",
        module.UID_ENV: "user-123",
    }

    report = _report(execute=True, env=env, reader=lambda uid: module.example_valid_source_metadata(uid))

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "PROVEN_READ_ONLY"
    assert report["read_only"] is True
    assert report["firestore_reads_executed"] is True
    assert report["firestore_writes_executed"] is False
    proof = report["production_read_source_proof"]
    assert proof["backend_service_principal_read_proven"] is True
    assert proof["production_projection_source_exists"] is True
    assert proof["production_projection_source_valid"] is True
    assert proof["source_validation_reason"] == "source_metadata_valid"
    assert proof["route_scoped_without_user_dimensions"] is True
    assert proof["fail_closed_on_missing_stale_malformed"] is True


def test_projection_read_source_gated_reader_fails_closed_on_missing_or_malformed_source():
    module = _module()
    env = {
        module.ALLOW_ENV: "1",
        module.PROJECT_ID_ENV: "omi-prod",
        module.SERVICE_ACCOUNT_EMAIL_ENV: "backend@omi-prod.iam.gserviceaccount.com",
        module.SERVICE_ACCOUNT_JSON_ENV: "{}",
        module.UID_ENV: "user-123",
    }

    missing = _report(execute=True, env=env, reader=lambda uid: None)
    assert missing["proof_status"] == "BLOCKED"
    assert missing["production_read_source_proof"]["source_validation_reason"] == "source_metadata_missing"

    malformed = _report(execute=True, env=env, reader=lambda uid: {"route_scope": "GET /v3/memories"})
    assert malformed["proof_status"] == "BLOCKED"
    assert malformed["production_read_source_proof"]["source_validation_reason"] in {
        "source_metadata_missing_required_fields",
        "source_metadata_malformed",
    }


def test_projection_read_source_static_script_has_no_mutating_paths_route_imports_or_sensitive_logging():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "p1_3_v3_projection_read_source_readiness.py"
    script_text = script_path.read_text(encoding="utf-8")

    for token in FORBIDDEN_STATIC_TOKENS:
        assert token not in script_text
    for sensitive in ["cursor_token", "raw_cursor", "request_payload", "memory_content", "session_id"]:
        assert sensitive in script_text
    assert "telemetry_safe_labels" in script_text
    assert "client_override_allowed" in script_text
    assert "legacy_fallback_allowed" in script_text


def test_projection_read_source_readiness_is_registered_in_test_runner_docs_and_parent_readiness():
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    runtime_readiness = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external_readiness = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")

    assert "test_p1_3_v3_projection_read_source_readiness.py" in test_sh
    assert "p1_3_v3_projection_read_source_readiness.py" in ticket_doc
    assert "projection read source contract/readiness" in ticket_doc
    assert "p1_3_v3_projection_read_source_readiness.py" in oracle_doc
    assert "projection read source contract/readiness" in oracle_doc
    assert "projection_read_source_readiness_proof" in runtime_readiness
    assert "projection_read_source_readiness_proof" in external_readiness


def test_projection_read_source_summary_json_is_stable():
    decoded = json.loads(json.dumps(_report(execute=True), sort_keys=True))

    assert decoded["summary"] == {
        "status": "BLOCKED",
        "proof_status": "NOT_RUN",
        "missing_prerequisite_count": 5,
        "read_source_requirement_count": 8,
        "selected_source_count": 2,
        "backend_service_principal_read_proven": False,
        "production_projection_source_exists": False,
        "production_projection_source_valid": False,
        "route_scoped_without_user_dimensions": False,
        "client_override_allowed": False,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "approval_claimed": False,
    }
