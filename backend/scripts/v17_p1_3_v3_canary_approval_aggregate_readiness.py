#!/usr/bin/env python3
"""Final local V17 `/v3` canary approval GO/NO-GO aggregate readiness report.

This runner is a local-only pre-runtime decision artifact. It consolidates the
schema, source/IAM, production read, lifecycle/evidence, observability, runtime,
and external compatibility readiness contracts into one NO-GO report. It does not
import FastAPI routers, read or write production services, call cloud/vector
providers, emit sink events, claim approval, or change route wiring. `--execute`
only executes local report builders and forces the production-read report into a
missing-prerequisite path so no production read can occur.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

ROUTE_SCOPE = "GET /v3/memories"
SCRIPT_DIR = Path(__file__).resolve().parent


def _load_script_module(script_name: str):
    spec = importlib.util.spec_from_file_location(script_name.removesuffix(".py"), SCRIPT_DIR / script_name)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SOURCE = _load_script_module("v17_p1_3_v3_canary_approval_source_readiness.py")
_PRODUCTION = _load_script_module("v17_p1_3_v3_canary_approval_production_readiness.py")
_LIFECYCLE = _load_script_module("v17_p1_3_v3_canary_approval_lifecycle_readiness.py")
_OBSERVABILITY = _load_script_module("v17_p1_3_v3_observability_approval_readiness.py")
_RUNTIME = _load_script_module("v17_p1_3_v3_get_runtime_wiring_readiness.py")
_EXTERNAL = _load_script_module("v17_p1_3_v3_external_compatibility_readiness.py")

SCHEMA_VALIDATOR_PROOF = {
    "source_artifact": "backend/utils/memory/v17_v3_canary_approval.py",
    "test_artifact": "backend/tests/unit/test_v17_v3_canary_approval_artifact.py",
    "status": "READY_LOCAL_CONTRACT",
    "route_scope": ROUTE_SCOPE,
    "local_schema_validator_present": True,
    "runtime_wired": False,
    "production_rollout_approved": False,
    "approval_claimed": False,
}

TELEMETRY_PRIVACY_LABEL_CONTRACT = {
    "label_scope": "route_level_low_cardinality_only",
    "allowed_route_label": "get_v3_memories",
    "allowed_decision_values": ["no_go", "blocked", "ready_local_contract"],
    "dynamic_labels_allowed": False,
    "sensitive_labels_allowed": False,
    "content_labels_allowed": False,
    "unbounded_labels_allowed": False,
    "sink_call_executed": False,
}

NON_CLAIMS = [
    "Default-off backend/routers/memories.py GET seam exists, but no effective runtime /v3 behavior change.",
    "No runtime /v3 behavior change.",
    "No production rollout approval.",
    "No production Firestore writes/cloud/provider/vector/network calls by default or with --execute.",
    "No telemetry sink production call.",
    "No PII/raw memory content telemetry.",
    "No secret/cursor token logging.",
    "No legacy fallback/merge for V17 failures.",
    "No Archive default visibility or stale Short-term default visibility.",
]


def _safe_report(script_module: Any, *, execute: bool) -> dict[str, Any]:
    return script_module.build_report(execute=execute)


def _production_report(*, execute: bool) -> dict[str, Any]:
    return _PRODUCTION.build_report(execute=execute, env={})


def _gate_rows(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    source_summary = reports["source"]["summary"]
    production_summary = reports["production"]["summary"]
    lifecycle_summary = reports["lifecycle"]["summary"]
    observability_summary = reports["observability"]["summary"]
    runtime_summary = reports["runtime"]["summary"]
    external_summary = reports["external"]["summary"]
    return [
        {
            "gate_id": "local_schema_validator_present",
            "status": "READY_LOCAL_CONTRACT",
            "route_scope": ROUTE_SCOPE,
            "source_artifact": SCHEMA_VALIDATOR_PROOF["source_artifact"],
            "test_artifact": SCHEMA_VALIDATOR_PROOF["test_artifact"],
            "local_schema_validator_present": True,
            "required_before_go": True,
            "approval_claimed": False,
        },
        {
            "gate_id": "source_iam_emulator_client_deny_readiness_present",
            "status": "READY_LOCAL_CONTRACT",
            "route_scope": ROUTE_SCOPE,
            "source_artifact": "backend/scripts/v17_p1_3_v3_canary_approval_source_readiness.py",
            "direct_client_access_proven_denied": source_summary["direct_client_access_proven_denied"],
            "static_iam_rules_emulator_readiness_present": source_summary[
                "static_iam_rules_emulator_readiness_present"
            ],
            "backend_service_principal_read_proven": source_summary["backend_service_principal_read_proven"],
            "production_artifact_source_exists": source_summary["production_artifact_source_exists"],
            "required_before_go": True,
            "approval_claimed": False,
        },
        {
            "gate_id": "production_read_proof_missing_not_run",
            "status": "BLOCKED",
            "route_scope": ROUTE_SCOPE,
            "source_artifact": "backend/scripts/v17_p1_3_v3_canary_approval_production_readiness.py",
            "proof_status": production_summary["proof_status"],
            "missing_prerequisite_count": production_summary["missing_prerequisite_count"],
            "backend_service_principal_read_proven": production_summary["backend_service_principal_read_proven"],
            "production_artifact_source_exists": production_summary["production_artifact_source_exists"],
            "production_artifact_valid": production_summary["production_artifact_valid"],
            "required_before_go": True,
            "approval_claimed": False,
        },
        {
            "gate_id": "lifecycle_evidence_bundle_missing_blocked",
            "status": "BLOCKED",
            "route_scope": ROUTE_SCOPE,
            "source_artifact": "backend/scripts/v17_p1_3_v3_canary_approval_lifecycle_readiness.py",
            "required_evidence_count": lifecycle_summary["required_evidence_count"],
            "blocked_required_evidence_count": lifecycle_summary["blocked_required_evidence_count"],
            "required_before_go": True,
            "approval_claimed": False,
        },
        {
            "gate_id": "observability_telemetry_approval_blocked",
            "status": "BLOCKED",
            "route_scope": ROUTE_SCOPE,
            "source_artifact": "backend/scripts/v17_p1_3_v3_observability_approval_readiness.py",
            "telemetry_field_count": observability_summary["telemetry_field_count"],
            "blocked_or_not_run_field_count": observability_summary["blocked_or_not_run_field_count"],
            "telemetry_sink_calls_executed": observability_summary["telemetry_sink_calls_executed"],
            "required_before_go": True,
            "approval_claimed": False,
        },
        {
            "gate_id": "runtime_wiring_blocked",
            "status": "BLOCKED",
            "route_scope": ROUTE_SCOPE,
            "source_artifact": "backend/scripts/v17_p1_3_v3_get_runtime_wiring_readiness.py",
            "remaining_gate_count": runtime_summary["remaining_gate_count"],
            "blocked_gate_count": runtime_summary["blocked_gate_count"],
            "route_wiring": runtime_summary.get("route_wiring", False),
            "runtime_wiring_changed": runtime_summary["runtime_wiring_changed"],
            "effective_runtime_behavior_changed": runtime_summary.get("effective_runtime_behavior_changed", False),
            "required_before_go": True,
            "approval_claimed": False,
        },
        {
            "gate_id": "external_compatibility_blocked",
            "status": "BLOCKED",
            "route_scope": ROUTE_SCOPE,
            "source_artifact": "backend/scripts/v17_p1_3_v3_external_compatibility_readiness.py",
            "surface_count": external_summary["surface_count"],
            "gap_count": external_summary["gap_count"],
            "required_before_go": True,
            "approval_claimed": False,
        },
    ]


def _remaining_blockers() -> list[dict[str, Any]]:
    return [
        {
            "blocker_id": "real_production_backend_service_principal_read_proof_missing",
            "status": "BLOCKED",
            "required_evidence": "Real read-only backend service-principal proof for the route-scoped approval artifact.",
            "required_before_go": True,
        },
        {
            "blocker_id": "production_artifact_existence_and_validity_missing",
            "status": "BLOCKED",
            "required_evidence": "Production approval artifact exists and validates against the local schema contract.",
            "required_before_go": True,
        },
        {
            "blocker_id": "human_approval_evidence_bundle_missing",
            "status": "BLOCKED",
            "required_evidence": "Human approval, owner groups, expiry/rotation, rollback owner, and monitoring evidence bundle.",
            "required_before_go": True,
        },
        {
            "blocker_id": "telemetry_sink_and_runbook_proof_missing",
            "status": "BLOCKED",
            "required_evidence": "Approved sink integration, bounded labels, alert/runbook, and rollback observability proof.",
            "required_before_go": True,
        },
        {
            "blocker_id": "runtime_route_wiring_gates_blocked",
            "status": "BLOCKED",
            "required_evidence": "All remaining runtime, external compatibility, fail-closed, and route wiring gates pass.",
            "required_before_go": True,
        },
    ]


def build_report(*, execute: bool = False) -> dict[str, Any]:
    local_execute = bool(execute)
    reports = {
        "source": _safe_report(_SOURCE, execute=local_execute),
        "production": _production_report(execute=local_execute),
        "lifecycle": _safe_report(_LIFECYCLE, execute=local_execute),
        "observability": _safe_report(_OBSERVABILITY, execute=local_execute),
        "runtime": _safe_report(_RUNTIME, execute=local_execute),
        "external": _safe_report(_EXTERNAL, execute=local_execute),
    }
    gates = _gate_rows(reports)
    ready_gate_count = sum(1 for gate in gates if gate["status"] == "READY_LOCAL_CONTRACT")
    blocked_gate_count = sum(1 for gate in gates if gate["status"] == "BLOCKED")
    blockers = _remaining_blockers()
    proof_status = "BLOCKED" if execute else "NOT_RUN"
    runtime_summary = reports["runtime"]["summary"]
    return {
        "artifact": "v17_p1_3_v3_canary_approval_aggregate_readiness",
        "status": "BLOCKED",
        "decision": "NO_GO",
        "proof_status": proof_status,
        "execute": execute,
        "route_scope": ROUTE_SCOPE,
        "read_only": True,
        "mutation_allowed": False,
        "route_wiring": runtime_summary.get("route_wiring", False),
        "runtime_wiring_changed": runtime_summary["runtime_wiring_changed"],
        "effective_runtime_behavior_changed": runtime_summary.get("effective_runtime_behavior_changed", False),
        "routers_memories_modified": runtime_summary.get("route_wiring", False),
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "telemetry_sink_calls_executed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "scope": "Final local NO-GO aggregate readiness for future GET /v3/memories canary approval.",
        "schema_validator_proof": SCHEMA_VALIDATOR_PROOF,
        "component_reports": reports,
        "gate_rows": gates,
        "remaining_blockers": blockers,
        "telemetry_privacy_label_contract": TELEMETRY_PRIVACY_LABEL_CONTRACT,
        "non_claims": NON_CLAIMS,
        "summary": {
            "status": "BLOCKED",
            "decision": "NO_GO",
            "proof_status": proof_status,
            "route_scope": ROUTE_SCOPE,
            "gate_count": len(gates),
            "ready_gate_count": ready_gate_count,
            "blocked_gate_count": blocked_gate_count,
            "remaining_blocker_count": len(blockers),
            "route_wiring": runtime_summary.get("route_wiring", False),
            "runtime_wiring_changed": runtime_summary["runtime_wiring_changed"],
            "effective_runtime_behavior_changed": runtime_summary.get("effective_runtime_behavior_changed", False),
            "production_rollout_approved": False,
            "approval_claimed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="Emit local aggregate NO-GO readiness without prod calls"
    )
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
