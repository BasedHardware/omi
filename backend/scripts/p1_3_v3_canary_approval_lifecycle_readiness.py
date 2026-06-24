#!/usr/bin/env python3
"""Safe V17 `/v3` canary approval lifecycle/evidence-bundle readiness contract.

This readiness artifact is local-only and pre-runtime. It defines the human/ops
approval evidence bundle, expiry/rotation rules, rollback ownership, monitoring
gates, audit references, and route scope that must exist before the future
`GET /v3/memories` canary approval artifact can be considered production-usable.
It does not import FastAPI routers, read or write production services, call cloud
or vector providers, emit telemetry sinks, or claim rollout approval.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

ROUTE_SCOPE = "GET /v3/memories"
ARTIFACT_DOCUMENT_PATH = "system/v17_v3_canary_approvals/routes/get_v3_memories"
ARTIFACT_SOURCE = f"firestore:{ARTIFACT_DOCUMENT_PATH}"
OWNER_GROUPS = ["product_privacy_ops", "memory_platform_oncall"]
APPROVER_ROLES = ["product_privacy_ops"]
ROLLBACK_OWNER_GROUPS = ["memory_platform_oncall", "product_privacy_ops"]
MONITORING_GATE_IDS = [
    "fail_closed_rate",
    "p95_latency_ms",
    "error_rate",
    "projection_freshness_seconds",
]

APPROVAL_LIFECYCLE_CONTRACT = {
    "route_scope": ROUTE_SCOPE,
    "artifact_source": ARTIFACT_SOURCE,
    "evidence_bundle_required_before_production_use": True,
    "owner_groups": OWNER_GROUPS,
    "approver_roles": APPROVER_ROLES,
    "rollback_owner_groups": ROLLBACK_OWNER_GROUPS,
    "monitoring_gate_ids": MONITORING_GATE_IDS,
    "approval_ids_and_timestamps_are_metadata_only": True,
    "max_lifetime_hours": 24,
    "rotation_required_before_expires_at": True,
    "explicit_route_scope_required": True,
    "runtime_wired_to_v3_get": False,
    "production_rollout_approved": False,
    "approval_claimed": False,
}

REQUIRED_EVIDENCE_BUNDLE = [
    {
        "evidence_id": "human_ops_approval_ticket_present",
        "status": "BLOCKED",
        "required_fields": ["approval_ticket_id", "approval_id"],
        "metadata_only": True,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "evidence_id": "bounded_owner_groups_and_approver_role_present",
        "status": "BLOCKED",
        "required_fields": ["owner_group", "approver_role"],
        "allowed_owner_groups": OWNER_GROUPS,
        "allowed_approver_roles": APPROVER_ROLES,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "evidence_id": "issued_approved_expires_rotation_window_valid",
        "status": "BLOCKED",
        "required_fields": ["issued_at", "approved_at", "expires_at"],
        "max_lifetime_hours": 24,
        "approved_at_must_be_between_issued_and_expires": True,
        "rotation_required_before_expires_at": True,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "evidence_id": "rollback_owner_and_steps_present",
        "status": "BLOCKED",
        "required_fields": ["rollback_owner", "rollback_steps"],
        "allowed_rollback_owner_groups": ROLLBACK_OWNER_GROUPS,
        "minimum_step_count": 2,
        "must_include_disable_and_verify_steps": True,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "evidence_id": "monitoring_gate_ids_present",
        "status": "BLOCKED",
        "required_fields": ["monitoring_gate_ids"],
        "required_gate_ids": MONITORING_GATE_IDS,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "evidence_id": "production_read_proof_reference_present",
        "status": "BLOCKED",
        "reference": "backend/scripts/p1_3_v3_canary_approval_production_readiness.py",
        "must_prove_backend_service_principal_read": True,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "evidence_id": "iam_emulator_proof_reference_present",
        "status": "BLOCKED",
        "reference": "backend/scripts/p1_3_v3_canary_approval_source_readiness.py",
        "must_prove_direct_client_denial_and_backend_read_source": True,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "evidence_id": "telemetry_runbook_reference_present",
        "status": "BLOCKED",
        "reference": "backend/scripts/p1_3_v3_observability_approval_readiness.py",
        "must_prove_observable_gates_and_runbook": True,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "evidence_id": "explicit_route_scope_matches_get_v3_memories",
        "status": "BLOCKED",
        "expected_route_scope": ROUTE_SCOPE,
        "route_scope_is_exact": True,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
]

FAIL_CLOSED_SEMANTICS = [
    {
        "state": "approval_evidence_missing",
        "future_route_behavior": "fail_closed_before_v17_read",
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "state": "approval_evidence_stale_or_unrotated",
        "future_route_behavior": "fail_closed_before_v17_read",
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "state": "rollback_owner_or_steps_missing",
        "future_route_behavior": "fail_closed_before_v17_read",
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "state": "monitoring_gates_missing",
        "future_route_behavior": "fail_closed_before_v17_read",
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "state": "production_read_proof_missing",
        "future_route_behavior": "fail_closed_before_v17_read",
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "state": "iam_emulator_proof_missing",
        "future_route_behavior": "fail_closed_before_v17_read",
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
    {
        "state": "route_scope_mismatch",
        "future_route_behavior": "fail_closed_before_v17_read",
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
        "approval_claimed": False,
    },
]


def build_report(*, execute: bool = False) -> dict[str, Any]:
    proof_status = "BLOCKED" if execute else "NOT_RUN"
    blocked_required_evidence_count = sum(1 for item in REQUIRED_EVIDENCE_BUNDLE if item["status"] == "BLOCKED")
    return {
        "artifact": "v17_p1_3_v3_canary_approval_lifecycle_readiness",
        "status": "BLOCKED",
        "proof_status": proof_status,
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "routers_memories_modified": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "telemetry_sink_calls_executed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "scope": "Read-only lifecycle and evidence-bundle readiness contract for future GET /v3/memories canary approval.",
        "approval_lifecycle_contract": APPROVAL_LIFECYCLE_CONTRACT,
        "required_evidence_bundle": REQUIRED_EVIDENCE_BUNDLE,
        "fail_closed_semantics": FAIL_CLOSED_SEMANTICS,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No runtime /v3 behavior changed.",
            "No production rollout approval claimed.",
            "No production Firestore/cloud/provider/vector/network calls executed.",
            "No telemetry sink production call executed or claimed.",
            "No PII/raw content telemetry emitted.",
            "No secret/cursor logging allowed or performed.",
            "No legacy fallback/merge for V17 failures claimed.",
            "No Archive default visibility or stale Short-term default visibility claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "proof_status": proof_status,
            "required_evidence_count": len(REQUIRED_EVIDENCE_BUNDLE),
            "blocked_required_evidence_count": blocked_required_evidence_count,
            "fail_closed_semantics_count": len(FAIL_CLOSED_SEMANTICS),
            "read_only": True,
            "mutation_allowed": False,
            "runtime_wiring_changed": False,
            "production_rollout_approved": False,
            "approval_claimed": False,
            "route_scope": ROUTE_SCOPE,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Emit safe BLOCKED lifecycle/evidence-bundle inventory")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
