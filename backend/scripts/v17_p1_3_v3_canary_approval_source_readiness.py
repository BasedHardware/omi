#!/usr/bin/env python3
"""Safe V17 `/v3` canary approval artifact source-selection readiness contract.

This artifact is deliberately pre-runtime and read-only. It selects and inventories
the future server-owned canary/approval artifact source, ownership groups, IAM/rules
constraints, privacy constraints, and fail-closed semantics required before any
`GET /v3/memories` runtime wiring may trust approval state. It does not import
FastAPI routers, read Firestore, call providers, mutate state, or claim approval.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

ROUTE_SCOPE = "GET /v3/memories"
ARTIFACT_DOCUMENT_PATH = "system/v17_v3_canary_approvals/routes/get_v3_memories"
FUTURE_ARTIFACT_SOURCE = f"firestore:{ARTIFACT_DOCUMENT_PATH}"
BOUNDED_OWNER_GROUPS = ["product_privacy_ops", "memory_platform_oncall"]
RULES_EMULATOR_COMMAND = "npm run test:v17-v3-canary-approval-source:emulator"

SOURCE_SELECTION_CONTRACT = {
    "route_scope": ROUTE_SCOPE,
    "future_artifact_source": FUTURE_ARTIFACT_SOURCE,
    "future_reader_shape": "server_backend_service_principal_reads_single_route_scoped_artifact",
    "server_owned_only": True,
    "client_supplied_artifact_trusted": False,
    "bounded_owner_groups": BOUNDED_OWNER_GROUPS,
    "artifact_path_dimensions": ["system", "v17_v3_canary_approvals", "routes", "get_v3_memories"],
    "forbidden_path_or_label_dimensions": [
        "uid",
        "user_id",
        "session_id",
        "memory_id",
        "cursor",
        "cursor_token",
        "token",
        "secret",
        "request_payload",
        "payload",
        "high_cardinality_labels",
    ],
    "approval_ids_and_timestamps_are_metadata_only": True,
    "production_approval_claimed": False,
    "production_artifact_source_status": "MISSING_NOT_RUN",
    "runtime_wired_to_v3_get": False,
}

REQUIRED_IAM_RULES_PRIVACY_PROOFS = [
    {
        "proof_id": "artifact_source_selected_server_owned_only",
        "status": "BLOCKED",
        "route_refs": [ROUTE_SCOPE],
        "required_evidence": (
            "Future approval state must come only from the selected server-owned artifact source; request bodies, "
            "headers, query params, client documents, or client-provided approval artifacts must never be trusted."
        ),
        "server_owned_only": True,
        "client_supplied_artifact_trusted": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "proof_id": "static_firestore_rules_emulator_harness_ready",
        "status": "READY_FOR_LOCAL_EMULATOR",
        "route_refs": [ROUTE_SCOPE],
        "required_evidence": (
            "Local Firestore rules/emulator harness includes the route-scoped system approval artifact path, proves "
            "signed-in client reads and writes are denied, and includes Admin-context read fixture coverage without "
            "calling production Firestore."
        ),
        "artifact_document_path": ARTIFACT_DOCUMENT_PATH,
        "firestore_rules_path": "firestore.rules",
        "rules_emulator_test": "backend/scripts/v17_firestore_rules_emulator_test.mjs",
        "emulator_command": RULES_EMULATOR_COMMAND,
        "direct_signed_in_client_read_denied_static": True,
        "direct_signed_in_client_write_denied_static": True,
        "backend_admin_read_harness_present": True,
        "production_firestore_read_executed": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "proof_id": "direct_client_read_write_denied_or_emulator_required",
        "status": "READY_FOR_LOCAL_EMULATOR",
        "route_refs": [ROUTE_SCOPE],
        "required_evidence": (
            "Firestore rules/IAM emulator or equivalent policy proof must show mobile/web clients cannot read or write "
            "the server-owned canary approval artifact path directly."
        ),
        "direct_client_read_allowed": False,
        "direct_client_write_allowed": False,
        "local_emulator_or_iam_evidence_required": True,
        "static_rules_denial_contract_present": True,
        "local_emulator_or_iam_evidence_present": True,
        "emulator_command": RULES_EMULATOR_COMMAND,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "proof_id": "backend_service_principal_read_required",
        "status": "BLOCKED",
        "route_refs": [ROUTE_SCOPE],
        "required_evidence": (
            "Runtime wiring must prove the backend service principal has least-privilege read access to exactly the "
            "route-scoped approval artifact source before the route can consume it."
        ),
        "backend_service_principal_read_required": True,
        "backend_service_principal_read_static_contract_present": True,
        "backend_service_principal_read_emulator_harness_present": True,
        "backend_service_principal_read_proven": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "proof_id": "artifact_path_has_no_user_request_or_secret_dimensions",
        "status": "READY_FOR_CONTRACT",
        "route_refs": [ROUTE_SCOPE],
        "required_evidence": (
            "Selected source path and future telemetry labels are route-scoped and contain no uid/session/memory id, "
            "cursor/token/secret, request payload, raw memory content, or high-cardinality dimensions."
        ),
        "artifact_path_contains_uid_session_memory_cursor_token_secret_or_payload": False,
        "high_cardinality_labels_allowed": False,
        "contains_pii": False,
        "contains_raw_memory_content": False,
        "logs_secret_or_cursor_token": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "proof_id": "production_artifact_source_missing_not_run",
        "status": "BLOCKED",
        "route_refs": [ROUTE_SCOPE],
        "required_evidence": (
            "Real production artifact existence, contents, ownership, update workflow, IAM/rules proofs, and backend "
            "read evidence remain missing/not-run until supplied by a future production-safe proof."
        ),
        "production_artifact_source_exists": False,
        "production_artifact_source_read": False,
        "production_approval_claimed": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
]

STATIC_IAM_RULES_EMULATOR_READINESS_PROOF = {
    "status": "STATIC_RULES_EMULATOR_HARNESS_READY_RUNTIME_BLOCKED",
    "route_scope": ROUTE_SCOPE,
    "artifact_document_path": ARTIFACT_DOCUMENT_PATH,
    "firestore_rules_path": "firestore.rules",
    "rules_emulator_test": "backend/scripts/v17_firestore_rules_emulator_test.mjs",
    "emulator_command": RULES_EMULATOR_COMMAND,
    "direct_signed_in_client_read_denied": True,
    "direct_signed_in_client_create_update_delete_denied": True,
    "backend_admin_or_service_principal_read_required": True,
    "backend_admin_or_service_principal_read_static_contract_present": True,
    "client_supplied_artifact_trusted": False,
    "path_has_uid_session_memory_cursor_token_secret_or_payload_dimensions": False,
    "production_firestore_read_executed": False,
    "production_firestore_write_executed": False,
    "production_approval_claimed": False,
    "runtime_wired": False,
}

FAILURE_SEMANTICS = [
    {
        "state": "source_missing",
        "future_route_behavior": "fail_closed_before_v17_read",
        "legacy_fallback_allowed": False,
        "approval_claimed": False,
    },
    {
        "state": "iam_denied_or_timeout",
        "future_route_behavior": "fail_closed_before_v17_read",
        "legacy_fallback_allowed": False,
        "approval_claimed": False,
    },
    {
        "state": "client_supplied_artifact_present",
        "future_route_behavior": "ignore_and_fail_closed_if_server_source_unavailable",
        "legacy_fallback_allowed": False,
        "approval_claimed": False,
    },
    {
        "state": "path_or_artifact_contains_sensitive_dimensions",
        "future_route_behavior": "reject_contract_and_do_not_wire",
        "legacy_fallback_allowed": False,
        "approval_claimed": False,
    },
    {
        "state": "owner_not_bounded_group_or_approval_stale",
        "future_route_behavior": "fail_closed_before_v17_read",
        "legacy_fallback_allowed": False,
        "approval_claimed": False,
    },
]


def build_report(*, execute: bool = False) -> dict[str, Any]:
    blocked_required_proof_count = sum(1 for proof in REQUIRED_IAM_RULES_PRIVACY_PROOFS if proof["status"] == "BLOCKED")
    return {
        "artifact": "v17_p1_3_v3_canary_approval_source_readiness",
        "status": "BLOCKED",
        "proof_status": "BLOCKED" if execute else "NOT_RUN",
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
        "scope": (
            "Read-only source-selection and ownership/IAM readiness contract for the future server-owned "
            "GET /v3/memories canary approval artifact."
        ),
        "source_selection_contract": SOURCE_SELECTION_CONTRACT,
        "static_iam_rules_emulator_readiness_proof": STATIC_IAM_RULES_EMULATOR_READINESS_PROOF,
        "required_iam_rules_privacy_proofs": REQUIRED_IAM_RULES_PRIVACY_PROOFS,
        "failure_semantics": FAILURE_SEMANTICS,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No runtime /v3 behavior changed.",
            "No production rollout approval claimed.",
            "No production Firestore/cloud/provider/vector/network calls executed.",
            "No telemetry sink production call executed or claimed.",
            "No PII/raw memory content telemetry emitted.",
            "No secret/cursor token logging allowed or performed.",
            "No legacy fallback/merge for V17 failures claimed.",
            "No Archive default visibility or stale Short-term default visibility claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "proof_status": "BLOCKED" if execute else "NOT_RUN",
            "required_iam_rules_privacy_proof_count": len(REQUIRED_IAM_RULES_PRIVACY_PROOFS),
            "blocked_required_proof_count": blocked_required_proof_count,
            "failure_semantics_count": len(FAILURE_SEMANTICS),
            "read_only": True,
            "mutation_allowed": False,
            "runtime_wiring_changed": False,
            "approval_claimed": False,
            "production_artifact_source_exists": False,
            "backend_service_principal_read_proven": False,
            "direct_client_access_proven_denied": True,
            "static_iam_rules_emulator_readiness_present": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Emit the same safe BLOCKED source readiness inventory")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
