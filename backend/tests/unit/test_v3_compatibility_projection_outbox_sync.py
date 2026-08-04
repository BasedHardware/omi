from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from database.memory_collections import MemoryCollections
from database.memory_compatibility_projection import read_v3_compatibility_projection_page
from models.memory_evidence import SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.short_term_promotion import _canonical_outbox_side_effects
from utils.memory.v3.compatibility_projection_sync import (
    CompatibilityProjectionSyncError,
    v3_compatibility_projection_skip_reason,
)
from utils.memory.v3.projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3_COMPATIBILITY_PROJECTION_SOURCE,
    V3_COMPATIBILITY_PROJECTION_VERSION,
    V3ProjectionReadRequest,
)

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
UID = "uid-compat-outbox"
MEMORY_ID = "mem-compat"


class _Snapshot:
    def __init__(self, path: str, data: dict[str, Any] | None):
        self.id = path.rsplit("/", 1)[-1]
        self.exists = data is not None
        self._data = copy.deepcopy(data)

    def to_dict(self):
        return copy.deepcopy(self._data)


class _Document:
    def __init__(self, db: "_Db", path: str):
        self._db = db
        self._path = path

    def get(self, transaction=None):
        return _Snapshot(self._path, self._db.docs.get(self._path))

    def set(self, payload: dict[str, Any]):
        self._db.docs[self._path] = copy.deepcopy(payload)

    def delete(self):
        self._db.docs.pop(self._path, None)


class _Transaction:
    def __init__(self, db: "_Db"):
        self._db = db
        self._writes: list[tuple[str, str, dict[str, Any] | None]] = []

    def _begin(self):
        self._writes = []

    def set(self, ref: _Document, payload: dict[str, Any]):
        self._writes.append(("set", ref._path, copy.deepcopy(payload)))

    def delete(self, ref: _Document):
        self._writes.append(("delete", ref._path, None))

    def _commit(self):
        for operation, path, payload in self._writes:
            if operation == "delete":
                self._db.docs.pop(path, None)
            else:
                assert payload is not None
                self._db.docs[path] = payload

    def _rollback(self):
        self._writes = []

    def _clean_up(self):
        return None


class _Query:
    def __init__(self, db: "_Db", path: str, *, limit: int | None = None):
        self._db = db
        self._path = path
        self._limit = limit

    def order_by(self, *_args, **_kwargs):
        return self

    def start_after(self, _cursor):
        return self

    def limit(self, value: int):
        return _Query(self._db, self._path, limit=value)

    def stream(self):
        prefix = f"{self._path}/"
        rows = [_Snapshot(path, payload) for path, payload in self._db.docs.items() if path.startswith(prefix)]
        rows.sort(
            key=lambda row: (
                cast_datetime((row.to_dict() or {}).get("created_at")),
                row.id,
            ),
            reverse=True,
        )
        return rows[: self._limit] if self._limit is not None else rows


class _Db:
    def __init__(self, docs: dict[str, dict[str, Any]]):
        self.docs = copy.deepcopy(docs)

    def document(self, path: str):
        return _Document(self, path)

    def collection(self, path: str):
        return _Query(self, path)

    def transaction(self):
        return _Transaction(self)


def cast_datetime(value: object) -> datetime:
    return value if isinstance(value, datetime) else datetime.min.replace(tzinfo=timezone.utc)


def _projection_state() -> dict[str, Any]:
    return {
        "uid": UID,
        "schema_version": V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        "source": V3_COMPATIBILITY_PROJECTION_SOURCE,
        "ready": True,
        "account_generation": 7,
        "projection_generation": 7,
        "freshness_fence_generation": 7,
        "tombstone_fence_generation": 7,
        "vector_cleanup_fence_generation": 7,
        "source_commit_id": "head-enrollment",
        "projection_commit_id": "commit-head-enrollment",
        "source_evidence_fence": "head-head-enrollment",
        "projection_evidence_fence": "head-head-enrollment",
        "projection_version": V3_COMPATIBILITY_PROJECTION_VERSION,
        "source_version": "memory_state_head:4",
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
        "empty_projection": False,
    }


def _item(
    *,
    content: str = "Original durable preference",
    revision: int = 1,
    tier: MemoryLayer = MemoryLayer.long_term,
) -> MemoryItem:
    captured_at = NOW - timedelta(days=2)
    return MemoryItem(
        memory_id=MEMORY_ID,
        uid=UID,
        version=revision,
        tier=tier,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=True,
        captured_at=captured_at,
        updated_at=captured_at + timedelta(minutes=revision),
        expires_at=NOW + timedelta(days=28) if tier == MemoryLayer.short_term else None,
        ledger_commit_id=f"commit_{revision}",
        ledger_sequence=revision,
        item_revision=revision,
        content_hash=f"hash-{revision}",
        account_generation=7,
        promotion={
            "category": "interesting",
            "tags": ["preference"],
            "reviewed": True,
            "user_review": True,
        },
    )


def _read(db: _Db) -> list[dict[str, Any]]:
    return read_v3_compatibility_projection_page(
        db_client=cast(Any, db),
        request=V3ProjectionReadRequest(
            uid=UID,
            limit=10,
            expected_account_generation=7,
        ),
    ).items


@pytest.mark.parametrize(
    ("patch", "expected_reason"),
    [
        ({}, None),
        ({"tier": MemoryLayer.archive}, "not_default_tier"),
        ({"status": MemoryItemStatus.tombstoned}, "not_active"),
        ({"source_state": SourceState.tombstoned}, "source_not_active"),
        ({"sensitivity_labels": ["credential"]}, "restricted_sensitivity"),
        ({"promotion": {"user_review": False}}, "user_rejected"),
        ({"content": "  "}, "missing_content"),
        ({"archive": True}, "archived"),
        ({"deleted": True}, "deleted_or_tombstoned"),
        ({"user_review": False}, "user_rejected"),
        ({"restricted_sensitivity": True}, "restricted_sensitivity"),
    ],
)
def test_projection_eligibility_policy_covers_canonical_and_legacy_representations(patch, expected_reason):
    payload = {**_item().model_dump(mode="python"), **patch}
    assert v3_compatibility_projection_skip_reason(payload) == expected_reason


def test_normal_projection_callback_creates_then_updates_the_v3_read_model():
    paths = MemoryCollections(uid=UID)
    original_state = _projection_state()
    db = _Db({paths.v3_compatibility_projection_state: original_state})
    keyword_sync = MagicMock(return_value=True)
    side_effects = _canonical_outbox_side_effects(db_client=db)

    with patch("utils.memory.short_term_promotion.sync_atom_keyword_index_for_item", keyword_sync):
        assert side_effects.projection_upsert(_item(), 7) is True
        assert [row["content"] for row in _read(db)] == ["Original durable preference"]

        updated = _item(content="Updated durable preference", revision=2)
        assert side_effects.projection_upsert(updated, 7) is True

    rows = _read(db)
    assert [row["content"] for row in rows] == ["Updated durable preference"]
    assert rows[0]["updated_at"] == updated.updated_at
    assert rows[0]["memory_tier"] == MemoryLayer.long_term.value
    assert "evidence" not in rows[0]
    assert db.docs[paths.v3_compatibility_projection_state] == original_state
    assert keyword_sync.call_count == 2


def test_processed_short_term_is_compatibility_visible_without_becoming_a_keyword_atom():
    paths = MemoryCollections(uid=UID)
    db = _Db({paths.v3_compatibility_projection_state: _projection_state()})
    keyword_sync = MagicMock(return_value=True)
    side_effects = _canonical_outbox_side_effects(db_client=db)

    with patch("utils.memory.short_term_promotion.sync_atom_keyword_index_for_item", keyword_sync):
        short_term = _item(content="Fresh source-backed context", tier=MemoryLayer.short_term)
        assert side_effects.projection_upsert(short_term, 7) is True

    assert [row["memory_tier"] for row in _read(db)] == [MemoryLayer.short_term.value]
    keyword_sync.assert_called_once_with(short_term, db_client=db)


def test_normal_projection_delete_hides_v3_content_before_retryable_external_cleanup():
    paths = MemoryCollections(uid=UID)
    graph_assertion_path = f"users/{UID}/memory_graph_assertions/{MEMORY_ID}"
    db = _Db(
        {
            paths.v3_compatibility_projection_state: _projection_state(),
            graph_assertion_path: {"memory_id": MEMORY_ID},
        }
    )
    side_effects = _canonical_outbox_side_effects(db_client=db)
    with patch("utils.memory.short_term_promotion.sync_atom_keyword_index_for_item", return_value=True):
        assert side_effects.projection_upsert(_item(), 7) is True
    assert len(_read(db)) == 1

    kg_prune = MagicMock()
    review_purge = MagicMock()
    with (
        patch("utils.memory.short_term_promotion.delete_atom_keyword_doc", return_value=False),
        patch("utils.memory.short_term_promotion.kg_db.prune_memory_citations_from_kg", kg_prune),
        patch(
            "utils.memory.short_term_promotion.purge_stale_review_conflicts_for_memories",
            review_purge,
        ),
    ):
        assert side_effects.projection_delete(UID, MEMORY_ID, 7) is False

    assert _read(db) == []
    assert f"{paths.v3_compatibility_projection_items}/{MEMORY_ID}" not in db.docs
    assert graph_assertion_path not in db.docs
    kg_prune.assert_not_called()
    review_purge.assert_not_called()


@pytest.mark.parametrize(
    "state_patch",
    [
        None,
        {"account_generation": 6, "projection_generation": 6},
    ],
)
def test_projection_upsert_fails_closed_without_valid_enrollment_fences(state_patch):
    paths = MemoryCollections(uid=UID)
    docs: dict[str, dict[str, Any]] = {}
    if state_patch is not None:
        docs[paths.v3_compatibility_projection_state] = {**_projection_state(), **state_patch}
    db = _Db(docs)
    side_effects = _canonical_outbox_side_effects(db_client=db)

    with (
        patch("utils.memory.short_term_promotion.sync_atom_keyword_index_for_item", return_value=True),
        pytest.raises(CompatibilityProjectionSyncError),
    ):
        side_effects.projection_upsert(_item(), 7)

    assert f"{paths.v3_compatibility_projection_items}/{MEMORY_ID}" not in db.docs


def test_projection_upsert_remains_admitted_while_rebuild_convergence_is_pending():
    paths = MemoryCollections(uid=UID)
    state = {
        **_projection_state(),
        "ready": False,
        "writer_admission_ready": True,
        "write_convergence_complete": False,
        "delete_convergence_complete": False,
        "tombstone_convergence_complete": False,
    }
    db = _Db({paths.v3_compatibility_projection_state: state})
    side_effects = _canonical_outbox_side_effects(db_client=db)

    with patch("utils.memory.short_term_promotion.sync_atom_keyword_index_for_item", return_value=True):
        assert side_effects.projection_upsert(_item(), 7) is True

    assert f"{paths.v3_compatibility_projection_items}/{MEMORY_ID}" in db.docs


def test_stale_generation_delete_cannot_remove_a_new_generation_projection_row():
    paths = MemoryCollections(uid=UID)
    new_generation_state = {
        **_projection_state(),
        "account_generation": 8,
        "projection_generation": 8,
        "freshness_fence_generation": 8,
        "tombstone_fence_generation": 8,
        "vector_cleanup_fence_generation": 8,
    }
    item_path = f"{paths.v3_compatibility_projection_items}/{MEMORY_ID}"
    db = _Db(
        {
            paths.v3_compatibility_projection_state: new_generation_state,
            item_path: {"new_generation_private_content": True},
        }
    )
    side_effects = _canonical_outbox_side_effects(db_client=db)

    with pytest.raises(CompatibilityProjectionSyncError):
        side_effects.projection_delete(UID, MEMORY_ID, 7)

    assert db.docs[item_path] == {"new_generation_private_content": True}
