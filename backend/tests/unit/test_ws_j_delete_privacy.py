"""WS-J delete/privacy matrix tests — vectors, account delete, cascade characterization."""

from __future__ import annotations

import ast
import hashlib
import importlib
import os
import re
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONVERSATIONS_ROUTER_PATH = BACKEND_DIR / "routers" / "conversations.py"

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_db_client_mod = types.ModuleType("database._client")
_db_client_mod.db = MagicMock()


def _document_id_from_seed(seed: str) -> str:
    seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=seed_hash[:16], version=4))


_db_client_mod.document_id_from_seed = _document_id_from_seed

from tests.unit.memory_import_isolation import (
    ensure_utils_memory_packages_importable,
    install_database_client_stub,
    install_ws_j_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _ws_j_import_isolation():
    saved = snapshot_sys_modules(["database._client"])
    install_database_client_stub()
    touched = install_ws_j_heavy_import_stubs()
    saved.update(snapshot_sys_modules(touched))
    from utils.memory.memory_service import MemoryService

    globals()["MemoryService"] = MemoryService
    yield
    restore_sys_modules(saved)


def _install_heavy_import_stubs():
    install_ws_j_heavy_import_stubs()


ensure_utils_memory_packages_importable(str(BACKEND_DIR))
from models.memories import MemoryCategory
from models.memory_apply import MemoryControlState
from models.memory_review import build_memory_review_conflict
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryTier, ProcessingState
from database.memory_apply_store import CanonicalReviewResolutionConflict
from database.memory_vector_metadata import canonical_memory_provider_id
from utils.memory.canonical_memory_adapter import (
    delete_all_canonical_memories,
    delete_canonical_memory,
    extraction_memory_id,
    purge_canonical_derived_user_data,
    read_canonical_memories,
    resolve_canonical_memory_review,
    retract_conversation_sourced_memories,
    update_canonical_memory_content,
    update_canonical_memory_product_fields,
    update_canonical_memory_visibility,
    write_canonical_extraction_memory,
)
from utils.memory.memory_system import MemorySystem, resolve_memory_system

from database import document_store
from tests.store_fakes import FakeDocumentStore


def _refresh_canonical_memory_adapter_runtime() -> None:
    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    globals().update(
        {
            "delete_all_canonical_memories": canonical_adapter.delete_all_canonical_memories,
            "delete_canonical_memory": canonical_adapter.delete_canonical_memory,
            "extraction_memory_id": canonical_adapter.extraction_memory_id,
            "purge_canonical_derived_user_data": canonical_adapter.purge_canonical_derived_user_data,
            "read_canonical_memories": canonical_adapter.read_canonical_memories,
            "resolve_canonical_memory_review": canonical_adapter.resolve_canonical_memory_review,
            "retract_conversation_sourced_memories": canonical_adapter.retract_conversation_sourced_memories,
            "update_canonical_memory_content": canonical_adapter.update_canonical_memory_content,
            "update_canonical_memory_product_fields": canonical_adapter.update_canonical_memory_product_fields,
            "update_canonical_memory_visibility": canonical_adapter.update_canonical_memory_visibility,
            "write_canonical_extraction_memory": canonical_adapter.write_canonical_extraction_memory,
        }
    )


@pytest.fixture(autouse=True)
def _clear_canonical_env(monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    _refresh_canonical_memory_adapter_runtime()
    clear_canonical_cohort(monkeypatch)


@pytest.fixture(autouse=True)
def _ensure_vector_db_delete_by_id_stub():
    """Re-apply stub attrs when other test modules replace ``database.vector_db`` at collection time."""
    _install_heavy_import_stubs()


LEGACY_UID = "uid-legacy-ws-j"


def _legacy_db_with_control(uid: str = LEGACY_UID) -> "_FakeDb":
    """Default memory_control/state with no ``memory_system=canonical`` — real resolver → LEGACY."""
    return _FakeDb(
        {
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json"),
        }
    )


def _canonical_doc_paths(db: "_FakeDb", uid: str) -> set[str]:
    prefixes = (
        f"users/{uid}/memory_items/",
        f"users/{uid}/memory_evidence/",
        f"users/{uid}/memory_outbox/",
        f"users/{uid}/memory_operations/",
    )
    return {path for path in db.docs if any(path.startswith(prefix) for prefix in prefixes)}


class _Snapshot:
    def __init__(self, data=None, *, exists=True, doc_id=None, reference=None):
        self._data = data
        self.exists = exists
        self.id = doc_id
        self.reference = reference

    def to_dict(self):
        return self._data


class _FakeTransaction:
    def __init__(self, db):
        self._db = db
        self.sets = []
        self.deletes = []
        self._read_only = False
        self._max_attempts = 1
        self._id = None

    def set(self, ref, data):
        self.sets.append((ref.path, data))

    def delete(self, ref):
        self.deletes.append(ref.path)

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self.sets = []
        self.deletes = []
        self._id = retry_id or "txn-1"

    def _commit(self):
        for path, data in self.sets:
            self._db.docs[path] = data
        for path in self.deletes:
            self._db.docs.pop(path, None)

    def _rollback(self):
        self._id = None
        self.sets = []
        self.deletes = []


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def get(self, transaction=None):
        if self.path not in self._db.docs:
            return _Snapshot(None, exists=False, doc_id=self.path.rsplit("/", 1)[-1], reference=self)
        return _Snapshot(
            self._db.docs[self.path],
            exists=True,
            doc_id=self.path.rsplit("/", 1)[-1],
            reference=self,
        )

    def set(self, data, merge=False):
        if merge and isinstance(self._db.docs.get(self.path), dict):
            self._db.docs[self.path].update(data)
            return
        self._db.docs[self.path] = data

    def update(self, data):
        self._db.docs[self.path].update(data)


class _CollectionRef:
    def __init__(self, db, path, *, filters=(), order_fields=(), limit_count=None, cursor=None):
        self._db = db
        self.path = path
        self._filters = tuple(filters)
        self._order_fields = tuple(order_fields)
        self._limit_count = limit_count
        self._cursor = cursor

    def where(self, field_path=None, op_string=None, value=None, *, filter=None):
        if filter is not None:
            field_path = filter.field_path
            op_string = filter.op_string
            value = filter.value
        return _CollectionRef(
            self._db,
            self.path,
            filters=(*self._filters, (field_path, op_string, value)),
            order_fields=self._order_fields,
            limit_count=self._limit_count,
            cursor=self._cursor,
        )

    def order_by(self, field_path):
        return _CollectionRef(
            self._db,
            self.path,
            filters=self._filters,
            order_fields=(*self._order_fields, field_path),
            limit_count=self._limit_count,
            cursor=self._cursor,
        )

    def limit(self, limit_count):
        return _CollectionRef(
            self._db,
            self.path,
            filters=self._filters,
            order_fields=self._order_fields,
            limit_count=limit_count,
            cursor=self._cursor,
        )

    def start_after(self, snapshot):
        return _CollectionRef(
            self._db,
            self.path,
            filters=self._filters,
            order_fields=self._order_fields,
            limit_count=self._limit_count,
            cursor=snapshot,
        )

    def stream(self):
        prefix = f"{self.path}/"
        rows = []
        for path, data in sorted(self._db.docs.items()):
            if not path.startswith(prefix) or "/" in path[len(prefix) :]:
                continue
            if not all(self._matches(data, field, operator, expected) for field, operator, expected in self._filters):
                continue
            doc_id = path[len(prefix) :]
            rows.append((self._sort_key(data, doc_id), path, data))
        rows.sort(key=lambda row: row[0])
        if self._cursor is not None:
            cursor_data = self._cursor.to_dict() or {}
            cursor_key = self._sort_key(cursor_data, self._cursor.id)
            rows = [row for row in rows if row[0] > cursor_key]
        if self._limit_count is not None:
            rows = rows[: self._limit_count]
        return [
            _Snapshot(
                data,
                exists=True,
                doc_id=path[len(prefix) :],
                reference=_DocRef(self._db, path),
            )
            for _sort_key, path, data in rows
        ]

    @staticmethod
    def _nested_value(data, field_path):
        current = data
        for part in str(field_path).split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @classmethod
    def _matches(cls, data, field, operator, expected):
        actual = cls._nested_value(data, field)
        if operator == "==":
            return actual == expected
        if operator == "in":
            return actual in expected
        if operator == "array_contains_any":
            return isinstance(actual, list) and bool(set(actual).intersection(expected))
        if operator == "array_contains":
            return isinstance(actual, list) and expected in actual
        if operator == "<=":
            return actual is not None and actual <= expected
        raise AssertionError(f"unsupported fake Firestore operator {operator}")

    def _sort_key(self, data, doc_id):
        values = [
            doc_id if field_path == "__name__" else self._nested_value(data, field_path)
            for field_path in self._order_fields
        ]
        return tuple([*values, doc_id] if "__name__" not in self._order_fields else values)


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.transaction_obj = _FakeTransaction(self)

    def transaction(self):
        return self.transaction_obj

    def document(self, path):
        return _DocRef(self, path)

    def collection(self, path):
        return _CollectionRef(self, path)


def _trusted_account_generation():
    return SimpleNamespace(
        account_generation=1,
        head_commit_id="head0",
        read_error_reason=None,
    )


def _mark_account_deletion_fenced(db, uid: str) -> None:
    db.docs[f"account_deletions/{uid}"] = {"wipe_status": "running"}


def _fence_reader_from(db):
    """Read the account-deletion fence from the seeded backing dict.

    ``database.account_deletion_projection_fence.read_account_deletion_projection_fence`` still reads
    through an injected Firestore-shaped ``db_client`` (it is not one of the port-migrated modules),
    while the migrated ``canonical_memory_adapter`` now calls it without a client. Route the adapter's
    call through the fake's backing dict so the fence still honours the doc seeded by
    ``_mark_account_deletion_fenced`` — keeping the negative path (no active fence → refusal) real.
    """
    from database.account_deletion_policy import account_deletion_blocks_access
    from database.account_deletion_projection_fence import AccountDeletionProjectionFence

    def _read(uid, **_):
        payload = db.docs.get(f"account_deletions/{uid}") or {}
        raw_status = payload.get("wipe_status")
        status = raw_status.strip() if isinstance(raw_status, str) and raw_status.strip() else None
        # Mirror read_account_deletion_projection_fence exactly: the fence blocks unless the status
        # explicitly restores access (open-ended policy, not a finite status set).
        return AccountDeletionProjectionFence(
            status=status,
            blocks_projection_writes=account_deletion_blocks_access(status),
        )

    return _read


def _sample_memory_payload(*, uid: str, conversation_id: str, content: str) -> dict:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    evidence_id = "ev_ws_j_1"
    memory_id = extraction_memory_id(uid=uid, source_id=conversation_id, content=content)
    return {
        "id": memory_id,
        "uid": uid,
        "content": content,
        "conversation_id": conversation_id,
        "category": MemoryCategory.interesting.value,
        "created_at": now,
        "updated_at": now,
        "tags": [],
        "manually_added": False,
        "reviewed": False,
        "visibility": "private",
        "evidence": [
            {
                "evidence_id": evidence_id,
                "source_id": conversation_id,
                "source_type": "conversation",
                "source_signal": "transcription",
                "extractor_id": "new_memories_extractor",
                "extractor_version": "v1",
                "artifact_ref": {},
                "capture_confidence": 0.5,
                "independence_group": conversation_id,
                "redaction_status": "active",
                "created_at": now,
            }
        ],
    }


def _seed_canonical_review(db_client: "_FakeDb", uid: str, memory_id: str) -> str:
    item = MemoryItem.model_validate(db_client.docs[f"users/{uid}/memory_items/{memory_id}"])
    review = build_memory_review_conflict(
        fact={"id": memory_id, "content": item.content, "veracity": 0.4, "importance": 0.5},
        conflict_with=[],
        authority="canonical_memory",
        source_commit_id=item.ledger_commit_id,
        source_item_revision=item.item_revision,
        source_content_hash=item.content_hash,
        source_short_term_id=memory_id,
        now=item.updated_at,
    )
    db_client.docs[f"users/{uid}/memory_review_queue/{review['review_id']}"] = review
    return review["review_id"]


@pytest.fixture
def canonical_db(monkeypatch):
    uid = "uid-canonical-ws-j"
    db = _FakeDb(
        {
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json"),
        }
    )
    # document_store now reads/writes through the neutral storage port (WP2, ADR-0022), not through
    # the injected Firestore-shaped fake. Point its ``_store`` seam at a FakeDocumentStore sharing the
    # fake's backing dict so seeded data and writes stay consistent between the two.
    monkeypatch.setattr(document_store, "_store", lambda: FakeDocumentStore(backing=db.docs))
    monkeypatch.setattr("database.memory_apply_store._store", lambda: FakeDocumentStore(backing=db.docs))
    monkeypatch.setattr("database.knowledge_graph._store", lambda: FakeDocumentStore(backing=db.docs))
    monkeypatch.setattr("database.review_queue._store", lambda: FakeDocumentStore(backing=db.docs))
    # The indexed source-cohort reads (``fetch_authoritative_product_memory_items_for_source`` used by
    # retract) go through this module's own ``_store`` seam (``get_document_store()``), not through
    # ``document_store``. Point it at the same backing dict so retract sees the seeded items.
    monkeypatch.setattr(
        "utils.memory.product_memory_read_service._store", lambda: FakeDocumentStore(backing=db.docs)
    )
    monkeypatch.setattr(
        "utils.memory.v3.compatibility_projection_sync._store", lambda: FakeDocumentStore(backing=db.docs)
    )
    monkeypatch.setattr(
        "database.memory_compatibility_projection._store", lambda: FakeDocumentStore(backing=db.docs)
    )
    return db


def test_external_projection_id_is_deterministic_and_user_scoped():
    uid = "uid-1"
    conversation_id = "conv-1"
    content = "User likes hiking"
    memory_id = extraction_memory_id(uid=uid, source_id=conversation_id, content=content)

    provider_once = canonical_memory_provider_id(uid, memory_id)
    provider_twice = canonical_memory_provider_id(uid, memory_id)
    assert provider_once == provider_twice
    assert provider_once != canonical_memory_provider_id("uid-2", memory_id)
    assert provider_once != memory_id
    assert memory_id.startswith("mem_")
    assert provider_once.startswith("memproj:")

    legacy_vector_id = f"{uid}-{memory_id}"
    assert provider_once != legacy_vector_id


def test_canonical_account_delete_purge_emits_user_scoped_vector_outbox(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-acct"
    content = "Canonical fact for account delete"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    _mark_account_deletion_fenced(canonical_db, uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_account_deletion_projection_fence",
        _fence_reader_from(canonical_db),
    )

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.resolve_memory_system",
        lambda uid, **_: MemorySystem.CANONICAL,
    )

    canonical_delete_calls = []

    def _fake_delete_canonical(delete_uid, memory_id=None):
        canonical_delete_calls.append((delete_uid, memory_id))
        return True

    monkeypatch.setattr(
        "database.vector_db.delete_canonical_memory_vectors",
        _fake_delete_canonical,
        raising=False,
    )
    delete_graph = MagicMock()
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.kg_db.delete_knowledge_graph",
        delete_graph,
    )

    write_canonical_extraction_memory(uid, payload)
    memory_id = payload["id"]
    item_path = f"users/{uid}/memory_items/{memory_id}"
    assert canonical_db.docs[item_path]["status"] == MemoryItemStatus.active.value

    result = purge_canonical_derived_user_data(uid)
    assert result["purged"] is True
    assert memory_id in result["memory_ids"]
    expected_vector_id = canonical_memory_provider_id(uid, memory_id)
    assert expected_vector_id in result["vector_ids"]
    assert canonical_delete_calls == [(uid, None)]
    delete_graph.assert_called_once_with(uid)

    outbox_paths = [path for path in canonical_db.docs if f"users/{uid}/memory_outbox/" in path]
    assert outbox_paths, "account delete should enqueue durable vector purge outbox records"
    purge_record = next(
        canonical_db.docs[path]
        for path in outbox_paths
        if canonical_db.docs[path].get("reason") == "account_delete_canonical_purge"
    )
    assert purge_record["vector_id"] == expected_vector_id


def test_canonical_account_delete_purge_raises_when_provider_is_unavailable(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-acct-partial"
    content = "Canonical fact for partial account delete"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    _mark_account_deletion_fenced(canonical_db, uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_account_deletion_projection_fence",
        _fence_reader_from(canonical_db),
    )

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.resolve_memory_system",
        lambda uid, **_: MemorySystem.CANONICAL,
    )
    monkeypatch.setattr(
        "database.vector_db.delete_canonical_memory_vectors",
        lambda delete_uid, memory_id=None: False,
        raising=False,
    )

    write_canonical_extraction_memory(uid, payload)

    with pytest.raises(RuntimeError, match="canonical vector purge could not reach the provider"):
        purge_canonical_derived_user_data(uid)


def test_canonical_account_delete_purge_waits_for_projection_lease(monkeypatch, canonical_db):
    uid = "uid-canonical-account-delete-lease"
    _mark_account_deletion_fenced(canonical_db, uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_account_deletion_projection_fence",
        _fence_reader_from(canonical_db),
    )
    canonical_db.docs[f"users/{uid}/memory_outbox/leased-vector"] = {
        "event_type": "vector_sync",
        "status": "processing",
    }
    delete_canonical = MagicMock(return_value=True)
    monkeypatch.setattr(
        "database.vector_db.delete_canonical_memory_vectors",
        delete_canonical,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="leased projection work drains"):
        purge_canonical_derived_user_data(uid)

    delete_canonical.assert_not_called()


def test_account_delete_purges_user_scoped_rows_even_without_canonical_items(monkeypatch):
    db = _legacy_db_with_control()
    monkeypatch.setattr(document_store, "_store", lambda: FakeDocumentStore(backing=db.docs))
    monkeypatch.setattr("database.memory_apply_store._store", lambda: FakeDocumentStore(backing=db.docs))
    monkeypatch.setattr("database.knowledge_graph._store", lambda: FakeDocumentStore(backing=db.docs))
    monkeypatch.setattr("database.review_queue._store", lambda: FakeDocumentStore(backing=db.docs))
    _mark_account_deletion_fenced(db, LEGACY_UID)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_account_deletion_projection_fence",
        _fence_reader_from(db),
    )
    assert resolve_memory_system(LEGACY_UID) == MemorySystem.LEGACY

    delete_canonical = MagicMock(return_value=True)
    monkeypatch.setattr(
        "database.vector_db.delete_canonical_memory_vectors",
        delete_canonical,
        raising=False,
    )
    keyword_purge = MagicMock(return_value=0)
    monkeypatch.setattr(
        "utils.memory.atom_keyword_index.purge_user_atom_keyword_index",
        keyword_purge,
    )
    graph_purge = MagicMock()
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.kg_db.delete_knowledge_graph",
        graph_purge,
    )
    before = set(db.docs.keys())

    result = purge_canonical_derived_user_data(LEGACY_UID)

    assert result["purged"] is True
    assert result["reason"] == "user_scoped_provider_purge"
    assert result["memory_ids"] == []
    delete_canonical.assert_called_once_with(LEGACY_UID)
    keyword_purge.assert_called_once_with(LEGACY_UID, force=True, raise_on_failure=True)
    graph_purge.assert_called_once_with(LEGACY_UID)
    assert set(db.docs.keys()) == before
    assert not _canonical_doc_paths(db, LEGACY_UID)


def test_legacy_purge_derived_user_data_still_purges_legacy_vectors(monkeypatch):
    """Canonical provider purge is inert for a real legacy uid; the legacy batch path stays separate."""
    db = _legacy_db_with_control()
    monkeypatch.setattr(document_store, "_store", lambda: FakeDocumentStore(backing=db.docs))
    monkeypatch.setattr("database.memory_apply_store._store", lambda: FakeDocumentStore(backing=db.docs))
    monkeypatch.setattr("database.knowledge_graph._store", lambda: FakeDocumentStore(backing=db.docs))
    monkeypatch.setattr("database.review_queue._store", lambda: FakeDocumentStore(backing=db.docs))
    _mark_account_deletion_fenced(db, LEGACY_UID)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_account_deletion_projection_fence",
        _fence_reader_from(db),
    )
    assert resolve_memory_system(LEGACY_UID) == MemorySystem.LEGACY

    delete_canonical = MagicMock(return_value=True)
    legacy_batch = MagicMock()
    monkeypatch.setattr(
        "database.vector_db.delete_canonical_memory_vectors",
        delete_canonical,
        raising=False,
    )
    monkeypatch.setattr(
        "database.vector_db.delete_memory_vectors_batch",
        legacy_batch,
        raising=False,
    )
    monkeypatch.setattr(
        "utils.memory.atom_keyword_index.purge_user_atom_keyword_index",
        MagicMock(return_value=0),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.kg_db.delete_knowledge_graph",
        MagicMock(),
    )
    before = set(db.docs.keys())

    purge_canonical_derived_user_data(LEGACY_UID)

    delete_canonical.assert_called_once_with(LEGACY_UID)
    assert set(db.docs.keys()) == before

    import database.vector_db as vector_db

    vector_db.delete_memory_vectors_batch(LEGACY_UID, ["legacy-m1"])
    legacy_batch.assert_called_once_with(LEGACY_UID, ["legacy-m1"])


def test_memory_service_retract_conversation_memories_is_noop_for_legacy():
    db = _legacy_db_with_control()
    assert resolve_memory_system(LEGACY_UID) == MemorySystem.LEGACY
    before = set(db.docs.keys())

    result = MemoryService().retract_conversation_memories(LEGACY_UID, "conv-x")

    assert result is None
    assert set(db.docs.keys()) == before
    assert not _canonical_doc_paths(db, LEGACY_UID)


def test_conversation_delete_cascade_tombstones_canonical_and_emits_durable_deletes(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-cascade"
    content = "Fact sourced from conversation"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload)
    retract_result = retract_conversation_sourced_memories(uid, conversation_id)

    assert retract_result["retracted_memory_ids"] == [memory_id]
    tombstoned = canonical_db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert tombstoned["status"] == MemoryItemStatus.tombstoned.value
    assert tombstoned["evidence"][0]["source_state"] == "tombstoned"

    outbox_paths = [path for path in canonical_db.docs if "memory_outbox" in path]
    assert outbox_paths
    delete_events = [
        canonical_db.docs[path]
        for path in outbox_paths
        if canonical_db.docs[path].get("payload", {}).get("reason") == "conversation_reprocess_retract"
    ]
    assert {event["event_type"] for event in delete_events} == {"projection_sync", "vector_sync"}
    assert all(event["memory_id"] == memory_id for event in delete_events)
    assert all(event["payload"]["action"] == "delete" for event in delete_events)
    assert all(event["payload"]["item_revision"] == tombstoned["item_revision"] for event in delete_events)
    assert all(event["payload"]["content_hash"] == tombstoned["content_hash"] for event in delete_events)
    assert all(isinstance(event["available_at"], datetime) for event in delete_events)


def test_conversation_full_retract_journals_every_source_item_in_one_commit(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-atomic-full-retract"
    first = _sample_memory_payload(
        uid=uid,
        conversation_id=conversation_id,
        content="Project Mercury meets on Tuesdays",
    )
    second = _sample_memory_payload(
        uid=uid,
        conversation_id=conversation_id,
        content="Project Mercury uses a written agenda",
    )
    second["evidence"][0]["evidence_id"] = "ev_ws_j_atomic_retract_second"

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    first_id = write_canonical_extraction_memory(uid, first)
    second_id = write_canonical_extraction_memory(uid, second)
    result = retract_conversation_sourced_memories(uid, conversation_id)

    assert set(result["retracted_memory_ids"]) == {first_id, second_id}
    assert set(result["tombstoned_evidence_ids"]) == {
        first["evidence"][0]["evidence_id"],
        second["evidence"][0]["evidence_id"],
    }
    tombstoned = [canonical_db.docs[f"users/{uid}/memory_items/{memory_id}"] for memory_id in (first_id, second_id)]
    assert all(item["status"] == MemoryItemStatus.tombstoned.value for item in tombstoned)
    assert len({item["ledger_commit_id"] for item in tombstoned}) == 1
    replacement_operations = [
        document
        for path, document in canonical_db.docs.items()
        if path.startswith(f"users/{uid}/memory_operations/") and document.get("operation_type") == "source_replacement"
    ]
    replacement_receipts = [
        document
        for path, document in canonical_db.docs.items()
        if path.startswith(f"users/{uid}/memory_source_replacements/")
    ]
    assert len(replacement_operations) == 1
    assert len(replacement_receipts) == 1


@pytest.mark.parametrize(
    "retained_status",
    [MemoryItemStatus.hidden, MemoryItemStatus.superseded],
)
def test_conversation_full_retract_closes_non_active_source_items_and_evidence(
    monkeypatch,
    canonical_db,
    retained_status,
):
    uid = "uid-canonical-ws-j"
    conversation_id = f"conv-full-retract-{retained_status.value}"
    payload = _sample_memory_payload(
        uid=uid,
        conversation_id=conversation_id,
        content=f"Private retained {retained_status.value} source fact",
    )
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    canonical_db.docs[item_path]["status"] = retained_status.value

    result = retract_conversation_sourced_memories(uid, conversation_id)

    assert result["retracted_memory_ids"] == [memory_id]
    assert result["tombstoned_evidence_ids"] == [payload["evidence"][0]["evidence_id"]]
    assert canonical_db.docs[item_path]["status"] == MemoryItemStatus.tombstoned.value
    assert canonical_db.docs[item_path]["content"] is None
    evidence_path = f"users/{uid}/memory_evidence/{payload['evidence'][0]['evidence_id']}"
    assert canonical_db.docs[evidence_path]["source_state"] == "tombstoned"


def test_conversation_delete_cascade_deletes_canonical_vector_immediately(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-cascade-vector"
    content = "Fact sourced from conversation with vector"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    deleted_vectors = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.delete_canonical_memory_vector",
        lambda u, mid: deleted_vectors.append((u, mid)),
    )

    write_canonical_extraction_memory(uid, payload)
    retract_conversation_sourced_memories(uid, conversation_id)

    assert deleted_vectors == [(uid, memory_id)]


def test_delete_canonical_memory_removes_v3_compatibility_projection_immediately(monkeypatch, canonical_db):
    from database.memory_collections import MemoryCollections

    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-delete-v3-projection",
        content="Private compatibility projection fact",
    )
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload)
    projection_path = f"{MemoryCollections(uid=uid).v3_compatibility_projection_items}/{memory_id}"
    canonical_db.docs[projection_path] = {"uid": uid, "memory_id": memory_id}

    delete_canonical_memory(uid, memory_id)

    assert projection_path not in canonical_db.docs


def test_retract_calls_kg_invalidation_hook(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-kg"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content="KG defer hook")

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    kg_calls = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction",
        lambda u, ids, **kwargs: kg_calls.append((u, list(ids))),
    )

    write_canonical_extraction_memory(uid, payload)
    retract_conversation_sourced_memories(uid, conversation_id)
    assert kg_calls
    assert kg_calls[0][0] == uid
    assert payload["id"] in kg_calls[0][1]


def test_delete_canonical_memory_calls_kg_invalidation_hook(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-delete-kg"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content="Delete KG hook")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    kg_calls = []
    deleted_vectors = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction",
        lambda u, ids, **kwargs: kg_calls.append((u, list(ids))),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.delete_canonical_memory_vector",
        lambda u, mid: deleted_vectors.append((u, mid)),
    )

    write_canonical_extraction_memory(uid, payload)
    delete_canonical_memory(uid, memory_id)

    assert kg_calls == [(uid, [memory_id])]
    assert deleted_vectors == [(uid, memory_id)]
    tombstoned = canonical_db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert tombstoned["status"] == MemoryItemStatus.tombstoned.value


def test_delete_canonical_survivor_tombstones_active_alias_lineage(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    observed_at = datetime(2026, 6, 2, tzinfo=timezone.utc)
    survivor_payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-lineage-survivor",
        content="Project Beacon uses weekly planning",
    )
    alias_payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-lineage-alias",
        content="Fresh duplicate: Project Beacon uses weekly planning",
    )
    alias_payload["evidence"][0]["evidence_id"] = "ev_ws_j_alias"

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    deleted_vectors = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.delete_canonical_memory_vector",
        lambda user_id, memory_id: deleted_vectors.append((user_id, memory_id)) or True,
    )
    monkeypatch.setattr("utils.memory.atom_keyword_index.delete_atom_keyword_doc", lambda *_, **__: True)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.purge_stale_review_conflicts_for_memories",
        lambda *_, **__: True,
    )
    kg_calls = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction",
        lambda user_id, memory_ids, **_: kg_calls.append((user_id, list(memory_ids))),
    )

    survivor_id = write_canonical_extraction_memory(uid, survivor_payload)
    alias_id = write_canonical_extraction_memory(uid, alias_payload)
    survivor_path = f"users/{uid}/memory_items/{survivor_id}"
    alias_path = f"users/{uid}/memory_items/{alias_id}"
    canonical_db.docs[survivor_path].update(
        {
            "canonical_memory_id": survivor_id,
            "tier": MemoryTier.long_term.value,
            "processing_state": ProcessingState.processed.value,
            "expires_at": None,
            "ledger_commit_id": "commit-lineage-survivor",
            "ledger_sequence": 1,
        }
    )
    canonical_db.docs[alias_path].update(
        {
            "canonical_memory_id": survivor_id,
            "processing_state": ProcessingState.processed.value,
        }
    )

    before = read_canonical_memories(uid, now=observed_at)
    assert [memory.id for memory in before] == [survivor_id]

    delete_canonical_memory(uid, survivor_id)

    assert canonical_db.docs[survivor_path]["status"] == MemoryItemStatus.tombstoned.value
    assert canonical_db.docs[alias_path]["status"] == MemoryItemStatus.tombstoned.value
    assert read_canonical_memories(uid, now=observed_at) == []
    assert set(deleted_vectors) == {(uid, survivor_id), (uid, alias_id)}
    assert kg_calls == [(uid, sorted([survivor_id, alias_id]))]


def test_delete_canonical_survivor_tombstones_superseded_alias_lineage(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    survivor_payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-superseded-lineage-survivor",
        content="Project Atlas has a Friday review",
    )
    alias_payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-superseded-lineage-alias",
        content="Project Atlas reviews progress every Friday",
    )
    alias_payload["evidence"][0]["evidence_id"] = "ev_ws_j_superseded_alias"

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter._run_immediate_privacy_cleanup",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.purge_stale_review_conflicts_for_memories",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction",
        lambda *_args, **_kwargs: None,
    )

    survivor_id = write_canonical_extraction_memory(uid, survivor_payload)
    alias_id = write_canonical_extraction_memory(uid, alias_payload)
    survivor_path = f"users/{uid}/memory_items/{survivor_id}"
    alias_path = f"users/{uid}/memory_items/{alias_id}"
    canonical_db.docs[survivor_path]["canonical_memory_id"] = survivor_id
    canonical_db.docs[alias_path].update(
        {
            "status": MemoryItemStatus.superseded.value,
            "superseded_by": survivor_id,
        }
    )

    delete_canonical_memory(uid, survivor_id)

    assert canonical_db.docs[survivor_path]["status"] == MemoryItemStatus.tombstoned.value
    assert canonical_db.docs[survivor_path]["content"] is None
    assert canonical_db.docs[alias_path]["status"] == MemoryItemStatus.tombstoned.value
    assert canonical_db.docs[alias_path]["content"] is None


def test_privacy_delete_rescans_lineage_when_control_changes(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    survivor_payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-racing-lineage-survivor",
        content="Project Aurora has a weekly checkpoint",
    )
    alias_payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-racing-lineage-alias",
        content="Project Aurora runs a weekly checkpoint",
    )
    alias_payload["evidence"][0]["evidence_id"] = "ev_ws_j_racing_alias"

    survivor_id = write_canonical_extraction_memory(uid, survivor_payload)
    alias_id = write_canonical_extraction_memory(uid, alias_payload)
    survivor_path = f"users/{uid}/memory_items/{survivor_id}"
    alias_path = f"users/{uid}/memory_items/{alias_id}"
    canonical_db.docs[survivor_path]["canonical_memory_id"] = survivor_id
    canonical_db.docs[alias_path]["canonical_memory_id"] = survivor_id
    survivor = MemoryItem.model_validate(canonical_db.docs[survivor_path])
    alias = MemoryItem.model_validate(canonical_db.docs[alias_path])

    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    observed = canonical_adapter._read_replacement_control(uid)
    changed = observed.model_copy(
        update={
            "head_commit_id": "head-after-racing-alias",
            "commit_sequence": observed.commit_sequence + 1,
        }
    )
    control_read = MagicMock(side_effect=[observed, changed, changed, changed])
    lineage_scan = MagicMock(side_effect=[[survivor], [survivor, alias]])
    tombstone_store = MagicMock(return_value=SimpleNamespace(memory_items=[survivor, alias]))
    monkeypatch.setattr(canonical_adapter, "_read_replacement_control", control_read)
    monkeypatch.setattr(
        canonical_adapter,
        "fetch_authoritative_product_memory_items",
        lineage_scan,
    )
    monkeypatch.setattr(
        canonical_adapter,
        "tombstone_memory_items_firestore",
        tombstone_store,
    )

    deleted = canonical_adapter._tombstone_memory_items_transaction(
        uid,
        [survivor_id],
        reason="canonical_memory_delete",
        expand_lineages=True,
    )

    assert [item.memory_id for item in deleted] == [survivor_id, alias_id]
    assert control_read.call_count == 4
    assert lineage_scan.call_count == 2
    tombstone_store.assert_called_once()
    assert tombstone_store.call_args.kwargs["observed_control"] == changed
    assert {item.memory_id for item in tombstone_store.call_args.kwargs["expected_items"]} == {survivor_id, alias_id}


def test_delete_remains_durable_when_every_immediate_projection_cleanup_fails(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-delete-projection-failure",
        content="Delete must survive provider failure",
    )
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    def fail(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("utils.memory.canonical_memory_adapter.delete_canonical_memory_vector", fail)
    monkeypatch.setattr("utils.memory.atom_keyword_index.delete_atom_keyword_doc", fail)
    monkeypatch.setattr(
        "utils.memory.v3.compatibility_projection_sync.delete_v3_compatibility_projection_item",
        fail,
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.purge_stale_review_conflicts_for_memories",
        fail,
    )
    monkeypatch.setattr("utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction", fail)

    write_canonical_extraction_memory(uid, payload)
    delete_canonical_memory(uid, memory_id)

    tombstoned = canonical_db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert tombstoned["status"] == MemoryItemStatus.tombstoned.value
    events = [
        record
        for path, record in canonical_db.docs.items()
        if path.startswith(f"users/{uid}/memory_outbox/")
        and record.get("memory_id") == memory_id
        and record.get("payload", {}).get("reason") == "canonical_memory_delete"
    ]
    assert {event["event_type"] for event in events} == {"projection_sync", "vector_sync"}
    assert all(event["status"] == "pending" for event in events)
    assert all(isinstance(event["available_at"], datetime) for event in events)


def test_update_canonical_visibility_validates_before_persisting(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(uid=uid, conversation_id="conv-invalid-visibility", content="Visibility invariant")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    before = dict(canonical_db.docs[item_path])

    with pytest.raises(ValueError, match="visibility"):
        update_canonical_memory_visibility(uid, memory_id, "friends")

    assert canonical_db.docs[item_path] == before


def test_update_canonical_visibility_commits_through_apply_and_outbox(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-visibility"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content="Visibility side effect")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter._persist_memory_item",
        lambda *_args, **_kwargs: pytest.fail("ordinary visibility mutation bypassed apply"),
    )

    updated = update_canonical_memory_visibility(uid, memory_id, "public")

    assert updated.visibility == "public"
    assert canonical_db.docs[f"users/{uid}/memory_items/{memory_id}"]["visibility"] == "public"
    operations = [
        doc
        for path, doc in canonical_db.docs.items()
        if path.startswith(f"users/{uid}/memory_operations/") and doc["operation_type"] == "user_mutation"
    ]
    assert len(operations) == 1
    assert operations[0]["logical_payload"]["target_visibility"] == "public"
    events = [
        canonical_db.docs[f"users/{uid}/memory_outbox/{event_id}"]
        for event_id in operations[0]["committed_outbox_event_ids"]
    ]
    assert {event["event_type"]: event["payload"]["action"] for event in events} == {
        "projection_sync": "upsert",
        "vector_sync": "upsert",
    }
    assert all(event["payload"]["item_revision"] == updated.item_revision for event in events)
    assert all(event["payload"]["content_hash"] == updated.content_hash for event in events)


def test_update_canonical_product_metadata_commits_through_apply(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(uid=uid, conversation_id="conv-product-fields", content="Product metadata")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    write_canonical_extraction_memory(uid, payload)
    initial_revision = canonical_db.docs[f"users/{uid}/memory_items/{memory_id}"]["item_revision"]
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter._persist_memory_item",
        lambda *_args, **_kwargs: pytest.fail("ordinary product metadata mutation bypassed apply"),
    )

    updated = update_canonical_memory_product_fields(
        uid,
        memory_id,
        tags=["launch", "customer"],
        category=MemoryCategory.system.value,
    )

    assert updated.item_revision == initial_revision + 1
    assert updated.promotion["tags"] == ["launch", "customer"]
    assert updated.promotion["category"] == MemoryCategory.system.value
    operations = [
        doc
        for path, doc in canonical_db.docs.items()
        if path.startswith(f"users/{uid}/memory_operations/") and doc["operation_type"] == "user_mutation"
    ]
    assert len(operations) == 1
    assert operations[0]["logical_payload"]["mutation_metadata"]["promotion_audit"]["tags"] == [
        "launch",
        "customer",
    ]


def test_update_canonical_content_fails_on_document_memory_id_mismatch(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(uid=uid, conversation_id="conv-id-mismatch", content="Original fact")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    canonical_db.docs[item_path] = {**canonical_db.docs[item_path], "memory_id": "different-memory-id"}

    with pytest.raises(ValueError, match="memory id mismatch"):
        update_canonical_memory_content(uid, memory_id, "Updated fact")

    assert canonical_db.docs[item_path]["content"] == "Original fact"


def test_update_canonical_content_invalidates_kg_and_returns_to_pending(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(uid=uid, conversation_id="conv-kg-merge", content="Original KG fact")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.resolve_memory_system", lambda *_, **__: MemorySystem.CANONICAL
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction", lambda *_, **__: None
    )
    monkeypatch.setattr(
        "utils.memory.canonical_kg_promotion.extract_kg_for_promoted_memory",
        lambda *_, **__: SimpleNamespace(success=False),
    )

    write_canonical_extraction_memory(uid, payload)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    canonical_db.docs[item_path].update(
        {
            "tier": "long_term",
            "processing_state": "processed",
            "expires_at": None,
            "ledger_commit_id": "commit1",
            "ledger_sequence": 1,
            "kg_extracted": True,
            "subject_entity_id": "user",
            "predicate": "likes",
            "arguments": {"activity": "climbing"},
            "graph_ready": True,
            "graph_assertion_id": "mga_edit",
            "graph_plan_hash": "plan_edit",
            "promotion": {"reviewed": False},
        }
    )
    assertion_path = f"users/{uid}/memory_graph_assertions/{memory_id}"
    canonical_db.docs[assertion_path] = {"assertion_id": "mga_edit", "memory_id": memory_id}
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter._persist_memory_item",
        lambda *_args, **_kwargs: pytest.fail("ordinary content mutation bypassed apply"),
    )

    updated = update_canonical_memory_content(uid, memory_id, "Updated KG fact")

    assert updated.kg_extracted is False
    assert updated.tier == MemoryTier.short_term
    assert updated.processing_state == ProcessingState.pending
    assert updated.promotion["processing_status"] == "pending_processing"
    assert updated.user_asserted is True
    assert updated.subject_entity_id is None
    assert updated.predicate is None
    assert updated.arguments == {}
    assert updated.graph_ready is False
    assert updated.graph_assertion_id is None
    assert updated.graph_plan_hash is None
    assert canonical_db.docs[item_path]["content"] == "Updated KG fact"
    assert canonical_db.docs[item_path]["kg_extracted"] is False
    assert assertion_path not in canonical_db.docs
    operations = [
        doc
        for path, doc in canonical_db.docs.items()
        if path.startswith(f"users/{uid}/memory_operations/")
        and doc["operation_type"] == "user_mutation"
        and doc["logical_payload"].get("memory_text") == "Updated KG fact"
    ]
    assert len(operations) == 1
    assert operations[0]["logical_payload"]["target_tier"] == MemoryTier.short_term.value
    assert operations[0]["logical_payload"]["clear_graph_assertion"] is True
    events = [
        canonical_db.docs[f"users/{uid}/memory_outbox/{event_id}"]
        for event_id in operations[0]["committed_outbox_event_ids"]
    ]
    assert {event["event_type"]: event["payload"]["action"] for event in events} == {
        "projection_sync": "delete",
        "vector_sync": "delete",
    }
    assert all(event["payload"]["item_revision"] == updated.item_revision for event in events)
    assert all(event["payload"]["content_hash"] == updated.content_hash for event in events)


def test_delete_all_canonical_memories_batches_kg_invalidation(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payloads = [
        _sample_memory_payload(uid=uid, conversation_id="conv-del-all-1", content="First fact"),
        _sample_memory_payload(uid=uid, conversation_id="conv-del-all-2", content="Second fact"),
    ]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    kg_calls = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction",
        lambda u, ids, **kwargs: kg_calls.append((u, list(ids))),
    )

    memory_ids = []
    for payload in payloads:
        write_canonical_extraction_memory(uid, payload)
        memory_ids.append(payload["id"])

    import utils.memory.canonical_memory_adapter as canonical_adapter

    original_fetch = canonical_adapter.fetch_authoritative_product_memory_items
    full_scan_calls = 0

    def counted_fetch(**kwargs):
        nonlocal full_scan_calls
        full_scan_calls += 1
        return original_fetch(**kwargs)

    monkeypatch.setattr(canonical_adapter, "fetch_authoritative_product_memory_items", counted_fetch)
    review_purge_calls = []
    monkeypatch.setattr(
        canonical_adapter,
        "purge_stale_review_conflicts_for_memories",
        lambda u, ids, **kwargs: review_purge_calls.append((u, list(ids))) or [],
    )
    delete_all_canonical_memories(uid)

    assert full_scan_calls == 2  # initial deletion set plus the final control-fenced empty rescan
    assert len(review_purge_calls) == 1
    assert review_purge_calls[0][0] == uid
    assert set(review_purge_calls[0][1]) == set(memory_ids)
    assert len(kg_calls) == 1
    assert kg_calls[0][0] == uid
    assert set(kg_calls[0][1]) == set(memory_ids)


def test_delete_all_final_rescan_tombstones_concurrent_write(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    first_payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-delete-all-initial",
        content="Initial delete-all memory",
    )
    concurrent_payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-delete-all-concurrent",
        content="Concurrent delete-all memory",
    )
    concurrent_payload["evidence"][0]["evidence_id"] = "ev_ws_j_delete_all_concurrent"

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    first_id = write_canonical_extraction_memory(uid, first_payload)

    import utils.memory.canonical_memory_adapter as canonical_adapter

    original_fetch = canonical_adapter.fetch_authoritative_product_memory_items
    injected = False

    def fetch_with_concurrent_write(**kwargs):
        nonlocal injected
        snapshot = original_fetch(**kwargs)
        if not injected:
            injected = True
            write_canonical_extraction_memory(uid, concurrent_payload)
        return snapshot

    monkeypatch.setattr(canonical_adapter, "fetch_authoritative_product_memory_items", fetch_with_concurrent_write)
    monkeypatch.setattr(
        canonical_adapter,
        "_run_immediate_privacy_cleanup",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        canonical_adapter,
        "purge_stale_review_conflicts_for_memories",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        canonical_adapter,
        "invalidate_kg_for_memory_retraction",
        lambda *_args, **_kwargs: None,
    )

    delete_all_canonical_memories(uid)

    concurrent_id = concurrent_payload["id"]
    assert injected is True
    for memory_id in (first_id, concurrent_id):
        stored = canonical_db.docs[f"users/{uid}/memory_items/{memory_id}"]
        assert stored["status"] == MemoryItemStatus.tombstoned.value
        assert stored["content"] is None


def test_canonical_review_accept_returns_archive_item_to_pending_short_term(canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-review-accept",
        content="The candidate belongs in durable memory",
    )
    memory_id = write_canonical_extraction_memory(uid, payload)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    canonical_db.docs[item_path].update(
        {
            "tier": MemoryTier.archive.value,
            "processing_state": ProcessingState.processed.value,
            "expires_at": None,
            "promotion": {"route": "review"},
        }
    )
    review_id = _seed_canonical_review(canonical_db, uid, memory_id)

    result = resolve_canonical_memory_review(
        uid,
        memory_id,
        review_id=review_id,
        decision="accept",
    )
    updated = MemoryItem(**canonical_db.docs[item_path])

    assert result["commit"]["commit_id"] == updated.ledger_commit_id
    assert updated.tier == MemoryTier.short_term
    assert updated.processing_state == ProcessingState.pending
    assert updated.graph_ready is False
    assert updated.user_asserted is True
    assert updated.promotion["review_resolution_id"] == review_id
    assert updated.promotion["review_decision"] == "accept"
    assert not any(path.startswith(f"users/{uid}/memories/") for path in canonical_db.docs)

    revision = updated.item_revision
    replay = resolve_canonical_memory_review(
        uid,
        memory_id,
        review_id=review_id,
        decision="accept",
    )
    assert replay["idempotent"] is True
    assert canonical_db.docs[item_path]["item_revision"] == revision


@pytest.mark.parametrize("decision", ["accept", "reject"])
def test_canonical_review_rejects_stale_source_revision(decision, canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(
        uid=uid,
        conversation_id=f"conv-review-stale-{decision}",
        content=f"Original review candidate for {decision}",
    )
    memory_id = write_canonical_extraction_memory(uid, payload)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    canonical_db.docs[item_path].update(
        {
            "tier": MemoryTier.archive.value,
            "processing_state": ProcessingState.processed.value,
            "expires_at": None,
            "promotion": {"route": "review"},
        }
    )
    review_id = _seed_canonical_review(canonical_db, uid, memory_id)
    review_path = f"users/{uid}/memory_review_queue/{review_id}"

    control_path = f"users/{uid}/memory_state/apply_control"
    prior_control = MemoryControlState.model_validate(canonical_db.docs[control_path])
    prior_item = MemoryItem.model_validate(canonical_db.docs[item_path])
    next_commit_id = f"commit-after-review-{decision}"
    next_sequence = prior_control.commit_sequence + 1
    changed_at = max(prior_control.updated_at, prior_item.updated_at)
    canonical_db.docs[control_path] = prior_control.model_copy(
        update={
            "head_commit_id": next_commit_id,
            "commit_sequence": next_sequence,
            "updated_at": changed_at,
        }
    ).model_dump(mode="json")
    canonical_db.docs[item_path].update(
        {
            "version": canonical_db.docs[item_path]["version"] + 1,
            "item_revision": canonical_db.docs[item_path]["item_revision"] + 1,
            "ledger_commit_id": next_commit_id,
            "ledger_sequence": next_sequence,
            "source_commit_id": next_commit_id,
            "source_commit_sequence": next_sequence,
            "updated_at": changed_at,
        }
    )
    edited = MemoryItem.model_validate(canonical_db.docs[item_path])
    pending_review = dict(canonical_db.docs[review_path])

    with pytest.raises(CanonicalReviewResolutionConflict) as exc_info:
        resolve_canonical_memory_review(
            uid,
            memory_id,
            review_id=review_id,
            decision=decision,
        )

    assert exc_info.value.status == "stale_review"
    assert MemoryItem.model_validate(canonical_db.docs[item_path]) == edited
    assert canonical_db.docs[review_path] == pending_review


def test_competing_canonical_review_decisions_preserve_atomic_queue_item_outcome(canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-review-competing-decisions",
        content="Keep the accepted candidate",
    )
    memory_id = write_canonical_extraction_memory(uid, payload)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    canonical_db.docs[item_path].update(
        {
            "tier": MemoryTier.archive.value,
            "processing_state": ProcessingState.processed.value,
            "expires_at": None,
            "promotion": {"route": "review"},
        }
    )
    review_id = _seed_canonical_review(canonical_db, uid, memory_id)
    review_path = f"users/{uid}/memory_review_queue/{review_id}"

    resolve_canonical_memory_review(
        uid,
        memory_id,
        review_id=review_id,
        decision="accept",
    )
    accepted_item = dict(canonical_db.docs[item_path])
    accepted_review = dict(canonical_db.docs[review_path])

    with pytest.raises(CanonicalReviewResolutionConflict) as exc_info:
        resolve_canonical_memory_review(
            uid,
            memory_id,
            review_id=review_id,
            decision="reject",
        )

    assert exc_info.value.status == "already_resolved"
    assert canonical_db.docs[item_path] == accepted_item
    assert canonical_db.docs[review_path] == accepted_review
    assert accepted_item["status"] == MemoryItemStatus.active.value
    assert accepted_review["status"] == "accepted"
    assert accepted_review["decision"] == "accept"
    assert accepted_review["candidate"] == {"id": memory_id}


def test_canonical_review_accept_rejects_correction_substitution(canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-review-accept-correction",
        content="Accept only this exact candidate",
    )
    memory_id = write_canonical_extraction_memory(uid, payload)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    canonical_db.docs[item_path].update(
        {
            "tier": MemoryTier.archive.value,
            "processing_state": ProcessingState.processed.value,
            "expires_at": None,
            "promotion": {"route": "review"},
        }
    )
    review_id = _seed_canonical_review(canonical_db, uid, memory_id)
    review_path = f"users/{uid}/memory_review_queue/{review_id}"
    before_item = dict(canonical_db.docs[item_path])
    before_review = dict(canonical_db.docs[review_path])

    with pytest.raises(ValueError, match="accept review resolution does not accept correction data"):
        resolve_canonical_memory_review(
            uid,
            memory_id,
            review_id=review_id,
            decision="accept",
            correction={"content": "Substitute a different candidate"},
        )

    assert canonical_db.docs[item_path] == before_item
    assert canonical_db.docs[review_path] == before_review


def test_canonical_review_reject_tombstones_content_and_rejects_unknown_decision(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(
        uid=uid,
        conversation_id="conv-review-reject",
        content="Delete this rejected candidate",
    )
    memory_id = write_canonical_extraction_memory(uid, payload)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    canonical_db.docs[item_path].update(
        {
            "tier": MemoryTier.archive.value,
            "processing_state": ProcessingState.processed.value,
            "expires_at": None,
            "promotion": {"route": "review"},
        }
    )
    review_id = _seed_canonical_review(canonical_db, uid, memory_id)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter._run_immediate_privacy_cleanup",
        lambda *_args, **_kwargs: None,
    )

    resolve_canonical_memory_review(
        uid,
        memory_id,
        review_id=review_id,
        decision="reject",
    )

    assert canonical_db.docs[item_path]["status"] == MemoryItemStatus.tombstoned.value
    assert canonical_db.docs[item_path]["content"] is None
    with pytest.raises(ValueError, match="unsupported canonical review decision"):
        resolve_canonical_memory_review(
            uid,
            memory_id,
            review_id=review_id,
            decision="overwrite",
        )


def test_conversation_delete_cascade_default_is_false():
    """Q8 gated: production default must stay cascade=false until owner sign-off."""
    source = CONVERSATIONS_ROUTER_PATH.read_text(encoding="utf-8")
    assert re.search(r"cascade:\s*bool\s*=\s*Query\(False\)", source)
    assert "Q8-gated" in source


def test_conversation_delete_cascade_branches_memory_delete_by_cohort():
    """Cascade delete must branch legacy delete vs canonical retract."""
    source = CONVERSATIONS_ROUTER_PATH.read_text(encoding="utf-8")
    cascade_start = source.index("if cascade:")
    cascade_block = source[cascade_start : source.index("return {\"status\": \"Ok\"}", cascade_start)]
    assert "memory_system = pin_memory_system(uid" in cascade_block
    assert "memory_system == MemorySystem.CANONICAL" in cascade_block
    assert ".retract_conversation_memories(uid, conversation_id)" in cascade_block
    assert "memories_db.delete_memories_for_conversation(uid, conversation_id)" in cascade_block
    canonical_branch_start = cascade_block.index("memory_system == MemorySystem.CANONICAL")
    legacy_delete_idx = cascade_block.index("memories_db.delete_memories_for_conversation")
    assert legacy_delete_idx > canonical_branch_start


def test_purge_derived_user_data_wires_canonical_purge_helper():
    users_source = (BACKEND_DIR / "services" / "users" / "account_deletion.py").read_text(encoding="utf-8")
    tree = ast.parse(users_source)
    purge_fn = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "purge_derived_user_data"
    )
    call_names = {
        node.func.id for node in ast.walk(purge_fn) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "purge_canonical_derived_user_data" in call_names
