#!/usr/bin/env python3
"""Firestore-emulator proof for fenced memory `/v3` compatibility projection reader.

Emulator-only: exits before constructing a Firestore client unless
FIRESTORE_EMULATOR_HOST is present. Writes only local emulator fixtures under the
server-owned memory compatibility projection paths, reads them via the projection
reader, and proves fail-closed fences. It does not wire runtime `/v3`, does not
read live memory_items, and does not contact production Firestore/providers.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from database.memory_collections import MemoryCollections
from database.memory_compatibility_projection import read_v3_compatibility_projection_page
from utils.memory.v3_projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3ProjectionFailureReason,
    V3ProjectionReadError,
    V3ProjectionReadRequest,
)

PROJECT_ID = os.environ.get("GCLOUD_PROJECT") or os.environ.get("FIREBASE_PROJECT") or "demo-memory"
UID = "memory-v3-projection-reader-emulator-user"
ACCOUNT_GENERATION = 70
PROJECTION_GENERATION = 90
SOURCE_COMMIT_ID = "source-90"
PROJECTION_COMMIT_ID = "commit-90"
FENCE = "fence-90"
PATHS = MemoryCollections(uid=UID)


def _require_emulator() -> None:
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise SystemExit("BLOCKED: FIRESTORE_EMULATOR_HOST is required; refusing production Firestore access")


def _state(**overrides: Any) -> dict[str, Any]:
    doc = {
        "uid": UID,
        "schema_version": V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        "source": "memory_items_projection",
        "ready": True,
        "account_generation": ACCOUNT_GENERATION,
        "projection_generation": PROJECTION_GENERATION,
        "source_commit_id": SOURCE_COMMIT_ID,
        "source_version": "memory",
        "projection_commit_id": PROJECTION_COMMIT_ID,
        "projection_version": "v3_memorydb_compatibility",
        "source_evidence_fence": FENCE,
        "projection_evidence_fence": FENCE,
        "freshness_fence_generation": PROJECTION_GENERATION,
        "tombstone_fence_generation": PROJECTION_GENERATION,
        "vector_cleanup_fence_generation": PROJECTION_GENERATION,
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
        "empty_projection": False,
    }
    doc.update(overrides)
    return doc


def _item(memory_id: str, created_at: datetime, **overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "uid": UID,
        "memory_id": memory_id,
        "schema_version": V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        "source": "memory_items_projection",
        "account_generation": ACCOUNT_GENERATION,
        "projection_generation": PROJECTION_GENERATION,
        "source_commit_id": SOURCE_COMMIT_ID,
        "projection_commit_id": PROJECTION_COMMIT_ID,
        "projection_evidence_fence": FENCE,
        "freshness_fence_generation": PROJECTION_GENERATION,
        "tombstone_fence_generation": PROJECTION_GENERATION,
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
        "deleted": False,
        "tombstoned": False,
        "archive": False,
        "short_term_stale": False,
        "created_at": created_at,
        "memorydb": {
            "id": memory_id,
            "uid": UID,
            "content": f"projection {memory_id}",
            "category": "system",
            "visibility": "private",
            "tags": [],
            "created_at": created_at,
            "updated_at": created_at,
            "reviewed": False,
            "user_review": None,
            "manually_added": False,
            "edited": False,
            "conversation_id": None,
            "data_protection_level": "standard",
        },
    }
    doc.update(overrides)
    return doc


def _request(**overrides: Any) -> V3ProjectionReadRequest:
    return V3ProjectionReadRequest(
        uid=UID,
        limit=2,
        expected_account_generation=ACCOUNT_GENERATION,
        cursor=None,
        offset=None,
        **overrides,
    )


def _delete_collection(db: Any, collection_path: str) -> None:
    for snap in db.collection(collection_path).stream():
        snap.reference.delete()


def _reset_fixture(db: firestore.Client) -> None:
    db.document(PATHS.v3_compatibility_projection_state).delete()
    _delete_collection(db, PATHS.v3_compatibility_projection_items)


def _write_items(db: Any, items: dict[str, dict[str, Any]]) -> None:
    for memory_id, item in items.items():
        db.collection(PATHS.v3_compatibility_projection_items).document(memory_id).set(item)


def _assert_failure(
    db: firestore.Client, reason: V3ProjectionFailureReason, request: V3ProjectionReadRequest | None = None
) -> None:
    try:
        read_v3_compatibility_projection_page(db_client=db, request=request or _request())
    except V3ProjectionReadError as exc:
        assert exc.reason == reason, (exc.reason, reason)
        return
    raise AssertionError(f"expected {reason.value}")


def _assert_ready_empty(db: Any) -> None:
    _reset_fixture(db)
    db.document(PATHS.v3_compatibility_projection_state).set(_state(empty_projection=True))
    page = read_v3_compatibility_projection_page(db_client=db, request=_request())
    assert page.items == []
    assert page.empty_projection is True


def _assert_fail_closed_cases(db: Any) -> None:
    _reset_fixture(db)
    db.document(PATHS.v3_compatibility_projection_state).set(_state())
    _assert_failure(
        db,
        V3ProjectionFailureReason.ACCOUNT_GENERATION_MISMATCH,
        _request(expected_account_generation=ACCOUNT_GENERATION + 1),
    )

    _reset_fixture(db)
    db.document(PATHS.v3_compatibility_projection_state).set(_state(projection_commit_id="old"))
    _assert_failure(db, V3ProjectionFailureReason.FENCE_MISMATCH)

    _reset_fixture(db)
    db.document(PATHS.v3_compatibility_projection_state).set(
        _state(freshness_fence_generation=PROJECTION_GENERATION - 1)
    )
    _assert_failure(db, V3ProjectionFailureReason.FENCE_MISMATCH)


def _assert_exclusions(db: Any) -> None:
    _reset_fixture(db)
    now = datetime(2026, 1, 4, tzinfo=timezone.utc)
    db.document(PATHS.v3_compatibility_projection_state).set(_state())
    _write_items(
        db,
        {
            "visible": _item("visible", now),
            "archive": _item("archive", now, archive=True),
            "tombstone": _item("tombstone", now, tombstoned=True),
            "stale": _item("stale", now, short_term_stale=True),
        },
    )
    page = read_v3_compatibility_projection_page(db_client=db, request=_request(limit=10))
    assert [item["id"] for item in page.items] == ["visible"]


def _assert_keyset(db: Any) -> None:
    _reset_fixture(db)
    t3 = datetime(2026, 1, 3, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db.document(PATHS.v3_compatibility_projection_state).set(_state())
    _write_items(
        db,
        {
            "a": _item("a", t1),
            "b": _item("b", t2),
            "c": _item("c", t2),
            "d": _item("d", t3),
        },
    )
    first = read_v3_compatibility_projection_page(db_client=db, request=_request(limit=2))
    second = read_v3_compatibility_projection_page(db_client=db, request=_request(limit=2, cursor=first.next_cursor))
    assert [item["id"] for item in first.items] == ["d", "c"]
    assert [item["id"] for item in second.items] == ["b", "a"]
    assert second.next_cursor is None


def main() -> int:
    _require_emulator()
    db = firestore.Client(project=PROJECT_ID)
    try:
        _assert_ready_empty(db)
        _assert_fail_closed_cases(db)
        _assert_exclusions(db)
        _assert_keyset(db)
    finally:
        _reset_fixture(db)
    print(
        "PASS: emulator Admin-context projection state/items reads proved ready-empty, generation mismatch, "
        "stale commit/fence, Archive/tombstone/stale Short-term exclusion, and two-page keyset ordering; "
        "no production Firestore, memory_items read, vector call, legacy fallback, router wiring, or writes outside emulator fixtures"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
