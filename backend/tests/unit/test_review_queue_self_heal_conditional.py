"""The stale-review self-heal must not clobber a row a concurrent accept/reject already resolved: it
re-reads under a transaction and only redacts (status -> tombstoned) while still pending (cubic review
PR 10887, backend/database/review_queue.py)."""

from database import review_queue as rq
from database.store.records import StoredDocument
from tests.store_fakes import FakeDocumentStore


def _seed(monkeypatch, path, stored_status):
    store = FakeDocumentStore()
    store._docs[path] = {"authority": "canonical_memory", "status": stored_status}
    monkeypatch.setattr(rq, "_store", lambda: store)
    return store


def test_repair_does_not_clobber_a_concurrently_resolved_row(monkeypatch):
    path = "users/u1/review_queue/r1"
    store = _seed(monkeypatch, path, "accepted")  # a concurrent accept already won
    doc = StoredDocument.present(path, dict(store._docs[path]))
    stale_item = {"authority": "canonical_memory", "status": "pending"}  # our scan read it as pending
    projected = {"status": "tombstoned", "reason": "x", "candidate": {}}

    rq._repair_scanned_review_documents([doc], [stale_item], [projected])

    assert store._docs[path]["status"] == "accepted"  # resolution preserved


def test_repair_redacts_a_still_pending_row(monkeypatch):
    path = "users/u1/review_queue/r2"
    store = _seed(monkeypatch, path, "pending")
    doc = StoredDocument.present(path, dict(store._docs[path]))
    item = {"authority": "canonical_memory", "status": "pending"}
    projected = {"status": "tombstoned", "reason": "x", "candidate": {}}

    rq._repair_scanned_review_documents([doc], [item], [projected])

    assert store._docs[path]["status"] == "tombstoned"  # redacted while still pending
