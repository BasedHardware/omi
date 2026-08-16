#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, cast

MCP_API_KEY_COLLECTION = "mcp_api_keys"
DEFAULT_ASSIGNMENT_FILE_ENV = "MEMORY_MCP_API_KEY_SCOPE_ASSIGNMENTS"
ALLOWED_SERVER_ASSIGNED_SCOPES = frozenset({"memories.read", "memories.write", "memories.archive.read"})
REQUIRED_DEFAULT_READ_SCOPE = "memories.read"


@dataclass(frozen=True)
class McpApiKeyInventoryRow:
    key_id: str
    user_id: Optional[str]
    app_id: Optional[str]
    scopes: Optional[List[str]]
    missing_app_id: bool
    missing_scopes: bool
    verified_memories_read: bool
    unknown_scopes: List[str]
    malformed_scopes: bool


def normalize_scope_list(value: Any) -> Tuple[Optional[List[str]], bool]:
    if value is None:
        return None, False
    if not isinstance(value, list):
        return None, True
    items = cast(List[Any], value)
    scopes: List[str] = []
    for scope in items:
        if not isinstance(scope, str):
            return None, True
        scopes.append(scope)
    return list(dict.fromkeys(scopes)), False


def row_from_snapshot(snapshot: Any) -> McpApiKeyInventoryRow:
    raw: object = snapshot.to_dict()
    data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    key_id = str(data.get("id") or getattr(snapshot, "id", ""))
    scopes, malformed_scopes = normalize_scope_list(data.get("scopes"))
    unknown_scopes = sorted(scope for scope in (scopes or []) if scope not in ALLOWED_SERVER_ASSIGNED_SCOPES)
    return McpApiKeyInventoryRow(
        key_id=key_id,
        user_id=data.get("user_id"),
        app_id=data.get("app_id"),
        scopes=scopes,
        missing_app_id=not bool(data.get("app_id")),
        missing_scopes=scopes is None,
        verified_memories_read=REQUIRED_DEFAULT_READ_SCOPE in (scopes or []),
        unknown_scopes=unknown_scopes,
        malformed_scopes=malformed_scopes,
    )


def inventory_mcp_api_keys(db_client: Any) -> List[McpApiKeyInventoryRow]:
    return [row_from_snapshot(snapshot) for snapshot in db_client.collection(MCP_API_KEY_COLLECTION).stream()]


def summarize_inventory(rows: Sequence[McpApiKeyInventoryRow]) -> Dict[str, int]:
    return {
        "total_keys": len(rows),
        "missing_app_id": sum(1 for row in rows if row.missing_app_id),
        "missing_scopes": sum(1 for row in rows if row.missing_scopes),
        "malformed_scopes": sum(1 for row in rows if row.malformed_scopes),
        "verified_memories_read": sum(1 for row in rows if row.verified_memories_read),
        "unknown_scopes": sum(1 for row in rows if row.unknown_scopes),
    }


def serialize_row(row: McpApiKeyInventoryRow) -> Dict[str, Any]:
    return {
        "key_id": row.key_id,
        "user_id": row.user_id,
        "app_id": row.app_id,
        "scopes": row.scopes,
        "needs_app_id": row.missing_app_id,
        "needs_scopes": row.missing_scopes or not row.verified_memories_read,
        "verified_memories_read": row.verified_memories_read,
        "unknown_scopes": row.unknown_scopes,
        "malformed_scopes": row.malformed_scopes,
    }


def normalize_assignments(
    assignments: Optional[Mapping[str, Mapping[str, Any]]],
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    for key_id, assignment in (assignments or {}).items():
        app_id = assignment.get("app_id")
        scopes, malformed_scopes = normalize_scope_list(assignment.get("scopes"))
        if not key_id:
            errors.append("invalid_key_id")
            continue
        if not isinstance(app_id, str) or not app_id:
            errors.append(f"{key_id}:missing_app_id")
            continue
        if malformed_scopes or scopes is None:
            errors.append(f"{key_id}:malformed_scopes")
            continue
        unknown = sorted(scope for scope in scopes if scope not in ALLOWED_SERVER_ASSIGNED_SCOPES)
        if unknown:
            errors.append(f"{key_id}:unknown_scope:{','.join(unknown)}")
            continue
        normalized[key_id] = {"app_id": app_id, "scopes": scopes}
    return normalized, errors


def apply_assignments(db_client: Any, assignments: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    applied: List[Dict[str, Any]] = []
    for key_id in sorted(assignments):
        patch = {"app_id": assignments[key_id]["app_id"], "scopes": list(assignments[key_id]["scopes"])}
        db_client.collection(MCP_API_KEY_COLLECTION).document(key_id).update(patch)
        applied.append({"key_id": key_id, "patch": patch})
    return applied


def base_non_claims(executed: bool) -> List[str]:
    claims = [
        "not executed against production unless --execute is supplied with a real project/runtime context",
        "no OAuth introspection is implemented by this runner",
        "no deployed Firestore/IAM proof is claimed by this runner",
        "scopes are server-owned and never infer scopes from advertised MCP tool metadata or client requests",
    ]
    if not executed:
        claims.insert(0, "no Firestore reads or writes were executed")
    return claims


def run_readiness_inventory(
    db_client: Any,
    *,
    execute: bool,
    allow_write: bool,
    assignments: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    if not execute:
        return {
            "status": "NOT_RUN",
            "read_only": True,
            "mutation_allowed": False,
            "summary": {},
            "rows": [],
            "planned_assignments": assignments or {},
            "non_claims": base_non_claims(executed=False),
        }

    rows = inventory_mcp_api_keys(db_client)
    normalized_assignments, assignment_errors = normalize_assignments(assignments)
    if assignment_errors:
        return {
            "status": "DENIED",
            "read_only": True,
            "mutation_allowed": False,
            "summary": summarize_inventory(rows),
            "rows": [serialize_row(row) for row in rows],
            "errors": assignment_errors,
            "non_claims": base_non_claims(executed=True),
        }

    result: Dict[str, Any] = {
        "status": "DRY_RUN",
        "read_only": True,
        "mutation_allowed": False,
        "summary": summarize_inventory(rows),
        "rows": [serialize_row(row) for row in rows],
        "planned_assignments": normalized_assignments,
        "non_claims": base_non_claims(executed=True),
    }
    if not normalized_assignments:
        return result
    if not allow_write:
        return result

    result["applied_assignments"] = apply_assignments(db_client, normalized_assignments)
    result["status"] = "APPLIED"
    result["read_only"] = False
    result["mutation_allowed"] = True
    return result


def load_assignments(path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        loaded: object = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("assignment file must be a JSON object keyed by MCP key id")
    return cast(Dict[str, Dict[str, Any]], loaded)


def build_production_db_client() -> Any:
    client_module = importlib.import_module("database._client")
    return client_module.db


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory MCP API-key app_id/scopes readiness and optionally apply deterministic "
            "server-owned scope assignments. Default mode is NOT_RUN and performs no Firestore reads or writes."
        )
    )
    parser.add_argument(
        "--execute", action="store_true", help="run Firestore inventory; without this, status is NOT_RUN"
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="allow applying assignment-file patches; requires --execute and an assignment file",
    )
    parser.add_argument(
        "--assignment-file",
        default=os.environ.get(DEFAULT_ASSIGNMENT_FILE_ENV),
        help="JSON mapping of key_id to {app_id, scopes}; scopes must be allowlisted server-owned values",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None, *, db_client: Any = None) -> int:
    args = parse_args(argv)
    if not args.execute:
        payload = run_readiness_inventory(db_client=None, execute=False, allow_write=False, assignments={})
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    try:
        assignments = load_assignments(args.assignment_file)
        client = db_client or build_production_db_client()
        payload = run_readiness_inventory(
            client, execute=True, allow_write=bool(args.allow_write), assignments=assignments
        )
    except Exception as exc:
        payload = {
            "status": "ERROR",
            "read_only": not bool(args.allow_write),
            "mutation_allowed": False,
            "error": str(exc),
            "non_claims": base_non_claims(executed=bool(args.execute)),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2

    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 2 if payload.get("status") in {"DENIED", "ERROR"} else 0


if __name__ == "__main__":
    sys.exit(main())
