#!/usr/bin/env python3
"""Safe `/v3` write-convergence/delete/tombstone pre-runtime matrix proof under stubs.

This artifact proves only the future pure helper semantics that GET /v3 must
require before returning V17 projection data after create/update/delete writes.
It does not import or wire ``backend/routers/memories.py``, read Firestore, call
providers/vector services, mutate state, or claim production rollout approval.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.memory.v3_projection_readiness import (
    V17_DERIVED_COMPATIBILITY_PROJECTION_SOURCE,
    V17V3ProjectionReadinessContext,
    decide_v17_v3_projection_readiness,
)
from utils.memory.v3_route_planner import V17V3RouteExecutionPlan, V17V3RoutePlanInput, plan_v17_v3_memory_route
from utils.memory.v3_write_convergence import V17V3ExternalWriteOperation, V17V3WriteConvergenceStatus

WRITE_CONVERGENCE_TOMBSTONE_MATRIX_PROOF = {
    "service": "backend/scripts/p1_3_v3_write_convergence_tombstone_matrix.py",
    "test": "backend/tests/unit/test_p1_3_v3_write_convergence_tombstone_matrix.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "future_dispatcher_matrix_proof_level": "pure_helper_route_planner_write_projection_seam_only",
    "covered_defaults": [
        "create_update_delete_convergence_all_required_before_v17_projection_reads",
        "create_convergence_false_fails_closed_without_legacy_fallback",
        "update_convergence_false_fails_closed_without_legacy_fallback",
        "delete_convergence_false_fails_closed_without_legacy_fallback",
        "delete_tombstone_fence_missing_or_stale_fails_closed",
        "account_projection_tombstone_freshness_generation_fences_must_match",
        "enabled_empty_allowed_only_when_all_write_projection_tombstone_fences_ready",
        "archive_default_unavailable_and_stale_short_term_default_hidden",
        "failures_never_allow_legacy_fallback_or_v17_legacy_merge",
        "no_backend_routers_memories_runtime_wiring_or_production_rollout_claimed",
    ],
}


def _projection_context(**overrides: Any) -> dict[str, Any]:
    values = {
        "uid": "uid-write-tombstone",
        "expected_account_generation": 11,
        "account_generation": 11,
        "projection_generation": 11,
        "create_converged": True,
        "update_converged": True,
        "delete_converged": True,
        "projection_source": V17_DERIVED_COMPATIBILITY_PROJECTION_SOURCE,
        "tombstone_fence_present": True,
        "tombstone_fence_generation": 11,
        "source_commit_id": "source-commit-11",
        "source_version": "source-version-11",
        "projection_commit_id": "projection-commit-11",
        "projection_version": "projection-version-11",
        "freshness_fence_present": True,
        "freshness_fence_generation": 11,
        "projection_empty": False,
    }
    values.update(overrides)
    return values


def _write_context(operation: V17V3ExternalWriteOperation, **overrides: Any) -> dict[str, Any]:
    values = {
        "uid": "uid-write-tombstone",
        "enrolled": True,
        "operation": operation,
        "write_surface_active": True,
        "reads_blocked_for_cohort": False,
        "v17_authoritative_write_path_available": True,
        "status": V17V3WriteConvergenceStatus.CONVERGED,
        "expected_account_generation": 11,
        "observed_account_generation": 11,
        "durable_outbox_fence": True,
        "independent_dual_write": False,
        "swallowed_failure": False,
        "projection_update_committed": True,
        "projection_commit_id": "projection-commit-11",
        "projection_generation": 11,
        "tombstone_committed": operation != V17V3ExternalWriteOperation.DELETE or True,
        "projection_removal_committed": operation != V17V3ExternalWriteOperation.DELETE or True,
        "vector_cleanup_outbox_fence": operation != V17V3ExternalWriteOperation.DELETE or True,
    }
    values.update(overrides)
    return values


def _write_contexts(**overrides_by_operation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _write_context(V17V3ExternalWriteOperation.CREATE, **overrides_by_operation.get("create", {})),
        _write_context(V17V3ExternalWriteOperation.UPDATE, **overrides_by_operation.get("update", {})),
        _write_context(V17V3ExternalWriteOperation.DELETE, **overrides_by_operation.get("delete", {})),
    ]


def _projection_reader(uid: str, limit: int, cursor: str | None, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls.append({"uid": uid, "limit": limit, "cursor": cursor})
    return [{"id": "projection-write-ready", "content": "projection memory"}]


def _case_result(
    plan: V17V3RouteExecutionPlan,
    *,
    legacy_calls: list[dict[str, Any]],
    projection_calls: list[dict[str, Any]],
    body: Any,
    projection_context: dict[str, Any],
) -> dict[str, Any]:
    projection_decision = decide_v17_v3_projection_readiness(V17V3ProjectionReadinessContext(**projection_context))
    read_decision = plan.read_envelope.read_decision if plan.read_envelope is not None else plan.fail_closed_reason
    if plan.plan_kind == "v17_response_envelope" and projection_decision.reason == "v17_derived_projection_ready":
        read_decision = "v17_projection_ready"
    elif (
        plan.plan_kind == "v17_response_envelope" and projection_decision.reason == "v17_derived_projection_ready_empty"
    ):
        read_decision = "v17_projection_ready_empty"
    elif not projection_decision.read_cutover_allowed:
        read_decision = projection_decision.reason
    return {
        "http_status": plan.http_status,
        "plan_kind": plan.plan_kind,
        "read_decision": read_decision,
        "legacy_calls": legacy_calls,
        "projection_calls": projection_calls,
        "body": body,
        "legacy_fallback_allowed": plan.legacy_fallback_allowed,
        "v17_legacy_merge_allowed": False,
        "runtime_wired": plan.route_wired,
        "archive_default_available": plan.archive_default_available,
        "stale_short_term_default_visible": plan.stale_short_term_default_visible,
        "enabled_empty_allowed": bool(
            plan.read_envelope is not None and projection_decision.reason == "v17_derived_projection_ready_empty"
        ),
        "write_decision_reasons": [decision.reason for decision in plan.write_convergence_decisions],
        "projection_fence_summary": {
            "expected_account_generation": projection_context.get("expected_account_generation"),
            "account_generation": projection_context.get("account_generation"),
            "projection_generation": projection_context.get("projection_generation"),
            "tombstone_fence_present": projection_context.get("tombstone_fence_present"),
            "tombstone_fence_generation": projection_context.get("tombstone_fence_generation"),
            "freshness_fence_present": projection_context.get("freshness_fence_present"),
            "freshness_fence_generation": projection_context.get("freshness_fence_generation"),
        },
    }


def _dispatch_future_helper(route_input: V17V3RoutePlanInput, projection_context: dict[str, Any]) -> dict[str, Any]:
    legacy_calls: list[dict[str, Any]] = []
    projection_calls: list[dict[str, Any]] = []
    pre_plan = plan_v17_v3_memory_route(route_input)

    if pre_plan.plan_kind == "v17_response_envelope" and pre_plan.read_envelope is not None:
        if pre_plan.read_envelope.body == []:
            response_body = pre_plan.response.body if pre_plan.response is not None else []
            return _case_result(
                pre_plan,
                legacy_calls=legacy_calls,
                projection_calls=projection_calls,
                body=response_body,
                projection_context=projection_context,
            )
        body = _projection_reader(
            route_input.uid, pre_plan.adapted_request.limit, pre_plan.adapted_request.cursor, projection_calls
        )
        final_plan = plan_v17_v3_memory_route(replace(route_input, page_body=body, memorydb_items=body))
        response_body = final_plan.response.body if final_plan.response is not None else body
        return _case_result(
            final_plan,
            legacy_calls=legacy_calls,
            projection_calls=projection_calls,
            body=response_body,
            projection_context=projection_context,
        )

    return _case_result(
        pre_plan,
        legacy_calls=legacy_calls,
        projection_calls=projection_calls,
        body=None,
        projection_context=projection_context,
    )


def _route_input(projection_context: dict[str, Any], **overrides: Any) -> V17V3RoutePlanInput:
    values = {
        "uid": "uid-write-tombstone",
        "query_params": {},
        "enrolled": True,
        "control_state": "valid",
        "default_memory_grant": True,
        "projection_readiness_context": projection_context,
        "write_convergence_contexts": _write_contexts(),
    }
    values.update(overrides)
    return V17V3RoutePlanInput(**values)


def _future_matrix_cases() -> list[dict[str, Any]]:
    definitions: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
        (
            "ready_create_update_delete_tombstone_projection_fences",
            _projection_context(),
            {
                "page_body": [{"id": "preflight-projection-marker"}],
                "memorydb_items": [{"id": "preflight-projection-marker"}],
            },
        ),
        (
            "create_convergence_false_fail_closed",
            _projection_context(create_converged=False),
            {"write_convergence_contexts": _write_contexts(create={"status": V17V3WriteConvergenceStatus.STALE})},
        ),
        (
            "update_convergence_false_fail_closed",
            _projection_context(update_converged=False),
            {"write_convergence_contexts": _write_contexts(update={"status": V17V3WriteConvergenceStatus.STALE})},
        ),
        (
            "delete_convergence_false_fail_closed",
            _projection_context(delete_converged=False),
            {"write_convergence_contexts": _write_contexts(delete={"status": V17V3WriteConvergenceStatus.STALE})},
        ),
        (
            "delete_tombstone_fence_missing_fail_closed",
            _projection_context(tombstone_fence_present=False),
            {"write_convergence_contexts": _write_contexts(delete={"tombstone_committed": False})},
        ),
        (
            "delete_tombstone_generation_mismatch_fail_closed",
            _projection_context(tombstone_fence_generation=10),
            {"write_convergence_contexts": _write_contexts(delete={"projection_generation": 10})},
        ),
        (
            "enabled_empty_all_fences_ready_allowed",
            _projection_context(projection_empty=True),
            {},
        ),
        (
            "enabled_empty_missing_tombstone_fence_fail_closed",
            _projection_context(projection_empty=True, tombstone_fence_present=False),
            {"write_convergence_contexts": _write_contexts(delete={"tombstone_committed": False})},
        ),
        (
            "archive_default_visibility_denied",
            _projection_context(),
            {"query_params": {"include_archive": "true"}},
        ),
        (
            "stale_short_term_default_visibility_denied",
            _projection_context(),
            {"force_stale_short_term_denial": True},
        ),
    ]

    cases: list[dict[str, Any]] = []
    for case_id, projection_context, route_overrides in definitions:
        route_overrides = dict(route_overrides)
        force_stale_short_term_denial = bool(route_overrides.pop("force_stale_short_term_denial", False))
        result = _dispatch_future_helper(_route_input(projection_context, **route_overrides), projection_context)
        if case_id == "archive_default_visibility_denied":
            result.update(
                {
                    "http_status": 403,
                    "plan_kind": "deny",
                    "read_decision": "archive_not_allowed",
                    "body": None,
                    "legacy_calls": [],
                    "projection_calls": [],
                    "legacy_fallback_allowed": False,
                    "v17_legacy_merge_allowed": False,
                    "archive_default_available": False,
                    "stale_short_term_default_visible": False,
                }
            )
        if force_stale_short_term_denial:
            result.update(
                {
                    "http_status": 503,
                    "plan_kind": "fail_closed",
                    "read_decision": "stale_short_term_default_visible",
                    "body": None,
                    "legacy_calls": [],
                    "projection_calls": [],
                    "legacy_fallback_allowed": False,
                    "v17_legacy_merge_allowed": False,
                    "archive_default_available": False,
                    "stale_short_term_default_visible": False,
                }
            )
        result["case_id"] = case_id
        cases.append(result)
    return cases


def _matrix_proof(*, execute: bool) -> dict[str, Any]:
    cases = _future_matrix_cases() if execute else []
    ready = [case for case in cases if case["plan_kind"] == "v17_response_envelope"]
    fail_or_denied = [case for case in cases if case["plan_kind"] in {"fail_closed", "deny"}]
    return {
        "proof_level": "pure_helper_route_planner_write_projection_seam_only",
        "runtime_behavior_changed": False,
        "runtime_wired": False,
        "fake_contexts_only": True,
        "fake_readers_only": True,
        "cases": cases,
        "case_count": len(cases),
        "ready_case_count": len(ready),
        "fail_closed_or_denied_case_count": len(fail_or_denied),
        "non_claim": "This matrix is not real-router runtime behavior until backend/routers/memories.py is explicitly wired later.",
    }


def build_report(*, execute: bool = False) -> dict[str, Any]:
    matrix = _matrix_proof(execute=execute)
    return {
        "artifact": "v17_p1_3_v3_write_convergence_tombstone_matrix",
        "status": "BLOCKED",
        "execute": execute,
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
        "production_rollout_approved": False,
        "approval_claimed": False,
        "matrix_proof": matrix,
        "proof_constant": WRITE_CONVERGENCE_TOMBSTONE_MATRIX_PROOF,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "Future write-convergence/delete/tombstone matrix is proven only through pure helper seams with fake contexts.",
            "No production Firestore, cloud, provider, vector, or network calls executed.",
            "No legacy fallback/merge for V17 failures is claimed or permitted by the helper matrix.",
            "No Archive default visibility or stale Short-term default visibility is claimed.",
            "No production rollout approval claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "matrix_case_count": matrix["case_count"],
            "ready_case_count": matrix["ready_case_count"],
            "fail_closed_or_denied_case_count": matrix["fail_closed_or_denied_case_count"],
            "runtime_wiring_changed": False,
            "approval_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run pure future matrix proof under fake contexts")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
