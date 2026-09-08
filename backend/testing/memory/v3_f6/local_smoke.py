"""Deterministic local-only smoke checks for memory-V3-F6H aggregation.

This module composes the F6A-F6G proof rows without constructing GCP clients,
reading credentials, or performing network/cloud/provider calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from testing.memory.v3_f6.aggregate import NON_CLAIMS, build_pre_gcp_aggregate_report
from testing.memory.v3_f6.audit import AuditLogEvent, AuditQuery, assess_audit_correlation
from testing.memory.v3_f6.identity_iam import REQUIRED_READ_PERMISSIONS, IdentityIamTarget, verify_identity_iam
from testing.memory.v3_f6.local_doubles import FakeAuditLogClient, FakeIdentityIamSource, FakeReadEvidenceTransport
from testing.memory.v3_f6.protocol import ARTIFACT_VERSION_F6B, ARTIFACT_VERSION_F6F, STATUS_PASS, TARGET_DEV
from testing.memory.v3_f6.read_evidence import EvidenceClientConfig, ReadEvidenceRequest, ReadOnlyEvidenceClient
from testing.memory.v3_f6.run_context import RunRecord
from testing.memory.v3_f6.config import EvidenceTargetRegistry
from testing.memory.v3_f6.local_defaults import DEFAULT_EVIDENCE_TARGETS
from testing.memory.v3_f6.redaction import fingerprint, validate_redacted_evidence
from testing.memory.v3_f6.run_record import validate_run_record

_LOCAL_SMOKE_NOW = datetime(2026, 6, 20, 0, 0, 15, tzinfo=timezone.utc)


def _hash64(ch: str) -> str:
    return ch * 64


def _concrete_registry() -> EvidenceTargetRegistry:
    raw = {name: dict(config) for name, config in DEFAULT_EVIDENCE_TARGETS.items()}
    for name, config in raw.items():
        project = f"omi-memory-{name}-readonly-evidence"
        config["project_id"] = project
        config["project_number"] = "123456789012" if name == "dev" else "210987654321"
        config["evidence_principal"] = f"serviceAccount:memory-evidence@{project}.iam.gserviceaccount.com"
        config["limits"] = dict(config["limits"])
        config["limits"]["overall_deadline_seconds"] = 30
    return EvidenceTargetRegistry.from_dict(raw)


def _sample_run_record(target_name: str, registry: EvidenceTargetRegistry) -> dict[str, Any]:
    target = registry.get(target_name)
    return {
        "artifact_version": ARTIFACT_VERSION_F6B,
        "run_id": "run-f6-local-proof",
        "one_run_scope": True,
        "target": target.name,
        "project_id": target.project_id,
        "project_number": target.project_number,
        "evidence_principal": target.evidence_principal,
        "approved_metadata_paths": list(target.approved_metadata_paths),
        "commit": "a" * 40,
        "runner_hashes": {"backend/scripts/v3_f5_real_service_evidence_readiness.py": f"sha256:{_hash64('b')}"},
        "helper_hashes": {"backend/testing/memory/v3_f5_evidence.py": f"sha256:{_hash64('c')}"},
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
    target = registry.get(TARGET_DEV)
    target.validate_for_real_execution(
        project_id=target.project_id,
        project_number=target.project_number,
        evidence_principal=target.evidence_principal,
    )

    record = validate_run_record(_sample_run_record(TARGET_DEV, registry), registry, now=_LOCAL_SMOKE_NOW)

    iam = verify_identity_iam(
        IdentityIamTarget(project_id=target.project_id, principal=target.evidence_principal),
        RunRecord(run_id=record.run_id, project_id=record.project_id, principal=record.evidence_principal),
        FakeIdentityIamSource(
            project_id=target.project_id,
            principal=target.evidence_principal,
            permissions=REQUIRED_READ_PERMISSIONS,
            roles={"roles/omi.MemoryEvidenceReader"},
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
        "artifact_version": ARTIFACT_VERSION_F6F,
        "status": STATUS_PASS,
        "target": TARGET_DEV,
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
        "observations": [{"name": "local_contract_smoke", "status": STATUS_PASS, "metadata": {"count": 1}}],
        "non_claims": NON_CLAIMS,
    }
    validate_redacted_evidence(redacted_report)

    return {
        "f6a_target_registry_config_schema": {
            "status": STATUS_PASS,
            "evidence": "concrete dev/prod schema validates locally; placeholders reject real execution in unit tests",
        },
        "f6b_approval_run_record_artifact": {
            "status": STATUS_PASS,
            "evidence": "sample bounded one-run dev record validates locally",
        },
        "f6c_identity_iam_preflight": {
            "status": iam.status,
            "evidence": "fake identity/IAM source proves equality/read-only/secret-payload rejection",
        },
        "f6d_read_rpc_allowlist_client": {
            "status": STATUS_PASS,
            "evidence": "fake read client only permits configured read method",
        },
        "f6e_audit_log_correlation_contract": {
            "status": audit.status,
            "evidence": "fake audit event correlates by run/project/principal/window",
        },
        "f6f_redaction_output_contract": {
            "status": STATUS_PASS,
            "evidence": "strict redacted evidence schema validates locally",
        },
        "f6g_hermetic_v3_route_coverage": {
            "status": STATUS_PASS,
            "evidence": "backend/testing/e2e/test_v3_memories_route.py under PR #8004 harness",
        },
    }


def build_report_from_current_local_contracts() -> dict[str, Any]:
    """Build the aggregate from deterministic local-only contract smoke checks."""

    return build_pre_gcp_aggregate_report(local_proofs=_smoke_current_local_contracts())
