import importlib.util
import json
from pathlib import Path

REQUIRED_TELEMETRY_FIELD_IDS = [
    "read_source",
    "route_decision",
    "failure_reason",
    "control_generation",
    "projection_generation",
    "account_generation",
    "cursor_validation_result",
    "cursor_validation_reason",
    "canary_cohort",
    "canary_enrollment",
    "no_legacy_fallback",
    "projection_source",
    "request_limit",
    "request_cursor_present",
    "request_offset_disallowed_in_v17",
    "archive_default_visibility_decision",
    "short_term_default_visibility_decision",
    "rollback_read_disable_gate",
    "approval_owner",
    "approval_status",
]


REQUIRED_GUARDRAIL_IDS = {
    "no_pii_or_raw_memory_content",
    "low_cardinality_failure_reasons_only",
    "no_secret_or_cursor_token_logging",
    "no_production_calls_by_default",
    "no_approval_claimed_by_readiness",
}


REQUIRED_BLOCKER_IDS = {
    "v3_route_telemetry_not_runtime_wired",
    "memory_v3_prometheus_metrics_missing",
    "structured_event_sink_not_selected",
    "canary_enrollment_artifact_missing",
    "rollback_read_disable_gate_not_wired_to_v3_get",
    "approval_artifact_missing",
}


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("v17_p1_3_v3_observability_approval_readiness", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=False):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "v17_p1_3_v3_observability_approval_readiness.py")
    return module.build_report(execute=execute)


def test_observability_approval_readiness_runner_exists_and_is_safe_by_default():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "v17_p1_3_v3_observability_approval_readiness.py"
    assert script_path.exists(), "missing safe observability/approval readiness runner"

    report = _report(execute=False)

    assert report["artifact"] == "v17_p1_3_v3_observability_approval_readiness"
    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "NOT_RUN"
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
    assert report["execute"] is False


def test_observability_approval_readiness_inventories_required_low_cardinality_fields():
    report = _report(execute=True)

    assert report["proof_status"] == "BLOCKED"
    fields = {field["field_id"]: field for field in report["required_telemetry_fields"]}
    assert list(fields) == REQUIRED_TELEMETRY_FIELD_IDS

    for field_id, field in fields.items():
        assert field["status"] in {"BLOCKED", "NOT_RUN"}, field_id
        assert field["route_refs"] == ["GET /v3/memories"]
        assert field["required_before_runtime_change"] is True
        assert field["runtime_wired"] is False
        assert field["approval_claimed"] is False
        assert field["contains_pii"] is False
        assert field["contains_raw_memory_content"] is False
        assert field["logs_secret_or_cursor_token"] is False
        assert field["cardinality"] in {"low", "bounded_integer", "boolean", "owner_identifier"}

    assert fields["read_source"]["allowed_values"] == ["legacy_primary", "v17_compatibility_projection", "fail_closed"]
    assert "control_timeout" in fields["failure_reason"]["allowed_values"]
    assert "cursor_tampered" in fields["cursor_validation_reason"]["allowed_values"]
    assert fields["no_legacy_fallback"]["allowed_values"] == [True]
    assert fields["request_offset_disallowed_in_v17"]["allowed_values"] == [True]
    assert fields["rollback_read_disable_gate"]["allowed_values"] == ["not_wired", "disabled", "enabled"]
    assert fields["approval_status"]["allowed_values"] == ["missing", "pending", "approved", "rejected"]


def test_observability_approval_readiness_links_existing_mechanisms_and_exact_blockers():
    report = _report(execute=True)

    mechanisms = {mechanism["mechanism_id"]: mechanism for mechanism in report["existing_mechanisms"]}
    assert (
        mechanisms["prometheus_metrics_endpoint"]["source"] == "backend/routers/metrics.py + backend/utils/metrics.py"
    )
    assert mechanisms["prometheus_metrics_endpoint"]["status"] == "EXISTS_NOT_V3_WIRED"
    assert mechanisms["prometheus_metrics_endpoint"]["production_call_executed"] is False
    assert mechanisms["log_sanitizer"]["source"] == "backend/utils/log_sanitizer.py"
    assert mechanisms["log_sanitizer"]["status"] == "EXISTS_REQUIRED_FOR_FUTURE_WIRING"
    assert mechanisms["v17_read_decision_model"]["source"] == "backend/utils/memory/v17_default_read_rollout.py"
    assert mechanisms["v17_read_decision_model"]["status"] == "EXISTS_NOT_V3_GET_WIRED"
    assert mechanisms["v17_v3_local_telemetry_and_rollback_seam"]["source"] == (
        "backend/utils/memory/v17_v3_local_telemetry.py"
    )
    assert mechanisms["v17_v3_local_telemetry_and_rollback_seam"]["test"] == (
        "backend/tests/unit/test_v17_v3_local_telemetry.py"
    )
    assert mechanisms["v17_v3_local_telemetry_and_rollback_seam"]["status"] == ("LOCAL_SEAM_PROVED_NOT_V3_GET_WIRED")
    assert mechanisms["v17_v3_local_telemetry_and_rollback_seam"]["production_call_executed"] is False
    assert mechanisms["v17_v3_local_telemetry_and_rollback_seam"]["runtime_wired_to_v3_get"] is False

    blockers = {blocker["blocker_id"]: blocker for blocker in report["blockers"]}
    assert set(blockers) == REQUIRED_BLOCKER_IDS
    for blocker in blockers.values():
        assert blocker["status"] == "BLOCKED"
        assert blocker["required_before_runtime_change"] is True
        assert blocker["approval_claimed"] is False


def test_observability_approval_readiness_static_guardrails_preserve_non_claims():
    report = _report(execute=True)

    guardrails = {guardrail["guardrail_id"]: guardrail for guardrail in report["static_guardrails"]}
    assert REQUIRED_GUARDRAIL_IDS.issubset(guardrails)
    assert guardrails["no_pii_or_raw_memory_content"]["status"] == "READY_FOR_REQUIREMENT"
    assert guardrails["low_cardinality_failure_reasons_only"]["status"] == "READY_FOR_REQUIREMENT"
    assert guardrails["no_secret_or_cursor_token_logging"]["status"] == "READY_FOR_REQUIREMENT"
    assert guardrails["no_production_calls_by_default"]["status"] == "READY_FOR_REQUIREMENT"
    assert guardrails["no_approval_claimed_by_readiness"]["status"] == "READY_FOR_REQUIREMENT"

    non_claims = "\n".join(report["non_claims"])
    assert "No backend/routers/memories.py runtime wiring changed." in non_claims
    assert "No telemetry sink production call executed or claimed." in non_claims
    assert "No PII/raw memory content telemetry emitted." in non_claims
    assert "No secret or cursor token logging allowed or performed." in non_claims
    assert "No production rollout approval claimed." in non_claims
    assert "No Archive default visibility or stale Short-term default visibility claimed." in non_claims


def test_observability_approval_readiness_json_summary_is_stable():
    decoded = json.loads(json.dumps(_report(execute=True), sort_keys=True))

    assert decoded["summary"] == {
        "status": "BLOCKED",
        "proof_status": "BLOCKED",
        "telemetry_field_count": 20,
        "blocked_or_not_run_field_count": 20,
        "existing_mechanism_count": 4,
        "blocker_count": 6,
        "guardrail_count": 5,
        "telemetry_sink_calls_executed": False,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "approval_claimed": False,
    }


def test_observability_approval_readiness_registered_in_test_runner_docs_and_parent_readiness():
    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "v17_memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "v17_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    runtime_readiness = (root / "scripts" / "v17_p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external_readiness = (root / "scripts" / "v17_p1_3_v3_external_compatibility_readiness.py").read_text(
        encoding="utf-8"
    )

    assert "test_v17_p1_3_v3_observability_approval_readiness.py" in test_sh
    assert "test_v17_v3_local_telemetry.py" in test_sh
    assert "v17_p1_3_v3_observability_approval_readiness.py" in ticket_doc
    assert "observability/telemetry approval readiness" in ticket_doc
    assert "v17_p1_3_v3_observability_approval_readiness.py" in oracle_doc
    assert "observability/telemetry approval readiness" in oracle_doc
    assert "observability_approval_readiness_proof" in runtime_readiness
    assert "v17_p1_3_v3_observability_approval_readiness.py" in external_readiness
