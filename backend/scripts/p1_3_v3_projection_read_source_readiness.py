#!/usr/bin/env python3
"""Production-safe memory `/v3` projection read source contract/readiness proof.

This runner defines the future backend-owned projection read source contract for
serving `GET /v3/memories` from memory-derived compatibility projection data. By
default it performs no production calls and reports NOT_RUN/BLOCKED. With explicit
environment gates it may run one read-only metadata/source-shape probe for the
authenticated subject's projection state and validate only source/contract fields.
It never imports FastAPI routers, changes route wiring, writes Firestore, reads
legacy memories, reads live memory memory_items, calls vector/provider services,
emits telemetry sinks, trusts client-selected collection/path/source values, logs
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
SOURCE_TYPE = "firestore_compatibility_projection"
STATE_PATH_TEMPLATE = "users/{uid}/v3_compatibility_projection/state"
ITEMS_PATH_TEMPLATE = "users/{uid}/v3_compatibility_projection_items/{memory_id}"
SOURCE_NAME = "memory_items_projection"
PROJECTION_VERSION = "v3_memorydb_compatibility"
MAX_LIMIT = 500
DEFAULT_LIMIT = 100
MAX_STALENESS_SECONDS = 300

ALLOW_ENV = "MEMORY_V3_PROJECTION_READ_SOURCE_PROD_READ_ALLOW"
PROJECT_ID_ENV = "MEMORY_V3_PROJECTION_READ_SOURCE_PROD_READ_PROJECT_ID"
SERVICE_ACCOUNT_EMAIL_ENV = "MEMORY_V3_PROJECTION_READ_SOURCE_PROD_READ_SERVICE_ACCOUNT_EMAIL"
UID_ENV = "MEMORY_V3_PROJECTION_READ_SOURCE_PROD_READ_UID"
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
    "read_source",
    "read_decision",
    "failure_reason",
    "projection_schema_version",
    "limit_bucket",
]

PROJECTION_READ_SOURCE_CONTRACT = {
    "source_type": SOURCE_TYPE,
    "route_scope": ROUTE_SCOPE,
    "route_scope_label": ROUTE_SCOPE_LABEL,
    "owner": "memory_platform",
    "state_path_template": STATE_PATH_TEMPLATE,
    "items_path_template": ITEMS_PATH_TEMPLATE,
    "server_owned": True,
    "client_override_allowed": False,
    "client_controlled_collection_or_path_allowed": False,
    "uid_usage": "authenticated_subject_selector_only",
    "configuration_dimension_fields": [],
    "limit_bounds": {"min": 1, "default": DEFAULT_LIMIT, "max": MAX_LIMIT},
    "ordering": [
        {"field": "created_at", "direction": "DESC"},
        {"field": "__name__", "direction": "DESC"},
    ],
    "cursor_fields": [
        "created_at",
        "memory_id",
        "account_generation",
        "projection_generation",
        "projection_commit_id",
    ],
    "required_state_fields": [
        "route_scope",
        "owner",
        "schema_version",
        "source",
        "projection_version",
        "ready",
        "uid",
        "account_generation",
        "projection_generation",
        "projection_commit_id",
        "max_staleness_seconds",
        "write_convergence_complete",
        "delete_convergence_complete",
        "tombstone_convergence_complete",
        "freshness_fence_generation",
        "tombstone_fence_generation",
        "vector_cleanup_fence_generation",
    ],
    "telemetry_safe_labels": TELEMETRY_SAFE_LABELS,
    "telemetry_forbidden_dimensions": FORBIDDEN_TELEMETRY_DIMENSIONS,
    "fail_closed_on_missing_stale_malformed_metadata": True,
    "legacy_fallback_allowed": False,
    "merge_legacy_and_memory_allowed": False,
    "archive_default_available": False,
    "stale_short_term_default_visible": False,
    "runtime_wired": False,
}

READ_SOURCE_REQUIREMENTS = [
    {
        "requirement_id": "route_scoped_server_owned_projection_source",
        "status": "LOCAL_CONTRACT_DEFINED",
        "route_scope": ROUTE_SCOPE,
        "server_owned": True,
        "state_path_template": STATE_PATH_TEMPLATE,
        "items_path_template": ITEMS_PATH_TEMPLATE,
        "client_override_allowed": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "authenticated_subject_selector_only",
        "status": "LOCAL_CONTRACT_DEFINED",
        "uid_as_authenticated_subject_selector": True,
        "uid_as_config_dimension_allowed": False,
        "client_supplied_uid_trusted": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "bounded_page_size_limit_contract",
        "status": "LOCAL_CONTRACT_DEFINED",
        "min_limit": 1,
        "default_limit": DEFAULT_LIMIT,
        "max_limit": MAX_LIMIT,
        "legacy_offset_zero_limit_5000_allowed_for_memory": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "deterministic_keyset_ordering_contract",
        "status": "LOCAL_CONTRACT_DEFINED",
        "ordering": PROJECTION_READ_SOURCE_CONTRACT["ordering"],
        "cursor_fields": PROJECTION_READ_SOURCE_CONTRACT["cursor_fields"],
        "offset_supported_for_memory": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "projection_metadata_freshness_fail_closed",
        "status": "LOCAL_CONTRACT_DEFINED",
        "fail_closed": True,
        "blocked_states": [
            "missing_projection_state",
            "malformed_projection_state",
            "unsupported_schema",
            "route_scope_mismatch",
            "uid_mismatch",
            "source_or_projection_version_mismatch",
            "stale_or_unbounded_max_staleness",
            "account_projection_or_fence_mismatch",
            "incomplete_write_delete_tombstone_convergence",
        ],
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "privacy_safe_telemetry_dimensions",
        "status": "LOCAL_CONTRACT_DEFINED",
        "telemetry_safe_labels": TELEMETRY_SAFE_LABELS,
        "telemetry_forbidden_dimensions": FORBIDDEN_TELEMETRY_DIMENSIONS,
        "telemetry_sink_calls_executed": False,
        "required_before_runtime_change": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "requirement_id": "no_client_controlled_source_or_path",
        "status": "LOCAL_CONTRACT_DEFINED",
        "client_source_path_override_allowed": False,
        "client_collection_override_allowed": False,
        "source_path_derived_from_server_contract_only": True,
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


def example_valid_source_metadata(uid: str) -> dict[str, Any]:
    return {
        "route_scope": ROUTE_SCOPE_LABEL,
        "owner": "memory_platform",
        "schema_version": 1,
        "source": SOURCE_NAME,
        "projection_version": PROJECTION_VERSION,
        "ready": True,
        "uid": uid,
        "account_generation": 7,
        "projection_generation": 7,
        "projection_commit_id": "commit-example",
        "max_staleness_seconds": MAX_STALENESS_SECONDS,
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
        "freshness_fence_generation": 7,
        "tombstone_fence_generation": 7,
        "vector_cleanup_fence_generation": 7,
    }


def _base_proof() -> dict[str, Any]:
    return {
        "route_scope": ROUTE_SCOPE,
        "projection_read_source_contract": PROJECTION_READ_SOURCE_CONTRACT,
        "backend_service_principal_read_required": True,
        "backend_service_principal_read_proven": False,
        "production_projection_source_exists": False,
        "production_projection_source_valid": False,
        "source_validation_reason": "not_run",
        "route_scoped_without_user_dimensions": False,
        "client_override_allowed": False,
        "fail_closed_on_missing_stale_malformed": True,
        "missing_prerequisites": [],
        "read_error": None,
        "project_id_present": False,
        "service_account_email_present": False,
        "credentials_present": False,
        "uid_present": False,
        "read_only_firestore_method": "google.cloud.firestore.Client(...).document(state_path).get",
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
    if not env.get(UID_ENV):
        missing.append(UID_ENV)
    return missing


def _state_path(uid: str) -> str:
    return STATE_PATH_TEMPLATE.format(uid=uid)


def _read_projection_source_metadata(project_id: str, uid: str) -> Mapping[str, Any] | None:
    firestore_module = importlib.import_module("google.cloud.firestore")
    client = firestore_module.Client(project=project_id)
    snapshot = client.document(_state_path(uid)).get()
    if getattr(snapshot, "exists", False) is False:
        return None
    data = snapshot.to_dict()
    return data if isinstance(data, Mapping) else None


def _contains_forbidden_dimension(value: str) -> bool:
    lowered = value.lower()
    forbidden_terms = ["session", "memory_content", "request_payload", "cursor_token", "raw_cursor", "secret"]
    return any(term in lowered for term in forbidden_terms)


def _validate_source_metadata(metadata: Mapping[str, Any] | None, *, expected_uid: str) -> dict[str, Any]:
    if metadata is None:
        return {
            "production_projection_source_exists": False,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_missing",
            "route_scoped_without_user_dimensions": False,
        }
    if not isinstance(metadata, Mapping):
        return {
            "production_projection_source_exists": True,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_malformed",
            "route_scoped_without_user_dimensions": False,
        }
    required = PROJECTION_READ_SOURCE_CONTRACT["required_state_fields"]
    if any(field not in metadata for field in required):
        return {
            "production_projection_source_exists": True,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_missing_required_fields",
            "route_scoped_without_user_dimensions": False,
        }
    dimension_values = [str(key) for key in metadata.keys()]
    dimension_values.extend(str(value) for value in metadata.values() if not isinstance(value, (int, bool)))
    if any(_contains_forbidden_dimension(value) for value in dimension_values):
        return {
            "production_projection_source_exists": True,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_contains_forbidden_dimension",
            "route_scoped_without_user_dimensions": False,
        }
    if metadata.get("route_scope") != ROUTE_SCOPE_LABEL or metadata.get("owner") != "memory_platform":
        return {
            "production_projection_source_exists": True,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_missing_route_scope_or_owner",
            "route_scoped_without_user_dimensions": False,
        }
    if metadata.get("uid") != expected_uid:
        return {
            "production_projection_source_exists": True,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_uid_mismatch",
            "route_scoped_without_user_dimensions": False,
        }
    if metadata.get("source") != SOURCE_NAME or metadata.get("projection_version") != PROJECTION_VERSION:
        return {
            "production_projection_source_exists": True,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_source_or_version_mismatch",
            "route_scoped_without_user_dimensions": False,
        }
    max_staleness = metadata.get("max_staleness_seconds")
    if not isinstance(max_staleness, int) or max_staleness < 0 or max_staleness > MAX_STALENESS_SECONDS:
        return {
            "production_projection_source_exists": True,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_staleness_unbounded",
            "route_scoped_without_user_dimensions": False,
        }
    generation_fields = [
        "account_generation",
        "projection_generation",
        "freshness_fence_generation",
        "tombstone_fence_generation",
        "vector_cleanup_fence_generation",
    ]
    generations = [metadata.get(field) for field in generation_fields]
    if (
        any(isinstance(value, bool) or not isinstance(value, int) for value in generations)
        or len(set(generations)) != 1
    ):
        return {
            "production_projection_source_exists": True,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_generation_or_fence_mismatch",
            "route_scoped_without_user_dimensions": False,
        }
    boolean_gates = [
        "ready",
        "write_convergence_complete",
        "delete_convergence_complete",
        "tombstone_convergence_complete",
    ]
    if any(metadata.get(field) is not True for field in boolean_gates):
        return {
            "production_projection_source_exists": True,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_not_ready_or_convergence_incomplete",
            "route_scoped_without_user_dimensions": False,
        }
    if not isinstance(metadata.get("schema_version"), int) or not str(
        metadata.get("projection_commit_id", "")
    ).startswith("commit-"):
        return {
            "production_projection_source_exists": True,
            "production_projection_source_valid": False,
            "source_validation_reason": "source_metadata_schema_or_commit_malformed",
            "route_scoped_without_user_dimensions": False,
        }
    return {
        "production_projection_source_exists": True,
        "production_projection_source_valid": True,
        "source_validation_reason": "source_metadata_valid",
        "route_scoped_without_user_dimensions": True,
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
    proof["uid_present"] = bool(effective_env.get(UID_ENV))
    proof["missing_prerequisites"] = _missing_prerequisites(effective_env)

    network_or_provider_calls_executed = False
    firestore_reads_executed = False
    proof_status = "NOT_RUN"

    if execute:
        missing = proof["missing_prerequisites"]
        if not missing:
            uid = effective_env.get(UID_ENV) or ""
            project_id = effective_env.get(PROJECT_ID_ENV) or effective_env.get(GOOGLE_PROJECT_ENV) or ""
            try:
                metadata = reader(uid) if reader is not None else _read_projection_source_metadata(project_id, uid)
                network_or_provider_calls_executed = reader is None
                firestore_reads_executed = True
                proof["backend_service_principal_read_proven"] = True
                validation = _validate_source_metadata(metadata, expected_uid=uid)
                for key, value in validation.items():
                    proof[key] = value
                proof_status = "PROVEN_READ_ONLY" if validation["production_projection_source_valid"] else "BLOCKED"
            except Exception as exc:  # pragma: no cover - injected tests cover blocked validation paths.
                network_or_provider_calls_executed = reader is None
                firestore_reads_executed = reader is None
                proof["read_error"] = type(exc).__name__
                proof["source_validation_reason"] = "source_metadata_read_failed"
                proof_status = "BLOCKED"

    report = {
        "artifact": "p1_3_v3_projection_read_source_readiness",
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
        "projection_read_source_contract": PROJECTION_READ_SOURCE_CONTRACT,
        "read_source_requirements": READ_SOURCE_REQUIREMENTS,
        "production_read_source_proof": proof,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No runtime /v3 behavior changed.",
            "No production calls by default; explicit execution is read-only projection source metadata proof only.",
            "No client-controlled collection/path/source, uid config dimension, legacy fallback, or memory/legacy merge is allowed.",
            "No uid, session, memory id, request payload, cursor token, secret, or memory content telemetry labels are allowed.",
            "No production Firestore write, vector/provider call, telemetry sink call, Archive default visibility, stale Short-term default visibility, rollout approval, or canary approval claimed.",
        ],
    }
    report["summary"] = {
        "status": report["status"],
        "proof_status": proof_status,
        "missing_prerequisite_count": len(proof["missing_prerequisites"]),
        "read_source_requirement_count": len(READ_SOURCE_REQUIREMENTS),
        "selected_source_count": 2,
        "backend_service_principal_read_proven": proof["backend_service_principal_read_proven"],
        "production_projection_source_exists": proof["production_projection_source_exists"],
        "production_projection_source_valid": proof["production_projection_source_valid"],
        "route_scoped_without_user_dimensions": proof["route_scoped_without_user_dimensions"],
        "client_override_allowed": proof["client_override_allowed"],
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "approval_claimed": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run gated read-only projection source metadata proof")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
