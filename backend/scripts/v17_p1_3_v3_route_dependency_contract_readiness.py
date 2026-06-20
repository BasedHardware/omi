#!/usr/bin/env python3
"""Safe V17 `/v3` route dependency auth/rate-limit/fail-closed readiness contract.

This pre-runtime artifact defines the route dependency contract that must exist
before changing GET `/v3/memories` runtime behavior. It is intentionally static
and read-only: it does not import the memories router or production app, execute
FastAPI clients, read Firestore, call providers, emit telemetry, mutate state, or
claim rollout approval.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

ROUTE_DEPENDENCY_CONTRACT_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_route_dependency_contract_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_route_dependency_contract_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "status": "BLOCKED",
    "proof_status": "NOT_RUN",
    "approval_claimed": False,
    "covered_defaults": [
        "authenticated_subject_binding_required_before_any_read",
        "legacy_token_api_key_mcp_auth_behavior_inventory_required",
        "client_uid_override_rejected_before_read_source_selection",
        "non_enrolled_legacy_boundary_and_enrolled_v17_boundary_required",
        "rate_limit_or_backpressure_dependency_hook_required_for_get",
        "missing_invalid_auth_control_cursor_config_fail_closed_required",
        "real_testclient_scenarios_blocked_until_runtime_route_wiring_exists",
    ],
}

REQUIRED_CONTRACT_EVIDENCE = [
    {
        "evidence_id": "authenticated_subject_binding_required_before_any_read",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_before_runtime_wiring": True,
        "required_contract": (
            "The future route must bind exactly one authenticated server-verified subject uid before reading "
            "control, cursor, projection, legacy, or telemetry context."
        ),
        "must_prove": [
            "missing_auth_blocks_before_read",
            "invalid_auth_blocks_before_read",
            "verified_subject_uid_is_the_only_uid_for_downstream_reads",
        ],
        "runtime_wired": False,
    },
    {
        "evidence_id": "legacy_token_api_key_mcp_auth_behavior_inventory_required",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_before_runtime_wiring": True,
        "required_contract": (
            "Document and preserve applicable legacy bearer-token/API-key/MCP-adjacent auth behavior while ensuring "
            "no unauthenticated or scope-less caller can enter a V17 read path."
        ),
        "must_prove": [
            "legacy_mobile_token_compatibility_inventory",
            "developer_api_key_not_treated_as_v3_user_auth_without_verified_subject",
            "mcp_auth_context_not_invented_for_v3_get",
        ],
        "runtime_wired": False,
    },
    {
        "evidence_id": "client_uid_override_rejected_before_read_source_selection",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_before_runtime_wiring": True,
        "required_contract": (
            "Client-supplied uid/user_id/account identifiers in query/header/body must be ignored or rejected; "
            "the authenticated subject uid must select enrollment, control, projection, cursor, and legacy reads."
        ),
        "must_prove": [
            "query_uid_cannot_override_auth_uid",
            "header_uid_cannot_override_auth_uid",
            "cursor_uid_mismatch_fails_closed",
        ],
        "runtime_wired": False,
    },
    {
        "evidence_id": "non_enrolled_legacy_boundary_and_enrolled_v17_boundary_required",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_before_runtime_wiring": True,
        "required_contract": (
            "Non-enrolled users preserve the current legacy-primary limit/offset behavior; enrolled users enter the "
            "V17 control/projection contract and never fall back to legacy on V17 failures."
        ),
        "must_prove": [
            "non_enrolled_offset_zero_limit_5000_legacy_only",
            "non_enrolled_explicit_limit_offset_legacy_only",
            "enrolled_v17_projection_only_when_all_gates_ready",
            "enrolled_no_legacy_merge_or_exception_fallback",
        ],
        "runtime_wired": False,
    },
    {
        "evidence_id": "rate_limit_or_backpressure_dependency_hook_required_for_get",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_before_runtime_wiring": True,
        "required_contract": (
            "GET must have an explicit route dependency or equivalent server-side backpressure hook before V17 reads "
            "can fan into control, projection, cursor, or compatibility stores."
        ),
        "must_prove": [
            "rate_limit_hook_runs_after_auth_before_read",
            "429_or_retry_after_does_not_read_projection_or_legacy",
            "hook_uses_low_cardinality_policy_name_without_uid_or_content_labels",
        ],
        "runtime_wired": False,
    },
    {
        "evidence_id": "missing_invalid_auth_control_cursor_config_fail_closed_required",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_before_runtime_wiring": True,
        "required_contract": (
            "Missing or invalid auth/control/cursor/config must fail closed with no legacy fallback, no V17/legacy "
            "merge, no provider/vector call, and no secret or content logging."
        ),
        "must_prove": [
            "missing_or_invalid_auth_blocks_before_read",
            "missing_malformed_timeout_control_returns_fail_closed",
            "invalid_expired_or_generation_mismatched_cursor_returns_fail_closed",
            "missing_disabled_or_malformed_runtime_config_returns_fail_closed",
        ],
        "runtime_wired": False,
    },
    {
        "evidence_id": "real_testclient_scenarios_blocked_until_runtime_route_wiring_exists",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_before_runtime_wiring": True,
        "required_contract": (
            "Route-level scenarios must later run through the actual GET route dependencies under a minimal app, but "
            "remain blocked now because this slice does not wire route behavior."
        ),
        "must_prove": [
            "actual_route_dependency_order",
            "actual_rate_limit_or_backpressure_dependency",
            "actual_fail_closed_responses_before_any_read",
            "actual_non_enrolled_legacy_boundary",
            "actual_enrolled_v17_boundary",
        ],
        "runtime_wired": False,
    },
]

BLOCKED_TESTCLIENT_SCENARIOS = [
    {
        "scenario_id": "missing_auth",
        "expected_behavior": "401_or_403_before_any_read",
        "executed_now": False,
        "blocked_until_route_wiring": True,
    },
    {
        "scenario_id": "invalid_auth",
        "expected_behavior": "401_or_403_before_any_read",
        "executed_now": False,
        "blocked_until_route_wiring": True,
    },
    {
        "scenario_id": "client_uid_override",
        "expected_behavior": "ignored_or_rejected_authenticated_uid_wins",
        "executed_now": False,
        "blocked_until_route_wiring": True,
    },
    {
        "scenario_id": "non_enrolled_legacy_safe",
        "expected_behavior": "legacy_primary_only_current_limit_offset_semantics",
        "executed_now": False,
        "blocked_until_route_wiring": True,
    },
    {
        "scenario_id": "enrolled_projection_ready",
        "expected_behavior": "v17_projection_only_no_legacy_merge",
        "executed_now": False,
        "blocked_until_route_wiring": True,
    },
    {
        "scenario_id": "enrolled_control_missing",
        "expected_behavior": "503_fail_closed_no_legacy_fallback",
        "executed_now": False,
        "blocked_until_route_wiring": True,
    },
    {
        "scenario_id": "cursor_invalid_or_generation_mismatch",
        "expected_behavior": "400_or_503_fail_closed_no_legacy_fallback",
        "executed_now": False,
        "blocked_until_route_wiring": True,
    },
    {
        "scenario_id": "rate_limited_or_backpressured",
        "expected_behavior": "429_or_retry_after_before_read",
        "executed_now": False,
        "blocked_until_route_wiring": True,
    },
    {
        "scenario_id": "config_missing_or_disabled",
        "expected_behavior": "503_fail_closed_no_legacy_fallback",
        "executed_now": False,
        "blocked_until_route_wiring": True,
    },
]

LOGGING_CONTRACT = {
    "logs_secret_material": False,
    "logs_cursor_token": False,
    "logs_user_content": False,
    "logs_client_supplied_uid": False,
    "allowed_low_cardinality_fields": [
        "route",
        "auth_result",
        "rate_limit_result",
        "read_decision",
        "fail_closed_reason",
        "cohort",
        "projection_generation_match",
    ],
}

PRODUCTION_CALL_CONTRACT = {
    "firestore_reads_allowed_by_default": False,
    "firestore_writes_allowed": False,
    "provider_or_vector_calls_allowed": False,
    "network_calls_allowed": False,
    "telemetry_sink_calls_allowed": False,
    "mutating_routes_allowed": False,
}


def build_report(*, execute: bool = False) -> dict[str, Any]:
    blocked_count = sum(1 for item in REQUIRED_CONTRACT_EVIDENCE if item["status"] == "BLOCKED")
    return {
        "artifact": "v17_p1_3_v3_route_dependency_contract_readiness",
        "status": "BLOCKED",
        "proof_status": "BLOCKED" if execute else "NOT_RUN",
        "execute": execute,
        "route": "GET /v3/memories",
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "routers_memories_modified": False,
        "production_app_imported": False,
        "app_startup_executed": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "telemetry_sink_calls_executed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "contract_evidence_count": len(REQUIRED_CONTRACT_EVIDENCE),
        "required_contract_evidence": REQUIRED_CONTRACT_EVIDENCE,
        "blocked_testclient_scenarios": BLOCKED_TESTCLIENT_SCENARIOS,
        "logging_contract": LOGGING_CONTRACT,
        "production_call_contract": PRODUCTION_CALL_CONTRACT,
        "proof": ROUTE_DEPENDENCY_CONTRACT_READINESS_PROOF,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No runtime /v3 behavior change or production rollout approval claimed.",
            "No production Firestore read/write, cloud, provider, vector, or network call executed.",
            "No telemetry sink production call executed or claimed.",
            "No secret material, cursor token, client-supplied uid, or user memory content logging.",
            "No legacy fallback/merge for V17 failures, Archive default visibility, or stale Short-term default visibility claimed.",
            "Real route-level scenarios remain blocked until explicit runtime route wiring exists.",
        ],
        "summary": {
            "status": "BLOCKED",
            "proof_status": "BLOCKED" if execute else "NOT_RUN",
            "contract_evidence_count": len(REQUIRED_CONTRACT_EVIDENCE),
            "blocked_contract_evidence_count": blocked_count,
            "real_testclient_scenario_count": len(BLOCKED_TESTCLIENT_SCENARIOS),
            "blocked_testclient_scenario_count": len(BLOCKED_TESTCLIENT_SCENARIOS),
            "read_only": True,
            "mutation_allowed": False,
            "runtime_wiring_changed": False,
            "approval_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Emit the same safe BLOCKED contract with execute=true")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
