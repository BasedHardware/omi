import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

sys.modules["database._client"] = MagicMock()

from database.v17_non_active_memory_routes import (
    NonActiveRoute,
    NonActiveRouteOutcome,
    persist_non_active_route_outcome,
)
from utils.memory.v17_non_active_route_audit import build_non_active_route_audit_report


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

    def _begin(self, retry_id=None):
        self._id = retry_id or "txn-1"
        self.sets = []

    def _commit(self):
        for path, data in self.sets:
            self._db.docs[path] = data

    def _rollback(self):
        self._id = None

    def _clean_up(self):
        self._id = None


class _FakeDb:
    def __init__(self):
        self.docs = {}
        self.transaction_obj = _FakeTransaction(self)

    def transaction(self):
        return self.transaction_obj

    def document(self, path):
        return _FakeDocumentRef(path, self)


def _persisted_route(route, source_id):
    return NonActiveRouteOutcome(
        uid="u1",
        route=route,
        idempotency_key=f"idem-{route.value}",
        source_ids=[source_id],
        reason=f"{route.value} terminal route",
        run_id="run-audit-1",
        patch_id=f"patch-{route.value}",
        audit_metadata={"actor": "v17_l2", "confidence": 0.42},
        created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
    )


def test_non_active_route_audit_counts_every_route_as_accounted_terminal_outcome():
    db = _FakeDb()
    for route in NonActiveRoute:
        persist_non_active_route_outcome(_persisted_route(route, f"source-{route.value}"), db_client=db)

    report = build_non_active_route_audit_report("u1", db.docs.values())

    assert report.uid == "u1"
    assert report.status == "green"
    assert report.total_accounted_outcomes == 6
    assert report.counts_by_route == {
        "review": 1,
        "archive": 1,
        "context_only": 1,
        "reject": 1,
        "hidden": 1,
        "skip": 1,
    }
    assert {item.terminal_outcome for item in report.evidence} == {
        "non_active_route:review",
        "non_active_route:archive",
        "non_active_route:context_only",
        "non_active_route:reject",
        "non_active_route:hidden",
        "non_active_route:skip",
    }
    assert all(item.accounted for item in report.evidence)
    assert all(item.default_long_term_visible is False for item in report.evidence)
    assert all(item.remediation_state == "accounted_terminal_outcome" for item in report.evidence)


def test_non_active_route_audit_is_red_for_missing_sources_duplicate_terminal_routes_and_default_visibility():
    db = _FakeDb()
    first = persist_non_active_route_outcome(_persisted_route(NonActiveRoute.review, "source-dup"), db_client=db)
    second = _persisted_route(NonActiveRoute.skip, "source-dup")
    second.idempotency_key = "idem-skip-dup"
    persist_non_active_route_outcome(second, db_client=db)

    visible_doc = dict(db.docs[f"users/u1/non_active_memory_routes/{first.outcome_id}"])
    visible_doc["outcome_id"] = "nar_bad_visible"
    visible_doc["idempotency_key"] = "idem-bad-visible"
    visible_doc["payload_fingerprint"] = "bad"
    visible_doc["default_long_term_visible"] = True
    db.docs["users/u1/non_active_memory_routes/nar_bad_visible"] = visible_doc

    report = build_non_active_route_audit_report(
        "u1", db.docs.values(), expected_source_ids=["source-dup", "source-missing"]
    )

    assert report.status == "red"
    assert "missing terminal outcome for source source-missing" in report.red_reasons
    assert "duplicate terminal outcomes for source source-dup" in report.red_reasons
    assert "non-active route nar_bad_visible is default Long-term visible" in report.red_reasons
    assert report.counts_by_route["review"] == 2
    assert report.counts_by_route["skip"] == 1
