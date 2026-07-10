#!/usr/bin/env python3
"""Production-safe memory `/v3` cursor secret/config metadata read-proof readiness contract.

This runner is disabled by default. Without explicit environment gates it performs
no production calls and reports NOT_RUN/BLOCKED. With gates present it may run one
read-only Secret Manager metadata lookup for a route-scoped memory `/v3` cursor
signing secret/config source, validate only metadata/readiness properties, and
still refuse to claim route wiring, secret-material proof, or production rollout
approval. It never imports FastAPI routers, accesses secret bytes, writes
Firestore/Secret Manager/config, calls vector/provider services, emits telemetry
sinks, logs secret material, or changes runtime behavior.
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
SECRET_ID = "memory-v3-get-cursor-signing-secret"
SECRET_RESOURCE_TEMPLATE = "projects/{project_id}/secrets/{secret_id}"
SOURCE_API_SHAPE = {
    "source_type": "secret_manager_metadata_or_equivalent_server_config_inventory",
    "route_scope": ROUTE_SCOPE,
    "resource_template": SECRET_RESOURCE_TEMPLATE,
    "secret_id": SECRET_ID,
    "allowed_metadata_labels": {
        "route_scope": ROUTE_SCOPE_LABEL,
        "purpose": "v3_cursor_signing",
        "owner": "memory_platform",
    },
    "forbidden_dimensions": ["uid", "user_id", "session_id", "memory_id", "request_payload", "raw_cursor"],
    "secret_material_returned_or_logged": False,
    "client_supplied_secret_trusted": False,
    "runtime_wired": False,
}

ALLOW_ENV = "MEMORY_V3_CURSOR_SECRET_PROD_READ_ALLOW"
PROJECT_ID_ENV = "MEMORY_V3_CURSOR_SECRET_PROD_READ_PROJECT_ID"
SERVICE_ACCOUNT_EMAIL_ENV = "MEMORY_V3_CURSOR_SECRET_PROD_READ_SERVICE_ACCOUNT_EMAIL"
SECRET_ID_ENV = "MEMORY_V3_CURSOR_SECRET_PROD_READ_SECRET_ID"
GOOGLE_PROJECT_ENV = "GOOGLE_CLOUD_PROJECT"
GOOGLE_CREDENTIALS_ENV = "GOOGLE_APPLICATION_CREDENTIALS"
SERVICE_ACCOUNT_JSON_ENV = "SERVICE_ACCOUNT_JSON"


def _base_proof() -> dict[str, Any]:
    return {
        "route_scope": ROUTE_SCOPE,
        "secret_id": SECRET_ID,
        "secret_resource_template": SECRET_RESOURCE_TEMPLATE,
        "source_api_shape": SOURCE_API_SHAPE,
        "backend_service_principal_metadata_read_required": True,
        "backend_service_principal_metadata_read_proven": False,
        "production_secret_config_source_exists": False,
        "production_secret_config_metadata_valid": False,
        "metadata_validation_reason": "not_run",
        "production_secret_material_read": False,
        "client_supplied_secret_trusted": False,
        "route_scoped_without_user_dimensions": False,
        "missing_prerequisites": [],
        "read_error": None,
        "project_id_present": False,
        "service_account_email_present": False,
        "credentials_present": False,
        "secret_id_present": False,
        "read_only_secret_manager_method": "SecretManagerServiceClient.get_secret",
        "secret_material_access_method_allowed": False,
        "mutating_secret_manager_methods_allowed": False,
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
    if env.get(SECRET_ID_ENV) != SECRET_ID:
        missing.append(SECRET_ID_ENV)
    return missing


def _read_secret_metadata_with_secret_manager(project_id: str, secret_id: str) -> dict[str, Any] | None:
    secretmanager_module = importlib.import_module("google.cloud.secretmanager")
    client = secretmanager_module.SecretManagerServiceClient()
    name = SECRET_RESOURCE_TEMPLATE.format(project_id=project_id, secret_id=secret_id)
    secret = client.get_secret(request={"name": name})
    labels = dict(getattr(secret, "labels", {}) or {})
    return {
        "name": getattr(secret, "name", name),
        "labels": labels,
        "replication": "present" if getattr(secret, "replication", None) is not None else "unknown",
    }


def _metadata_name(metadata: Mapping[str, Any]) -> str:
    name = metadata.get("name")
    return name if isinstance(name, str) else ""


def _metadata_labels(metadata: Mapping[str, Any]) -> dict[str, str]:
    labels = metadata.get("labels")
    if not isinstance(labels, Mapping):
        return {}
    return {str(key): str(value) for key, value in labels.items()}


def _contains_forbidden_dimension(value: str) -> bool:
    lowered = value.lower()
    forbidden_terms = ["/users/", "uid", "user_id", "session", "memory_id", "request", "raw_cursor"]
    return any(term in lowered for term in forbidden_terms)


def _evaluate_metadata(metadata: Mapping[str, Any] | None, *, expected_project_id: str) -> dict[str, Any]:
    if metadata is None:
        return {
            "production_secret_config_source_exists": False,
            "production_secret_config_metadata_valid": False,
            "metadata_validation_reason": "metadata_missing",
            "route_scoped_without_user_dimensions": False,
        }

    name = _metadata_name(metadata)
    labels = _metadata_labels(metadata)
    expected_suffix = f"/secrets/{SECRET_ID}"
    if not name.endswith(expected_suffix):
        return {
            "production_secret_config_source_exists": True,
            "production_secret_config_metadata_valid": False,
            "metadata_validation_reason": "metadata_wrong_secret_id",
            "route_scoped_without_user_dimensions": False,
        }
    if expected_project_id and not name.startswith(f"projects/{expected_project_id}/"):
        return {
            "production_secret_config_source_exists": True,
            "production_secret_config_metadata_valid": False,
            "metadata_validation_reason": "metadata_wrong_project",
            "route_scoped_without_user_dimensions": False,
        }
    if labels.get("route_scope") != ROUTE_SCOPE_LABEL or labels.get("purpose") != "v3_cursor_signing":
        return {
            "production_secret_config_source_exists": True,
            "production_secret_config_metadata_valid": False,
            "metadata_validation_reason": "metadata_missing_route_scope_or_purpose",
            "route_scoped_without_user_dimensions": False,
        }
    dimension_values = [name, *labels.keys(), *labels.values()]
    if any(_contains_forbidden_dimension(value) for value in dimension_values):
        return {
            "production_secret_config_source_exists": True,
            "production_secret_config_metadata_valid": False,
            "metadata_validation_reason": "metadata_contains_forbidden_dimension",
            "route_scoped_without_user_dimensions": False,
        }
    return {
        "production_secret_config_source_exists": True,
        "production_secret_config_metadata_valid": True,
        "metadata_validation_reason": "metadata_valid",
        "route_scoped_without_user_dimensions": True,
    }


def build_report(
    *,
    execute: bool = False,
    env: Mapping[str, str] | None = None,
    reader: Callable[[], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    effective_env = os.environ if env is None else env
    proof = _base_proof()
    proof["project_id_present"] = bool(effective_env.get(PROJECT_ID_ENV) or effective_env.get(GOOGLE_PROJECT_ENV))
    proof["service_account_email_present"] = bool(effective_env.get(SERVICE_ACCOUNT_EMAIL_ENV))
    proof["credentials_present"] = bool(
        effective_env.get(GOOGLE_CREDENTIALS_ENV) or effective_env.get(SERVICE_ACCOUNT_JSON_ENV)
    )
    proof["secret_id_present"] = bool(effective_env.get(SECRET_ID_ENV))
    proof["missing_prerequisites"] = _missing_prerequisites(effective_env)

    network_or_provider_calls_executed = False
    secret_manager_metadata_reads_executed = False
    proof_status = "NOT_RUN"

    if execute:
        missing = proof["missing_prerequisites"]
        if not missing:
            try:
                project_id = effective_env.get(PROJECT_ID_ENV) or effective_env.get(GOOGLE_PROJECT_ENV) or ""
                secret_id = effective_env.get(SECRET_ID_ENV) or SECRET_ID
                network_or_provider_calls_executed = True
                secret_manager_metadata_reads_executed = True
                metadata = (
                    reader() if reader is not None else _read_secret_metadata_with_secret_manager(project_id, secret_id)
                )
                proof["backend_service_principal_metadata_read_proven"] = True
                proof = {**proof, **_evaluate_metadata(metadata, expected_project_id=project_id)}
                proof_status = "PROVEN_READ_ONLY" if proof["production_secret_config_metadata_valid"] else "BLOCKED"
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
        "backend_service_principal_metadata_read_proven": proof["backend_service_principal_metadata_read_proven"],
        "production_secret_config_source_exists": proof["production_secret_config_source_exists"],
        "production_secret_config_metadata_valid": proof["production_secret_config_metadata_valid"],
        "production_secret_material_read": False,
        "client_supplied_secret_trusted": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
    }
    return {
        "artifact": "p1_3_v3_cursor_secret_production_readiness",
        "status": "BLOCKED",
        "proof_status": proof_status,
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "routers_memories_modified": False,
        "network_or_provider_calls_executed": network_or_provider_calls_executed,
        "provider_calls_executed": False,
        "secret_manager_metadata_reads_executed": secret_manager_metadata_reads_executed,
        "secret_manager_payload_reads_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "telemetry_sink_calls_executed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "production_read_proof": proof,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No runtime /v3 behavior changed.",
            "No production cursor secret material is read, printed, logged, or returned.",
            "No client-supplied cursor signing secret is trusted.",
            "No production rollout approval claimed, even when metadata reads and shape validate.",
            "No production Firestore write, vector/provider call, or telemetry sink call is allowed.",
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
        help="Run the read-only metadata proof only when all explicit environment gates are present",
    )
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
