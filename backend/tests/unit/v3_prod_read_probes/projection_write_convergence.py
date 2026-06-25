#!/usr/bin/env python3
"""Production-safe memory `/v3` projection write convergence/freshness-fence readiness proof.

This runner defines the future evidence contract that must be proven before
`GET /v3/memories` can trust the memory-derived compatibility projection read
source. By default it performs no production calls and reports NOT_RUN/BLOCKED.
With explicit environment gates it may run one read-only metadata/evidence probe
for a route-scoped convergence state document. It never imports FastAPI routers,
changes route wiring, writes Firestore, calls vector/provider services, emits
telemetry sinks, trusts client-selected collection/path/source values, logs
secret/cursor/user content, or claims production rollout approval.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from collections.abc import Callable, Mapping
from typing import Any

ROUTE_SCOPE = "GET /v3/memories"
ROUTE_SCOPE_LABEL = "get_v3_memories"
SOURCE_TYPE = "firestore_projection_write_convergence_state"
STATE_PATH_TEMPLATE = "memory_control/projection_write_convergence"
ROUTE_STATE_PATH_TEMPLATE = "memory_control/projection_write_convergence/routes/{route_scope_label}"
SOURCE_NAME = "projection_write_convergence_state"
PROJECTION_VERSION = "v3_memorydb_compatibility"
MAX_STALENESS_SECONDS = 300

ALLOW_ENV = "MEMORY_V3_PROJECTION_WRITE_CONVERGENCE_PROD_READ_ALLOW"
PROJECT_ID_ENV = "MEMORY_V3_PROJECTION_WRITE_CONVERGENCE_PROD_READ_PROJECT_ID"
SERVICE_ACCOUNT_EMAIL_ENV = "MEMORY_V3_PROJECTION_WRITE_CONVERGENCE_PROD_READ_SERVICE_ACCOUNT_EMAIL"
ROUTE_SCOPE_LABEL_ENV = "MEMORY_V3_PROJECTION_WRITE_CONVERGENCE_PROD_READ_ROUTE_SCOPE_LABEL"
GOOGLE_PROJECT_ENV = "GOOGLE_CLOUD_PROJECT"
GOOGLE_CREDENTIALS_ENV = "GOOGLE_APPLICATION_CREDENTIALS"
SERVICE_ACCOUNT_JSON_ENV = "SERVICE_ACCOUNT_JSON"

FORBIDDEN_TELEMETRY_DIMENSIONS = [
    "uid",
    "user_id",
    "session_id",
    "memory_id",
    "request_payload",
    "cursor_token",
    "raw_cursor",
    "secret",
    "memory_content",
]

TELEMETRY_SAFE_LABELS = [
    "route_scope",
    "readiness_artifact",
    "evidence_decision",
    "failure_reason",
    "projection_schema_version",
    "writer_mode",
]

REQUIRED_FENCE_FIELDS = [
    "account_generation",
    "projection_generation",
    "freshness_fence_generation",
    "tombstone_fence_generation",
    "vector_cleanup_fence_generation",
]

PROJECTION_WRITE_CONVERGENCE_CONTRACT = {
    "source_type": SOURCE_TYPE,
    "route_scope": ROUTE_SCOPE,
    "route_scope_label": ROUTE_SCOPE_LABEL,
    "owner": "memory_platform",
    "state_path_template": STATE_PATH_TEMPLATE,
    "route_state_path_template": ROUTE_STATE_PATH_TEMPLATE,
    "source": SOURCE_NAME,
    "projection_version": PROJECTION_VERSION,
    "server_owned": True,
    "client_override_allowed": False,
    "client_controlled_collection_or_path_allowed": False,
    "durable_outbox_required": True,
    "durable_outbox_ack_required": True,
    "dual_write_projection_writer_required": True,
    "delete_tombstone_convergence_required": True,
    "idempotency_key_required": True,
    "required_fence_fields": REQUIRED_FENCE_FIELDS,
    "rollback_fail_closed_required": True,
    "rollback_to_legacy_after_memory_write_allowed": False,
    "fail_closed_on_missing_stale_malformed_evidence": True,
    "legacy_fallback_allowed": False,
    "merge_legacy_and_memory_allowed": False,
    "archive_default_available": False,
    "stale_short_term_default_visible": False,
    "runtime_wired": False,
    "required_state_fields": [
        "route_scope",
        "route_scope_label",
        "owner",
        "schema_version",
        "source",
        "projection_version",
        "ready",
        "max_staleness_seconds",
        "durable_outbox_ready",
        "all_outbox_events_acknowledged",
        "dual_write_projection_writer_ready",
        "projection_writer_ready",
        "create_update_convergence_complete",
        "delete_convergence_complete",
        "tombstone_convergence_complete",
        "delete_tombstone_convergence_complete",
        "idempotency_key_contract",
        "account_generation",
        "projection_generation",
        "freshness_fence_generation",
        "tombstone_fence_generation",
        "vector_cleanup_fence_generation",
        "rollback_behavior",
        "legacy_fallback_allowed",
        "merge_legacy_and_memory_allowed",
    ],
    "telemetry_safe_labels": TELEMETRY_SAFE_LABELS,
    "telemetry_forbidden_dimensions": FORBIDDEN_TELEMETRY_DIMENSIONS,
}

WRITE_CONVERGENCE_REQUIREMENTS = [
    {
        "requirement_id": "route_scoped_projection_write_convergence_source",
        "status": "LOCAL_CONTRACT_DEFINED",
        "route_scope": ROUTE_SCOPE,
        "server_owned": True,
        "state_path_template": STATE_PATH_TEMPLATE,
        "route_state_path_template": ROUTE_STATE_PATH_TEMPLATE,
        "client_override_allowed": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "durable_outbox_acknowledged_before_projection_reads",
        "status": "LOCAL_CONTRACT_DEFINED",
        "durable_outbox_required": True,
        "all_outbox_events_acknowledged": True,
        "projection_reads_trust_outbox_before_ack": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "dual_write_projection_writer_ready",
        "status": "LOCAL_CONTRACT_DEFINED",
        "dual_write_projection_writer_required": True,
        "projection_writer_ready": True,
        "direct_legacy_only_write_after_memory_enabled_allowed": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "delete_tombstone_convergence_complete",
        "status": "LOCAL_CONTRACT_DEFINED",
        "delete_tombstone_convergence_complete": True,
        "tombstone_required_before_projection_absence_trusted": True,
        "vector_cleanup_fence_required": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "idempotency_key_contract",
        "status": "LOCAL_CONTRACT_DEFINED",
        "idempotency_key_required": True,
        "duplicate_write_replay_must_return_same_projection_commit": True,
        "payload_mismatch_same_key_must_fail_closed": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "generation_freshness_tombstone_vector_fences_aligned",
        "status": "LOCAL_CONTRACT_DEFINED",
        "required_fence_fields": REQUIRED_FENCE_FIELDS,
        "all_fences_must_match_account_generation": True,
        "stale_or_missing_fence_behavior": "fail_closed",
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "rollback_behavior_fail_closed",
        "status": "LOCAL_CONTRACT_DEFINED",
        "rollback_behavior": "fail_closed_disable_memory_reads_until_reconciled",
        "rollback_to_legacy_after_memory_write_allowed": False,
        "decommission_reconciliation_required_for_write_to_off": True,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "no_legacy_fallback_or_merge_claim",
        "status": "LOCAL_CONTRACT_DEFINED",
        "legacy_fallback_allowed": False,
        "merge_legacy_and_memory_allowed": False,
        "empty_projection_allows_legacy_query": False,
        "projection_error_allows_legacy_query": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
]


def example_valid_convergence_evidence(route_scope_label: str) -> dict[str, Any]:
    return {
        "route_scope": ROUTE_SCOPE,
        "route_scope_label": route_scope_label,
        "owner": "memory_platform",
        "schema_version": 1,
        "source": SOURCE_NAME,
        "projection_version": PROJECTION_VERSION,
        "ready": True,
        "max_staleness_seconds": MAX_STALENESS_SECONDS,
        "durable_outbox_ready": True,
        "all_outbox_events_acknowledged": True,
        "dual_write_projection_writer_ready": True,
        "projection_writer_ready": True,
        "create_update_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
        "delete_tombstone_convergence_complete": True,
        "idempotency_key_contract": "required_stable_route_source_operation_key_payload_hash",
        "account_generation": 7,
        "projection_generation": 7,
        "freshness_fence_generation": 7,
        "tombstone_fence_generation": 7,
        "vector_cleanup_fence_generation": 7,
        "rollback_behavior": "fail_closed_disable_memory_reads_until_reconciled",
        "legacy_fallback_allowed": False,
        "merge_legacy_and_memory_allowed": False,
    }


def _base_proof() -> dict[str, Any]:
    return {
        "route_scope": ROUTE_SCOPE,
        "projection_write_convergence_contract": PROJECTION_WRITE_CONVERGENCE_CONTRACT,
        "backend_service_principal_read_required": True,
        "backend_service_principal_read_proven": False,
        "production_convergence_evidence_exists": False,
        "production_convergence_evidence_valid": False,
        "evidence_validation_reason": "not_run",
        "fences_aligned": False,
        "rollback_fail_closed": False,
        "client_override_allowed": False,
        "fail_closed_on_missing_stale_malformed": True,
        "missing_prerequisites": [],
        "read_error": None,
        "project_id_present": False,
        "service_account_email_present": False,
        "credentials_present": False,
        "route_scope_label_present": False,
        "read_only_firestore_method": "google.cloud.firestore.Client(...).document(route_state_path).get",
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
    if not env.get(ROUTE_SCOPE_LABEL_ENV):
        missing.append(ROUTE_SCOPE_LABEL_ENV)
    return missing


def _route_state_path(route_scope_label: str) -> str:
    return ROUTE_STATE_PATH_TEMPLATE.format(route_scope_label=route_scope_label)


def _read_convergence_evidence(project_id: str, route_scope_label: str) -> Mapping[str, Any] | None:
    firestore_module = importlib.import_module("google.cloud.firestore")
    client = firestore_module.Client(project=project_id)
    snapshot = client.document(_route_state_path(route_scope_label)).get()
    if getattr(snapshot, "exists", False) is False:
        return None
    data = snapshot.to_dict()
    return data if isinstance(data, Mapping) else None


def _contains_forbidden_dimension(value: str) -> bool:
    lowered = value.lower()
    forbidden_terms = ["session", "memory_content", "request_payload", "cursor_token", "raw_cursor", "secret"]
    return any(term in lowered for term in forbidden_terms)


def _invalid_result(reason: str, *, exists: bool = True) -> dict[str, Any]:
    return {
        "production_convergence_evidence_exists": exists,
        "production_convergence_evidence_valid": False,
        "evidence_validation_reason": reason,
        "fences_aligned": False,
        "rollback_fail_closed": False,
    }


def _validate_convergence_evidence(
    metadata: Mapping[str, Any] | None, *, expected_route_scope_label: str
) -> dict[str, Any]:
    if metadata is None:
        return _invalid_result("convergence_evidence_missing", exists=False)
    if not isinstance(metadata, Mapping):
        return _invalid_result("convergence_evidence_malformed")
    required = PROJECTION_WRITE_CONVERGENCE_CONTRACT["required_state_fields"]
    if any(field not in metadata for field in required):
        return _invalid_result("convergence_evidence_missing_required_fields")
    dimension_values = [str(key) for key in metadata.keys()]
    dimension_values.extend(str(value) for value in metadata.values() if not isinstance(value, (int, bool)))
    if any(_contains_forbidden_dimension(value) for value in dimension_values):
        return _invalid_result("convergence_evidence_contains_forbidden_dimension")
    if metadata.get("route_scope") != ROUTE_SCOPE or metadata.get("route_scope_label") != expected_route_scope_label:
        return _invalid_result("convergence_evidence_route_scope_mismatch")
    if metadata.get("owner") != "memory_platform":
        return _invalid_result("convergence_evidence_owner_mismatch")
    if metadata.get("source") != SOURCE_NAME or metadata.get("projection_version") != PROJECTION_VERSION:
        return _invalid_result("convergence_evidence_source_or_version_mismatch")
    max_staleness = metadata.get("max_staleness_seconds")
    if not isinstance(max_staleness, int) or max_staleness < 0 or max_staleness > MAX_STALENESS_SECONDS:
        return _invalid_result("convergence_evidence_staleness_unbounded")
    generations = [metadata.get(field) for field in REQUIRED_FENCE_FIELDS]
    if (
        any(isinstance(value, bool) or not isinstance(value, int) for value in generations)
        or len(set(generations)) != 1
    ):
        return _invalid_result("convergence_evidence_generation_or_fence_mismatch")
    boolean_gates = [
        "ready",
        "durable_outbox_ready",
        "all_outbox_events_acknowledged",
        "dual_write_projection_writer_ready",
        "projection_writer_ready",
        "create_update_convergence_complete",
        "delete_convergence_complete",
        "tombstone_convergence_complete",
        "delete_tombstone_convergence_complete",
    ]
    if any(metadata.get(field) is not True for field in boolean_gates):
        return _invalid_result("convergence_evidence_not_ready_or_convergence_incomplete")
    if not isinstance(metadata.get("schema_version"), int):
        return _invalid_result("convergence_evidence_schema_malformed")
    if not isinstance(metadata.get("idempotency_key_contract"), str) or "payload_hash" not in metadata.get(
        "idempotency_key_contract", ""
    ):
        return _invalid_result("convergence_evidence_idempotency_contract_malformed")
    if metadata.get("rollback_behavior") != "fail_closed_disable_memory_reads_until_reconciled":
        return _invalid_result("convergence_evidence_rollback_behavior_unsafe")
    if (
        metadata.get("legacy_fallback_allowed") is not False
        or metadata.get("merge_legacy_and_memory_allowed") is not False
    ):
        return _invalid_result("convergence_evidence_legacy_fallback_or_merge_allowed")
    return {
        "production_convergence_evidence_exists": True,
        "production_convergence_evidence_valid": True,
        "evidence_validation_reason": "convergence_evidence_valid",
        "fences_aligned": True,
        "rollback_fail_closed": True,
    }


def build_report(
    *,
    execute: bool = False,
    env: Mapping[str, str] | None = None,
    reader: Callable[[str], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    effective_env = os.environ if env is None else env
    proof = _base_proof()
    proof["project_id_present"] = bool(effective_env.get(PROJECT_ID_ENV) or effective_env.get(GOOGLE_PROJECT_ENV))
    proof["service_account_email_present"] = bool(effective_env.get(SERVICE_ACCOUNT_EMAIL_ENV))
    proof["credentials_present"] = bool(
        effective_env.get(GOOGLE_CREDENTIALS_ENV) or effective_env.get(SERVICE_ACCOUNT_JSON_ENV)
    )
    proof["route_scope_label_present"] = bool(effective_env.get(ROUTE_SCOPE_LABEL_ENV))
    proof["missing_prerequisites"] = _missing_prerequisites(effective_env)

    network_or_provider_calls_executed = False
    firestore_reads_executed = False
    proof_status = "NOT_RUN"

    if execute:
        missing = proof["missing_prerequisites"]
        if not missing:
            route_scope_label = effective_env.get(ROUTE_SCOPE_LABEL_ENV) or ""
            project_id = effective_env.get(PROJECT_ID_ENV) or effective_env.get(GOOGLE_PROJECT_ENV) or ""
            try:
                metadata = (
                    reader(route_scope_label)
                    if reader is not None
                    else _read_convergence_evidence(project_id, route_scope_label)
                )
                network_or_provider_calls_executed = reader is None
                firestore_reads_executed = True
                proof["backend_service_principal_read_proven"] = True
                validation = _validate_convergence_evidence(metadata, expected_route_scope_label=route_scope_label)
                for key, value in validation.items():
                    proof[key] = value
                proof_status = "PROVEN_READ_ONLY" if validation["production_convergence_evidence_valid"] else "BLOCKED"
            except Exception as exc:  # pragma: no cover - injected tests cover blocked validation paths.
                network_or_provider_calls_executed = reader is None
                firestore_reads_executed = reader is None
                proof["read_error"] = type(exc).__name__
                proof["evidence_validation_reason"] = "convergence_evidence_read_failed"
                proof_status = "BLOCKED"

    report = {
        "artifact": "p1_3_v3_projection_write_convergence_readiness",
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
        "projection_write_convergence_contract": PROJECTION_WRITE_CONVERGENCE_CONTRACT,
        "write_convergence_requirements": WRITE_CONVERGENCE_REQUIREMENTS,
        "production_write_convergence_proof": proof,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No runtime /v3 behavior changed.",
            "No production calls by default; explicit execution is read-only route-scoped convergence evidence proof only.",
            "No client-controlled collection/path/source, legacy fallback, memory/legacy merge, or rollback-to-legacy-after-memory-write is allowed.",
            "No uid, session, memory id, request payload, cursor token, secret, or memory content telemetry labels are allowed.",
            "No production Firestore write, vector/provider call, telemetry sink call, Archive default visibility, stale Short-term default visibility, rollout approval, or canary approval claimed.",
        ],
    }
    report["summary"] = {
        "status": report["status"],
        "proof_status": proof_status,
        "missing_prerequisite_count": len(proof["missing_prerequisites"]),
        "write_convergence_requirement_count": len(WRITE_CONVERGENCE_REQUIREMENTS),
        "selected_source_count": 2,
        "backend_service_principal_read_proven": proof["backend_service_principal_read_proven"],
        "production_convergence_evidence_exists": proof["production_convergence_evidence_exists"],
        "production_convergence_evidence_valid": proof["production_convergence_evidence_valid"],
        "fences_aligned": proof["fences_aligned"],
        "rollback_fail_closed": proof["rollback_fail_closed"],
        "client_override_allowed": proof["client_override_allowed"],
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "approval_claimed": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run gated read-only projection write convergence proof")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
