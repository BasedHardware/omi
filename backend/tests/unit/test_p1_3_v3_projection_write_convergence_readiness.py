import importlib.util
import json
from pathlib import Path

REQUIRED_REQUIREMENT_IDS = [
    "route_scoped_projection_write_convergence_source",
    "durable_outbox_acknowledged_before_projection_reads",
    "dual_write_projection_writer_ready",
    "delete_tombstone_convergence_complete",
    "idempotency_key_contract",
    "generation_freshness_tombstone_vector_fences_aligned",
    "rollback_behavior_fail_closed",
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
    "delete_memory_vector",
    "requests.",
    "httpx.",
    "telemetry_client",
    "posthog",
]


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_projection_write_convergence_readiness", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module():
    root = Path(__file__).resolve().parents[2]
    return _load_module(root / "scripts" / "p1_3_v3_projection_write_convergence_readiness.py")


def _report(execute=False, env=None, reader=None):
    return _module().build_report(execute=execute, env={} if env is None else env, reader=reader)


def test_projection_write_convergence_readiness_is_safe_blocked_by_default():
    report = _report(execute=False)

    assert report["artifact"] == "v17_p1_3_v3_projection_write_convergence_readiness"
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
    assert report["summary"]["missing_prerequisite_count"] == 5


def test_projection_write_convergence_contract_inventories_required_evidence_shape():
    report = _report(execute=True)
    contract = report["projection_write_convergence_contract"]
    requirements = {item["requirement_id"]: item for item in report["write_convergence_requirements"]}

    assert list(requirements) == REQUIRED_REQUIREMENT_IDS
    assert contract["route_scope"] == "GET /v3/memories"
    assert contract["source_type"] == "firestore_v17_projection_write_convergence_state"
    assert contract["state_path_template"] == "memory_control/v17_projection_write_convergence"
    assert (
        contract["route_state_path_template"]
        == "memory_control/v17_projection_write_convergence/routes/{route_scope_label}"
    )
    assert contract["server_owned"] is True
    assert contract["client_override_allowed"] is False
    assert contract["client_controlled_collection_or_path_allowed"] is False
    assert contract["durable_outbox_required"] is True
    assert contract["dual_write_projection_writer_required"] is True
    assert contract["idempotency_key_required"] is True
    assert contract["fail_closed_on_missing_stale_malformed_evidence"] is True
    assert contract["legacy_fallback_allowed"] is False
    assert contract["merge_legacy_and_v17_allowed"] is False
    assert contract["required_fence_fields"] == [
        "account_generation",
        "projection_generation",
        "freshness_fence_generation",
        "tombstone_fence_generation",
        "vector_cleanup_fence_generation",
    ]

    assert requirements["durable_outbox_acknowledged_before_projection_reads"]["all_outbox_events_acknowledged"] is True
    assert requirements["dual_write_projection_writer_ready"]["projection_writer_ready"] is True
    assert requirements["delete_tombstone_convergence_complete"]["delete_tombstone_convergence_complete"] is True
    assert requirements["idempotency_key_contract"]["idempotency_key_required"] is True
    assert requirements["rollback_behavior_fail_closed"]["rollback_to_legacy_after_v17_write_allowed"] is False


def test_projection_write_convergence_missing_env_execute_is_blocked_without_reads():
    report = _report(execute=True, env={})

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
    assert report["firestore_reads_executed"] is False
    proof = report["production_write_convergence_proof"]
    assert proof["missing_prerequisites"] == [
        "V17_V3_PROJECTION_WRITE_CONVERGENCE_PROD_READ_ALLOW=1",
        "V17_V3_PROJECTION_WRITE_CONVERGENCE_PROD_READ_PROJECT_ID or GOOGLE_CLOUD_PROJECT",
        "GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNT_JSON",
        "V17_V3_PROJECTION_WRITE_CONVERGENCE_PROD_READ_SERVICE_ACCOUNT_EMAIL",
        "V17_V3_PROJECTION_WRITE_CONVERGENCE_PROD_READ_ROUTE_SCOPE_LABEL",
    ]
    assert proof["production_convergence_evidence_exists"] is False
    assert proof["production_convergence_evidence_valid"] is False
    assert proof["evidence_validation_reason"] == "not_run"


def test_projection_write_convergence_gated_reader_validates_evidence_read_only():
    module = _module()
    env = {
        module.ALLOW_ENV: "1",
        module.PROJECT_ID_ENV: "omi-prod",
        module.SERVICE_ACCOUNT_EMAIL_ENV: "backend@omi-prod.iam.gserviceaccount.com",
        module.SERVICE_ACCOUNT_JSON_ENV: "{}",
        module.ROUTE_SCOPE_LABEL_ENV: module.ROUTE_SCOPE_LABEL,
    }

    report = _report(
        execute=True,
        env=env,
        reader=lambda route_scope_label: module.example_valid_convergence_evidence(route_scope_label),
    )

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "PROVEN_READ_ONLY"
    assert report["read_only"] is True
    assert report["firestore_reads_executed"] is True
    assert report["firestore_writes_executed"] is False
    proof = report["production_write_convergence_proof"]
    assert proof["backend_service_principal_read_proven"] is True
    assert proof["production_convergence_evidence_exists"] is True
    assert proof["production_convergence_evidence_valid"] is True
    assert proof["evidence_validation_reason"] == "convergence_evidence_valid"
    assert proof["fences_aligned"] is True
    assert proof["rollback_fail_closed"] is True


def test_projection_write_convergence_gated_reader_fails_closed_on_missing_stale_or_malformed_evidence():
    module = _module()
    env = {
        module.ALLOW_ENV: "1",
        module.PROJECT_ID_ENV: "omi-prod",
        module.SERVICE_ACCOUNT_EMAIL_ENV: "backend@omi-prod.iam.gserviceaccount.com",
        module.SERVICE_ACCOUNT_JSON_ENV: "{}",
        module.ROUTE_SCOPE_LABEL_ENV: module.ROUTE_SCOPE_LABEL,
    }

    missing = _report(execute=True, env=env, reader=lambda route_scope_label: None)
    assert missing["proof_status"] == "BLOCKED"
    assert missing["production_write_convergence_proof"]["evidence_validation_reason"] == "convergence_evidence_missing"

    malformed = _report(execute=True, env=env, reader=lambda route_scope_label: {"route_scope": "GET /v3/memories"})
    assert malformed["proof_status"] == "BLOCKED"
    assert malformed["production_write_convergence_proof"]["evidence_validation_reason"] in {
        "convergence_evidence_missing_required_fields",
        "convergence_evidence_malformed",
    }

    stale = module.example_valid_convergence_evidence(module.ROUTE_SCOPE_LABEL)
    stale["max_staleness_seconds"] = module.MAX_STALENESS_SECONDS + 1
    stale_report = _report(execute=True, env=env, reader=lambda route_scope_label: stale)
    assert stale_report["proof_status"] == "BLOCKED"
    assert (
        stale_report["production_write_convergence_proof"]["evidence_validation_reason"]
        == "convergence_evidence_staleness_unbounded"
    )


def test_projection_write_convergence_static_script_has_no_mutating_paths_route_imports_or_sensitive_logging():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "p1_3_v3_projection_write_convergence_readiness.py"
    script_text = script_path.read_text(encoding="utf-8")

    for token in FORBIDDEN_STATIC_TOKENS:
        assert token not in script_text
    for sensitive in ["cursor_token", "raw_cursor", "request_payload", "memory_content", "session_id", "secret"]:
        assert sensitive in script_text
    assert "telemetry_safe_labels" in script_text
    assert "client_override_allowed" in script_text
    assert "legacy_fallback_allowed" in script_text
    assert "rollback_to_legacy_after_v17_write_allowed" in script_text


def test_projection_write_convergence_readiness_is_registered_in_test_runner_docs_and_parent_readiness():
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    runtime_readiness = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external_readiness = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(
        encoding="utf-8"
    )

    assert "test_p1_3_v3_projection_write_convergence_readiness.py" in test_sh
    assert "p1_3_v3_projection_write_convergence_readiness.py" in ticket_doc
    assert "projection write convergence/freshness-fence readiness" in ticket_doc
    assert "p1_3_v3_projection_write_convergence_readiness.py" in oracle_doc
    assert "projection write convergence/freshness-fence readiness" in oracle_doc
    assert "projection_write_convergence_readiness_proof" in runtime_readiness
    assert "projection_write_convergence_readiness_proof" in external_readiness


def test_projection_write_convergence_summary_json_is_stable():
    decoded = json.loads(json.dumps(_report(execute=True), sort_keys=True))

    assert decoded["summary"] == {
        "status": "BLOCKED",
        "proof_status": "NOT_RUN",
        "missing_prerequisite_count": 5,
        "write_convergence_requirement_count": 8,
        "selected_source_count": 2,
        "backend_service_principal_read_proven": False,
        "production_convergence_evidence_exists": False,
        "production_convergence_evidence_valid": False,
        "fences_aligned": False,
        "rollback_fail_closed": False,
        "client_override_allowed": False,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "approval_claimed": False,
    }
