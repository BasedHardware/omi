"""Pure memory-V3-F6H pre-GCP aggregate report builder."""

from __future__ import annotations

from typing import Any

from testing.memory.v3_f6.protocol import (
    ARTIFACT_VERSION_F6H,
    DECISION_BLOCKED_ON_GCP_ACCESS,
    DECISION_NO_GO,
    STATUS_BLOCKED,
    STATUS_BLOCKED_ON_GCP_ACCESS,
    STATUS_MISSING,
    STATUS_PASS,
    STATUS_PRE_GCP_READY,
)

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
        gate_id
        for gate_id in known & provided
        if local_proofs[gate_id].get("status") not in {STATUS_PASS, STATUS_PRE_GCP_READY}
    )
    local_rows = [
        {
            "gate_id": gate_id,
            "status": local_proofs.get(gate_id, {}).get("status", STATUS_MISSING),
            "evidence": local_proofs.get(gate_id, {}).get("evidence"),
        }
        for gate_id in F6_LOCAL_GATE_IDS
    ]
    gcp_rows = [
        {
            "gate_id": gate_id,
            "status": STATUS_BLOCKED_ON_GCP_ACCESS,
            "evidence": None,
        }
        for gate_id in GCP_ACCESS_GATE_IDS
    ]
    local_ready = not missing and not unknown and not failed
    return {
        "artifact_version": ARTIFACT_VERSION_F6H,
        "status": STATUS_PRE_GCP_READY if local_ready else STATUS_BLOCKED,
        "decision": DECISION_BLOCKED_ON_GCP_ACCESS if local_ready else DECISION_NO_GO,
        "local_gates": local_rows,
        "gcp_access_gates": gcp_rows,
        "missing_local_gates": missing,
        "unknown_local_gates": unknown,
        "failed_local_gates": failed,
        "remaining_blockers": ["gcp_access"] if local_ready else ["local_pre_gcp_gates", "gcp_access"],
        "non_claims": NON_CLAIMS,
    }
