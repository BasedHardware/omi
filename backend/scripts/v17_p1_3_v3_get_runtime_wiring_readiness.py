#!/usr/bin/env python3
"""Safe Oracle P1-3 `/v3` GET runtime-wiring remaining-gates readiness artifact.

This is a read-only gate inventory for the future `GET /v3/memories` V17
runtime cutover. It intentionally does not import FastAPI routers, read
Firestore, call providers, mutate state, change `backend/routers/memories.py`,
or claim approval. It ties the current local proof chain to the remaining real
service/runtime evidence that must exist before route wiring changes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


def _load_external_readiness_module():
    spec = importlib.util.spec_from_file_location(
        "v17_p1_3_v3_external_compatibility_readiness",
        Path(__file__).with_name("v17_p1_3_v3_external_compatibility_readiness.py"),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v17_p1_3_v3_external_compatibility_readiness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_EXTERNAL = _load_external_readiness_module()

PROOF_CONSTANTS = {
    "decision_service_proof": _EXTERNAL.DECISION_SERVICE_PROOF,
    "cursor_service_proof": _EXTERNAL.CURSOR_SERVICE_PROOF,
    "projection_readiness_proof": _EXTERNAL.PROJECTION_READINESS_PROOF,
    "memory_read_service_proof": _EXTERNAL.MEMORY_READ_SERVICE_PROOF,
    "write_convergence_proof": _EXTERNAL.WRITE_CONVERGENCE_PROOF,
    "response_adapter_proof": _EXTERNAL.RESPONSE_ADAPTER_PROOF,
    "request_adapter_proof": _EXTERNAL.REQUEST_ADAPTER_PROOF,
    "route_planner_proof": _EXTERNAL.ROUTE_PLANNER_PROOF,
    "route_signature_integration_proof": _EXTERNAL.ROUTE_SIGNATURE_INTEGRATION_PROOF,
    "fastapi_route_contract_proof": _EXTERNAL.FASTAPI_ROUTE_CONTRACT_PROOF,
    "real_router_dependency_map_proof": _EXTERNAL.REAL_ROUTER_DEPENDENCY_MAP_PROOF,
    "real_router_get_testclient_proof": _EXTERNAL.REAL_ROUTER_GET_TESTCLIENT_PROOF,
    "get_dependency_auth_readiness_proof": _EXTERNAL.GET_DEPENDENCY_AUTH_READINESS_PROOF,
    "projection_store_readiness_proof": _EXTERNAL.PROJECTION_STORE_READINESS_PROOF,
    "control_reader_readiness_proof": _EXTERNAL.CONTROL_READER_READINESS_PROOF,
}


EXISTING_LOCAL_PROOF_ARTIFACTS = {
    key: {
        **proof,
        "missing_real_service_runtime_evidence": True,
        **(
            {
                "current_runtime_behavior_proven": (
                    "GET /v3/memories still calls stubbed legacy memories_db.get_memories(uid, limit, offset)"
                )
            }
            if key == "real_router_get_testclient_proof"
            else {}
        ),
    }
    for key, proof in PROOF_CONSTANTS.items()
}


REMAINING_GATES = [
    {
        "gate_id": "real_v17_control_read_fail_closed",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_evidence": (
            "Real V17 cohort/enrollment/control read source must be server-side, bounded, schema/uid validated, "
            "and fail-closed for enrolled missing/malformed/timeout states, without client-side direct control reads "
            "if that is unsafe."
        ),
        "existing_local_proofs": [
            "decision_service_proof",
            "memory_read_service_proof",
            "route_planner_proof",
            "control_reader_readiness_proof",
        ],
        "missing_real_service_runtime_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "gate_id": "real_v17_compatibility_projection_read_api_store",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_evidence": (
            "Real V17-derived compatibility projection read API/store must return MemoryDB-compatible items, prove "
            "ready empty projection state returns [], and expose generation/freshness fences without legacy fallback."
        ),
        "existing_local_proofs": [
            "projection_readiness_proof",
            "projection_store_readiness_proof",
            "memory_read_service_proof",
            "response_adapter_proof",
        ],
        "missing_real_service_runtime_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "gate_id": "real_external_write_convergence_source_of_truth",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_evidence": (
            "Real external write-convergence/source-of-truth evidence for /v3 create/update/delete must prove V17 "
            "authoritative writes, projection commits, tombstones, vector cleanup fences, and no direct legacy write "
            "fallback before V17 read cutover."
        ),
        "existing_local_proofs": ["write_convergence_proof", "projection_readiness_proof"],
        "missing_real_service_runtime_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "gate_id": "real_cursor_secret_validation_integration",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_evidence": (
            "Real cursor signing secret/config and route validation integration must reject tamper/expiry/filter or "
            "generation mismatch and must not apply offset=0 -> limit=5000 behavior in V17 cursor mode."
        ),
        "existing_local_proofs": ["cursor_service_proof", "request_adapter_proof", "memory_read_service_proof"],
        "missing_real_service_runtime_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "gate_id": "real_route_dependency_auth_rate_limit_testclient",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_evidence": (
            "Real route-level dependency overrides/auth/rate-limit behavior under TestClient must execute GET through "
            "the actual router dependencies while keeping production app startup and mutating routes out of scope."
        ),
        "existing_local_proofs": [
            "fastapi_route_contract_proof",
            "real_router_dependency_map_proof",
            "real_router_get_testclient_proof",
            "get_dependency_auth_readiness_proof",
        ],
        "missing_real_service_runtime_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "gate_id": "non_enrolled_legacy_backward_compatibility",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_evidence": (
            "Backward compatibility for non-enrolled legacy users must preserve current limit/offset semantics, "
            "including offset=0 -> limit=5000 first-page behavior only on the legacy-primary path."
        ),
        "existing_local_proofs": [
            "decision_service_proof",
            "request_adapter_proof",
            "memory_read_service_proof",
            "real_router_get_testclient_proof",
        ],
        "missing_real_service_runtime_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "gate_id": "enrolled_fail_closed_no_fallback_states",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_evidence": (
            "Enrolled fail-closed/no-grant/projection-not-ready/write-not-ready behavior must return the prescribed "
            "deny/fail-closed response with no legacy fallback, no V17/legacy merge, and no exception downgrade."
        ),
        "existing_local_proofs": ["decision_service_proof", "route_planner_proof", "memory_read_service_proof"],
        "missing_real_service_runtime_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "gate_id": "archive_unavailable_short_term_not_default_visible",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_evidence": (
            "Archive default-unavailable and stale Short-term not default-visible proof must be preserved in real route "
            "fixtures, projection reads, cursor mode, and observability before exposing V17 GET reads."
        ),
        "existing_local_proofs": [
            "projection_readiness_proof",
            "write_convergence_proof",
            "response_adapter_proof",
            "request_adapter_proof",
            "route_planner_proof",
        ],
        "missing_real_service_runtime_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "gate_id": "observability_telemetry_and_approval",
        "status": "BLOCKED",
        "route_refs": ["GET /v3/memories"],
        "required_evidence": (
            "Observability/telemetry gates and explicit approval gates must exist for read source, decision, failure "
            "reason, projection generation, cursor validation, canary cohort, rollback, and product/privacy approval."
        ),
        "existing_local_proofs": ["response_adapter_proof", "memory_read_service_proof"],
        "missing_real_service_runtime_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
]


PROPOSED_SAFE_CUTOVER_SEQUENCE = [
    {
        "step_id": "wire_server_side_control_reader",
        "description": "Add the real server-side V17 cohort/control/grant reader behind bounded fail-closed semantics.",
        "implements_runtime_wiring_now": False,
    },
    {
        "step_id": "wire_projection_store_read_api",
        "description": "Add the real V17-derived compatibility projection read API/store with generation/freshness checks.",
        "implements_runtime_wiring_now": False,
    },
    {
        "step_id": "prove_write_convergence_source_of_truth",
        "description": "Prove external /v3 create/update/delete converge to V17 authoritative state before reads use V17.",
        "implements_runtime_wiring_now": False,
    },
    {
        "step_id": "configure_cursor_secret_and_validation",
        "description": "Configure real cursor signing secret and integrate route validation for V17 cursor mode only.",
        "implements_runtime_wiring_now": False,
    },
    {
        "step_id": "add_route_dependency_testclient_proofs",
        "description": "Extend real-router TestClient proofs to actual auth/rate-limit/dependency behavior for GET.",
        "implements_runtime_wiring_now": False,
    },
    {
        "step_id": "wire_get_route_behind_fail_closed_planner",
        "description": "Only after gates pass, route GET through request adapter -> planner -> read service -> response adapter.",
        "implements_runtime_wiring_now": False,
        "must_preserve": [
            "non_enrolled_legacy_primary_current_limit_offset_behavior",
            "offset_zero_limit_5000_only_for_legacy_primary",
            "enrolled_fail_closed_no_legacy_fallback",
            "archive_default_unavailable",
            "stale_short_term_not_default_visible",
        ],
    },
    {
        "step_id": "observe_shadow_then_canary",
        "description": "Run shadow/canary with telemetry for read-source/decision/failure/cursor/projection-generation and rollback.",
        "implements_runtime_wiring_now": False,
    },
    {
        "step_id": "approval_gate_before_rollout",
        "description": "Require explicit product/privacy/operational approval before expanding beyond canary.",
        "implements_runtime_wiring_now": False,
    },
]


def build_report(*, execute: bool = False) -> dict[str, Any]:
    blocked_gate_count = sum(1 for gate in REMAINING_GATES if gate["status"] == "BLOCKED")
    missing_runtime_evidence_count = sum(1 for gate in REMAINING_GATES if gate["missing_real_service_runtime_evidence"])
    return {
        "artifact": "v17_p1_3_v3_get_runtime_wiring_readiness",
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
        "production_rollout_approved": False,
        "approval_claimed": False,
        "scope": "Remaining gates before changing backend/routers/memories.py GET /v3/memories runtime wiring.",
        "current_runtime_baseline": {
            "source": "backend/scripts/v17_p1_3_v3_real_router_get_testclient.py",
            "status": "BLOCKED",
            "proven_behavior": (
                "GET /v3/memories currently invokes legacy memories_db.get_memories(uid, limit, offset); "
                "offset=0 is coerced to limit=5000; nonzero limit/offset are preserved; V17 adapters are not invoked."
            ),
            "runtime_cutover_claimed": False,
        },
        "remaining_gates": REMAINING_GATES,
        "existing_local_proof_artifacts": EXISTING_LOCAL_PROOF_ARTIFACTS,
        "proposed_safe_cutover_sequence": PROPOSED_SAFE_CUTOVER_SEQUENCE,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No production traffic, Firestore, Pinecone, cloud, provider, or network calls executed.",
            "No mutations or approval claimed.",
            "Readiness/unit proofs are not production evidence for real service runtime gates.",
        ],
        "summary": {
            "status": "BLOCKED",
            "proof_status": "BLOCKED" if execute else "NOT_RUN",
            "remaining_gate_count": len(REMAINING_GATES),
            "blocked_gate_count": blocked_gate_count,
            "existing_local_proof_count": len(EXISTING_LOCAL_PROOF_ARTIFACTS),
            "missing_real_service_runtime_evidence_count": missing_runtime_evidence_count,
            "read_only": True,
            "mutation_allowed": False,
            "runtime_wiring_changed": False,
            "approval_claimed": False,
            "safe_cutover_step_count": len(PROPOSED_SAFE_CUTOVER_SEQUENCE),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Emit the same safe BLOCKED gate inventory")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
