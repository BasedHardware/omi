#!/usr/bin/env python3
"""Safe `/v3` V17 cohort/control reader readiness artifact.

This is a read-only local contract inventory for the future server-side V17
cohort/enrollment/control reader needed before `GET /v3/memories` can be cut
over. It intentionally does not import FastAPI routers, read Firestore, call
Pinecone/providers/cloud/network services, mutate state, implement a production
control reader, wire runtime routes, or claim approval.
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
    "fastapi_route_contract_proof": _EXTERNAL.FASTAPI_ROUTE_CONTRACT_PROOF,
    "get_dependency_auth_readiness_proof": _EXTERNAL.GET_DEPENDENCY_AUTH_READINESS_PROOF,
    "projection_store_readiness_proof": _EXTERNAL.PROJECTION_STORE_READINESS_PROOF,
    "control_reader_contract_proof": _EXTERNAL.CONTROL_READER_CONTRACT_PROOF,
    "control_reader_emulator_readiness_proof": _EXTERNAL.CONTROL_READER_EMULATOR_READINESS_PROOF,
    "get_runtime_wiring_readiness_proof": _EXTERNAL.GET_RUNTIME_WIRING_READINESS_PROOF,
}

EXISTING_LOCAL_PROOF_ARTIFACTS = {
    key: {
        **proof,
        "missing_real_firestore_api_emulator_rules_iam_evidence": True,
    }
    for key, proof in PROOF_CONSTANTS.items()
}

FAIL_CLOSED_REASONS = [
    "missing_control_doc",
    "control_read_failed",
    "malformed_control_doc",
    "uid_mismatch",
    "unsupported_control_schema",
    "global_read_gate_closed",
    "stale_generation",
    "no_default_memory_grant",
    "projection_not_ready",
    "write_convergence_not_ready",
    "invalid_or_missing_cursor_secret",
    "archive_not_allowed",
]

CONTROL_READER_REQUIREMENTS = [
    {
        "requirement_id": "canonical_control_source_path_api",
        "status": "READY_LOCAL_ADAPTER_PROVEN",
        "required_contract": "Reuse the existing canonical server-side V17 rollout state path for `/v3` cohort enrollment and per-user read control.",
        "canonical_path": "users/{uid}/memory_control/state",
        "explicit_blocker": None,
        "candidate_paths": ["users/{uid}/memory_control/state"],
        "evidence_sources": [
            "control_reader_state_adapter_proof",
            "decision_service_proof",
            "get_runtime_wiring_readiness_proof",
        ],
        "missing_real_firestore_api_emulator_rules_iam_evidence": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "server_owned_control_reads_only",
        "status": "BLOCKED",
        "required_contract": "V17 cohort/enrollment/control reads for `/v3` must be server-owned and must not require or permit direct client control-document reads.",
        "server_owned_read_only": True,
        "direct_client_control_reads_allowed": False,
        "security_rules_and_iam_proof_required": True,
        "evidence_sources": ["get_dependency_auth_readiness_proof", "decision_service_proof"],
        "missing_real_firestore_api_emulator_rules_iam_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "fake_injectable_control_reader_interface",
        "status": "BLOCKED",
        "required_contract": "Define a fake-injectable server control reader interface shape for future route wiring, without wiring it now.",
        "runtime_route_wiring_now": False,
        "production_firestore_reader_implemented": False,
        "evidence_sources": [
            "control_reader_contract_proof",
            "memory_read_service_proof",
            "route_planner_proof",
            "get_runtime_wiring_readiness_proof",
        ],
        "missing_real_firestore_api_emulator_rules_iam_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "fail_closed_decision_matrix",
        "status": "BLOCKED",
        "required_contract": "Enrolled effective-read V17 users must fail closed or privacy-deny for control-read, schema, uid, global gate, stale-generation, no-grant, projection, write, cursor, or archive failures. Stale Short-term filtering is item/read-service state, not route-control state.",
        "fail_closed_reasons": FAIL_CLOSED_REASONS,
        "evidence_sources": [
            "decision_service_proof",
            "control_reader_contract_proof",
            "cursor_service_proof",
            "projection_readiness_proof",
            "write_convergence_proof",
            "request_adapter_proof",
            "route_planner_proof",
        ],
        "missing_real_firestore_api_emulator_rules_iam_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "non_enrolled_legacy_path_preservation",
        "status": "BLOCKED",
        "required_contract": "Non-enrolled users preserve current legacy `/v3` GET behavior, including offset=0 -> limit=5000 only on the legacy-primary path.",
        "non_enrolled_read_path": "legacy_primary",
        "offset_zero_limit_5000_preserved_for_legacy_only": True,
        "v17_cursor_required_for_enrolled": True,
        "evidence_sources": [
            "memory_read_service_proof",
            "request_adapter_proof",
            "get_runtime_wiring_readiness_proof",
        ],
        "missing_real_firestore_api_emulator_rules_iam_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "enrolled_no_legacy_fallback_on_gate_failure",
        "status": "BLOCKED",
        "required_contract": "Enrolled effective-read users must not fall back to legacy reads on V17 control, grant, projection, write-convergence, cursor, or Archive failures. Effective off/shadow/write keeps legacy primary authoritative, not fallback.",
        "legacy_fallback_allowed_for_enrolled_gate_failures": False,
        "legacy_v17_result_merge_allowed": False,
        "exception_downgrade_to_legacy_allowed": False,
        "evidence_sources": [
            "decision_service_proof",
            "control_reader_contract_proof",
            "memory_read_service_proof",
            "route_planner_proof",
        ],
        "missing_real_firestore_api_emulator_rules_iam_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "proof_chain_dependencies",
        "status": "BLOCKED",
        "required_contract": "Control reader cutover requires the projection store, dependency/auth, route planner, request/response/cursor, and write-convergence proof chain.",
        "required_proofs": list(PROOF_CONSTANTS),
        "evidence_sources": list(PROOF_CONSTANTS),
        "missing_real_firestore_api_emulator_rules_iam_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "real_evidence_blockers",
        "status": "BLOCKED",
        "required_contract": "Real Firestore/API/emulator/security rules/IAM evidence remains missing and must be collected before runtime route changes.",
        "missing_evidence": [
            "real_firestore_control_document_read",
            "controlled_api_or_emulator_control_reader_fixture",
            "security_rules_no_direct_client_control_reads",
            "iam_server_reader_principal_scope",
            "route_runtime_auth_dependency_execution",
        ],
        "evidence_sources": ["get_dependency_auth_readiness_proof", "get_runtime_wiring_readiness_proof"],
        "missing_real_firestore_api_emulator_rules_iam_evidence": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
]

FAKE_INJECTABLE_CONTROL_READER_INTERFACE = {
    "interface_name": "V17V3ControlReader",
    "method": "read_v17_v3_control",
    "input_fields": ["uid", "db_client", "rollout_config", "consumer"],
    "output_fields": [
        "cohort_enrolled",
        "source_path",
        "uid",
        "schema_version",
        "configured_mode",
        "persisted_mode",
        "effective_mode",
        "mode_epoch",
        "cutover_epoch",
        "default_memory_grant",
        "account_generation",
        "projection_ready",
        "rollout_write_ready",
        "global_read_gate_open",
        "write_convergence_ready",
        "archive_allowed",
        "decision",
        "fail_closed_reason",
    ],
    "fake_injectable": True,
    "production_firestore_reader_implemented": True,
    "canonical_source_path": "users/{uid}/memory_control/state",
    "runtime_route_wiring_now": False,
}

FAIL_CLOSED_DECISION_MATRIX = [
    {
        "reason": "missing_control_doc",
        "enrolled_decision": "FAIL_CLOSED",
        "http_status": 503,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "control_read_failed",
        "enrolled_decision": "FAIL_CLOSED",
        "http_status": 503,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "malformed_control_doc",
        "enrolled_decision": "FAIL_CLOSED",
        "http_status": 503,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "uid_mismatch",
        "enrolled_decision": "FAIL_CLOSED",
        "http_status": 503,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "unsupported_control_schema",
        "enrolled_decision": "FAIL_CLOSED",
        "http_status": 503,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "global_read_gate_closed",
        "enrolled_decision": "FAIL_CLOSED",
        "http_status": 503,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "stale_generation",
        "enrolled_decision": "FAIL_CLOSED",
        "http_status": 503,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "no_default_memory_grant",
        "enrolled_decision": "DENY",
        "http_status": 403,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "projection_not_ready",
        "enrolled_decision": "FAIL_CLOSED",
        "http_status": 503,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "write_convergence_not_ready",
        "enrolled_decision": "FAIL_CLOSED",
        "http_status": 503,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "invalid_or_missing_cursor_secret",
        "enrolled_decision": "FAIL_CLOSED",
        "http_status": 503,
        "legacy_fallback_allowed": False,
        "required_before_runtime_change": True,
    },
    {
        "reason": "archive_not_allowed",
        "enrolled_decision": "DENY",
        "http_status": 403,
        "legacy_fallback_allowed": False,
        "archive_default_available": False,
        "required_before_runtime_change": True,
    },
]

LEGACY_BOUNDARY_CONTRACT = {
    "non_enrolled_read_path": "legacy_primary",
    "non_enrolled_offset_zero_limit_5000_preserved": True,
    "offset_zero_limit_5000_allowed_for_v17_cursor": False,
    "enrolled_gate_failure_legacy_fallback_allowed": False,
    "legacy_v17_result_merge_allowed": False,
}

PROPOSED_NEXT_SAFE_STEPS = [
    {
        "step_id": "choose_canonical_control_source_and_security_contract",
        "description": "Choose and document the canonical server-side V17 `/v3` control source/path/API plus security rules/IAM contract.",
        "implements_runtime_wiring_now": False,
    },
    {
        "step_id": "add_fake_control_reader_contract_tests",
        "description": "Add pure fake-reader tests for enrollment, grant, generation, projection, write, cursor, Archive, and Short-term fail-closed cases.",
        "implements_runtime_wiring_now": False,
    },
    {
        "step_id": "add_firestore_emulator_control_reader_proof",
        "description": "Use Firestore emulator fixtures to prove real control document reads without cloud calls.",
        "implements_runtime_wiring_now": False,
    },
    {
        "step_id": "prove_security_rules_and_iam_no_client_control_reads",
        "description": "Prove clients cannot directly read control docs and only the server principal can execute the reader.",
        "implements_runtime_wiring_now": False,
    },
    {
        "step_id": "wire_route_only_after_all_control_projection_write_cursor_gates_pass",
        "description": "Only wire `GET /v3/memories` after control, projection, write-convergence, cursor, auth, telemetry, and approval gates pass.",
        "implements_runtime_wiring_now": False,
    },
]


def build_report(*, execute: bool = False) -> dict[str, Any]:
    blocked_requirement_count = sum(1 for item in CONTROL_READER_REQUIREMENTS if item["status"] == "BLOCKED")
    missing_evidence_count = sum(
        1 for item in CONTROL_READER_REQUIREMENTS if item["missing_real_firestore_api_emulator_rules_iam_evidence"]
    )
    return {
        "artifact": "v17_p1_3_v3_control_reader_readiness",
        "status": "BLOCKED",
        "proof_status": "BLOCKED" if execute else "NOT_RUN",
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "production_control_reader_implemented": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "cloud_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "scope": "Readiness/local contract inventory for future server-side V17 `/v3` cohort/enrollment/control reader.",
        "control_reader_requirements": CONTROL_READER_REQUIREMENTS,
        "fake_injectable_control_reader_interface": FAKE_INJECTABLE_CONTROL_READER_INTERFACE,
        "fail_closed_decision_matrix": FAIL_CLOSED_DECISION_MATRIX,
        "legacy_boundary_contract": LEGACY_BOUNDARY_CONTRACT,
        "existing_local_proof_artifacts": EXISTING_LOCAL_PROOF_ARTIFACTS,
        "proposed_next_safe_steps": PROPOSED_NEXT_SAFE_STEPS,
        "non_claims": [
            "No production server-side control reader implemented.",
            "No real Firestore/API/emulator/security rules/IAM evidence collected.",
            "No Firestore, Pinecone, provider, cloud, or network calls executed.",
            "No `/v3` route wiring changed.",
            "No direct client control reads allowed or proven safe.",
            "No Archive default visibility or stale Short-term default visibility introduced.",
            "No rollout approval claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "proof_status": "BLOCKED" if execute else "NOT_RUN",
            "requirement_count": len(CONTROL_READER_REQUIREMENTS),
            "blocked_requirement_count": blocked_requirement_count,
            "fail_closed_reason_count": len(FAIL_CLOSED_REASONS),
            "existing_local_proof_count": len(EXISTING_LOCAL_PROOF_ARTIFACTS),
            "missing_real_evidence_requirement_count": missing_evidence_count,
            "read_only": True,
            "mutation_allowed": False,
            "runtime_wiring_changed": False,
            "production_control_reader_implemented": False,
            "approval_claimed": False,
            "safe_next_step_count": len(PROPOSED_NEXT_SAFE_STEPS),
            "control_reader_contract_proof_present": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Emit the same safe BLOCKED control reader report")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
