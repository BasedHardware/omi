"""Shared canonical-memory Firestore fakes extracted from retired rollout tests."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from google.api_core.exceptions import NotFound

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.memories import MemoryCategory
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryTier, ProcessingState
from tests.unit.memory_import_isolation import install_ws_i_heavy_import_stubs
from utils.memory.canonical_memory_adapter import (
    extraction_memory_id,
    write_canonical_extraction_memory,
)


def _install_heavy_import_stubs() -> None:
    install_ws_i_heavy_import_stubs()


class _Snapshot:
    def __init__(self, data=None, *, exists=True, doc_id=None):
        self._data = data
        self.exists = exists
        self.id = doc_id

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
        doc_id = self.path.rsplit("/", 1)[-1]
        if self.path not in self._db.docs:
            return _Snapshot(None, exists=False, doc_id=doc_id)
        return _Snapshot(self._db.docs[self.path], exists=True, doc_id=doc_id)

    def set(self, data, merge=False):
        if merge and self.path in self._db.docs:
            self._db.docs[self.path] = self._db.docs[self.path] | data
            return
        self._db.docs[self.path] = data

    def update(self, data):
        if self.path not in self._db.docs:
            raise NotFound(f"Document {self.path} not found")
        self._db.docs[self.path] = self._db.docs[self.path] | data


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

    def start_after(self, snapshot):
        return _CollectionRef(
            self._db,
            self.path,
            filters=self._filters,
            order_fields=self._order_fields,
            limit_count=self._limit_count,
            cursor=snapshot,
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

    def stream(self):
        prefix = f"{self.path}/"
        rows = []
        for path, data in sorted(self._db.docs.items()):
            if not path.startswith(prefix) or "/" in path[len(prefix) :]:
                continue
            if not all(self._matches(data, field, operator, expected) for field, operator, expected in self._filters):
                continue
            doc_id = path[len(prefix) :]
            rows.append((self._sort_key(data, doc_id), doc_id, data))
        rows.sort(key=lambda row: row[0])
        if self._cursor is not None:
            cursor_payload = self._cursor.to_dict() or {}
            cursor_key = self._sort_key(cursor_payload, self._cursor.id)
            rows = [row for row in rows if row[0] > cursor_key]
        if self._limit_count is not None:
            rows = rows[: self._limit_count]
        return [_Snapshot(data, exists=True, doc_id=doc_id) for _sort_key, doc_id, data in rows]

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
        if operator == "array_contains":
            return isinstance(actual, list) and expected in actual
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
    return SimpleNamespace(account_generation=1, head_commit_id="head0", read_error_reason=None)


def _sample_memory_payload(*, uid: str, conversation_id: str, content: str) -> dict:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return {
        "id": extraction_memory_id(uid=uid, source_id=conversation_id, content=content),
        "uid": uid,
        "content": content,
        "category": MemoryCategory.interesting.value,
        "conversation_id": conversation_id,
        "created_at": now,
        "updated_at": now,
        "evidence": [
            {
                "evidence_id": "ev_ws_i_1",
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


def _stored_item(item: MemoryItem) -> dict:
    return item.model_dump(mode="json")


def _fresh_short_term_item(*, uid: str, memory_id: str, conversation_id: str, content: str) -> MemoryItem:
    now = datetime.now(timezone.utc)
    evidence = MemoryEvidence(
        evidence_id="ev1",
        source_type="conversation",
        source_id=conversation_id,
        source_version="v1",
        conversation_id=conversation_id,
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    return MemoryItem(
        memory_id=memory_id,
        uid=uid,
        version=1,
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[evidence],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=30),
        ledger_commit_id="commit_1",
        ledger_sequence=1,
        source_commit_id="commit_1",
        source_commit_sequence=1,
        content_hash="hash1",
        account_generation=1,
    )


__all__ = [
    "_DocRef",
    "_FakeDb",
    "_fresh_short_term_item",
    "_install_heavy_import_stubs",
    "_sample_memory_payload",
    "_stored_item",
    "_trusted_account_generation",
    "extraction_memory_id",
    "write_canonical_extraction_memory",
]
