#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, cast

DEFAULT_ASSIGNMENT_FILE_ENV = "MEMORY_APP_KEY_MEMORY_GRANT_ASSIGNMENTS"
APP_KEY_MEMORY_GRANT_SUBPATH = "memory_control/app_key_memory_grants"
ALLOWED_CONSUMERS = frozenset({"developer_api", "mcp", "third_party"})
ALLOWED_PERSISTED_SCOPES = frozenset({"memories.read", "memories.write", "memories.archive.read"})
REQUIRED_FIELDS = frozenset(
    {
        "uid",
        "consumer",
        "app_id",
        "key_id",
        "scopes",
        "default_read",
        "archive_read",
        "write",
        "archive_default_visible",
    }
)
OPTIONAL_FIELDS = frozenset({"enabled", "reason"})
ALLOWED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS


def normalize_scope_list(value: Any) -> Tuple[Optional[List[str]], bool]:
    if not isinstance(value, list):
        return None, True
    items: List[Any] = cast(List[Any], value)
    scopes: List[str] = []
    for scope in items:
        if not isinstance(scope, str) or not scope:
            return None, True
        scopes.append(scope)
    return list(dict.fromkeys(scopes)), False


def _validate_bool(assignment: Mapping[str, Any], field: str, errors: List[str], index: int) -> Optional[bool]:
    value = assignment.get(field)
    if not isinstance(value, bool):
        errors.append(f"assignment[{index}]:{field}_must_be_boolean")
        return None
    return value


def _validate_string(assignment: Mapping[str, Any], field: str, errors: List[str], index: int) -> Optional[str]:
    value = assignment.get(field)
    if not isinstance(value, str) or not value:
        errors.append(f"assignment[{index}]:{field}_must_be_non_empty_string")
        return None
    return value


def normalize_assignments(assignments: Optional[Sequence[object]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    normalized: List[Dict[str, Any]] = []
    errors: List[str] = []
    if assignments is None:
        return [], []
    if not isinstance(assignments, list):
        return [], ["assignment_file_must_be_json_list_or_object_with_assignments_list"]

    for index, assignment in enumerate(assignments):
        if not isinstance(assignment, Mapping):
            errors.append(f"assignment[{index}]:must_be_object")
            continue
        assignment = cast(Mapping[str, Any], assignment)
        unknown_fields = sorted(set(assignment) - ALLOWED_FIELDS)
        for field in unknown_fields:
            errors.append(f"assignment[{index}]:unknown_capability_or_field:{field}")
        missing_fields = sorted(REQUIRED_FIELDS - set(assignment))
        for field in missing_fields:
            errors.append(f"assignment[{index}]:missing_required_field:{field}")

        uid = _validate_string(assignment, "uid", errors, index)
        consumer = _validate_string(assignment, "consumer", errors, index)
        app_id = _validate_string(assignment, "app_id", errors, index)
        key_id = _validate_string(assignment, "key_id", errors, index)
        default_read = _validate_bool(assignment, "default_read", errors, index)
        archive_read = _validate_bool(assignment, "archive_read", errors, index)
        write = _validate_bool(assignment, "write", errors, index)
        archive_default_visible = _validate_bool(assignment, "archive_default_visible", errors, index)
        enabled_value = assignment.get("enabled", True)
        if not isinstance(enabled_value, bool):
            errors.append(f"assignment[{index}]:enabled_must_be_boolean")
            enabled = True
        else:
            enabled = enabled_value

        scopes, malformed_scopes = normalize_scope_list(assignment.get("scopes"))
        if malformed_scopes or scopes is None:
            errors.append(f"assignment[{index}]:malformed_scopes")
            scopes = []
        unknown_scopes = sorted(scope for scope in scopes if scope not in ALLOWED_PERSISTED_SCOPES)
        for scope in unknown_scopes:
            errors.append(f"assignment[{index}]:unknown_scope:{scope}")
        if consumer and consumer not in ALLOWED_CONSUMERS:
            errors.append(f"assignment[{index}]:unknown_consumer:{consumer}")
        if default_read and "memories.read" not in scopes:
            errors.append(f"assignment[{index}]:default_read_requires_memories.read")
        if archive_read and "memories.archive.read" not in scopes:
            errors.append(f"assignment[{index}]:archive_read_requires_memories.archive.read")
        if write and "memories.write" not in scopes:
            errors.append(f"assignment[{index}]:write_requires_memories.write")
        if archive_default_visible:
            errors.append(f"assignment[{index}]:archive_default_visible_not_allowed")

        if any(value is None for value in [uid, consumer, app_id, key_id, default_read, archive_read, write]):
            continue
        if (
            unknown_fields
            or missing_fields
            or unknown_scopes
            or consumer not in ALLOWED_CONSUMERS
            or archive_default_visible
        ):
            continue
        normalized.append(
            {
                "uid": uid,
                "consumer": consumer,
                "app_id": app_id,
                "key_id": key_id,
                "grant_path": f"grants.{consumer}.apps.{app_id}.keys.{key_id}",
                "document_path": f"users/{uid}/{APP_KEY_MEMORY_GRANT_SUBPATH}",
                "grant": {
                    "enabled": enabled,
                    "scopes": scopes,
                    "default_read": default_read,
                    "archive_read": archive_read,
                    "write": write,
                    "archive_default_visible": False,
                },
            }
        )
    return normalized, errors


def build_nested_grant_patch(plan: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "grants": {
            str(plan["consumer"]): {"apps": {str(plan["app_id"]): {"keys": {str(plan["key_id"]): dict(plan["grant"])}}}}
        }
    }


def serialize_plan(plan: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "document_path": plan["document_path"],
        "grant_path": plan["grant_path"],
        "consumer": plan["consumer"],
        "uid": plan["uid"],
        "app_id": plan["app_id"],
        "key_id": plan["key_id"],
        "grant": dict(plan["grant"]),
    }


def apply_assignments(db_client: Any, plans: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    applied: List[Dict[str, Any]] = []
    for plan in plans:
        patch = build_nested_grant_patch(plan)
        db_client.document(str(plan["document_path"])).set(patch, merge=True)
        applied.append({"document_path": plan["document_path"], "grant_path": plan["grant_path"], "patch": patch})
    return applied


def base_non_claims(executed: bool) -> List[str]:
    claims = [
        "not executed against production unless --execute is supplied with an intentional backend/Admin runtime context",
        "no app/key grants assigned unless --execute --allow-write --assignment-file succeeds",
        "no deployed Firestore/IAM proof is claimed by this runner",
        "grants are server-owned and never inferred from MCP advertised metadata, client request fields, or key scopes alone",
        "Archive is never default-visible; archive_read is only an explicit capability flag",
        "production rollout remains blocked/no-go until Oracle P0 gates and real cloud proofs pass",
    ]
    if not executed:
        claims.insert(0, "no Firestore reads or writes were executed")
    return claims


def run_assignment_readiness(
    db_client: Any,
    *,
    execute: bool,
    allow_write: bool,
    assignments: Optional[Sequence[object]] = None,
) -> Dict[str, Any]:
    if not execute:
        return {
            "status": "NOT_RUN",
            "read_only": True,
            "mutation_allowed": False,
            "planned_writes": [],
            "errors": [],
            "non_claims": base_non_claims(executed=False),
        }

    plans, errors = normalize_assignments(assignments or [])
    if errors:
        return {
            "status": "DENIED",
            "read_only": True,
            "mutation_allowed": False,
            "planned_writes": [serialize_plan(plan) for plan in plans],
            "errors": errors,
            "non_claims": base_non_claims(executed=True),
        }

    result: Dict[str, Any] = {
        "status": "DRY_RUN",
        "read_only": True,
        "mutation_allowed": False,
        "planned_writes": [serialize_plan(plan) for plan in plans],
        "errors": [],
        "non_claims": base_non_claims(executed=True),
    }
    if not plans or not allow_write:
        return result

    result["applied_writes"] = apply_assignments(db_client, plans)
    result["status"] = "APPLIED"
    result["read_only"] = False
    result["mutation_allowed"] = True
    return result


def load_assignments(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path:
        return []
    with Path(path).open("r", encoding="utf-8") as handle:
        loaded: object = json.load(handle)
    if isinstance(loaded, list):
        return cast(List[Dict[str, Any]], loaded)
    if isinstance(loaded, dict):
        loaded_dict: Dict[str, Any] = cast(Dict[str, Any], loaded)
        assignments = loaded_dict.get("assignments")
        if isinstance(assignments, list):
            return cast(List[Dict[str, Any]], assignments)
    raise ValueError("assignment file must be a JSON list or an object with an assignments list")


def build_production_db_client() -> Any:
    client_module = importlib.import_module("database._client")
    return client_module.db


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and optionally apply deterministic server-owned memory app/key memory grant assignments. "
            "Default mode is NOT_RUN and performs no Firestore reads or writes."
        )
    )
    parser.add_argument(
        "--execute", action="store_true", help="validate assignment plan; without this, status is NOT_RUN"
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="apply assignments; requires --execute and --assignment-file",
    )
    parser.add_argument(
        "--assignment-file",
        default=os.environ.get(DEFAULT_ASSIGNMENT_FILE_ENV),
        help="JSON list of {uid, consumer, app_id, key_id, scopes, default_read, archive_read, write, archive_default_visible}",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None, *, db_client: Any = None) -> int:
    args = parse_args(argv)
    if not args.execute:
        payload = run_assignment_readiness(db_client=None, execute=False, allow_write=False, assignments=[])
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.allow_write and not args.assignment_file:
        payload = {
            "status": "DENIED",
            "read_only": True,
            "mutation_allowed": False,
            "errors": ["--assignment-file or APP_KEY_MEMORY_GRANT_ASSIGNMENTS is required with --allow-write"],
            "non_claims": base_non_claims(executed=True),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2

    try:
        assignments = load_assignments(args.assignment_file)
        client = db_client or (build_production_db_client() if args.allow_write else None)
        payload = run_assignment_readiness(
            client, execute=True, allow_write=bool(args.allow_write), assignments=assignments
        )
    except Exception as exc:
        payload = {
            "status": "ERROR",
            "read_only": not bool(args.allow_write),
            "mutation_allowed": False,
            "error": str(exc),
            "non_claims": base_non_claims(executed=True),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2

    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 2 if payload.get("status") in {"DENIED", "ERROR"} else 0


if __name__ == "__main__":
    sys.exit(main())
