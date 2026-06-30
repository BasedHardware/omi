#!/usr/bin/env python3
"""Production-safe memory `/v3` runtime control/config source-selection readiness proof.

This runner selects the server-owned route-scoped config sources that future
`GET /v3/memories` runtime enablement decisions must consult before any route
wiring. By default it performs no production calls and reports NOT_RUN/BLOCKED.
With explicit environment gates it may execute read-only Firestore document reads
for route-scoped global config sources only. It never imports FastAPI routers,
writes Firestore, reads user memory content, calls vector/provider services,
emits telemetry sinks, accepts client overrides, changes runtime behavior, or
claims production rollout approval.
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
GLOBAL_READ_GATE_PATH = "memory_control/global_read_gate"
WRITE_CONVERGENCE_GATE_PATH = "memory_control/write_convergence_gate"
SELECTED_CONFIG_PATHS = [GLOBAL_READ_GATE_PATH, WRITE_CONVERGENCE_GATE_PATH]
EXPECTED_CONFIG_PATHS_VALUE = ",".join(SELECTED_CONFIG_PATHS)
MAX_STALENESS_SECONDS = 300

ALLOW_ENV = "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_ALLOW"
PROJECT_ID_ENV = "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_PROJECT_ID"
SERVICE_ACCOUNT_EMAIL_ENV = "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_SERVICE_ACCOUNT_EMAIL"
CONFIG_PATHS_ENV = "MEMORY_V3_RUNTIME_CONFIG_SOURCE_PROD_READ_CONFIG_PATHS"
GOOGLE_PROJECT_ENV = "GOOGLE_CLOUD_PROJECT"
GOOGLE_CREDENTIALS_ENV = "GOOGLE_APPLICATION_CREDENTIALS"
SERVICE_ACCOUNT_JSON_ENV = "SERVICE_ACCOUNT_JSON"

FORBIDDEN_DIMENSIONS = [
    "uid",
    "user_id",
    "session_id",
    "memory_id",
    "request_payload",
    "raw_cursor",
    "cursor",
    "cursor-token",
    "secret",
]

SOURCE_API_SHAPE = {
    "source_type": "firestore_route_scoped_runtime_config_or_equivalent_server_config_inventory",
    "route_scope": ROUTE_SCOPE,
    "selected_sources": [
        {
            "path": GLOBAL_READ_GATE_PATH,
            "purpose": "v3_runtime_enablement",
            "required_fields": [
                "route_scope",
                "purpose",
                "owner",
                "config_schema_version",
                "max_staleness_seconds",
                "memory_reads_enabled",
                "kill_switch_active",
            ],
        },
        {
            "path": WRITE_CONVERGENCE_GATE_PATH,
            "purpose": "v3_write_convergence_gate",
            "required_fields": [
                "route_scope",
                "purpose",
                "owner",
                "config_schema_version",
                "max_staleness_seconds",
                "durable_outbox_enabled",
                "dual_write_projection_ready",
                "delete_convergence_ready",
                "idempotency_contract_ready",
            ],
        },
    ],
    "allowed_metadata_keys": [
        "route_scope",
        "purpose",
        "owner",
        "config_schema_version",
        "max_staleness_seconds",
        "memory_reads_enabled",
        "kill_switch_active",
        "durable_outbox_enabled",
        "dual_write_projection_ready",
        "delete_convergence_ready",
        "idempotency_contract_ready",
    ],
    "forbidden_dimensions": FORBIDDEN_DIMENSIONS,
    "client_override_allowed": False,
    "runtime_wired": False,
}


def _base_proof() -> dict[str, Any]:
    return {
        "route_scope": ROUTE_SCOPE,
        "source_api_shape": SOURCE_API_SHAPE,
        "selected_sources": SOURCE_API_SHAPE["selected_sources"],
        "backend_service_principal_read_required": True,
        "backend_service_principal_read_proven": False,
        "production_config_sources_exist": False,
        "production_config_sources_valid": False,
        "config_validation_reason": "not_run",
        "route_scoped_without_user_dimensions": False,
        "client_override_allowed": False,
        "fail_closed_on_missing_stale_malformed": True,
        "missing_prerequisites": [],
        "read_error": None,
        "project_id_present": False,
        "service_account_email_present": False,
        "credentials_present": False,
        "config_paths_present": False,
        "read_only_firestore_method": "google.cloud.firestore.Client(...).document(path).get",
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
    if env.get(CONFIG_PATHS_ENV) != EXPECTED_CONFIG_PATHS_VALUE:
        missing.append(CONFIG_PATHS_ENV)
    return missing


def _read_firestore_config_docs(project_id: str) -> dict[str, Mapping[str, Any] | None]:
    firestore_module = importlib.import_module("google.cloud.firestore")
    client = firestore_module.Client(project=project_id)
    docs: dict[str, Mapping[str, Any] | None] = {}
    for path in SELECTED_CONFIG_PATHS:
        snapshot = client.document(path).get()
        docs[path] = snapshot.to_dict() if getattr(snapshot, "exists", True) else None
    return docs


def _contains_forbidden_dimension(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in FORBIDDEN_DIMENSIONS)


def _source_purpose(path: str) -> str:
    for source in SOURCE_API_SHAPE["selected_sources"]:
        if source["path"] == path:
            return str(source["purpose"])
    return ""


def _source_required_fields(path: str) -> list[str]:
    for source in SOURCE_API_SHAPE["selected_sources"]:
        if source["path"] == path:
            return list(source["required_fields"])
    return []


def _validate_config_docs(docs: Mapping[str, Mapping[str, Any] | None]) -> dict[str, Any]:
    if set(docs) != set(SELECTED_CONFIG_PATHS):
        return {
            "production_config_sources_exist": False,
            "production_config_sources_valid": False,
            "config_validation_reason": "config_source_paths_mismatch",
            "route_scoped_without_user_dimensions": False,
        }
    for path in SELECTED_CONFIG_PATHS:
        doc = docs.get(path)
        if doc is None:
            return {
                "production_config_sources_exist": False,
                "production_config_sources_valid": False,
                "config_validation_reason": "config_missing",
                "route_scoped_without_user_dimensions": False,
            }
        if not isinstance(doc, Mapping):
            return {
                "production_config_sources_exist": True,
                "production_config_sources_valid": False,
                "config_validation_reason": "config_malformed",
                "route_scoped_without_user_dimensions": False,
            }
        values_for_dimension_check = [path, *[str(key) for key in doc.keys()], *[str(value) for value in doc.values()]]
        if any(_contains_forbidden_dimension(value) for value in values_for_dimension_check):
            return {
                "production_config_sources_exist": True,
                "production_config_sources_valid": False,
                "config_validation_reason": "config_contains_forbidden_dimension",
                "route_scoped_without_user_dimensions": False,
            }
        required_fields = _source_required_fields(path)
        if doc.get("route_scope") != ROUTE_SCOPE_LABEL or doc.get("purpose") != _source_purpose(path):
            return {
                "production_config_sources_exist": True,
                "production_config_sources_valid": False,
                "config_validation_reason": "config_missing_route_scope_or_purpose",
                "route_scoped_without_user_dimensions": False,
            }
        if doc.get("owner") != "memory_platform" or not isinstance(doc.get("config_schema_version"), int):
            return {
                "production_config_sources_exist": True,
                "production_config_sources_valid": False,
                "config_validation_reason": "config_missing_owner_or_schema",
                "route_scoped_without_user_dimensions": False,
            }
        max_staleness = doc.get("max_staleness_seconds")
        if not isinstance(max_staleness, int) or max_staleness < 0 or max_staleness > MAX_STALENESS_SECONDS:
            return {
                "production_config_sources_exist": True,
                "production_config_sources_valid": False,
                "config_validation_reason": "config_staleness_unbounded",
                "route_scoped_without_user_dimensions": False,
            }
        if any(field not in doc for field in required_fields):
            return {
                "production_config_sources_exist": True,
                "production_config_sources_valid": False,
                "config_validation_reason": "config_missing_required_fields",
                "route_scoped_without_user_dimensions": False,
            }
        bool_fields = [
            field
            for field in required_fields
            if field not in {"route_scope", "purpose", "owner", "config_schema_version", "max_staleness_seconds"}
        ]
        if any(not isinstance(doc.get(field), bool) for field in bool_fields):
            return {
                "production_config_sources_exist": True,
                "production_config_sources_valid": False,
                "config_validation_reason": "config_boolean_gate_malformed",
                "route_scoped_without_user_dimensions": False,
            }
    return {
        "production_config_sources_exist": True,
        "production_config_sources_valid": True,
        "config_validation_reason": "config_valid",
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
    proof["config_paths_present"] = bool(effective_env.get(CONFIG_PATHS_ENV))
    proof["missing_prerequisites"] = _missing_prerequisites(effective_env)

    network_or_provider_calls_executed = False
    firestore_reads_executed = False
    proof_status = "NOT_RUN"

    if execute:
        missing = proof["missing_prerequisites"]
        if not missing:
            try:
                project_id = effective_env.get(PROJECT_ID_ENV) or effective_env.get(GOOGLE_PROJECT_ENV) or ""
                if reader is None:
                    docs = _read_firestore_config_docs(project_id)
                else:
                    docs = {path: reader(path) for path in SELECTED_CONFIG_PATHS}
                network_or_provider_calls_executed = True
                firestore_reads_executed = True
                proof["backend_service_principal_read_proven"] = True
                validation = _validate_config_docs(docs)
                for key, value in validation.items():
                    proof[key] = value
                proof_status = "PROVEN_READ_ONLY" if validation["production_config_sources_valid"] else "BLOCKED"
            except Exception as exc:  # pragma: no cover - exercised by injected tests through invalid docs instead.
                network_or_provider_calls_executed = reader is None
                firestore_reads_executed = reader is None
                proof["read_error"] = type(exc).__name__
                proof["config_validation_reason"] = "config_read_failed"
                proof_status = "BLOCKED"
        else:
            proof_status = "NOT_RUN"

    report = {
        "artifact": "p1_3_v3_runtime_config_source_readiness",
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
        "source_selection_proof": proof,
        "non_claims": [
            "No backend/routers/memories.py runtime wiring changed.",
            "No production calls by default; explicit execution is read-only config/source proof only.",
            "No client override, user content, cursor token, secret material, telemetry sink, provider, vector, or write path used.",
            "Valid source-selection proof is not route wiring, rollout approval, or canary approval.",
        ],
    }
    report["summary"] = {
        "status": report["status"],
        "proof_status": proof_status,
        "missing_prerequisite_count": len(proof["missing_prerequisites"]),
        "selected_source_count": len(SELECTED_CONFIG_PATHS),
        "backend_service_principal_read_proven": proof["backend_service_principal_read_proven"],
        "production_config_sources_exist": proof["production_config_sources_exist"],
        "production_config_sources_valid": proof["production_config_sources_valid"],
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
    parser.add_argument("--execute", action="store_true", help="Run gated read-only production config source proof")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
