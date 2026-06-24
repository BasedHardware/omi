import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import ensure_non_active_routes_firestore_transactional_stub

ensure_non_active_routes_firestore_transactional_stub()
sys.modules["database._client"] = MagicMock()

from database.memory_collections import V17Collections
from database.memory_non_active_routes import (
    NonActiveRoute,
    NonActiveRouteOutcome,
    NonActiveRouteStoreConflict,
    persist_non_active_route_outcome,
)


class _FakeSnapshot:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeDocumentRef:
    def __init__(self, path, db):
        self.path = path
        self._db = db

    def get(self, transaction=None):
        if self.path not in self._db.docs:
            return _FakeSnapshot(None, exists=False)
        return _FakeSnapshot(self._db.docs[self.path], exists=True)


class _FakeTransaction:
    def __init__(self, db):
        self._db = db
        self.sets = []
        self._read_only = False
        self._max_attempts = 1
        self._id = None

    def set(self, ref, data):
        self.sets.append((ref.path, data))

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or "txn-1"
        self.sets = []

    def _commit(self):
        for path, data in self.sets:
            self._db.docs[path] = data

    def _rollback(self):
        self._id = None


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.transaction_obj = _FakeTransaction(self)

    def transaction(self):
        return self.transaction_obj

    def document(self, path):
        return _FakeDocumentRef(path, self)


def _outcome(**overrides):
    data = dict(
        uid="u1",
        route=NonActiveRoute.review,
        idempotency_key="idem-review-1",
        source_ids=["conv1", "ev1"],
        reason="low confidence needs user confirmation",
        run_id="run1",
        patch_id="patch1",
        audit_metadata={"actor": "v17_l2", "score": 0.62},
        created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
    )
    data.update(overrides)
    return NonActiveRouteOutcome(**data)


def test_persist_non_active_outcome_is_idempotent_and_uses_one_deterministic_document():
    db = _FakeDb()
    outcome = _outcome()

    first = persist_non_active_route_outcome(outcome, db_client=db)
    second = persist_non_active_route_outcome(outcome, db_client=db)

    assert first == second
    assert len(db.docs) == 1
    assert len(db.transaction_obj.sets) == 0
    path, stored = next(iter(db.docs.items()))
    assert path == f"users/u1/non_active_memory_routes/{first.outcome_id}"
    assert stored["idempotency_key"] == "idem-review-1"
    assert stored["source_ids"] == ["conv1", "ev1"]
    assert stored["reason"] == "low confidence needs user confirmation"
    assert stored["route"] == "review"
    assert stored["run_id"] == "run1"
    assert stored["patch_id"] == "patch1"
    assert stored["audit_metadata"] == {"actor": "v17_l2", "score": 0.62}


def test_same_idempotency_key_with_different_payload_fails_closed():
    db = _FakeDb()
    persist_non_active_route_outcome(_outcome(), db_client=db)

    with pytest.raises(NonActiveRouteStoreConflict, match="idempotency key payload mismatch"):
        persist_non_active_route_outcome(_outcome(reason="different", source_ids=["conv2"]), db_client=db)

    assert len(db.docs) == 1


def test_all_t17_non_active_routes_are_persistable_auditable_and_kept_out_of_default_memory_items():
    db = _FakeDb()
    collections = V17Collections(uid="u1")

    for route in [
        NonActiveRoute.review,
        NonActiveRoute.archive,
        NonActiveRoute.context_only,
        NonActiveRoute.reject,
        NonActiveRoute.hidden,
        NonActiveRoute.skip,
    ]:
        persisted = persist_non_active_route_outcome(
            _outcome(
                route=route,
                idempotency_key=f"idem-{route.value}",
                reason=f"{route.value} decision",
                source_ids=[f"src-{route.value}"],
            ),
            db_client=db,
        )
        assert persisted.route == route
        assert persisted.default_long_term_visible is False
        assert persisted.audit_metadata["actor"] == "v17_l2"

    assert len(db.docs) == 6
    assert all(path.startswith("users/u1/non_active_memory_routes/") for path in db.docs)
    assert not any(path.startswith(f"{collections.memory_items}/") for path in db.docs)
