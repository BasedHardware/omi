"""The legacy offset read must not cost O(rounds x prefix) Firestore work.

``MemoryService.read`` deepens an adaptive historical scan when the newest-first
prefix is suppressed by canonical. Every round re-reads that prefix from the
start, so a linear step plus an uncached status lookup made one page of a fully
suppressed account cost 330 sequential Firestore round trips over 82,500
documents — past the 30s edge timeout, which is how GET /v3/memories 504'd in
prod on 2026-08-18 for both the offset>0 pages and the first page's fallback.

The cost a page pays is what Firestore reads, not what it returns: the
newest-first sort is index-less, so each historical query streams two candidate
windows of ``limit + offset`` documents. Walking the prefix in offset pages
re-reads everything it skips, which kept the page over the edge timeout after
the round cost was fixed.
"""

from unittest.mock import MagicMock

import pytest

from tests.unit.test_memory_service_parity import _load_memory_service, _sample_memory_dict

# Scaled-down mirror of the prod window so the guard stays a fast unit test.
TEST_COMPATIBILITY_WINDOW = 500
TEST_PAGE_SIZE = 50
# One geometric walk of the window reads it once per round (2,500 scanned here,
# 25,000 at the prod window). Chunking the walk into MAX_PAGE_SIZE offset pages
# read 10,500 (105,000 in prod).
SCANNED_DOCUMENT_BUDGET = 3000


class _Snapshot:
    def __init__(self, payload=None, *, exists=True, reference=None):
        self._payload = payload
        self.exists = exists
        self.reference = reference

    def to_dict(self):
        return self._payload


class _Ref:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self, **_kwargs):
        payload = self.db.docs.get(self.path)
        return _Snapshot(payload, exists=payload is not None)


class _CountingDb:
    """Counts batch-get round trips, the documents they read, and repeat reads."""

    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.get_all_calls = 0
        self.get_all_docs = 0
        self.read_paths = []

    def document(self, path):
        return _Ref(self, path)

    def get_all(self, refs):
        refs = list(refs)
        self.get_all_calls += 1
        self.get_all_docs += len(refs)
        for ref in refs:
            self.read_paths.append(ref.path)
            payload = self.docs.get(ref.path)
            yield _Snapshot(payload, exists=payload is not None, reference=ref)


@pytest.fixture
def service_mod(monkeypatch):
    monkeypatch.setenv("MEMORY_MODE", "read")
    module = _load_memory_service(monkeypatch)
    monkeypatch.setattr(
        module.HistoricalMemoryAdapter,
        "MAX_COMPATIBILITY_WINDOW",
        TEST_COMPATIBILITY_WINDOW,
    )
    monkeypatch.setattr(module.HistoricalMemoryAdapter, "MAX_PAGE_SIZE", TEST_PAGE_SIZE)
    return module


def _suppressed_account(service_mod, monkeypatch, uid, *, rows):
    """An account whose entire historical prefix is suppressed by canonical."""
    from database.memory_collections import MemoryCollections

    collections = MemoryCollections(uid=uid)
    docs = {}
    payloads = []
    for index in range(rows):
        memory_id = f"hist-{index:05d}"
        docs[f"{collections.memory_historical_overrides}/{memory_id}"] = {"status": "tombstoned"}
        payload = _sample_memory_dict(memory_id)
        payload["updated_at"] = f"2026-01-01T00:00:{index % 60:02d}+00:00"
        payloads.append(payload)

    db = _CountingDb(docs)
    stats = {"calls": 0, "docs": 0, "scanned": 0}

    def fake_get_memories(_uid, limit, offset, sort=None, **_kwargs):
        del _uid, sort
        page = payloads[offset : offset + limit]
        stats["calls"] += 1
        stats["docs"] += len(page)
        # Charge what Firestore actually reads. The newest-first sort has no
        # index, so ``get_memories`` streams two candidate windows of
        # ``limit + offset`` documents and orders them in Python: rows that an
        # offset skips are still read and billed. Counting only returned rows
        # hides an offset walk's quadratic cost, which is how the 105,000-read
        # prod page passed this guard at 12,500.
        stats["scanned"] += 2 * min(limit + offset, TEST_COMPATIBILITY_WINDOW)
        return [dict(row) for row in page]

    monkeypatch.setattr(service_mod.memories_db, "get_memories", fake_get_memories)
    service = service_mod.MemoryService(db_client=db)
    service._canonical.read = MagicMock(return_value=[])
    return service, db, stats


def test_fully_suppressed_offset_read_stays_within_a_bounded_scan_cost(service_mod, monkeypatch):
    uid = "uid-cost"
    service, db, stats = _suppressed_account(
        service_mod,
        monkeypatch,
        uid,
        rows=TEST_COMPATIBILITY_WINDOW,
    )

    assert service.read(uid, limit=TEST_PAGE_SIZE, offset=0) == []

    # Linear growth walked the prefix 10 times (55 queries / 2,750 documents);
    # geometric growth needs 5 rounds and never re-reads the whole window.
    assert stats["calls"] <= 30
    assert stats["docs"] <= 1500
    # Each round must fetch its prefix in one query, not an offset walk that
    # re-reads every row it skips.
    assert stats["scanned"] <= SCANNED_DOCUMENT_BUDGET
    # Canonical status is a stable read within one request, so a repeated
    # prefix must not be re-queried: previously 30 batch gets / 3,000 documents.
    assert db.get_all_calls <= 8
    assert len(db.read_paths) == len(set(db.read_paths))


def test_status_lookups_are_not_repeated_across_expansion_rounds(service_mod, monkeypatch):
    uid = "uid-cache"
    service, db, _ = _suppressed_account(
        service_mod,
        monkeypatch,
        uid,
        rows=TEST_COMPATIBILITY_WINDOW,
    )
    seen = []
    original = service.canonical_statuses

    def tracking_statuses(_uid, memory_ids):
        seen.extend(memory_ids)
        return original(_uid, memory_ids)

    monkeypatch.setattr(service, "canonical_statuses", tracking_statuses)

    service.read(uid, limit=TEST_PAGE_SIZE, offset=0)

    assert seen, "the suppressed prefix must still be status-checked"
    assert len(seen) == len(set(seen))


def test_first_expansion_step_is_unchanged_for_a_lightly_suppressed_account(service_mod, monkeypatch):
    """Geometric growth must not over-scan an account that needs one expansion."""
    from datetime import datetime, timezone

    from database.memory_collections import MemoryCollections

    uid = "uid-light"
    service = service_mod.MemoryService(db_client=_CountingDb())
    records = []
    for index in range(4):
        memory_id = f"hist-{index}"
        if index < 3:
            path = f"{MemoryCollections(uid=uid).memory_historical_overrides}/{memory_id}"
            service.db_client.docs[path] = {"status": "tombstoned"}
        payload = _sample_memory_dict(memory_id)
        memory = service_mod.MemoryDB.model_validate(payload).model_copy(
            update={"updated_at": datetime(2026, 1, 20 - index, tzinfo=timezone.utc)}
        )
        records.append(
            service_mod.HistoricalMemoryRecord(
                memory=memory,
                locator=service_mod.MemoryLocator(uid, "legacy", memory_id),
            )
        )
    scan_limits = []

    def fake_history_read(_uid, *, limit, offset, device_scope_request=None):
        del _uid, offset, device_scope_request
        scan_limits.append(limit)
        return records[:limit]

    service._canonical.read = MagicMock(return_value=[])
    service.history.read = MagicMock(side_effect=fake_history_read)

    page = service.read(uid, limit=1)

    assert [memory.id for memory in page] == ["hist-3"]
    # window == step == 1, so the first expansion is still current + step.
    assert scan_limits[:2] == [1, 2]
