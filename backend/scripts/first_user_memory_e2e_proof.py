#!/usr/bin/env python3
"""Read-only first-user canonical-memory dev proof.

The proof reads Firestore state and calls `/v3/memories`; it never writes
Firestore/GCP state. Output is summarized and redacted.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from google.cloud import firestore
except ImportError:  # pragma: no cover - exercised when optional cloud deps are absent in lightweight test envs
    firestore = None

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database.google_credentials import prepare_google_credentials
from database.memory_collections import MemoryCollections
from utils.memory.v3_limited_rollout_config import GLOBAL_READ_GATE_PATH, WRITE_CONVERGENCE_GATE_PATH

FIRST_USER_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
DEFAULT_PROJECT = "based-hardware"


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    body: Any
    headers: dict[str, str]


def _snapshot_data(snapshot) -> dict[str, Any] | None:
    if snapshot is None or getattr(snapshot, "exists", False) is False:
        return None
    data = snapshot.to_dict()
    return data if isinstance(data, dict) else None


def _load_firestore_client(*, project: str):
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is required to run this script against Firestore")
    prepare_google_credentials()
    return firestore.Client(project=project)


def _read_id_token(args: argparse.Namespace) -> str:
    if args.id_token:
        return args.id_token.strip()
    if args.id_token_file:
        return Path(args.id_token_file).read_text(encoding="utf-8").strip()
    raise SystemExit("--id-token or --id-token-file is required")


def _check(name: str, ok: bool, **details) -> dict[str, Any]:
    return {"name": name, "status": "pass" if ok else "fail", **details}


def _int_matches(data: dict[str, Any], expected: int, *fields: str) -> bool:
    return all(type(data.get(field)) is int and data.get(field) == expected for field in fields)


def _decode_http_body(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"redacted_text_body_length": len(raw)}


def verify_firestore_state(db_client, *, uid: str, limit: int) -> dict[str, Any]:
    paths = MemoryCollections(uid=uid)
    global_gate = _snapshot_data(db_client.document(GLOBAL_READ_GATE_PATH).get())
    write_gate = _snapshot_data(db_client.document(WRITE_CONVERGENCE_GATE_PATH).get())
    control = _snapshot_data(db_client.document(paths.memory_control_state).get())
    head = _snapshot_data(db_client.document(paths.memory_state_head).get())
    projection_state = _snapshot_data(db_client.document(paths.v3_compatibility_projection_state).get())
    items = []
    for snapshot in db_client.collection(paths.v3_compatibility_projection_items).limit(limit).stream():
        data = _snapshot_data(snapshot)
        if data is None:
            continue
        memorydb = data.get("memorydb") if isinstance(data.get("memorydb"), dict) else {}
        items.append(
            {
                "doc_id": getattr(snapshot, "id", ""),
                "uid": data.get("uid"),
                "memory_id": data.get("memory_id") or getattr(snapshot, "id", ""),
                "account_generation": data.get("account_generation"),
                "projection_generation": data.get("projection_generation"),
                "content_length": len(memorydb.get("content") or "") if isinstance(memorydb.get("content"), str) else 0,
                "memorydb_fields": sorted(memorydb.keys()),
            }
        )

    expected_generation = head.get("account_generation") if isinstance(head, dict) else None
    projection_ready = isinstance(projection_state, dict) and projection_state.get("ready") is True
    projection_generation = (
        projection_state.get("projection_generation") if isinstance(projection_state, dict) else None
    )
    fences_match = (
        type(expected_generation) is int
        and isinstance(projection_state, dict)
        and type(projection_generation) is int
        and projection_state.get("account_generation") == expected_generation
        and _int_matches(
            projection_state,
            projection_generation,
            "freshness_fence_generation",
            "tombstone_fence_generation",
            "vector_cleanup_fence_generation",
        )
        and all(
            item["uid"] == uid
            and item["account_generation"] == expected_generation
            and item["projection_generation"] == projection_generation
            for item in items
        )
    )
    checks = [
        _check(
            "global_read_gate_open",
            isinstance(global_gate, dict)
            and global_gate.get("memory_reads_enabled") is True
            and global_gate.get("kill_switch_active") is False,
            path=GLOBAL_READ_GATE_PATH,
        ),
        _check(
            "write_convergence_gate_ready",
            isinstance(write_gate, dict)
            and all(
                write_gate.get(field) is True
                for field in (
                    "durable_outbox_enabled",
                    "dual_write_projection_ready",
                    "delete_convergence_ready",
                    "idempotency_contract_ready",
                )
            ),
            path=WRITE_CONVERGENCE_GATE_PATH,
        ),
        _check(
            "user_control_read_mode",
            isinstance(control, dict)
            and control.get("uid") == uid
            and control.get("mode") == "read"
            and control.get("grants", {}).get("omi_chat", {}).get("default_memory") is True,
            path=paths.memory_control_state,
        ),
        _check(
            "memory_state_head_exists", isinstance(head, dict) and head.get("uid") == uid, path=paths.memory_state_head
        ),
        _check(
            "projection_state_ready",
            projection_ready and projection_state.get("uid") == uid,
            path=paths.v3_compatibility_projection_state,
        ),
        _check(
            "projection_items_exist", len(items) > 0, path=paths.v3_compatibility_projection_items, count=len(items)
        ),
        _check("projection_generation_fences_match_head", fences_match, expected_generation=expected_generation),
    ]
    return {
        "status": "pass" if all(check["status"] == "pass" for check in checks) else "fail",
        "checks": checks,
        "redacted_projection_items": items,
    }


def urllib_http_get(url: str, headers: dict[str, str], timeout_seconds: float) -> HttpResult:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            return HttpResult(response.status, _decode_http_body(raw), dict(response.headers))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return HttpResult(exc.code, _decode_http_body(raw), dict(exc.headers))
    except URLError as exc:
        raise RuntimeError(f"HTTP request failed: {exc}") from exc


def verify_api_behavior(
    *,
    backend_url: str,
    uid: str,
    id_token: str,
    limit: int,
    timeout_seconds: float,
    http_get=urllib_http_get,
) -> dict[str, Any]:
    url = backend_url.rstrip("/") + "/v3/memories?" + urlencode({"limit": str(limit)})
    authenticated = http_get(url, {"Authorization": f"Bearer {id_token}"}, timeout_seconds)
    unauthenticated = http_get(url, {}, timeout_seconds)
    body_is_list = isinstance(authenticated.body, list)
    body = authenticated.body if body_is_list else []
    only_requested_uid = all(isinstance(item, dict) and item.get("uid") == uid for item in body)
    lifecycle_fields_present = all(
        isinstance(item, dict) and ("layer" in item or "memory_tier" in item) for item in body
    )
    redacted_items = [
        {
            "id": item.get("id"),
            "uid": item.get("uid"),
            "fields": sorted(item.keys()),
            "content_length": len(item.get("content") or "") if isinstance(item.get("content"), str) else 0,
            "layer": item.get("layer"),
            "memory_tier": item.get("memory_tier"),
        }
        for item in body
        if isinstance(item, dict)
    ]
    checks = [
        _check(
            "authenticated_get_v3_memories_200", authenticated.status_code == 200, status_code=authenticated.status_code
        ),
        _check("authenticated_get_v3_memories_body_list", body_is_list, body_type=type(authenticated.body).__name__),
        _check("response_only_requested_uid", only_requested_uid, uid=uid),
        _check(
            "canonical_lifecycle_fields_present",
            lifecycle_fields_present if body else True,
            item_count=len(body),
            skipped_reason=None if body else "empty response has no item lifecycle fields to inspect",
        ),
        _check(
            "unauthenticated_request_rejected",
            unauthenticated.status_code in {401, 403},
            status_code=unauthenticated.status_code,
        ),
    ]
    return {
        "status": "pass" if all(check["status"] == "pass" for check in checks) else "fail",
        "checks": checks,
        "authenticated_status": authenticated.status_code,
        "unauthenticated_status": unauthenticated.status_code,
        "redacted_items": redacted_items,
        "headers": {
            key: authenticated.headers.get(key)
            for key in ("X-Omi-Memory-Read-Source", "X-Omi-Memory-Read-Decision", "X-Omi-Memory-Next-Cursor")
            if authenticated.headers.get(key) is not None
        },
    }


def build_not_checked_surfaces() -> dict[str, dict[str, str]]:
    return {
        "search": {
            "status": "not_checked",
            "reason": "No generic authenticated first-user search endpoint contract is available to this script.",
        },
        "default_read_surfaces": {
            "status": "not_checked",
            "reason": "Only `/v3/memories` has a stable generic API proof path here; MCP/developer/default-read surfaces require route-specific harnesses.",
        },
    }


def build_report(*, uid: str, project: str, firestore_report: dict, api_report: dict) -> dict[str, Any]:
    status = "pass" if firestore_report["status"] == "pass" and api_report["status"] == "pass" else "fail"
    return {
        "artifact": "first_user_memory_e2e_proof",
        "uid": uid,
        "project": project,
        "status": status,
        "mutation_allowed": False,
        "firestore": firestore_report,
        "api": api_report,
        "additional_surfaces": build_not_checked_surfaces(),
        "redaction": {
            "raw_memory_content_printed": False,
            "tokens_printed": False,
            "output_includes": ["ids", "uid", "field names", "content lengths", "status codes", "generation checks"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run read-only first-user memory dev E2E proof.")
    parser.add_argument("--uid", default=FIRST_USER_UID)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--id-token-file", default="")
    parser.add_argument("--id-token", default="")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be positive")
    id_token = _read_id_token(args)
    db_client = _load_firestore_client(project=args.project)
    firestore_report = verify_firestore_state(db_client, uid=args.uid, limit=args.limit)
    api_report = verify_api_behavior(
        backend_url=args.backend_url,
        uid=args.uid,
        id_token=id_token,
        limit=args.limit,
        timeout_seconds=args.timeout_seconds,
    )
    report = build_report(uid=args.uid, project=args.project, firestore_report=firestore_report, api_report=api_report)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
