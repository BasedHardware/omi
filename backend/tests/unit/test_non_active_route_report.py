import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

sys.modules["database._client"] = MagicMock()

from database.memory_non_active_routes import NonActiveRoute
from utils.memory.non_active_route_report import fetch_non_active_route_audit_report


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _FakeQuery:
    def __init__(self, docs, db, filters=None):
        self._docs = docs
        self._db = db
        self._filters = filters or []

    def where(self, field, op, value):
        self._db.where_calls.append((field, op, value))
        return _FakeQuery(self._docs, self._db, self._filters + [(field, op, value)])

    def stream(self):
        self._db.streamed = True
        docs = list(self._docs)
        for field, op, value in self._filters:
            assert op == "=="
            docs = [doc for doc in docs if doc.get(field) == value]
        return [_FakeSnapshot(doc) for doc in docs]


class _FakeDb:
    def __init__(self, docs):
        self.docs = docs
        self.collection_paths = []
        self.where_calls = []
        self.streamed = False

    def collection(self, path):
        self.collection_paths.append(path)
        return _FakeQuery(self.docs, self)


def _route_doc(route, *, source_id=None, run_id="run-1"):
    source_id = source_id or f"src-{route.value}"
    return {
        "uid": "u1",
        "route": route.value,
        "idempotency_key": f"idem-{route.value}",
        "source_ids": [source_id],
        "reason": f"{route.value} routed away from active Long-term",
        "run_id": run_id,
        "patch_id": f"patch-{route.value}",
        "audit_metadata": {"route_store_source": "unit-test"},
        "created_at": datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        "default_long_term_visible": False,
        "outcome_id": f"nar-{route.value}",
        "payload_fingerprint": f"fp-{route.value}",
    }


def test_fetch_non_active_route_audit_report_fetches_run_docs_and_returns_accounted_terminal_counts():
    docs = [_route_doc(route) for route in NonActiveRoute]
    docs.append(_route_doc(NonActiveRoute.review, source_id="other-run-source", run_id="run-2"))
    db = _FakeDb(docs)

    report = fetch_non_active_route_audit_report(
        "u1",
        run_id="run-1",
        expected_source_ids=[f"src-{route.value}" for route in NonActiveRoute],
        db_client=db,
    )

    assert db.collection_paths == ["users/u1/non_active_memory_routes"]
    assert db.where_calls == [("run_id", "==", "run-1")]
    assert db.streamed is True
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
    assert all(evidence.accounted for evidence in report.evidence)
    assert {evidence.terminal_outcome for evidence in report.evidence} == {
        f"non_active_route:{route.value}" for route in NonActiveRoute
    }
    assert all(evidence.default_long_term_visible is False for evidence in report.evidence)


def test_fetch_non_active_route_audit_report_does_not_query_default_long_term_memory_items():
    db = _FakeDb([_route_doc(NonActiveRoute.context_only)])

    report = fetch_non_active_route_audit_report("u1", expected_source_ids=["src-context_only"], db_client=db)

    assert report.status == "green"
    assert db.collection_paths == ["users/u1/non_active_memory_routes"]
    assert not any("memory_items" in path for path in db.collection_paths)
    context_only = report.evidence[0]
    assert context_only.route == NonActiveRoute.context_only
    assert context_only.preserved is True
    assert context_only.default_long_term_visible is False
