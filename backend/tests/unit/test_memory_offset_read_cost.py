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
# read 10,500 (105,000 in prod). Metadata windows are still billed reads; the
# 504 was decrypting that prefix. Hydrate only the emitted page.
SCANNED_DOCUMENT_BUDGET = 3000
HYDRATED_DOCUMENT_BUDGET = 0


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
    stats = {"calls": 0, "docs": 0, "scanned": 0, "hydrated": 0}

    def fake_index(_uid, limit, offset=0, **_kwargs):
        del _uid
        page = payloads[offset : offset + limit]
        stats["calls"] += 1
        stats["docs"] += len(page)
        # Charge what Firestore actually reads. The newest-first sort has no
        # index, so the list index streams two candidate windows of
        # ``limit + offset`` metadata documents and orders them in Python.
        stats["scanned"] += 2 * min(limit + offset, TEST_COMPATIBILITY_WINDOW)
        return [dict(row) for row in page]

    def fake_by_ids(_uid, memory_ids, **_kwargs):
        del _uid
        stats["hydrated"] += len(memory_ids)
        by_id = {row["id"]: dict(row) for row in payloads}
        return [by_id[memory_id] for memory_id in memory_ids if memory_id in by_id]

    monkeypatch.setattr(service_mod.memories_db, "list_memory_updated_or_created_index", fake_index)
    monkeypatch.setattr(service_mod.memories_db, "get_memories_by_ids", fake_by_ids)
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
    # Fully suppressed: the mixed page is empty, so no content decrypt.
    assert stats["hydrated"] <= HYDRATED_DOCUMENT_BUDGET
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

    def tracking_statuses(_uid, memory_ids, *, budget=None):
        del budget
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

    def fake_history_read(_uid, *, limit, offset, device_scope_request=None, **_kwargs):
        del _uid, offset, device_scope_request
        scan_limits.append(limit)
        return records[:limit]

    service._canonical.read = MagicMock(return_value=[])
    service.history.read = MagicMock(side_effect=fake_history_read)

    page = service.read(uid, limit=1)

    assert [memory.id for memory in page] == ["hist-3"]
    # window == step == 1, so the first expansion is still current + step.
    assert scan_limits[:2] == [1, 2]


def test_high_offset_read_hydrates_only_the_emitted_page(service_mod, monkeypatch):
    """offset=2500/limit=100 in prod streamed 5200 full docs and decrypted 2600.

    The mixed list still indexes ``limit+offset`` metadata rows so merge order
    is preserved, but content decrypt is the returned page only.
    Scaled: offset=250, limit=10, window=260.
    """
    uid = "uid-offset"
    service, _db, stats = _suppressed_account(
        service_mod,
        monkeypatch,
        uid,
        rows=TEST_COMPATIBILITY_WINDOW,
    )
    # Visible historical: skip tombstone overrides so the page is hydrated.
    service.db_client.docs.clear()
    service.canonical_statuses = MagicMock(return_value={})

    page = service.read(uid, limit=10, offset=250)

    assert len(page) == 10
    assert stats["scanned"] <= 2 * 260
    assert stats["hydrated"] == 10
    assert stats["hydrated"] < stats["scanned"]


class _IndexDoc:
    def __init__(self, doc_id, data, *, selected=None):
        self.id = doc_id
        self.exists = True
        self._data = {k: v for k, v in data.items() if selected is None or k in selected}

    def to_dict(self):
        return dict(self._data)


class _DocRef:
    def __init__(self, doc_id):
        self.id = doc_id


class _MemoriesCollection:
    def __init__(self, db):
        self.db = db

    def select(self, fields):
        self.db.select_fields.append(tuple(fields))
        return _DualWindowQuery(self.db, selected=set(fields))

    def order_by(self, field, **_kwargs):
        return _DualWindowQuery(self.db, order_field=field)

    def document(self, memory_id):
        return _DocRef(memory_id)


class _DualWindowQuery:
    def __init__(self, db, *, selected=None, order_field=None, limit_n=None):
        self.db = db
        self.selected = selected
        self.order_field = order_field
        self.limit_n = limit_n

    def select(self, fields):
        self.db.select_fields.append(tuple(fields))
        return _DualWindowQuery(self.db, selected=set(fields), order_field=self.order_field, limit_n=self.limit_n)

    def order_by(self, field, **_kwargs):
        return _DualWindowQuery(self.db, selected=self.selected, order_field=field, limit_n=self.limit_n)

    def limit(self, n):
        return _DualWindowQuery(self.db, selected=self.selected, order_field=self.order_field, limit_n=n)

    def stream(self):
        rows = list(self.db.rows)
        if self.order_field:

            def _key(row):
                value = row.get(self.order_field) or row.get("created_at")
                return value is not None, value

            rows.sort(key=_key, reverse=True)
        if self.limit_n is not None:
            rows = rows[: self.limit_n]
        self.db.streamed += len(rows)
        for row in rows:
            yield _IndexDoc(row["id"], row, selected=self.selected)


class _DualWindowDb:
    """Counts metadata streams vs full-document hydrates for get_memories."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.streamed = 0
        self.hydrated = 0
        self.select_fields = []

    def collection(self, name):
        assert name == "users"
        return self

    def document(self, _uid):
        return self

    def collection_memories(self):
        return _MemoriesCollection(self)

    def get_all(self, refs):
        refs = list(refs)
        self.hydrated += len(refs)
        by_id = {row["id"]: row for row in self.rows}
        for ref in refs:
            payload = by_id.get(ref.id)
            yield _IndexDoc(ref.id, payload or {}, selected=None)


def test_get_memories_dual_window_hydrates_only_the_returned_page(service_mod, monkeypatch):
    """Billed-read contract for the remaining 504 path.

    Before: offset=0/limit=500 streamed and decrypted 1000 docs; offset=2500
    limit=100 streamed 5200 full docs and decrypted 2600 (MemoryService asked
    for the prefix). After: metadata windows of 2*(limit+offset), hydrate the
    page only.
    """
    from datetime import datetime, timezone

    memories_db = service_mod.memories_db
    get_memories = service_mod._prod_get_memories
    monkeypatch.setattr(
        memories_db,
        "list_memory_updated_or_created_index",
        service_mod._prod_list_memory_updated_or_created_index,
    )

    def _rows(n):
        rows = []
        for index in range(n):
            stamp = datetime(2026, 1, 1, tzinfo=timezone.utc).replace(minute=index % 60, second=index % 60)
            rows.append(
                {
                    "id": f"m-{index:04d}",
                    "uid": "uid-db",
                    "content": f"secret-{index}",
                    "created_at": stamp,
                    "updated_at": stamp if index % 2 == 0 else None,
                    "user_review": None,
                    "invalid_at": None,
                }
            )
        return rows

    class _Client(_DualWindowDb):
        def collection(self, name):
            if name == "users":
                return self
            assert name == "memories"
            return _MemoriesCollection(self)

        def document(self, uid_or_id):
            # users/{uid} then memories/{id}
            return self

    first = _Client(_rows(2000))
    page = get_memories(
        "uid-db",
        500,
        0,
        sort="updated_or_created_desc",
        firestore_client=first,
    )
    assert len(page) == 500
    assert first.streamed == 1000  # two metadata windows of 500
    assert first.hydrated == 500
    assert first.select_fields
    assert "visibility" in first.select_fields[0]
    assert "capture_device_ids" in first.select_fields[0]
    assert page[0]["content"].startswith("secret-")

    high = _Client(_rows(4000))
    page = get_memories(
        "uid-db",
        100,
        2500,
        sort="updated_or_created_desc",
        firestore_client=high,
    )
    assert len(page) == 100
    assert high.streamed == 5200  # two windows of min(100+2500, 5000)
    assert high.hydrated == 100
