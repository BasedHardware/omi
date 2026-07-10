#!/usr/bin/env python3
"""Production-safe memory `/v3` canary approval read-proof readiness contract.

This runner is disabled by default. Without explicit environment gates it performs
no production calls and reports NOT_RUN/BLOCKED. With the gates present it may run
one read-only backend service-principal document read for
`system/v3_canary_approvals/routes/get_v3_memories`, validate the artifact
using the local memory canary approval schema seam, and still refuse to claim product
rollout approval or route readiness. It never imports FastAPI routers, writes
Firestore, calls vector/provider services, emits telemetry sinks, or changes
runtime behavior.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from testing.memory.v3_canary_approval import ROUTE_SCOPE, validate_memory_v3_canary_approval_artifact

ARTIFACT_DOCUMENT_PATH = "system/v3_canary_approvals/routes/get_v3_memories"
ARTIFACT_SOURCE = f"firestore:{ARTIFACT_DOCUMENT_PATH}"
ALLOW_ENV = "MEMORY_V3_CANARY_APPROVAL_PROD_READ_ALLOW"
PROJECT_ID_ENV = "MEMORY_V3_CANARY_APPROVAL_PROD_READ_PROJECT_ID"
SERVICE_ACCOUNT_EMAIL_ENV = "MEMORY_V3_CANARY_APPROVAL_PROD_READ_SERVICE_ACCOUNT_EMAIL"
GOOGLE_PROJECT_ENV = "GOOGLE_CLOUD_PROJECT"
GOOGLE_CREDENTIALS_ENV = "GOOGLE_APPLICATION_CREDENTIALS"
SERVICE_ACCOUNT_JSON_ENV = "SERVICE_ACCOUNT_JSON"
DEFAULT_COHORT = "canary_1"

CANARY_APPROVAL_LIFECYCLE_READINESS_PROOF = {
    "service": "backend/scripts/p1_3_v3_canary_approval_lifecycle_readiness.py",
    "test": "backend/tests/unit/test_p1_3_v3_canary_approval_lifecycle_readiness.py",
    "status": "BLOCKED",
    "proof_status": "NOT_RUN",
    "route_scope": ROUTE_SCOPE,
    "read_only": True,
    "runtime_wired": False,
    "production_rollout_approved": False,
    "approval_claimed": False,
    "blocker": "Production artifact read proof remains insufficient without lifecycle/evidence-bundle approval evidence.",
}


def _base_proof() -> dict[str, Any]:
    return {
        "artifact_document_path": ARTIFACT_DOCUMENT_PATH,
        "artifact_source": ARTIFACT_SOURCE,
        "route_scope": ROUTE_SCOPE,
        "backend_service_principal_read_required": True,
        "backend_service_principal_read_proven": False,
        "production_artifact_source_exists": False,
        "production_artifact_valid": False,
        "artifact_validation_reason": "not_run",
        "bounded_owners_and_cohorts_valid": False,
        "approval_metadata_only": False,
        "no_high_cardinality_or_sensitive_fields": False,
        "missing_prerequisites": [],
        "read_error": None,
        "project_id_present": False,
        "service_account_email_present": False,
        "credentials_present": False,
        "read_only_firestore_method": "DocumentReference.get",
        "mutating_firestore_methods_allowed": False,
        "runtime_wired": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
    }


def _missing_prerequisites(env: Mapping[str, str]) -> list[str]:
    missing: list[str] = []
    if env.get(ALLOW_ENV) != "1":
        missing.append(f"{ALLOW_ENV}=1")
    if not (env.get(PROJECT_ID_ENV) or env.get(GOOGLE_PROJECT_ENV)):
        missing.append(f"{PROJECT_ID_ENV} or {GOOGLE_PROJECT_ENV}")
    if not (env.get(GOOGLE_CREDENTIALS_ENV) or env.get(SERVICE_ACCOUNT_JSON_ENV)):
        missing.append(f"{GOOGLE_CREDENTIALS_ENV} or {SERVICE_ACCOUNT_JSON_ENV}")
    if not env.get(SERVICE_ACCOUNT_EMAIL_ENV):
        missing.append(SERVICE_ACCOUNT_EMAIL_ENV)
    return missing


def _read_artifact_with_firestore(project_id: str) -> dict[str, Any] | None:
    firestore_module = importlib.import_module("google.cloud.firestore")
    client = firestore_module.Client(project=project_id)
    snapshot = client.document(ARTIFACT_DOCUMENT_PATH).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict()
    if not isinstance(data, dict):
        return None
    return data


def _evaluate_artifact(artifact: dict[str, Any] | None, *, now: datetime) -> dict[str, Any]:
    decision = validate_memory_v3_canary_approval_artifact(
        artifact,
        requested_route_scope=ROUTE_SCOPE,
        requested_cohort=DEFAULT_COHORT,
        now=now,
    )
    valid = bool(decision.approved and not decision.fail_closed and decision.reason == "approved")
    return {
        "production_artifact_source_exists": artifact is not None,
        "production_artifact_valid": valid,
        "artifact_validation_reason": decision.reason,
        "bounded_owners_and_cohorts_valid": valid,
        "approval_metadata_only": valid,
        "no_high_cardinality_or_sensitive_fields": valid,
    }


def build_report(
    *,
    execute: bool = False,
    env: Mapping[str, str] | None = None,
    reader: Callable[[], dict[str, Any] | None] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    effective_env = os.environ if env is None else env
    checked_at = now or datetime.now(timezone.utc)
    proof = _base_proof()
    proof["project_id_present"] = bool(effective_env.get(PROJECT_ID_ENV) or effective_env.get(GOOGLE_PROJECT_ENV))
    proof["service_account_email_present"] = bool(effective_env.get(SERVICE_ACCOUNT_EMAIL_ENV))
    proof["credentials_present"] = bool(
        effective_env.get(GOOGLE_CREDENTIALS_ENV) or effective_env.get(SERVICE_ACCOUNT_JSON_ENV)
    )
    proof["missing_prerequisites"] = _missing_prerequisites(effective_env)

    network_or_provider_calls_executed = False
    firestore_reads_executed = False
    proof_status = "NOT_RUN"

    if execute:
        missing = proof["missing_prerequisites"]
        if not missing:
            try:
                project_id = effective_env.get(PROJECT_ID_ENV) or effective_env.get(GOOGLE_PROJECT_ENV) or ""
                network_or_provider_calls_executed = True
                firestore_reads_executed = True
                artifact = reader() if reader is not None else _read_artifact_with_firestore(project_id)
                proof["backend_service_principal_read_proven"] = True
                evaluation = _evaluate_artifact(artifact, now=checked_at)
                proof = {**proof, **evaluation}
                proof_status = "PROVEN_READ_ONLY" if proof["production_artifact_valid"] else "BLOCKED"
            except ModuleNotFoundError as exc:
                proof["read_error"] = f"dependency_unavailable:{exc.name}"
                proof_status = "BLOCKED"
            except Exception as exc:
                proof["read_error"] = f"read_failed:{type(exc).__name__}"
                proof_status = "BLOCKED"

    summary = {
        "status": "BLOCKED",
        "proof_status": proof_status,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "missing_prerequisite_count": len(proof["missing_prerequisites"]),
        "backend_service_principal_read_proven": proof["backend_service_principal_read_proven"],
        "production_artifact_source_exists": proof["production_artifact_source_exists"],
        "production_artifact_valid": proof["production_artifact_valid"],
        "production_rollout_approved": False,
        "approval_claimed": False,
    }
    return {
        "artifact": "p1_3_v3_canary_approval_production_readiness",
        "status": "BLOCKED",
        "proof_status": proof_status,
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "routers_memories_modified": False,
        "network_or_provider_calls_executed": network_or_provider_calls_executed,
        "provider_calls_executed": False,
        "firestore_reads_executed": firestore_reads_executed,
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "telemetry_sink_calls_executed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "production_read_proof": proof,
        "canary_approval_lifecycle_readiness_proof": CANARY_APPROVAL_LIFECYCLE_READINESS_PROOF,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No runtime /v3 behavior changed.",
            "No production rollout approval claimed, even when the artifact read and shape validate.",
            "No production Firestore write, vector/provider call, or telemetry sink call is allowed.",
            "No PII/raw memory content telemetry emitted.",
            "No secret/cursor token logging allowed or performed.",
            "No legacy fallback/merge for memory failures claimed.",
            "No Archive default visibility or stale Short-term default visibility claimed.",
        ],
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the read-only production proof only when all explicit environment gates are present",
    )
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
