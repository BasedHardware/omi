"""Production-safe projection write convergence evidence read proof."""

from __future__ import annotations

from tests.unit.v3_prod_read_probes import projection_write_convergence as module

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


def test_contract_inventories_required_evidence_shape():
    report = module.build_report(execute=True, env={})
    contract = report["projection_write_convergence_contract"]
    requirements = {item["requirement_id"]: item for item in report["write_convergence_requirements"]}
    assert list(requirements) == REQUIRED_REQUIREMENT_IDS
    assert contract["route_scope"] == "GET /v3/memories"
    assert contract["server_owned"] is True
    assert contract["client_override_allowed"] is False
    assert contract["legacy_fallback_allowed"] is False


def test_missing_env_execute_is_blocked_without_reads():
    report = module.build_report(execute=True, env={})
    assert report["firestore_reads_executed"] is False
    proof = report["production_write_convergence_proof"]
    assert proof["production_convergence_evidence_exists"] is False
    assert proof["evidence_validation_reason"] == "not_run"
    assert len(proof["missing_prerequisites"]) == 5


def test_gated_reader_validates_evidence_read_only():
    env = {
        module.ALLOW_ENV: "1",
        module.PROJECT_ID_ENV: "omi-prod",
        module.SERVICE_ACCOUNT_EMAIL_ENV: "backend@omi-prod.iam.gserviceaccount.com",
        module.SERVICE_ACCOUNT_JSON_ENV: "{}",
        module.ROUTE_SCOPE_LABEL_ENV: module.ROUTE_SCOPE_LABEL,
    }
    report = module.build_report(
        execute=True,
        env=env,
        reader=lambda route_scope_label: module.example_valid_convergence_evidence(route_scope_label),
    )
    proof = report["production_write_convergence_proof"]
    assert proof["production_convergence_evidence_valid"] is True
    assert proof["evidence_validation_reason"] == "convergence_evidence_valid"
    assert proof["fences_aligned"] is True
    assert report["firestore_writes_executed"] is False


def test_gated_reader_fails_closed_on_missing_or_malformed_evidence():
    env = {
        module.ALLOW_ENV: "1",
        module.PROJECT_ID_ENV: "omi-prod",
        module.SERVICE_ACCOUNT_EMAIL_ENV: "backend@omi-prod.iam.gserviceaccount.com",
        module.SERVICE_ACCOUNT_JSON_ENV: "{}",
        module.ROUTE_SCOPE_LABEL_ENV: module.ROUTE_SCOPE_LABEL,
    }

    missing = module.build_report(execute=True, env=env, reader=lambda route_scope_label: None)
    assert missing["production_write_convergence_proof"]["evidence_validation_reason"] == "convergence_evidence_missing"

    stale = module.example_valid_convergence_evidence(module.ROUTE_SCOPE_LABEL)
    stale["max_staleness_seconds"] = module.MAX_STALENESS_SECONDS + 1
    stale_report = module.build_report(execute=True, env=env, reader=lambda route_scope_label: stale)
    assert (
        stale_report["production_write_convergence_proof"]["evidence_validation_reason"]
        == "convergence_evidence_staleness_unbounded"
    )
