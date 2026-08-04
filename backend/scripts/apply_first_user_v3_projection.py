#!/usr/bin/env python3
"""Build/apply a complete, redacted `/v3` compatibility projection repair.

Default mode is dry-run. Firestore writes require both ``--apply`` and an exact
``--confirm-uid`` match. The script writes only the compatibility projection
state/items paths for the requested user. It deliberately never publishes read
cutover readiness: only the canonical migration controller may do that after it
has verified graph assertions, projection freshness, and the durable outbox.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from google.cloud import firestore
except ImportError:  # pragma: no cover - exercised when optional cloud deps are absent in lightweight test envs
    firestore = None

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database.google_credentials import prepare_google_credentials
from database.memory_collections import MemoryCollections
from utils.memory.v3.projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3_COMPATIBILITY_PROJECTION_SOURCE,
    V3_COMPATIBILITY_PROJECTION_VERSION,
)

FIRST_USER_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
DEFAULT_PROJECT = "based-hardware"
DEFAULT_LIMIT = 5_000
MAX_LIMIT = 10_000
FIRESTORE_WRITE_BATCH_SIZE = 400
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
    source_head: dict[str, Any]
    source_memory_item_count: int
    source_item_paths: list[str]
    writes: dict[str, dict[str, Any]]
    stale_projection_paths: list[str]
    rollback_manifest: dict[str, Any]
    redacted_items: list[dict[str, Any]]
    skipped_by_reason: dict[str, int]
    full_rebuild: bool
    rebuild_id: str


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
    for snapshot in db_client.collection(paths.memory_items).stream():
        data = _snapshot_data(snapshot)
        if data is None:
            continue
        doc_id = getattr(snapshot, "id", "") or str(data.get("memory_id") or "")
        rows.append((doc_id, f"{paths.memory_items}/{doc_id}", data))
        if len(rows) > limit:
            raise RuntimeError(f"source memory item count exceeds safety limit ({limit})")
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


def _validate_source_identity(uid: str, memory_id: str, path: str, data: dict[str, Any]) -> None:
    if not path.startswith(f"users/{uid}/memory_items/"):
        raise RuntimeError(f"refusing cross-user source path: {path}")
    if data.get("uid") != uid:
        raise RuntimeError(f"refusing cross-user memory item at {path}")
    if data.get("memory_id") not in (None, memory_id):
        raise RuntimeError(f"memory_id mismatch at {path}")


def _projection_skip_reason(data: dict[str, Any]) -> str | None:
    """Return why a source row must not be copied into the default-read projection.

    Keep this aligned with the normal outbox projection writer.  Rows outside this
    policy are expected in the authoritative store and must not make a complete
    rebuild look incomplete.
    """

    if data.get("status") != "active":
        return "not_active"
    if data.get("processing_state") != "processed":
        return "not_processed"
    if data.get("source_state") != "active":
        return "source_not_active"
    if data.get("tier") not in {"short_term", "long_term"}:
        return "not_default_tier"
    if data.get("deleted") is True or data.get("tombstoned") is True:
        return "deleted_or_tombstoned"
    if data.get("archive") is True:
        return "archived"
    restricted = _labels(data).intersection(RESTRICTED_SENSITIVITY_LABELS)
    if restricted or data.get("restricted_sensitivity") is True:
        return "restricted_sensitivity"
    if data.get("user_review") is False:
        return "user_rejected"
    promotion = data.get("promotion")
    if isinstance(promotion, dict) and promotion.get("user_review") is False:
        return "user_rejected"
    try:
        _content(data)
    except RuntimeError:
        return "missing_content"
    return None


def _timestamp(data: dict[str, Any], *fields: str) -> datetime:
    for field in fields:
        value = data.get(field)
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _projection_fences(uid: str, head: dict[str, Any], *, ready: bool, rebuild_id: str) -> dict[str, Any]:
    generation = _as_int(head, "account_generation")
    head_commit_id = _as_nonempty_str(head, "head_commit_id")
    commit_sequence = _as_int(head, "commit_sequence")
    return {
        "uid": uid,
        "schema_version": V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        "source": V3_COMPATIBILITY_PROJECTION_SOURCE,
        "ready": ready,
        "rebuild_id": rebuild_id,
        "rebuild_complete": True,
        # This admits canonical outbox writers while ``ready`` remains the
        # independent reader/cutover gate.  A rebuild therefore cannot lose
        # writes that arrive after its initial scan.
        "writer_admission_ready": True,
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


def _projection_item_paths(db_client, *, uid: str) -> list[str]:
    collection_path = MemoryCollections(uid=uid).v3_compatibility_projection_items
    return [
        f"{collection_path}/{getattr(snapshot, 'id', '')}"
        for snapshot in db_client.collection(collection_path).stream()
        if getattr(snapshot, "id", "")
    ]


def build_projection(db_client, *, uid: str, project: str, memory_id: str | None, limit: int) -> ProjectionBuild:
    if limit < 1 or limit > MAX_LIMIT:
        raise ValueError(f"--limit must be between 1 and {MAX_LIMIT}")
    head_path, head = _read_head(db_client, uid=uid)
    full_rebuild = memory_id is None
    # A manual projection rebuild is a repair operation, not canonical migration
    # verification.  Keep reads fail-closed until the controller writes a
    # verified read-cutover checkpoint at this same inventory/head fence.
    rebuild_id = f"rebuild_{uuid4().hex}"
    fences = _projection_fences(uid, head, ready=False, rebuild_id=rebuild_id)
    source_rows = _stream_memory_items(db_client, uid=uid, memory_id=memory_id, limit=limit)
    if not source_rows and not full_rebuild:
        raise RuntimeError("memory item was not found for partial projection inspection")

    paths = MemoryCollections(uid=uid)
    state_path = paths.v3_compatibility_projection_state
    writes: dict[str, dict[str, Any]] = {}
    if full_rebuild:
        writes[state_path] = {**fences, "empty_projection": False}
    source_paths: list[str] = []
    redacted_items: list[dict[str, Any]] = []
    skipped_by_reason: dict[str, int] = {}
    for doc_id, source_path, data in source_rows:
        resolved_memory_id = str(data.get("memory_id") or doc_id)
        _validate_source_identity(uid, resolved_memory_id, source_path, data)
        skip_reason = _projection_skip_reason(data)
        if skip_reason is not None:
            skipped_by_reason[skip_reason] = skipped_by_reason.get(skip_reason, 0) + 1
            continue
        target_path = projection_target_item_path(uid, resolved_memory_id)
        projection = _projection_item(uid, resolved_memory_id, data, fences)
        writes[target_path] = projection
        source_paths.append(source_path)
        redacted_items.append(_redacted_item_summary(resolved_memory_id, source_path, data, projection))

    if full_rebuild:
        writes[state_path]["empty_projection"] = not redacted_items

    projected_paths = set(writes) - {state_path}
    stale_projection_paths = (
        sorted(set(_projection_item_paths(db_client, uid=uid)) - projected_paths) if full_rebuild else []
    )

    touched_paths = sorted(set(writes).union(stale_projection_paths))
    return ProjectionBuild(
        uid=uid,
        project=project,
        head_path=head_path,
        source_head=head,
        source_memory_item_count=len(source_rows),
        source_item_paths=source_paths,
        writes=writes,
        stale_projection_paths=stale_projection_paths,
        rollback_manifest={
            "project": project,
            "uid": uid,
            "dry_run_default": True,
            "touched_path_count": len(touched_paths),
            "touched_doc_paths": touched_paths,
            "operator_action": "delete or restore these exact projection docs from backup if rollback is required",
        },
        redacted_items=redacted_items,
        skipped_by_reason=skipped_by_reason,
        full_rebuild=full_rebuild,
        rebuild_id=rebuild_id,
    )


def apply_projection(db_client, build: ProjectionBuild) -> list[str]:
    if not build.full_rebuild:
        raise RuntimeError("refusing to apply a partial projection; run a complete rebuild")

    state_path = MemoryCollections(uid=build.uid).v3_compatibility_projection_state
    final_state = build.writes[state_path]
    # Publishing this first fences all later finalization to one build id.  It
    # leaves writers admitted, but no reader may observe a partial inventory.
    staged_state = {
        **final_state,
        "ready": False,
        "rebuild_complete": False,
        "write_convergence_complete": False,
        "delete_convergence_complete": False,
        "tombstone_convergence_complete": False,
    }
    db_client.document(state_path).set(staged_state)

    item_paths = [path for path in sorted(build.writes) if path != state_path]
    for path in item_paths:
        if not path.startswith(f"users/{build.uid}/v3_compatibility_projection"):
            raise RuntimeError(f"refusing write outside v3 projection paths: {path}")
    for path in build.stale_projection_paths:
        if not path.startswith(f"users/{build.uid}/v3_compatibility_projection_items/"):
            raise RuntimeError(f"refusing delete outside projection items: {path}")
    _apply_item_mutations(
        db_client,
        writes=[(path, build.writes[path]) for path in item_paths],
        deletes=build.stale_projection_paths,
    )

    _finalize_projection_rebuild(db_client, build=build, state_path=state_path, final_state=final_state)
    return [state_path, *item_paths, *build.stale_projection_paths]


def _finalize_projection_rebuild(
    db_client, *, build: ProjectionBuild, state_path: str, final_state: dict[str, Any]
) -> None:
    """CAS finalization: a stale or superseded rebuild can never publish itself."""
    state_ref = db_client.document(state_path)

    def finalize(transaction=None) -> None:
        if transaction is None:
            _, observed_head = _read_head(db_client, uid=build.uid)
            state = _snapshot_data(state_ref.get())
        else:
            observed_head = _snapshot_data(db_client.document(build.head_path).get(transaction=transaction))
            state = _snapshot_data(state_ref.get(transaction=transaction))
        if observed_head != build.source_head:
            raise RuntimeError("source head changed during projection rebuild; projection remains not ready")
        if (
            not isinstance(state, dict)
            or state.get("rebuild_id") != build.rebuild_id
            or state.get("ready") is not False
        ):
            raise RuntimeError("projection rebuild was superseded or already cut over")
        if transaction is None:
            state_ref.set(final_state)
        else:
            transaction.set(state_ref, final_state)

    transaction = db_client.transaction() if hasattr(db_client, "transaction") else None
    if transaction is None:
        finalize()
        return
    if firestore is not None and transaction.__class__.__module__.startswith("google.cloud.firestore"):
        firestore.transactional(finalize)(transaction)
        return
    if hasattr(transaction, "_begin"):
        transaction._begin()
    try:
        finalize(transaction)
        if hasattr(transaction, "_commit"):
            transaction._commit()
    except Exception:
        if hasattr(transaction, "_rollback"):
            transaction._rollback()
        raise
    finally:
        if hasattr(transaction, "_clean_up"):
            transaction._clean_up()


def _apply_item_mutations(db_client, *, writes: list[tuple[str, dict[str, Any]]], deletes: list[str]) -> None:
    """Write the item set in bounded commits; leave state not-ready on any failure."""

    mutations: list[tuple[str, str, dict[str, Any] | None]] = [("set", path, payload) for path, payload in writes] + [
        ("delete", path, None) for path in deletes
    ]
    if not mutations:
        return
    if not hasattr(db_client, "batch"):
        for kind, path, payload in mutations:
            if kind == "set":
                db_client.document(path).set(payload)
            else:
                db_client.document(path).delete()
        return
    for start in range(0, len(mutations), FIRESTORE_WRITE_BATCH_SIZE):
        batch = db_client.batch()
        for kind, path, payload in mutations[start : start + FIRESTORE_WRITE_BATCH_SIZE]:
            reference = db_client.document(path)
            if kind == "set":
                batch.set(reference, payload)
            else:
                batch.delete(reference)
        batch.commit()


def build_report(build: ProjectionBuild, *, applied_paths: list[str] | None = None) -> dict[str, Any]:
    return {
        "artifact": "first_user_v3_projection_apply",
        "uid": build.uid,
        "project": build.project,
        "dry_run": applied_paths is None,
        "source": {
            "head_path": build.head_path,
            "memory_item_count": build.source_memory_item_count,
        },
        "projection": {
            "state_path": MemoryCollections(uid=build.uid).v3_compatibility_projection_state,
            "item_count": len(build.redacted_items),
            "stale_item_count": len(build.stale_projection_paths),
            "skipped_by_reason": dict(sorted(build.skipped_by_reason.items())),
            "full_rebuild": build.full_rebuild,
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
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum source rows to inspect")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-uid", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and args.confirm_uid != args.uid:
        raise SystemExit("--apply requires --confirm-uid to exactly match --uid")
    if args.apply and args.memory_id:
        raise SystemExit("--apply does not allow --memory-id; a ready projection must be rebuilt in full")
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
