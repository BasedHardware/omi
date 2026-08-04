"""Review queue cascade purge when canonical memories are tombstoned or superseded."""

from __future__ import annotations

import os
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_BACKEND = Path(__file__).resolve().parents[2]
_CREATED_AT = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def review_queue():
    """Load a fresh database.review_queue against stubbed database deps.

    review_queue binds ``db`` and sibling database modules at import time
    (``from ._client import db``, ``from database import memories``, ...), so the
    fakes must be active before the module is exec'd. This is the sanctioned
    Tier-2 "fake must precede import" case -- see backend/docs/test_isolation.md
    and testing/import_isolation.load_module_fresh.
    """
    ledger_stub = types.ModuleType("database.memory_ledger")
    ledger_stub.add_fact = lambda fact: {"type": "add_fact", "fact": fact}
    ledger_stub.supersede_fact = lambda existing_id, **kwargs: {
        "type": "supersede_fact",
        "fact_id": existing_id,
        **kwargs,
    }
    ledger_stub.retract_fact = lambda fact_id, **kwargs: {"type": "retract_fact", "fact_id": fact_id, **kwargs}
    ledger_stub.refine_fact = lambda fact_id, arg_changes: {
        "type": "refine_fact",
        "fact_id": fact_id,
        "arg_changes": arg_changes,
    }
    ledger_stub.append_commit = MagicMock()

    fakes = {
        "database._client": MagicMock(),
        "database.memories": MagicMock(),
        "database.memory_ledger": ledger_stub,
        "database.short_term_memories": MagicMock(),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.review_queue",
            os.path.join(str(_BACKEND), "database", "review_queue.py"),
        )
        yield module


class _FakeDocRef:
    def __init__(self, store, full_path, update_log):
        self._store = store
        self.path = full_path
        self._update_log = update_log

    def update(self, payload):
        self._store[self.path].update(payload)
        self._update_log.append((self.path, dict(payload)))


class _FakeDoc:
    def __init__(self, store, full_path, doc_id, data, update_log):
        self.id = doc_id
        self._store = store
        self._full_path = full_path
        self._data = data
        self._update_log = update_log

    def to_dict(self):
        return dict(self._data)

    @property
    def reference(self):
        return _FakeDocRef(self._store, self._full_path, self._update_log)


class _FakeQuery:
    def __init__(
        self,
        store,
        path_prefix,
        *,
        filters=(),
        order_fields=(),
        limit_count=None,
        cursor_key=None,
        query_log,
        update_log,
    ):
        self._store = store
        self._path_prefix = path_prefix
        self._filters = tuple(filters)
        self._order_fields = tuple(order_fields)
        self._limit_count = limit_count
        self._cursor_key = cursor_key
        self._query_log = query_log
        self._update_log = update_log

    def where(self, *, filter):
        return _FakeQuery(
            self._store,
            self._path_prefix,
            filters=(*self._filters, (filter.field_path, filter.op_string, filter.value)),
            order_fields=self._order_fields,
            limit_count=self._limit_count,
            cursor_key=self._cursor_key,
            query_log=self._query_log,
            update_log=self._update_log,
        )

    def order_by(self, field_path):
        return _FakeQuery(
            self._store,
            self._path_prefix,
            filters=self._filters,
            order_fields=(*self._order_fields, field_path),
            limit_count=self._limit_count,
            cursor_key=self._cursor_key,
            query_log=self._query_log,
            update_log=self._update_log,
        )

    def limit(self, limit_count):
        return _FakeQuery(
            self._store,
            self._path_prefix,
            filters=self._filters,
            order_fields=self._order_fields,
            limit_count=limit_count,
            cursor_key=self._cursor_key,
            query_log=self._query_log,
            update_log=self._update_log,
        )

    def start_after(self, snapshot):
        return _FakeQuery(
            self._store,
            self._path_prefix,
            filters=self._filters,
            order_fields=self._order_fields,
            limit_count=self._limit_count,
            cursor_key=snapshot.id,
            query_log=self._query_log,
            update_log=self._update_log,
        )

    def stream(self):
        prefix = f"{self._path_prefix}/"
        documents = []
        for key, data in sorted(self._store.items()):
            if not key.startswith(prefix) or "/" in key[len(prefix) :]:
                continue
            doc_id = key[len(prefix) :]
            if not all(self._matches(data, field, operator, expected) for field, operator, expected in self._filters):
                continue
            sort_key = doc_id
            if self._cursor_key is not None and sort_key <= self._cursor_key:
                continue
            documents.append((sort_key, _FakeDoc(self._store, key, doc_id, data, self._update_log)))
        if self._order_fields != ("__name__",):
            raise AssertionError(f"expected deterministic document-id ordering, got {self._order_fields}")
        if self._limit_count is None:
            raise AssertionError("review purge query must apply a page limit before streaming")
        page = [document for _sort_key, document in sorted(documents)[: self._limit_count]]
        self._query_log.append(
            {
                "filters": self._filters,
                "order_fields": self._order_fields,
                "limit": self._limit_count,
                "cursor_id": self._cursor_key,
                "returned_ids": [document.id for document in page],
            }
        )
        return page

    @staticmethod
    def _matches(data, field, operator, expected):
        if operator == "in":
            return data.get(field) in expected
        if operator == "array_contains_any":
            values = data.get(field)
            return isinstance(values, list) and bool(set(values).intersection(expected))
        raise AssertionError(f"unexpected review purge operator {operator}")


class _FakeCollection(_FakeQuery):
    def __init__(self, store, path_prefix, *, query_log, update_log):
        super().__init__(
            store,
            path_prefix,
            query_log=query_log,
            update_log=update_log,
        )

    def stream(self):
        raise AssertionError("review purge must not stream the lifetime queue")


class _FakeUserDoc:
    def __init__(self, store, uid, query_log, update_log):
        self._store = store
        self._uid = uid
        self._query_log = query_log
        self._update_log = update_log

    def collection(self, name):
        return _FakeCollection(
            self._store,
            f"users/{self._uid}/{name}",
            query_log=self._query_log,
            update_log=self._update_log,
        )


class _FakeUsers:
    def __init__(self, store, query_log, update_log):
        self._store = store
        self._query_log = query_log
        self._update_log = update_log

    def document(self, uid):
        return _FakeUserDoc(self._store, uid, self._query_log, self._update_log)


class _FakeDb:
    def __init__(self, store):
        self.store = store
        self.query_log = []
        self.update_log = []

    def collection(self, name):
        assert name == "users"
        return _FakeUsers(self.store, self.query_log, self.update_log)


class _ProjectionSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if isinstance(self._data, dict) else None


class _ProjectionDocRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    @property
    def id(self):
        return self._path.rsplit("/", 1)[-1]

    @property
    def path(self):
        return self._path

    def get(self):
        return _ProjectionSnapshot(self.id, self._store.get(self._path))


class _ProjectionCollection:
    def __init__(self, store, path):
        self._store = store
        self._path = path
        self._limit = None

    def document(self, doc_id):
        return _ProjectionDocRef(self._store, f"{self._path}/{doc_id}")

    def order_by(self, _field_path, *, direction):
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def stream(self):
        prefix = f"{self._path}/"
        snapshots = [
            _ProjectionSnapshot(path[len(prefix) :], data)
            for path, data in sorted(self._store.items())
            if path.startswith(prefix) and "/" not in path[len(prefix) :]
        ]
        return snapshots[: self._limit] if self._limit is not None else snapshots


class _ProjectionUserDoc:
    def __init__(self, store, uid):
        self._store = store
        self._uid = uid

    def collection(self, name):
        return _ProjectionCollection(self._store, f"users/{self._uid}/{name}")


class _ProjectionDb:
    def __init__(self, store):
        self._store = store

    def collection(self, name):
        assert name == "users"
        return SimpleNamespace(document=lambda uid: _ProjectionUserDoc(self._store, uid))

    def get_all(self, refs):
        return [_ProjectionSnapshot(ref.id, self._store.get(ref.path)) for ref in refs]


def _seed_queue(store, uid: str, items: dict) -> None:
    base = f"users/{uid}/memory_review_queue"
    for doc_id, data in items.items():
        payload = dict(data)
        payload.setdefault("created_at", _CREATED_AT)
        store[f"{base}/{doc_id}"] = payload


def test_purge_drops_pending_items_referencing_deleted_memory(monkeypatch, review_queue):
    uid = "uid-review-purge"
    store = {}
    _seed_queue(
        store,
        uid,
        {
            "review-hit-fact": {
                "review_id": "review-hit-fact",
                "fact_id": "mem_deleted",
                "conflict_with": ["mem_other"],
                "candidate": {"id": "mem_deleted", "content": "deleted private fact"},
                "permitted_uses": ["answers_with_disclaimer"],
                "status": "pending",
            },
            "review-hit-conflict": {
                "review_id": "review-hit-conflict",
                "fact_id": "mem_survivor",
                "conflict_with": ["mem_deleted"],
                "status": "pending",
            },
            "review-unrelated": {
                "review_id": "review-unrelated",
                "fact_id": "mem_alive",
                "conflict_with": ["mem_other"],
                "referenced_memory_ids": ["mem_alive", "mem_other"],
                "status": "pending",
            },
            "review-resolved": {
                "review_id": "review-resolved",
                "fact_id": "mem_deleted",
                "conflict_with": [],
                "status": "accepted",
            },
        },
    )

    db = _FakeDb(store)
    store[f"users/{uid}/memory_review_queue/review-hit-fact"].pop("created_at")
    monkeypatch.setattr(review_queue, "db", db)

    purged = review_queue.purge_stale_review_conflicts_for_memories(uid, ["mem_deleted"])

    assert sorted(purged) == ["review-hit-conflict", "review-hit-fact", "review-resolved"]
    dropped = store[f"users/{uid}/memory_review_queue/review-hit-fact"]
    assert dropped["status"] == "tombstoned"
    assert dropped["candidate"] == {"id": "mem_deleted"}
    assert dropped["permitted_uses"] == []
    assert store[f"users/{uid}/memory_review_queue/review-unrelated"]["status"] == "pending"
    resolved = store[f"users/{uid}/memory_review_queue/review-resolved"]
    assert resolved["status"] == "tombstoned"
    assert resolved["previous_status"] == "accepted"
    assert resolved["candidate"] == {}
    assert resolved["permitted_uses"] == []
    assert db.query_log[0]["filters"] == (("fact_id", "in", ["mem_deleted"]),)
    assert db.query_log[0]["order_fields"] == ("__name__",)
    assert db.query_log[0]["limit"] == 100
    assert db.query_log[1]["filters"] == (("conflict_with", "array_contains_any", ["mem_deleted"]),)

    original_audit = {key: resolved[key] for key in ("previous_status", "reason", "resolved_at", "updated_at")}
    first_update_count = len(db.update_log)

    replayed = review_queue.purge_stale_review_conflicts_for_memories(
        uid,
        ["mem_deleted"],
        reason="different_replay_reason",
    )

    assert sorted(replayed) == ["review-hit-conflict", "review-hit-fact", "review-resolved"]
    assert len(db.update_log) == first_update_count
    assert {key: resolved[key] for key in ("previous_status", "reason", "resolved_at", "updated_at")} == original_audit


def test_purge_chunks_target_ids_and_pages_matches_in_document_order(monkeypatch, review_queue):
    uid = "uid-review-purge-pages"
    store = {}
    first_target = "mem-000"
    last_target = "mem-030"
    items = {
        f"review-{index}": {
            "review_id": f"review-{index}",
            "fact_id": first_target,
            "conflict_with": [],
            "referenced_memory_ids": [first_target],
            "candidate": {"id": first_target, "content": f"private-{index}"},
            "permitted_uses": ["answers_with_disclaimer"],
            "status": "pending",
        }
        for index in range(5)
    }
    items["review-cross"] = {
        "review_id": "review-cross",
        "fact_id": first_target,
        "conflict_with": [last_target],
        "referenced_memory_ids": [first_target, last_target],
        "candidate": {"id": first_target, "content": "cross-chunk private"},
        "permitted_uses": ["answers_with_disclaimer"],
        "status": "pending",
    }
    items["review-last"] = {
        "review_id": "review-last",
        "fact_id": last_target,
        "conflict_with": [],
        "referenced_memory_ids": [last_target],
        "candidate": {"id": last_target, "content": "last private"},
        "permitted_uses": ["answers_with_disclaimer"],
        "status": "pending",
    }
    _seed_queue(store, uid, items)
    db = _FakeDb(store)
    monkeypatch.setattr(review_queue, "db", db)
    monkeypatch.setattr(review_queue, "REVIEW_PURGE_PAGE_SIZE", 2)

    purged = review_queue.purge_stale_review_conflicts_for_memories(
        uid,
        [f"mem-{index:03d}" for index in range(31)],
    )

    assert purged == sorted(items)
    assert len(db.update_log) == len(items)
    chunk_values = {tuple(entry["filters"][0][2]) for entry in db.query_log}
    assert chunk_values == {
        tuple(f"mem-{index:03d}" for index in range(30)),
        ("mem-030",),
    }
    first_chunk_pages = [
        entry
        for entry in db.query_log
        if entry["filters"][0][0] == "fact_id"
        and tuple(entry["filters"][0][2]) == tuple(f"mem-{index:03d}" for index in range(30))
    ]
    assert [entry["cursor_id"] for entry in first_chunk_pages] == [
        None,
        "review-1",
        "review-3",
        "review-cross",
    ]
    assert all(entry["limit"] == 2 for entry in db.query_log)


def test_failed_review_purge_cannot_expose_tombstoned_canonical_candidate(monkeypatch, review_queue):
    uid = "uid-review-projection-fence"
    memory_id = "mem-private"
    review_id = "review-private"
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    store = {
        f"users/{uid}/memory_review_queue/{review_id}": {
            "review_id": review_id,
            "fact_id": memory_id,
            "candidate": {"id": memory_id, "content": "Deleted private candidate"},
            "conflict_with": [],
            "authority": "canonical_memory",
            "source_commit_id": "commit-before-delete",
            "source_item_revision": 1,
            "source_content_hash": "hash-before-delete",
            "status": "pending",
            "impact": 0.5,
            "created_at": now,
            "permitted_uses": ["answers_with_disclaimer"],
        },
        f"users/{uid}/memory_items/{memory_id}": {
            "memory_id": memory_id,
            "uid": uid,
            "version": 2,
            "tier": "archive",
            "status": "tombstoned",
            "processing_state": "processed",
            "content": None,
            "evidence": [],
            "source_state": "tombstoned",
            "sensitivity_labels": [],
            "visibility": "private",
            "user_asserted": False,
            "captured_at": now,
            "updated_at": now,
            "ledger_commit_id": "commit-delete",
            "ledger_sequence": 2,
            "item_revision": 2,
            "source_commit_id": "commit-delete",
            "source_commit_sequence": 2,
            "content_hash": "hash-after-delete",
            "account_generation": 1,
        },
    }
    monkeypatch.setattr(review_queue, "db", _ProjectionDb(store))

    fetched = review_queue.get_review_conflict(uid, review_id)
    listed = review_queue.list_review_conflicts(uid, status="", limit=10)

    assert fetched is not None
    assert fetched["status"] == "tombstoned"
    assert fetched["candidate"] == {"id": memory_id}
    assert fetched["permitted_uses"] == []
    assert listed == [fetched]
    assert store[f"users/{uid}/memory_review_queue/{review_id}"]["candidate"]["content"] == (
        "Deleted private candidate"
    )
