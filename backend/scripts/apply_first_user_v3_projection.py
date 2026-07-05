#!/usr/bin/env python3
"""Build/apply a redacted first-user `/v3` compatibility projection.

Default mode is dry-run. Firestore writes require both ``--apply`` and an exact
``--confirm-uid`` match. The script writes only the compatibility projection
state/items paths for the requested user.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from google.cloud import firestore
except ImportError:  # pragma: no cover - exercised when optional cloud deps are absent in lightweight test envs
    firestore = None

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database.google_credentials import prepare_google_credentials
from database.memory_collections import MemoryCollections
from utils.memory.v3_projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3_COMPATIBILITY_PROJECTION_SOURCE,
    V3_COMPATIBILITY_PROJECTION_VERSION,
)

FIRST_USER_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
DEFAULT_PROJECT = "based-hardware"
DEFAULT_LIMIT = 25
MAX_LIMIT = 500
RESTRICTED_SENSITIVITY_LABELS = {
    "credential",
    "secret",
    "financial",
    "health",
    "intimate",
    "minor",
    "minors",
    "workplace_confidential",
    "identity_authentication",
}


@dataclass(frozen=True)
class ProjectionBuild:
    uid: str
    project: str
    head_path: str
    source_item_paths: list[str]
    writes: dict[str, dict[str, Any]]
    rollback_manifest: dict[str, Any]
    redacted_items: list[dict[str, Any]]


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


def _as_int(data: dict[str, Any], field: str) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _as_nonempty_str(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _read_head(db_client, *, uid: str) -> tuple[str, dict[str, Any]]:
    path = MemoryCollections(uid=uid).memory_state_head
    data = _snapshot_data(db_client.document(path).get())
    if data is None:
        raise RuntimeError(f"missing required head doc: {path}")
    if data.get("uid") != uid:
        raise RuntimeError(f"refusing cross-user head doc at {path}")
    if data.get("schema_version") != 1 or data.get("source") != "memory_state_head":
        raise RuntimeError(f"malformed memory_state/head at {path}")
    _as_int(data, "account_generation")
    _as_int(data, "commit_sequence")
    _as_nonempty_str(data, "head_commit_id")
    return path, data


def _stream_memory_items(
    db_client, *, uid: str, memory_id: str | None, limit: int
) -> list[tuple[str, str, dict[str, Any]]]:
    paths = MemoryCollections(uid=uid)
    if memory_id:
        path = f"{paths.memory_items}/{memory_id}"
        data = _snapshot_data(db_client.document(path).get())
        return [(memory_id, path, data)] if data is not None else []

    rows: list[tuple[str, str, dict[str, Any]]] = []
    for snapshot in db_client.collection(paths.memory_items).limit(limit).stream():
        data = _snapshot_data(snapshot)
        if data is None:
            continue
        doc_id = getattr(snapshot, "id", "") or str(data.get("memory_id") or "")
        rows.append((doc_id, f"{paths.memory_items}/{doc_id}", data))
    return rows


def _labels(data: dict[str, Any]) -> set[str]:
    labels = data.get("sensitivity_labels") or []
    if not isinstance(labels, list):
        raise RuntimeError("sensitivity_labels must be a list")
    return {str(label).strip().lower() for label in labels if str(label).strip()}


def _content(data: dict[str, Any]) -> str:
    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("active projection source memory requires nonempty content")
    return content


def _user_review_value(data: dict[str, Any]):
    promotion = data.get("promotion")
    if isinstance(promotion, dict) and "user_review" in promotion:
        return promotion.get("user_review")
    return data.get("user_review")


def _require_safe_active_item(uid: str, memory_id: str, path: str, data: dict[str, Any]) -> None:
    if not path.startswith(f"users/{uid}/memory_items/"):
        raise RuntimeError(f"refusing cross-user source path: {path}")
    if data.get("uid") != uid:
        raise RuntimeError(f"refusing cross-user memory item at {path}")
    if data.get("memory_id") not in (None, memory_id):
        raise RuntimeError(f"memory_id mismatch at {path}")
    if data.get("status") != "active":
        raise RuntimeError(f"refusing non-active memory item at {path}")
    if data.get("source_state") != "active":
        raise RuntimeError(f"refusing non-active source_state at {path}")
    if data.get("tier") == "archive" or data.get("archive") is True:
        raise RuntimeError(f"refusing archive memory item at {path}")
    if data.get("deleted") is True or data.get("tombstoned") is True:
        raise RuntimeError(f"refusing deleted/tombstoned memory item at {path}")
    restricted = _labels(data).intersection(RESTRICTED_SENSITIVITY_LABELS)
    if restricted or data.get("restricted_sensitivity") is True:
        raise RuntimeError(f"refusing restricted sensitivity memory item at {path}: {sorted(restricted)}")
    if data.get("user_review") is False:
        raise RuntimeError(f"refusing user-rejected memory item at {path}")
    promotion = data.get("promotion")
    if isinstance(promotion, dict) and promotion.get("user_review") is False:
        raise RuntimeError(f"refusing user-rejected memory item at {path}")
    _content(data)


def _timestamp(data: dict[str, Any], *fields: str) -> datetime:
    for field in fields:
        value = data.get(field)
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _projection_fences(uid: str, head: dict[str, Any]) -> dict[str, Any]:
    generation = _as_int(head, "account_generation")
    head_commit_id = _as_nonempty_str(head, "head_commit_id")
    commit_sequence = _as_int(head, "commit_sequence")
    return {
        "uid": uid,
        "schema_version": V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        "source": V3_COMPATIBILITY_PROJECTION_SOURCE,
        "ready": True,
        "account_generation": generation,
        "projection_generation": generation,
        "freshness_fence_generation": generation,
        "tombstone_fence_generation": generation,
        "vector_cleanup_fence_generation": generation,
        "source_commit_id": head_commit_id,
        "projection_commit_id": f"commit-{head_commit_id}",
        "source_evidence_fence": f"head-{head_commit_id}",
        "projection_evidence_fence": f"head-{head_commit_id}",
        "projection_version": V3_COMPATIBILITY_PROJECTION_VERSION,
        "source_version": f"memory_state_head:{commit_sequence}",
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
    }


def _memorydb_payload(uid: str, memory_id: str, data: dict[str, Any]) -> dict[str, Any]:
    captured_at = _timestamp(data, "captured_at", "created_at", "updated_at")
    updated_at = _timestamp(data, "updated_at", "captured_at", "created_at")
    tier = data.get("tier") or data.get("memory_tier") or "short_term"
    return {
        "id": memory_id,
        "uid": uid,
        "content": _content(data),
        "category": data.get("category") or "system",
        "visibility": data.get("visibility") or "private",
        "tags": data.get("tags") if isinstance(data.get("tags"), list) else [],
        "created_at": captured_at,
        "updated_at": updated_at,
        "reviewed": data.get("reviewed") if isinstance(data.get("reviewed"), bool) else True,
        "user_review": _user_review_value(data),
        "manually_added": data.get("manually_added") if isinstance(data.get("manually_added"), bool) else False,
        "edited": data.get("edited") if isinstance(data.get("edited"), bool) else False,
        "conversation_id": data.get("conversation_id"),
        "data_protection_level": data.get("data_protection_level") or "standard",
        "memory_tier": tier,
    }


def _projection_item(uid: str, memory_id: str, data: dict[str, Any], fences: dict[str, Any]) -> dict[str, Any]:
    created_at = _timestamp(data, "created_at", "captured_at", "updated_at")
    return {
        "uid": uid,
        "memory_id": memory_id,
        "schema_version": V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        "source": V3_COMPATIBILITY_PROJECTION_SOURCE,
        "account_generation": fences["account_generation"],
        "projection_generation": fences["projection_generation"],
        "source_commit_id": fences["source_commit_id"],
        "projection_commit_id": fences["projection_commit_id"],
        "projection_evidence_fence": fences["projection_evidence_fence"],
        "freshness_fence_generation": fences["freshness_fence_generation"],
        "tombstone_fence_generation": fences["tombstone_fence_generation"],
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
        "created_at": created_at,
        "memorydb": _memorydb_payload(uid, memory_id, data),
    }


def _redacted_item_summary(
    memory_id: str, path: str, item: dict[str, Any], projection: dict[str, Any]
) -> dict[str, Any]:
    memorydb = projection["memorydb"]
    return {
        "source_path": path,
        "target_path": projection_target_item_path(memorydb["uid"], memory_id),
        "memory_id": memory_id,
        "uid": memorydb["uid"],
        "account_generation": projection["account_generation"],
        "projection_generation": projection["projection_generation"],
        "fences": {
            "source_commit_id": projection["source_commit_id"],
            "projection_commit_id": projection["projection_commit_id"],
            "projection_evidence_fence": projection["projection_evidence_fence"],
            "freshness_fence_generation": projection["freshness_fence_generation"],
            "tombstone_fence_generation": projection["tombstone_fence_generation"],
        },
        "source_fields": sorted(item.keys()),
        "memorydb_fields": sorted(memorydb.keys()),
        "content_length": len(memorydb["content"]),
        "sensitivity_labels": sorted(_labels(item)),
    }


def projection_target_item_path(uid: str, memory_id: str) -> str:
    return f"{MemoryCollections(uid=uid).v3_compatibility_projection_items}/{memory_id}"


def build_projection(db_client, *, uid: str, project: str, memory_id: str | None, limit: int) -> ProjectionBuild:
    if limit < 1 or limit > MAX_LIMIT:
        raise ValueError(f"--limit must be between 1 and {MAX_LIMIT}")
    head_path, head = _read_head(db_client, uid=uid)
    fences = _projection_fences(uid, head)
    source_rows = _stream_memory_items(db_client, uid=uid, memory_id=memory_id, limit=limit)
    if not source_rows:
        raise RuntimeError("no active source memory_items found for projection")

    paths = MemoryCollections(uid=uid)
    state_path = paths.v3_compatibility_projection_state
    writes: dict[str, dict[str, Any]] = {
        state_path: {
            **fences,
            "empty_projection": False,
        }
    }
    source_paths: list[str] = []
    redacted_items: list[dict[str, Any]] = []
    for doc_id, source_path, data in source_rows:
        resolved_memory_id = str(data.get("memory_id") or doc_id)
        _require_safe_active_item(uid, resolved_memory_id, source_path, data)
        target_path = projection_target_item_path(uid, resolved_memory_id)
        projection = _projection_item(uid, resolved_memory_id, data, fences)
        writes[target_path] = projection
        source_paths.append(source_path)
        redacted_items.append(_redacted_item_summary(resolved_memory_id, source_path, data, projection))

    return ProjectionBuild(
        uid=uid,
        project=project,
        head_path=head_path,
        source_item_paths=source_paths,
        writes=writes,
        rollback_manifest={
            "project": project,
            "uid": uid,
            "dry_run_default": True,
            "touched_doc_paths": sorted(writes.keys()),
            "operator_action": "delete or restore these exact projection docs from backup if rollback is required",
        },
        redacted_items=redacted_items,
    )


def apply_projection(db_client, build: ProjectionBuild) -> list[str]:
    for path in sorted(build.writes):
        if not path.startswith(f"users/{build.uid}/v3_compatibility_projection"):
            raise RuntimeError(f"refusing write outside v3 projection paths: {path}")
        db_client.document(path).set(build.writes[path])
    return sorted(build.writes)


def build_report(build: ProjectionBuild, *, applied_paths: list[str] | None = None) -> dict[str, Any]:
    return {
        "artifact": "first_user_v3_projection_apply",
        "uid": build.uid,
        "project": build.project,
        "dry_run": applied_paths is None,
        "source": {
            "head_path": build.head_path,
            "memory_item_paths": build.source_item_paths,
        },
        "projection": {
            "state_path": MemoryCollections(uid=build.uid).v3_compatibility_projection_state,
            "item_count": len(build.redacted_items),
            "items": build.redacted_items,
        },
        "applied_paths": applied_paths or [],
        "rollback_manifest": build.rollback_manifest,
        "redaction": {
            "raw_memory_content_printed": False,
            "output_includes": ["doc paths", "ids", "generations", "fences", "field names", "content lengths"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build/apply first-user v3 compatibility projection docs.")
    parser.add_argument("--uid", default=FIRST_USER_UID)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--memory-id", default="")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-uid", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and args.confirm_uid != args.uid:
        raise SystemExit("--apply requires --confirm-uid to exactly match --uid")
    db_client = _load_firestore_client(project=args.project)
    build = build_projection(
        db_client,
        uid=args.uid,
        project=args.project,
        memory_id=args.memory_id or None,
        limit=args.limit,
    )
    applied_paths = apply_projection(db_client, build) if args.apply else None
    print(json.dumps(build_report(build, applied_paths=applied_paths), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
