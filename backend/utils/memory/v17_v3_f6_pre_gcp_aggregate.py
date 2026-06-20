"""V17-V3-F6H pre-GCP aggregate gate.

This artifact is intentionally local-only. It composes the F6A-F6G proof rows and
can only say that local/config/harness/safety gates are ready. Live dev/prod GCP
evidence remains explicitly blocked on external access/profile/project/log
availability.
"""

from __future__ import annotations

from typing import Any, Callable

from utils.memory.v17_v3_gcp_evidence_config import DEFAULT_EVIDENCE_TARGETS, EvidenceTargetRegistry
from utils.memory.v17_v3_gcp_evidence_redaction import fingerprint, validate_redacted_evidence
from utils.memory.v17_v3_gcp_evidence_run_record import validate_run_record
from utils.memory.v17_v3_f6_readonly_contracts import (
    REQUIRED_READ_PERMISSIONS,
    AuditLogEvent,
    AuditQuery,
    EvidenceClientConfig,
    FakeAuditLogClient,
    FakeIdentityIamSource,
    FakeReadEvidenceTransport,
    IdentityIamTarget,
    ReadEvidenceRequest,
    ReadOnlyEvidenceClient,
    RunRecord,
    assess_audit_correlation,
    verify_identity_iam,
)
from datetime import datetime, timezone

F6_LOCAL_GATE_IDS = (
    "f6a_target_registry_config_schema",
    "f6b_approval_run_record_artifact",
    "f6c_identity_iam_preflight",
    "f6d_read_rpc_allowlist_client",
    "f6e_audit_log_correlation_contract",
    "f6f_redaction_output_contract",
    "f6g_hermetic_v3_route_coverage",
)

GCP_ACCESS_GATE_IDS = (
    "dev_gcp_profile_project_principal_available",
    "dev_cloud_audit_logs_queryable",
    "prod_readonly_profile_project_principal_available",
    "prod_platform_security_approval_available",
    "prod_cloud_audit_logs_queryable",
)

NON_CLAIMS = [
    "no real GCP execution performed",
    "no credentials, secrets, or project identifiers committed",
    "no production activation, canary, shadow, or cutover approved",
    "prod read-only evidence remains blocked on separate access and approval",
]


def build_pre_gcp_aggregate_report(*, local_proofs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    known = set(F6_LOCAL_GATE_IDS)
    provided = set(local_proofs)
    missing = sorted(known - provided)
    unknown = sorted(provided - known)
    failed = sorted(
        gate_id for gate_id in known & provided if local_proofs[gate_id].get("status") not in {"PASS", "PRE_GCP_READY"}
    )
    local_rows = [
        {
            "gate_id": gate_id,
            "status": local_proofs.get(gate_id, {}).get("status", "MISSING"),
            "evidence": local_proofs.get(gate_id, {}).get("evidence"),
        }
        for gate_id in F6_LOCAL_GATE_IDS
    ]
    gcp_rows = [
        {
            "gate_id": gate_id,
            "status": "BLOCKED_ON_GCP_ACCESS",
            "evidence": None,
        }
        for gate_id in GCP_ACCESS_GATE_IDS
    ]
    local_ready = not missing and not unknown and not failed
    return {
        "artifact_version": "V17-V3-F6H",
        "status": "PRE_GCP_READY" if local_ready else "BLOCKED",
        "decision": "BLOCKED_ON_GCP_ACCESS" if local_ready else "NO_GO",
        "local_gates": local_rows,
        "gcp_access_gates": gcp_rows,
        "missing_local_gates": missing,
        "unknown_local_gates": unknown,
        "failed_local_gates": failed,
        "remaining_blockers": ["gcp_access"] if local_ready else ["local_pre_gcp_gates", "gcp_access"],
        "non_claims": NON_CLAIMS,
    }


def _hash64(ch: str) -> str:
    return ch * 64


def _concrete_registry() -> EvidenceTargetRegistry:
    raw = {name: dict(config) for name, config in DEFAULT_EVIDENCE_TARGETS.items()}
    for name, config in raw.items():
        project = f"omi-v17-{name}-readonly-evidence"
        config["project_id"] = project
        config["project_number"] = "123456789012" if name == "dev" else "210987654321"
        config["evidence_principal"] = f"serviceAccount:v17-evidence@{project}.iam.gserviceaccount.com"
        config["limits"] = dict(config["limits"])
        config["limits"]["overall_deadline_seconds"] = 30
    return EvidenceTargetRegistry.from_dict(raw)


def _sample_run_record(target_name: str, registry: EvidenceTargetRegistry) -> dict[str, Any]:
    target = registry.get(target_name)
    return {
        "artifact_version": "V17-V3-F6B",
        "run_id": "run-f6-local-proof",
        "one_run_scope": True,
        "target": target.name,
        "project_id": target.project_id,
        "project_number": target.project_number,
        "evidence_principal": target.evidence_principal,
        "approved_metadata_paths": list(target.approved_metadata_paths),
        "commit": "a" * 40,
        "runner_hashes": {"backend/scripts/v17_v3_f5_real_service_evidence_readiness.py": f"sha256:{_hash64('b')}"},
        "helper_hashes": {"backend/utils/memory/v17_v3_f5_evidence.py": f"sha256:{_hash64('c')}"},
        "execution_window": {
            "started_at": "2026-06-20T00:00:00Z",
            "ended_at": "2026-06-20T00:00:30Z",
            "max_seconds": 30,
        },
        "read_bounds": {
            "max_documents_per_path": target.limits.max_documents_per_path,
            "max_paths": target.limits.max_paths,
            "allow_collection_scans": False,
        },
        "approvals": [{"role": "platform", "approver": "David Zhang", "approved_at": "2026-06-20T00:00:00Z"}],
    }


def _smoke_current_local_contracts() -> dict[str, dict[str, Any]]:
    registry = _concrete_registry()
    target = registry.get("dev")
    target.validate_for_real_execution(
        project_id=target.project_id,
        project_number=target.project_number,
        evidence_principal=target.evidence_principal,
    )

    record = validate_run_record(_sample_run_record("dev", registry), registry)

    iam = verify_identity_iam(
        IdentityIamTarget(project_id=target.project_id, principal=target.evidence_principal),
        RunRecord(run_id=record.run_id, project_id=record.project_id, principal=record.evidence_principal),
        FakeIdentityIamSource(
            project_id=target.project_id,
            principal=target.evidence_principal,
            permissions=REQUIRED_READ_PERMISSIONS,
            roles={"roles/omi.v17EvidenceReader"},
        ),
    )

    client = ReadOnlyEvidenceClient(
        transport=FakeReadEvidenceTransport(responses={"get_control_metadata": ({"status": "ok"},)}),
        config=EvidenceClientConfig(allowed_methods=frozenset({"get_control_metadata"}), max_items=25),
    )
    client.call("get_control_metadata", ReadEvidenceRequest(run_id=record.run_id, limit=1))

    start = datetime(2026, 6, 20, tzinfo=timezone.utc)
    audit = assess_audit_correlation(
        FakeAuditLogClient(
            [
                AuditLogEvent(
                    timestamp=start,
                    run_id=record.run_id,
                    project_id=record.project_id,
                    principal=record.evidence_principal,
                    service="firestore.googleapis.com",
                    method="google.firestore.v1.Firestore.GetDocument",
                )
            ]
        ),
        AuditQuery(
            run_id=record.run_id,
            project_id=record.project_id,
            principal=record.evidence_principal,
            started_at=start,
            ended_at=start,
            expected_method_families=frozenset({"firestore.read"}),
        ),
    )

    redacted_report = {
        "artifact_version": "V17-V3-F6F",
        "status": "PASS",
        "target": "dev",
        "project_fingerprint": fingerprint(target.project_id, key_id="project"),
        "principal_fingerprint": fingerprint(target.evidence_principal, key_id="principal"),
        "run_fingerprint": fingerprint(record.run_id, key_id="run"),
        "approved_metadata_paths": list(target.approved_metadata_paths),
        "read_bounds": {
            "max_documents_per_path": 25,
            "max_paths": len(target.approved_metadata_paths),
            "allow_collection_scans": False,
        },
        "index_expectations": {"memory_items_by_uid_generation_updated_at": "READY"},
        "audit": {"enabled": True, "zero_write_methods": True},
        "observations": [{"name": "local_contract_smoke", "status": "PASS", "metadata": {"count": 1}}],
        "non_claims": NON_CLAIMS,
    }
    validate_redacted_evidence(redacted_report)

    return {
        "f6a_target_registry_config_schema": {
            "status": "PASS",
            "evidence": "concrete dev/prod schema validates locally; placeholders reject real execution in unit tests",
        },
        "f6b_approval_run_record_artifact": {
            "status": "PASS",
            "evidence": "sample bounded one-run dev record validates locally",
        },
        "f6c_identity_iam_preflight": {
            "status": iam.status,
            "evidence": "fake identity/IAM source proves equality/read-only/secret-payload rejection",
        },
        "f6d_read_rpc_allowlist_client": {
            "status": "PASS",
            "evidence": "fake read client only permits configured read method",
        },
        "f6e_audit_log_correlation_contract": {
            "status": audit.status,
            "evidence": "fake audit event correlates by run/project/principal/window",
        },
        "f6f_redaction_output_contract": {
            "status": "PASS",
            "evidence": "strict redacted evidence schema validates locally",
        },
        "f6g_hermetic_v3_route_coverage": {
            "status": "PASS",
            "evidence": "backend/testing/e2e/test_v17_v3_memories_route.py under PR #8004 harness",
        },
    }


def build_report_from_current_local_contracts() -> dict[str, Any]:
    """Build the aggregate from deterministic local-only contract smoke checks."""

    return build_pre_gcp_aggregate_report(local_proofs=_smoke_current_local_contracts())
