#!/usr/bin/env python3
"""Safe memory `/v3` GET dependency seam/adapter readiness artifact.

This pre-runtime artifact exercises the pure dependency seam shape for future GET
`/v3/memories` route wiring. It is read-only and local: it does not import
FastAPI routers or the production app, read Firestore, call providers/vector
stores/network services, emit telemetry sink calls, mutate state, or claim
runtime rollout approval.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from utils.memory.v3_get_dependency_seam import (
    LOW_CARDINALITY_DECISION_CODES,
    V3GetDependencyAdapters,
    V3GetDependencyContext,
    V3GetDependencyDecision,
    V3GetDependencyChainResult,
    plan_v3_get_dependency_chain,
)

GET_DEPENDENCY_SEAM_READINESS_PROOF = {
    "service": "backend/scripts/p1_3_v3_get_dependency_seam_readiness.py",
    "test": "backend/tests/unit/test_p1_3_v3_get_dependency_seam_readiness.py",
    "utility": "backend/utils/memory/v3_get_dependency_seam.py",
    "utility_test": "backend/tests/unit/test_v3_get_dependency_seam.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "status": "BLOCKED",
    "proof_status": "NOT_RUN",
    "approval_claimed": False,
    "covered_defaults": [
        "authenticated_subject_first",
        "client_uid_override_rejected_before_control_or_reads",
        "non_enrolled_legacy_primary_only_without_memory_legacy_merge",
        "control_config_cursor_projection_source_validated_before_reads",
        "rate_limit_backpressure_before_projection_read",
        "missing_invalid_auth_control_cursor_config_source_backpressure_fail_closed",
        "bounded_low_cardinality_decision_codes_no_secret_cursor_content_logging",
    ],
}

DEPENDENCY_ORDER = [
    "authenticate_subject",
    "reject_client_uid_override",
    "load_enrollment_control",
    "validate_runtime_config",
    "validate_cursor",
    "select_projection_source",
    "check_rate_limit_backpressure",
    "projection_read_allowed_after_rate_limit_backpressure",
]


def _context(**overrides: Any) -> V3GetDependencyContext:
    values = {
        "route": "GET /v3/memories",
        "client_uid_override_present": False,
        "enrolled": True,
        "control_ready": True,
        "config_ready": True,
        "cursor_ready": True,
        "projection_source_ready": True,
        "backpressure_ready": True,
    }
    values.update(overrides)
    return V3GetDependencyContext(**values)


def _adapters() -> V3GetDependencyAdapters:
    def authenticate_subject(context: V3GetDependencyContext) -> V3GetDependencyDecision:
        return V3GetDependencyDecision.allowed("auth_ok", subject_uid="server_verified_subject")

    def reject_client_uid_override(context: V3GetDependencyContext) -> V3GetDependencyDecision:
        if context.client_uid_override_present:
            return V3GetDependencyDecision.fail_closed("client_uid_override_rejected", http_status=403)
        return V3GetDependencyDecision.allowed("no_client_uid_override")

    def load_enrollment_control(context: V3GetDependencyContext) -> V3GetDependencyDecision:
        if not context.enrolled:
            return V3GetDependencyDecision.legacy("non_enrolled_legacy_primary")
        if not context.control_ready:
            return V3GetDependencyDecision.fail_closed("control_unavailable", http_status=503)
        return V3GetDependencyDecision.allowed("control_ok")

    def validate_runtime_config(context: V3GetDependencyContext) -> V3GetDependencyDecision:
        if not context.config_ready:
            return V3GetDependencyDecision.fail_closed("config_unavailable", http_status=503)
        return V3GetDependencyDecision.allowed("config_ok")

    def validate_cursor(context: V3GetDependencyContext) -> V3GetDependencyDecision:
        if not context.cursor_ready:
            return V3GetDependencyDecision.fail_closed("cursor_invalid", http_status=400)
        return V3GetDependencyDecision.allowed("cursor_ok")

    def select_projection_source(context: V3GetDependencyContext) -> V3GetDependencyDecision:
        if not context.projection_source_ready:
            return V3GetDependencyDecision.fail_closed("projection_source_unavailable", http_status=503)
        return V3GetDependencyDecision.allowed("projection_source_ok")

    def check_rate_limit_backpressure(context: V3GetDependencyContext) -> V3GetDependencyDecision:
        if not context.backpressure_ready:
            return V3GetDependencyDecision.fail_closed("backpressure_denied", http_status=429)
        return V3GetDependencyDecision.allowed("rate_limit_backpressure_ok")

    return V3GetDependencyAdapters(
        authenticate_subject=authenticate_subject,
        reject_client_uid_override=reject_client_uid_override,
        load_enrollment_control=load_enrollment_control,
        validate_runtime_config=validate_runtime_config,
        validate_cursor=validate_cursor,
        select_projection_source=select_projection_source,
        check_rate_limit_backpressure=check_rate_limit_backpressure,
    )


def _case_result(case_id: str, result: V3GetDependencyChainResult) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "status": result.status,
        "http_status": result.http_status,
        "decision_code": result.decision_code,
        "dependency_step": result.dependency_step,
        "executed_steps": list(result.executed_steps),
        "should_fetch_legacy": result.should_fetch_legacy,
        "should_fetch_memory_projection": result.should_fetch_memory_projection,
        "legacy_fallback_allowed": result.legacy_fallback_allowed,
        "memory_legacy_merge_allowed": result.memory_legacy_merge_allowed,
        "projection_reads_allowed_after_step": result.projection_reads_allowed_after_step,
        "route_wired": result.route_wired,
        "logs_secret_material": result.logs_secret_material,
        "logs_cursor_token": result.logs_cursor_token,
        "logs_user_content": result.logs_user_content,
        "logs_client_supplied_uid": result.logs_client_supplied_uid,
        "logged_fields": dict(result.logged_fields),
    }


def _seam_cases() -> list[dict[str, Any]]:
    adapters = _adapters()
    inputs = [
        ("happy_enrolled_ready", _context()),
        ("client_uid_override", _context(client_uid_override_present=True)),
        ("non_enrolled", _context(enrolled=False)),
        ("control_missing", _context(control_ready=False)),
        ("config_missing", _context(config_ready=False)),
        ("cursor_invalid", _context(cursor_ready=False)),
        ("projection_source_missing", _context(projection_source_ready=False)),
        ("backpressure_denied", _context(backpressure_ready=False)),
    ]
    return [_case_result(case_id, plan_v3_get_dependency_chain(context, adapters)) for case_id, context in inputs]


def build_report(*, execute: bool = False) -> dict[str, Any]:
    cases = _seam_cases() if execute else []
    blocked_case_count = sum(1 for case in cases if case["status"] == "BLOCKED")
    legacy_case_count = sum(1 for case in cases if case["status"] == "LEGACY_PRIMARY_ONLY")
    return {
        "artifact": "p1_3_v3_get_dependency_seam_readiness",
        "route": "GET /v3/memories",
        "status": "BLOCKED",
        "proof_status": "BLOCKED" if execute else "NOT_RUN",
        "execute_requested": execute,
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
        "approval_claimed": False,
        "proof": GET_DEPENDENCY_SEAM_READINESS_PROOF,
        "dependency_order": DEPENDENCY_ORDER,
        "auth_subject_first": True,
        "client_uid_override_rejected_before_control": True,
        "rate_limit_before_projection_read": True,
        "low_cardinality_decision_codes": sorted(LOW_CARDINALITY_DECISION_CODES),
        "seam_cases": cases,
        "logging_contract": {
            "logs_secret_material": False,
            "logs_cursor_token": False,
            "logs_user_content": False,
            "logs_client_supplied_uid": False,
            "allowed_fields": ["route", "decision_code", "dependency_step", "status"],
        },
        "non_claims": [
            "No backend/routers/memories.py change or runtime route wiring.",
            "No production rollout approval claimed.",
            "No Firestore reads/writes, provider/vector/cloud/network calls, mutating calls, or telemetry sink calls.",
            "No secret material, cursor token, client-supplied uid, or user memory content logging.",
            "No legacy fallback/merge for enrolled memory failures.",
            "No Archive default visibility or stale Short-term default visibility claim.",
        ],
        "summary": {
            "status": "BLOCKED",
            "case_count": len(cases),
            "blocked_case_count": blocked_case_count,
            "legacy_primary_only_case_count": legacy_case_count,
            "runtime_wired": False,
            "read_only": True,
            "approval_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run local pure seam cases and emit blocked report")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
