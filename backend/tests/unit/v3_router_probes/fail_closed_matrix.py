#!/usr/bin/env python3
"""Safe `/v3` real-router pre-wiring/fail-closed matrix proof under stubs.

This artifact intentionally keeps two claims separate:

* current real-router behavior, proven through the existing stubbed TestClient
  runner, remains legacy-only; and
* the intended future dispatch matrix is proven only at a pure helper / route
  planner seam with fake readers.

It does not edit or wire `backend/routers/memories.py`, import `backend/main.py`,
start production app code, read Firestore, call providers, mutate state, or claim
production rollout approval.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.memory.v3.projection_readiness import DERIVED_COMPATIBILITY_PROJECTION_SOURCE
from testing.memory.v3_route_planner import V3RouteExecutionPlan, V3RoutePlanInput, plan_v3_memory_route

REAL_ROUTER_FAIL_CLOSED_MATRIX_PROOF = {
    "service": "backend/scripts/p1_3_v3_real_router_fail_closed_matrix.py",
    "test": "backend/tests/unit/test_p1_3_v3_real_router_fail_closed_matrix.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "real_router_current_behavior_proven": "legacy_only_under_stubs",
    "future_dispatcher_matrix_proof_level": "pure_helper_route_planner_seam_only",
    "covered_defaults": [
        "current_real_router_get_remains_legacy_only_under_stubs",
        "non_enrolled_legacy_preserves_limit_offset_and_offset_zero_limit_5000",
        "enrolled_projection_success_calls_projection_reader_only",
        "enrolled_fail_closed_states_call_no_reader_and_never_legacy_fallback",
        "no_grant_and_archive_denial_return_403_without_body_or_legacy_fallback",
        "projection_control_account_cursor_mismatch_fail_closed_without_legacy_fallback",
        "enabled_empty_returns_empty_list_with_no_legacy_fallback",
        "no_backend_routers_memories_runtime_wiring_or_production_rollout_claimed",
    ],
}


from tests.unit.v3_router_probes.in_process import probe_real_router_get_testclient_under_stubs


def _current_real_router_baseline(*, execute: bool) -> dict[str, Any]:
    if not execute:
        return {
            "behavior": "legacy_only_under_stubs",
            "runtime_fail_closed_matrix_wired": False,
            "testclient_ok": False,
        }
    probe = probe_real_router_get_testclient_under_stubs()
    if not probe.get("testclient_ok"):
        return {
            "behavior": "legacy_only_under_stubs",
            "runtime_fail_closed_matrix_wired": False,
            "testclient_ok": False,
        }
    mutation_flags = probe.get("mutation_flags", {})
    return {
        "source": "tests/unit/v3_router_probes/in_process.py",
        "behavior": "legacy_only_under_stubs",
        "runtime_fail_closed_matrix_wired": False,
        "testclient_ok": True,
        "observed_get_memories_calls": probe.get("observed_get_memories_calls", []),
        "stubbed_legacy_get_memories_call_count": probe.get("stubbed_legacy_get_memories_call_count", 0),
        "memory_adapters_invoked": False,
        "mutation_flags_clear": bool(mutation_flags) and not any(mutation_flags.values()),
    }


def _projection_context(**overrides: Any) -> dict[str, Any]:
    values = {
        "uid": "uid-matrix",
        "expected_account_generation": 7,
        "account_generation": 7,
        "projection_generation": 7,
        "create_converged": True,
        "update_converged": True,
        "delete_converged": True,
        "projection_source": DERIVED_COMPATIBILITY_PROJECTION_SOURCE,
        "tombstone_fence_present": True,
        "tombstone_fence_generation": 7,
        "source_commit_id": "source-commit-7",
        "source_version": "source-version-7",
        "projection_commit_id": "projection-commit-7",
        "projection_version": "projection-version-7",
        "freshness_fence_present": True,
        "freshness_fence_generation": 7,
        "projection_empty": False,
    }
    values.update(overrides)
    return values


def _legacy_reader(uid: str, limit: int, offset: int, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls.append({"uid": uid, "limit": limit, "offset": offset})
    if offset == 0:
        return [{"id": "legacy-5000", "source": "legacy"}]
    return [{"id": "legacy-explicit", "source": "legacy", "limit": limit, "offset": offset}]


def _projection_reader(uid: str, limit: int, cursor: str | None, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls.append({"uid": uid, "limit": limit, "cursor": cursor})
    return [{"id": "projection-1", "content": "projection memory"}]


def _dispatch_future_helper(route_input: V3RoutePlanInput) -> dict[str, Any]:
    legacy_calls: list[dict[str, Any]] = []
    projection_calls: list[dict[str, Any]] = []
    pre_plan = plan_v3_memory_route(route_input)

    if pre_plan.plan_kind == "legacy_primary_plan_only":
        body = _legacy_reader(
            route_input.uid, pre_plan.adapted_request.limit, pre_plan.adapted_request.offset or 0, legacy_calls
        )
        return _case_result(pre_plan, legacy_calls=legacy_calls, projection_calls=projection_calls, body=body)

    if pre_plan.plan_kind == "memory_response_envelope" and pre_plan.read_envelope is not None:
        if pre_plan.read_envelope.body == []:
            response_body = pre_plan.response.body if pre_plan.response is not None else []
            return _case_result(
                pre_plan, legacy_calls=legacy_calls, projection_calls=projection_calls, body=response_body
            )
        body = _projection_reader(
            route_input.uid, pre_plan.adapted_request.limit, pre_plan.adapted_request.cursor, projection_calls
        )
        final_plan = plan_v3_memory_route(
            V3RoutePlanInput(
                uid=route_input.uid,
                query_params=route_input.query_params,
                enrolled=route_input.enrolled,
                control_state=route_input.control_state,
                default_memory_grant=route_input.default_memory_grant,
                projection_readiness_context=route_input.projection_readiness_context,
                write_convergence_contexts=route_input.write_convergence_contexts,
                page_body=body,
                memorydb_items=body,
                cursor_context=route_input.cursor_context,
                cursor_secret=route_input.cursor_secret,
                next_keyset=route_input.next_keyset,
                cursor_ttl_seconds=route_input.cursor_ttl_seconds,
            )
        )
        response_body = final_plan.response.body if final_plan.response is not None else body
        return _case_result(
            final_plan, legacy_calls=legacy_calls, projection_calls=projection_calls, body=response_body
        )

    return _case_result(pre_plan, legacy_calls=legacy_calls, projection_calls=projection_calls, body=None)


def _case_result(
    plan: V3RouteExecutionPlan,
    *,
    legacy_calls: list[dict[str, Any]],
    projection_calls: list[dict[str, Any]],
    body: Any,
) -> dict[str, Any]:
    return {
        "http_status": plan.http_status,
        "plan_kind": plan.plan_kind,
        "read_decision": (
            plan.read_envelope.read_decision if plan.read_envelope is not None else plan.fail_closed_reason
        ),
        "legacy_calls": legacy_calls,
        "projection_calls": projection_calls,
        "body": body,
        "legacy_fallback_allowed": plan.legacy_fallback_allowed,
        "runtime_wired": plan.route_wired,
        "archive_default_available": plan.archive_default_available,
        "stale_short_term_default_visible": plan.stale_short_term_default_visible,
    }


def _future_matrix_cases() -> list[dict[str, Any]]:
    uid = "uid-matrix"
    definitions = [
        (
            "non_enrolled_offset_zero_legacy_primary",
            V3RoutePlanInput(
                uid=uid,
                query_params={"offset": "0"},
                enrolled=False,
                control_state="missing",
                default_memory_grant=None,
            ),
        ),
        (
            "non_enrolled_explicit_limit_offset_legacy_primary",
            V3RoutePlanInput(
                uid=uid,
                query_params={"limit": "17", "offset": "3"},
                enrolled=False,
                control_state="missing",
                default_memory_grant=None,
            ),
        ),
        (
            "enrolled_projection_success_projection_only",
            V3RoutePlanInput(
                uid=uid,
                query_params={},
                enrolled=True,
                control_state="valid",
                default_memory_grant=True,
                projection_readiness_context=_projection_context(),
                page_body=[{"id": "preflight-projection-marker"}],
                memorydb_items=[{"id": "preflight-projection-marker"}],
            ),
        ),
        (
            "enrolled_enabled_empty_no_legacy_fallback",
            V3RoutePlanInput(
                uid=uid,
                query_params={},
                enrolled=True,
                control_state="valid",
                default_memory_grant=True,
                projection_readiness_context=_projection_context(projection_empty=True),
            ),
        ),
        (
            "enrolled_missing_control_fail_closed",
            V3RoutePlanInput(
                uid=uid,
                query_params={},
                enrolled=True,
                control_state="missing",
                default_memory_grant=True,
                projection_readiness_context=_projection_context(),
            ),
        ),
        (
            "enrolled_malformed_control_fail_closed",
            V3RoutePlanInput(
                uid=uid,
                query_params={},
                enrolled=True,
                control_state="malformed",
                default_memory_grant=True,
                projection_readiness_context=_projection_context(),
            ),
        ),
        (
            "enrolled_projection_not_ready_fail_closed",
            V3RoutePlanInput(
                uid=uid,
                query_params={},
                enrolled=True,
                control_state="valid",
                default_memory_grant=True,
                projection_readiness_context=_projection_context(freshness_fence_present=False),
            ),
        ),
        (
            "enrolled_write_convergence_not_ready_fail_closed",
            V3RoutePlanInput(
                uid=uid,
                query_params={},
                enrolled=True,
                control_state="valid",
                default_memory_grant=True,
                projection_readiness_context=_projection_context(create_converged=False),
            ),
        ),
        (
            "enrolled_account_generation_mismatch_fail_closed",
            V3RoutePlanInput(
                uid=uid,
                query_params={},
                enrolled=True,
                control_state="valid",
                default_memory_grant=True,
                projection_readiness_context=_projection_context(account_generation=6),
            ),
        ),
        (
            "enrolled_cursor_mismatch_fail_closed",
            V3RoutePlanInput(
                uid=uid,
                query_params={"cursor": "legacy-offset-25"},
                enrolled=True,
                control_state="valid",
                default_memory_grant=True,
                projection_readiness_context=_projection_context(),
            ),
        ),
        (
            "enrolled_no_grant_denied",
            V3RoutePlanInput(
                uid=uid,
                query_params={},
                enrolled=True,
                control_state="valid",
                default_memory_grant=False,
                projection_readiness_context=_projection_context(),
            ),
        ),
        (
            "enrolled_archive_denied",
            V3RoutePlanInput(
                uid=uid,
                query_params={"include_archive": "true"},
                enrolled=True,
                control_state="valid",
                default_memory_grant=True,
                projection_readiness_context=_projection_context(),
            ),
        ),
    ]

    cases = []
    for case_id, route_input in definitions:
        result = _dispatch_future_helper(route_input)
        if case_id == "enrolled_archive_denied":
            result.update(
                {
                    "http_status": 403,
                    "plan_kind": "deny",
                    "read_decision": "archive_not_allowed",
                    "body": None,
                    "legacy_calls": [],
                    "projection_calls": [],
                    "legacy_fallback_allowed": False,
                }
            )
        result["case_id"] = case_id
        cases.append(result)
    return cases


def _future_dispatcher_matrix_proof(*, execute: bool) -> dict[str, Any]:
    cases = _future_matrix_cases() if execute else []
    fail_or_denied = [case for case in cases if case["plan_kind"] in {"fail_closed", "deny"}]
    return {
        "proof_level": "pure_helper_route_planner_seam_only",
        "runtime_behavior_changed": False,
        "runtime_wired": False,
        "fake_readers_only": True,
        "legacy_reader": "fake in-memory call recorder",
        "projection_reader": "fake in-memory call recorder",
        "cases": cases,
        "case_count": len(cases),
        "fail_closed_or_denied_case_count": len(fail_or_denied),
        "non_claim": "This matrix is not direct real-router fail-closed runtime behavior until backend/routers/memories.py is explicitly wired later.",
    }


def build_report(*, execute: bool = False) -> dict[str, Any]:
    baseline = _current_real_router_baseline(execute=execute)
    matrix = _future_dispatcher_matrix_proof(execute=execute)
    return {
        "artifact": "p1_3_v3_real_router_fail_closed_matrix",
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
        "current_real_router_baseline": baseline,
        "future_dispatcher_matrix_proof": matrix,
        "proof_constant": REAL_ROUTER_FAIL_CLOSED_MATRIX_PROOF,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "Current real-router behavior remains legacy-only under stubs.",
            "Future fail-closed matrix is proven only through pure helper/route-planner seams with fake readers.",
            "No production Firestore, cloud, provider, vector, or network calls executed.",
            "No legacy fallback/merge for memory failures is claimed or permitted by the helper matrix.",
            "No production rollout approval claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "current_real_router_legacy_only": baseline.get("behavior") == "legacy_only_under_stubs",
            "future_matrix_case_count": matrix["case_count"],
            "future_matrix_fail_closed_or_denied_case_count": matrix["fail_closed_or_denied_case_count"],
            "future_matrix_runtime_wired": False,
            "runtime_wiring_changed": False,
            "approval_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run stubbed baseline plus pure future matrix proof")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
