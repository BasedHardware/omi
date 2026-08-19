"""Cursor pagination for the universal mixed canonical+historical memory list."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from tests.unit.test_memory_service_parity import _load_memory_service
from tests.unit.test_universal_memory_service import _Db, _memory
from utils.memory.universal_list_cursor import (
    StreamKeyset,
    UniversalListCursorError,
    UniversalListCursorState,
    decode_universal_list_cursor,
    encode_universal_list_cursor,
)


@pytest.fixture
def service_mod(monkeypatch):
    monkeypatch.setenv("MEMORY_MODE", "read")
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "unit-test-universal-list-cursor-secret")
    module = _load_memory_service(monkeypatch)
    missing = object()
    original_seams = {
        name: getattr(module, name, missing)
        for name in (
            "read_canonical_memories",
            "read_canonical_scan_page",
            "fetch_authoritative_product_memory_items",
            "iter_authoritative_product_memory_items",
        )
    }
    try:
        yield module
    finally:
        # The focused tests replace imported module-level seams directly rather
        # than through monkeypatch. Restore them so a later test file cannot
        # inherit the cursor suite's fail-fast mocks through sys.modules.
        for name, value in original_seams.items():
            if value is missing:
                if hasattr(module, name):
                    delattr(module, name)
            else:
                setattr(module, name, value)


def _dated_memory(service_mod, memory_id: str, *, day: int = 0, stamp: Optional[datetime] = None):
    value = stamp or (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day))
    return _memory(service_mod, memory_id).model_copy(update={"updated_at": value, "created_at": value})


def _dated_historical(
    service_mod,
    memory_id: str,
    *,
    day: int = 0,
    stamp: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
    created_at: Optional[datetime] = None,
):
    base = stamp or (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day))
    memory = _memory(service_mod, memory_id).model_copy(
        update={
            "updated_at": updated_at if updated_at is not None else base,
            "created_at": created_at if created_at is not None else base,
        }
    )
    return service_mod.HistoricalMemoryRecord(
        memory=memory,
        locator=service_mod.MemoryLocator("uid-test", "legacy", memory_id),
    )


def _scan_cursor_for(memory) -> Tuple[datetime, str]:
    stamp = memory.updated_at or memory.created_at
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp, memory.id


def _install_streams(service, service_mod, *, canonical, historical, statuses=None):
    """Install bounded canonical keyset + dual historical keyset fakes.

    Canonical pages are served only through ``read_canonical_scan_page`` in
    bounded chunks. Full-set ``read_canonical_memories`` / authoritative fetch
    seams raise if touched. Historical uses independent updated/created streams.
    """
    ordered = sorted(
        list(canonical),
        key=lambda memory: (-(memory.updated_at or memory.created_at).timestamp(), memory.id),
    )

    def fake_canonical_scan(
        _uid,
        *,
        limit,
        start_after=None,
        db_client=None,
        device_scope_request=None,
        include_pending_processing=False,
        include_archive=False,
        now=None,
    ):
        del db_client, device_scope_request, include_pending_processing, include_archive, now
        assert limit <= 500
        start = 0
        if start_after is not None:
            cursor_time, cursor_id = start_after
            cursor_key = (-cursor_time.timestamp(), cursor_id)
            start = next(
                (
                    index
                    for index, memory in enumerate(ordered)
                    if (-(memory.updated_at or memory.created_at).timestamp(), memory.id) > cursor_key
                ),
                len(ordered),
            )
        chunk = ordered[start : start + limit]
        slots = [(memory, _scan_cursor_for(memory)) for memory in chunk]
        exhausted = len(chunk) < limit or (start + len(chunk)) >= len(ordered)
        return slots, exhausted

    service_mod.read_canonical_scan_page = MagicMock(side_effect=fake_canonical_scan)
    service_mod.read_canonical_memories = MagicMock(
        side_effect=AssertionError("read_page must not full-fetch canonical memories")
    )

    def forbid_full_fetch(*_args, **_kwargs):
        raise AssertionError("read_page must not load the full canonical set")

    service_mod.fetch_authoritative_product_memory_items = MagicMock(side_effect=forbid_full_fetch)
    service_mod.iter_authoritative_product_memory_items = MagicMock(side_effect=forbid_full_fetch)

    # Partition historical into updated_at-present vs created-only streams.
    updated_rows = []
    created_rows = []
    for record in historical:
        # Test records always have updated_at set; treat day-based fixtures as
        # updated-stream members unless explicitly tagged via created-only helper.
        raw_has_updated = getattr(record, "_raw_has_updated_at", True)
        if raw_has_updated:
            updated_rows.append(record)
        else:
            created_rows.append(record)

    updated_rows = sorted(
        updated_rows,
        key=lambda record: (-record.memory.updated_at.timestamp(), record.memory.id),
    )
    created_rows = sorted(
        created_rows,
        key=lambda record: (-record.memory.created_at.timestamp(), record.memory.id),
    )

    def _keyset_page(rows, *, limit, start_after, order_attr):
        start = 0
        if start_after is not None:
            cursor_time, cursor_id = start_after
            cursor_key = (-cursor_time.timestamp(), cursor_id)
            start = next(
                (
                    index
                    for index, record in enumerate(rows)
                    if (-getattr(record.memory, order_attr).timestamp(), record.memory.id) > cursor_key
                ),
                len(rows),
            )
        chunk = rows[start : start + limit]
        slots = []
        for record in chunk:
            stamp = getattr(record.memory, order_attr)
            slots.append((record, (stamp, record.memory.id)))
        exhausted = len(chunk) < limit or (start + len(chunk)) >= len(rows)
        return slots, exhausted

    updated_mock = MagicMock(
        side_effect=lambda _uid, *, limit, start_after=None, device_scope_request=None: _keyset_page(
            updated_rows, limit=limit, start_after=start_after, order_attr="updated_at"
        )
    )
    created_mock = MagicMock(
        side_effect=lambda _uid, *, limit, start_after=None, device_scope_request=None: _keyset_page(
            created_rows, limit=limit, start_after=start_after, order_attr="created_at"
        )
    )
    service.history.read_updated_scan_page = updated_mock
    service.history.read_created_scan_page = created_mock
    service.history.read_scan_page = MagicMock(side_effect=RuntimeError("historical offset scan must not be used"))
    if statuses is not None:
        service.canonical_statuses = MagicMock(return_value=statuses)
    return service_mod.read_canonical_scan_page, updated_mock, created_mock


def test_cursor_pages_beyond_6000_historical_with_bounded_calls_no_cap(service_mod):
    service = service_mod.MemoryService(db_client=_Db())
    historical = [_dated_historical(service_mod, f"h-{index:04d}", day=7000 - index) for index in range(6500)]
    scan_mock, updated_mock, created_mock = _install_streams(
        service, service_mod, canonical=[], historical=historical, statuses={}
    )

    seen = []
    cursor = None
    pages = 0
    while True:
        page = service.read_page("uid-test", limit=500, cursor=cursor)
        pages += 1
        seen.extend(memory.id for memory in page.memories)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
        claims = decode_universal_list_cursor(
            cursor,
            uid="uid-test",
            include_archive=False,
            include_pending_processing=False,
            device_scope="all",
            client_device_id=None,
            secret=b"unit-test-universal-list-cursor-secret",
        )
        assert not hasattr(claims.state, "historical_scan_offset")
        assert claims.state.historical_updated_scan is not None or claims.state.historical_updated_exhausted

    assert len(seen) == 6500
    assert len(set(seen)) == 6500
    assert pages == 13
    assert updated_mock.call_count >= pages
    assert all(call.kwargs["limit"] <= 500 for call in updated_mock.call_args_list)
    assert created_mock.call_count >= 1
    service_mod.read_canonical_memories.assert_not_called()
    service.history.read_scan_page.assert_not_called()
    del scan_mock


def test_cursor_advances_raw_canonical_scan_through_filtered_rows(service_mod):
    service = service_mod.MemoryService(db_client=_Db())
    visible = [_dated_memory(service_mod, f"visible-{index}", day=40 - index) for index in range(3)]
    filtered = [_dated_memory(service_mod, f"filtered-{index}", day=100 - index) for index in range(6)]

    ordered = sorted(
        filtered + visible,
        key=lambda memory: (-(memory.updated_at or memory.created_at).timestamp(), memory.id),
    )
    filtered_ids = {memory.id for memory in filtered}

    def fake_canonical_scan(_uid, *, limit, start_after=None, **_kwargs):
        assert limit <= 500
        start = 0
        if start_after is not None:
            cursor_time, cursor_id = start_after
            cursor_key = (-cursor_time.timestamp(), cursor_id)
            start = next(
                (
                    index
                    for index, memory in enumerate(ordered)
                    if (-(memory.updated_at or memory.created_at).timestamp(), memory.id) > cursor_key
                ),
                len(ordered),
            )
        chunk = ordered[start : start + limit]
        slots = []
        for memory in chunk:
            if memory.id in filtered_ids:
                slots.append((None, _scan_cursor_for(memory)))
            else:
                slots.append((memory, _scan_cursor_for(memory)))
        exhausted = len(chunk) < limit or (start + len(chunk)) >= len(ordered)
        return slots, exhausted

    service_mod.read_canonical_scan_page = MagicMock(side_effect=fake_canonical_scan)
    service_mod.read_canonical_memories = MagicMock(
        side_effect=AssertionError("read_page must not full-fetch canonical memories")
    )
    service.history.read_updated_scan_page = MagicMock(return_value=([], True))
    service.history.read_created_scan_page = MagicMock(return_value=([], True))
    service.canonical_statuses = MagicMock(return_value={})

    first = service.read_page("uid-test", limit=2, cursor=None)
    assert [memory.id for memory in first.memories] == ["visible-0", "visible-1"]
    assert first.next_cursor
    claims = decode_universal_list_cursor(
        first.next_cursor,
        uid="uid-test",
        include_archive=False,
        include_pending_processing=False,
        device_scope="all",
        client_device_id=None,
        secret=b"unit-test-universal-list-cursor-secret",
    )
    assert claims.state.canonical is not None
    assert claims.state.canonical.memory_id == "visible-1"
    assert claims.state.canonical_scan is not None
    assert claims.state.canonical_scan.memory_id == "visible-1"

    second = service.read_page("uid-test", limit=2, cursor=first.next_cursor)
    assert [memory.id for memory in second.memories] == ["visible-2"]
    assert second.next_cursor is None
    service_mod.read_canonical_memories.assert_not_called()


def test_one_us_timestamps_span_canonical_page_boundary(service_mod):
    service = service_mod.MemoryService(db_client=_Db())
    base = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Three docs within the same millisecond: A at +2us, C at +1us, B at +0us.
    docs = [
        _dated_memory(service_mod, "A", stamp=base.replace(microsecond=2)),
        _dated_memory(service_mod, "C", stamp=base.replace(microsecond=1)),
        _dated_memory(service_mod, "B", stamp=base.replace(microsecond=0)),
    ]
    ordered = sorted(docs, key=lambda memory: (-memory.updated_at.timestamp(), memory.id))

    def fake_canonical_scan(_uid, *, limit, start_after=None, **_kwargs):
        start = 0
        if start_after is not None:
            cursor_time, cursor_id = start_after
            # Exact datetime comparison — millisecond truncation would drop C.
            cursor_key = (-service_mod.MemoryService._datetime_to_us(cursor_time), cursor_id)
            start = next(
                (
                    index
                    for index, memory in enumerate(ordered)
                    if (-service_mod.MemoryService._datetime_to_us(memory.updated_at), memory.id) > cursor_key
                ),
                len(ordered),
            )
        chunk = ordered[start : start + limit]
        slots = [(memory, (memory.updated_at, memory.id)) for memory in chunk]
        exhausted = len(chunk) < limit or (start + len(chunk)) >= len(ordered)
        return slots, exhausted

    service_mod.read_canonical_scan_page = MagicMock(side_effect=fake_canonical_scan)
    service_mod.read_canonical_memories = MagicMock(
        side_effect=AssertionError("read_page must not full-fetch canonical memories")
    )
    service.history.read_updated_scan_page = MagicMock(return_value=([], True))
    service.history.read_created_scan_page = MagicMock(return_value=([], True))
    service.canonical_statuses = MagicMock(return_value={})

    first = service.read_page("uid-test", limit=1, cursor=None)
    assert [memory.id for memory in first.memories] == ["A"]
    second = service.read_page("uid-test", limit=2, cursor=first.next_cursor)
    assert [memory.id for memory in second.memories] == ["C", "B"]
    assert second.next_cursor is None

    # Encoded scan keyset keeps microsecond precision for A.
    claims = decode_universal_list_cursor(
        first.next_cursor,
        uid="uid-test",
        include_archive=False,
        include_pending_processing=False,
        device_scope="all",
        client_device_id=None,
        secret=b"unit-test-universal-list-cursor-secret",
    )
    assert claims.state.canonical_scan is not None
    assert claims.state.canonical_scan.updated_at_us == service_mod.MemoryService._datetime_to_us(
        base.replace(microsecond=2)
    )


def test_cursor_advances_through_suppressed_historical_prefix(service_mod):
    from database.memory_collections import MemoryCollections
    from models.product_memory import MemoryItemStatus

    uid = "uid-test"
    db = _Db()
    service = service_mod.MemoryService(db_client=db)
    suppressed = []
    for index in range(8):
        memory_id = f"suppressed-{index}"
        path = f"{MemoryCollections(uid=uid).memory_historical_overrides}/{memory_id}"
        db.docs[path] = {"status": "tombstoned"}
        suppressed.append(_dated_historical(service_mod, memory_id, day=100 - index))
    visible = [_dated_historical(service_mod, f"visible-{index}", day=50 - index) for index in range(3)]
    canonical = [_dated_memory(service_mod, "canonical-old", day=1)]
    statuses = {f"suppressed-{index}": MemoryItemStatus.tombstoned for index in range(8)}
    _install_streams(
        service,
        service_mod,
        canonical=canonical,
        historical=suppressed + visible,
        statuses=statuses,
    )

    first = service.read_page(uid, limit=2, cursor=None)
    assert [memory.id for memory in first.memories] == ["visible-0", "visible-1"]
    assert first.next_cursor

    second = service.read_page(uid, limit=2, cursor=first.next_cursor)
    assert [memory.id for memory in second.memories] == ["visible-2", "canonical-old"]
    assert second.next_cursor is None
    service_mod.read_canonical_memories.assert_not_called()


def test_fully_suppressed_historical_set_stops_at_the_scan_row_budget(service_mod, monkeypatch):
    """Prod 2026-08-18: GET /v3/memories 504'd at the 30s edge timeout.

    An account whose historical rows are all suppressed by canonical makes the
    first page walk the whole historical collection — 50 rows per Firestore
    round trip, unbounded — before it can emit anything, so even ``limit=8``
    ran past the edge timeout. The walk must stop at a bounded row count and
    surface the detail the route falls back on, instead of hanging.
    """
    from fastapi import HTTPException
    from models.product_memory import MemoryItemStatus

    # The shipped bound is what keeps the walk inside the edge timeout; the test
    # shrinks it so the mechanism is asserted without scanning thousands of rows.
    assert service_mod.MEMORY_LIST_SCAN_ROW_BUDGET >= 1000
    monkeypatch.setattr(service_mod, "MEMORY_LIST_SCAN_ROW_BUDGET", 100)

    service = service_mod.MemoryService(db_client=_Db())
    total = 400
    historical = [_dated_historical(service_mod, f"h-{index:05d}", day=9000 - index) for index in range(total)]
    statuses = {f"h-{index:05d}": MemoryItemStatus.tombstoned for index in range(total)}
    _, updated_mock, _ = _install_streams(service, service_mod, canonical=[], historical=historical, statuses=statuses)

    with pytest.raises(HTTPException) as exc_info:
        service.read_page("uid-test", limit=8, cursor=None)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == service_mod.MEMORY_LIST_SCAN_BUDGET_DETAIL
    # The walk stopped at the budget instead of scanning every historical row.
    scanned = sum(call.kwargs["limit"] for call in updated_mock.call_args_list)
    assert scanned <= 150
    assert scanned < total


def test_scan_budget_stops_on_the_wall_clock_deadline_before_the_row_budget(service_mod, monkeypatch):
    """Prod 2026-08-18T08:09Z+: first pages still 504'd after the row budget shipped.

    4000 skipped rows is ~80 sequential Firestore round trips, so a slow account
    burned the whole 30s edge budget inside the bound and left the offset-read
    fallback no time to answer. The walk must stop on elapsed seconds too, well
    before the row budget is spent.
    """
    from fastapi import HTTPException
    from models.product_memory import MemoryItemStatus

    monkeypatch.setattr(service_mod, "MEMORY_LIST_SCAN_DEADLINE_SECONDS", 0.0)
    service = service_mod.MemoryService(db_client=_Db())
    total = 400
    historical = [_dated_historical(service_mod, f"h-{index:05d}", day=9000 - index) for index in range(total)]
    statuses = {f"h-{index:05d}": MemoryItemStatus.tombstoned for index in range(total)}
    _, updated_mock, _ = _install_streams(service, service_mod, canonical=[], historical=historical, statuses=statuses)

    with pytest.raises(HTTPException) as exc_info:
        service.read_page("uid-test", limit=8, cursor=None)

    assert exc_info.value.status_code == 503
    # Same detail the route's first-page fallback already keys on.
    assert exc_info.value.detail == service_mod.MEMORY_LIST_SCAN_BUDGET_DETAIL
    # Time stopped the walk, not rows: far fewer rows were scanned than the row budget allows.
    scanned = sum(call.kwargs["limit"] for call in updated_mock.call_args_list)
    assert scanned < service_mod.MEMORY_LIST_SCAN_ROW_BUDGET


def test_scan_budget_charges_within_the_deadline_do_not_raise(service_mod):
    """The deadline is elapsed-time, not per-charge: charges before it are free."""
    from fastapi import HTTPException

    ticks = iter([100.0, 101.0, 105.9, 106.0])
    budget = service_mod._ScanRowBudget(deadline_seconds=6.0, clock=lambda: next(ticks))

    budget.charge()
    budget.charge()

    with pytest.raises(HTTPException) as exc_info:
        budget.charge()
    assert exc_info.value.detail == service_mod.MEMORY_LIST_SCAN_BUDGET_DETAIL


def test_suppressed_prefix_under_the_budget_still_serves_the_page(service_mod, monkeypatch):
    """The budget bounds pathological accounts only — ordinary skips still page."""
    from models.product_memory import MemoryItemStatus

    monkeypatch.setattr(service_mod, "MEMORY_LIST_SCAN_ROW_BUDGET", 300)
    service = service_mod.MemoryService(db_client=_Db())
    suppressed_count = 200
    suppressed = [
        _dated_historical(service_mod, f"s-{index:05d}", day=9000 - index) for index in range(suppressed_count)
    ]
    visible = [_dated_historical(service_mod, f"visible-{index}", day=50 - index) for index in range(3)]
    statuses = {f"s-{index:05d}": MemoryItemStatus.tombstoned for index in range(suppressed_count)}
    _install_streams(
        service,
        service_mod,
        canonical=[],
        historical=suppressed + visible,
        statuses=statuses,
    )

    page = service.read_page("uid-test", limit=2, cursor=None)

    assert [memory.id for memory in page.memories] == ["visible-0", "visible-1"]
    assert page.next_cursor


def test_historical_status_suppression_batched_once_per_chunk(service_mod):
    from models.product_memory import MemoryItemStatus

    service = service_mod.MemoryService(db_client=_Db())
    historical = [_dated_historical(service_mod, f"h-{index}", day=100 - index) for index in range(12)]
    statuses = {f"h-{index}": MemoryItemStatus.tombstoned for index in range(10)}
    _install_streams(service, service_mod, canonical=[], historical=historical, statuses=statuses)
    status_mock = MagicMock(
        side_effect=lambda _uid, ids: {memory_id: statuses[memory_id] for memory_id in ids if memory_id in statuses}
    )
    service.canonical_statuses = status_mock

    page = service.read_page("uid-test", limit=2, cursor=None)
    assert [memory.id for memory in page.memories] == ["h-10", "h-11"]
    # One batch call per refilled chunk, never one call per suppressed row.
    assert status_mock.call_count == 1
    assert len(status_mock.call_args.args[1]) == 12


def test_front_insert_and_delete_do_not_omit_under_keyset_continuation(service_mod):
    service = service_mod.MemoryService(db_client=_Db())
    rows = [_dated_historical(service_mod, f"h-{index}", day=50 - index) for index in range(6)]
    mutable = {"rows": list(rows)}

    def updated_page(_uid, *, limit, start_after=None, device_scope_request=None):
        del device_scope_request
        ordered = sorted(mutable["rows"], key=lambda record: (-record.memory.updated_at.timestamp(), record.memory.id))
        start = 0
        if start_after is not None:
            cursor_time, cursor_id = start_after
            cursor_key = (-cursor_time.timestamp(), cursor_id)
            start = next(
                (
                    index
                    for index, record in enumerate(ordered)
                    if (-record.memory.updated_at.timestamp(), record.memory.id) > cursor_key
                ),
                len(ordered),
            )
        chunk = ordered[start : start + limit]
        slots = [(record, (record.memory.updated_at, record.memory.id)) for record in chunk]
        exhausted = len(chunk) < limit or (start + len(chunk)) >= len(ordered)
        return slots, exhausted

    service_mod.read_canonical_scan_page = MagicMock(return_value=([], True))
    service_mod.read_canonical_memories = MagicMock(
        side_effect=AssertionError("read_page must not full-fetch canonical memories")
    )
    service.history.read_updated_scan_page = MagicMock(side_effect=updated_page)
    service.history.read_created_scan_page = MagicMock(return_value=([], True))
    service.canonical_statuses = MagicMock(return_value={})

    first = service.read_page("uid-test", limit=2, cursor=None)
    assert [memory.id for memory in first.memories] == ["h-0", "h-1"]

    # Front insert + delete-before-cursor must not omit not-yet-seen rows.
    mutable["rows"].insert(0, _dated_historical(service_mod, "h-front", day=100))
    mutable["rows"] = [record for record in mutable["rows"] if record.memory.id != "h-1"]

    second = service.read_page("uid-test", limit=4, cursor=first.next_cursor)
    assert [memory.id for memory in second.memories] == ["h-2", "h-3", "h-4", "h-5"]
    assert "h-front" not in [memory.id for memory in second.memories]  # soft-live newer insert
    assert second.next_cursor is None


def test_cursor_rejects_malformed_tampered_scope_and_pending_mismatch(service_mod):
    service = service_mod.MemoryService(db_client=_Db())
    _install_streams(
        service,
        service_mod,
        canonical=[_dated_memory(service_mod, "c-1", day=2)],
        historical=[_dated_historical(service_mod, "h-1", day=1)],
        statuses={},
    )
    first = service.read_page("uid-test", limit=1, cursor=None, include_archive=False, include_pending_processing=False)
    assert first.next_cursor

    with pytest.raises(service_mod.HTTPException) as malformed:
        service.read_page("uid-test", limit=1, cursor="not-a-cursor")
    assert malformed.value.status_code == 400
    assert "malformed_cursor" in malformed.value.detail

    tampered = first.next_cursor[:-1] + ("A" if first.next_cursor[-1] != "A" else "B")
    with pytest.raises(service_mod.HTTPException) as bad_sig:
        service.read_page("uid-test", limit=1, cursor=tampered)
    assert bad_sig.value.status_code == 400
    assert "invalid_signature" in bad_sig.value.detail

    with pytest.raises(service_mod.HTTPException) as archive_mismatch:
        service.read_page("uid-test", limit=1, cursor=first.next_cursor, include_archive=True)
    assert archive_mismatch.value.status_code == 400
    assert "include_archive_mismatch" in archive_mismatch.value.detail

    with pytest.raises(service_mod.HTTPException) as pending_mismatch:
        service.read_page(
            "uid-test",
            limit=1,
            cursor=first.next_cursor,
            include_pending_processing=True,
        )
    assert pending_mismatch.value.status_code == 400
    assert "include_pending_processing_mismatch" in pending_mismatch.value.detail

    from utils.client_device import DeviceScopeRequest

    with pytest.raises(service_mod.HTTPException) as scope_mismatch:
        service.read_page(
            "uid-test",
            limit=1,
            cursor=first.next_cursor,
            device_scope_request=DeviceScopeRequest(device_scope="current", client_device_id="device-a"),
        )
    assert scope_mismatch.value.status_code == 400
    assert "device_scope_mismatch" in scope_mismatch.value.detail


def test_legacy_offset_window_cap_still_enforced(service_mod):
    service = service_mod.MemoryService(db_client=_Db())
    with pytest.raises(service_mod.HTTPException) as exc_info:
        service.read("uid-test", limit=2, offset=4999)
    assert exc_info.value.status_code == 413


def test_universal_list_cursor_round_trip_binds_archive_pending_device_and_dual_scans():
    secret = b"unit-test-universal-list-cursor-secret"
    state = UniversalListCursorState(
        uid="uid-a",
        include_archive=True,
        include_pending_processing=True,
        device_scope="explicit",
        client_device_id="device-9",
        canonical=StreamKeyset(updated_at_us=1_700_000_000_000_123, memory_id="c-1"),
        canonical_scan=StreamKeyset(updated_at_us=1_700_000_000_500_456, memory_id="c-scan"),
        historical=StreamKeyset(updated_at_us=1_699_000_000_000_789, memory_id="h-1"),
        historical_updated_scan=StreamKeyset(updated_at_us=1_699_000_000_000_100, memory_id="h-u"),
        historical_created_scan=StreamKeyset(updated_at_us=1_698_000_000_000_200, memory_id="h-c"),
        canonical_exhausted=False,
        historical_updated_exhausted=False,
        historical_created_exhausted=True,
    )
    token = encode_universal_list_cursor(state, secret=secret, now_epoch_seconds=1_800_000_000)
    claims = decode_universal_list_cursor(
        token,
        uid="uid-a",
        include_archive=True,
        include_pending_processing=True,
        device_scope="explicit",
        client_device_id="device-9",
        secret=secret,
        now_epoch_seconds=1_800_000_000,
    )
    assert claims.state == state
    with pytest.raises(UniversalListCursorError) as exc_info:
        decode_universal_list_cursor(
            token,
            uid="uid-a",
            include_archive=True,
            include_pending_processing=False,
            device_scope="explicit",
            client_device_id="device-9",
            secret=secret,
            now_epoch_seconds=1_800_000_000,
        )
    assert exc_info.value.reason == "include_pending_processing_mismatch"


def test_read_canonical_scan_page_snapshot_id_mismatch_and_lineage(monkeypatch):
    import os

    os.environ.setdefault(
        "ENCRYPTION_SECRET",
        "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
    )
    from database.firestore_index_registry import UNIVERSAL_CANONICAL_LIST_SCAN_QUERY
    from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
    from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
    from utils.memory import canonical_memory_adapter as adapter

    uid = "uid-scan"
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)

    def _item(
        memory_id: str,
        *,
        day: int,
        processing_state=ProcessingState.processed,
        tier=MemoryLayer.short_term,
        canonical_memory_id=None,
        doc_id=None,
    ):
        stamp = now - timedelta(hours=day)
        evidence = MemoryEvidence(
            evidence_id=f"evidence-{memory_id}",
            source_id=f"source-{memory_id}",
            source_type="conversation",
            source_version="v1",
            source_state=SourceState.active,
            artifact_preservation=ArtifactPreservationState.preserved,
        )
        return (
            doc_id or memory_id,
            MemoryItem(
                memory_id=memory_id,
                uid=uid,
                version=1,
                content=f"content-{memory_id}",
                tier=tier,
                status=MemoryItemStatus.active,
                processing_state=processing_state,
                source_state=SourceState.active,
                created_at=stamp,
                updated_at=stamp,
                captured_at=stamp,
                expires_at=now + timedelta(days=30),
                evidence=[evidence],
                sensitivity_labels=[],
                visibility="private",
                user_asserted=False,
                promotion={},
                account_generation=1,
                canonical_memory_id=canonical_memory_id,
                ledger_commit_id=("ledger-root" if tier == MemoryLayer.long_term else None),
                ledger_sequence=(1 if tier == MemoryLayer.long_term else None),
            ),
        )

    mismatch_doc, mismatch_item = _item("payload-other", day=0, doc_id="snapshot-real")
    alias_doc, alias_item = _item("alias", day=1, canonical_memory_id="root")
    root_doc, root_item = _item("root", day=2, tier=MemoryLayer.long_term)
    visible_doc, visible_item = _item("visible", day=3)
    rows = [
        (mismatch_doc, mismatch_item),
        (alias_doc, alias_item),
        (root_doc, root_item),
        (visible_doc, visible_item),
    ]

    class _Snapshot:
        def __init__(self, doc_id: str, item: MemoryItem):
            self.id = doc_id
            self._item = item

        def to_dict(self):
            return self._item.model_dump(mode="python")

        @property
        def exists(self):
            return True

        @property
        def reference(self):
            return type("Ref", (), {"path": f"users/{uid}/memory_items/{self.id}"})()

    class _Query:
        def __init__(self, db, *, order_fields=(), limit_count=None, start_after_values=None):
            self._db = db
            self._order_fields = tuple(order_fields)
            self._limit_count = limit_count
            self._start_after_values = dict(start_after_values or {})

        def order_by(self, field_path, direction=None):
            direction_name = getattr(direction, "name", direction)
            return _Query(
                self._db,
                order_fields=(*self._order_fields, (field_path, direction_name)),
                limit_count=self._limit_count,
                start_after_values=self._start_after_values,
            )

        def start_after(self, values):
            return _Query(
                self._db,
                order_fields=self._order_fields,
                limit_count=self._limit_count,
                start_after_values=values,
            )

        def limit(self, count):
            return _Query(
                self._db,
                order_fields=self._order_fields,
                limit_count=count,
                start_after_values=self._start_after_values,
            )

        def stream(self):
            assert self._order_fields == (
                ("updated_at", "DESCENDING"),
                ("__name__", None),
            )
            ordered = sorted(self._db.items, key=lambda pair: (-pair[1].updated_at.timestamp(), pair[0]))
            if self._start_after_values:
                cursor_time = self._start_after_values["updated_at"]
                cursor_ref = self._start_after_values["__name__"]
                cursor_id = cursor_ref.id
                cursor_key = (-cursor_time.timestamp(), cursor_id)
                ordered = [pair for pair in ordered if (-pair[1].updated_at.timestamp(), pair[0]) > cursor_key]
            if self._limit_count is not None:
                ordered = ordered[: self._limit_count]
            return [_Snapshot(doc_id, item) for doc_id, item in ordered]

    class _DocRef:
        def __init__(self, db, memory_id):
            self.id = memory_id
            self._db = db
            self.path = f"users/{uid}/memory_items/{memory_id}"

        def get(self):
            for doc_id, item in self._db.items:
                if doc_id == self.id:
                    return _Snapshot(doc_id, item)
            return type("Missing", (), {"exists": False})()

    class _Collection:
        def __init__(self, db):
            self._db = db

        def document(self, memory_id):
            return _DocRef(self._db, memory_id)

        def order_by(self, field_path, direction=None):
            return _Query(self._db).order_by(field_path, direction=direction)

    class _Db:
        def __init__(self, items):
            self.items = list(items)

        def collection(self, path):
            assert path.endswith("/memory_items")
            return _Collection(self)

        def document(self, path):
            memory_id = path.rsplit("/", 1)[-1]
            return _DocRef(self, memory_id)

    db = _Db(rows)
    direction = type("_Direction", (), {"name": "DESCENDING"})()
    monkeypatch.setattr(adapter.firestore.Query, "DESCENDING", direction)
    monkeypatch.setattr(
        adapter,
        "UNIVERSAL_CANONICAL_LIST_SCAN_QUERY",
        UNIVERSAL_CANONICAL_LIST_SCAN_QUERY,
    )

    slots, exhausted = adapter.read_canonical_scan_page(
        uid,
        limit=10,
        db_client=db,
        include_pending_processing=False,
        now=now,
    )
    assert exhausted is True
    # snapshot/payload mismatch filtered; alias suppressed because visible root wins;
    # root + visible emitted.
    assert [memory.id if memory else None for memory, _ in slots] == [None, None, "root", "visible"]
    assert [cursor[1] for _, cursor in slots] == ["snapshot-real", "alias", "root", "visible"]


def _canonical_scan_page_fixture(monkeypatch, *, uid: str, rows, now: datetime):
    """Hermetic Firestore keyset + point-get fake for ``read_canonical_scan_page``."""
    import os

    os.environ.setdefault(
        "ENCRYPTION_SECRET",
        "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
    )
    from database.firestore_index_registry import UNIVERSAL_CANONICAL_LIST_SCAN_QUERY
    from models.product_memory import MemoryItem
    from utils.memory import canonical_memory_adapter as adapter

    class _Snapshot:
        def __init__(self, doc_id: str, item: MemoryItem):
            self.id = doc_id
            self._item = item

        def to_dict(self):
            return self._item.model_dump(mode="python")

        @property
        def exists(self):
            return True

        @property
        def reference(self):
            return type("Ref", (), {"path": f"users/{uid}/memory_items/{self.id}"})()

    class _Query:
        def __init__(self, db, *, order_fields=(), limit_count=None, start_after_values=None):
            self._db = db
            self._order_fields = tuple(order_fields)
            self._limit_count = limit_count
            self._start_after_values = dict(start_after_values or {})

        def order_by(self, field_path, direction=None):
            direction_name = getattr(direction, "name", direction)
            return _Query(
                self._db,
                order_fields=(*self._order_fields, (field_path, direction_name)),
                limit_count=self._limit_count,
                start_after_values=self._start_after_values,
            )

        def start_after(self, values):
            return _Query(
                self._db,
                order_fields=self._order_fields,
                limit_count=self._limit_count,
                start_after_values=values,
            )

        def limit(self, count):
            return _Query(
                self._db,
                order_fields=self._order_fields,
                limit_count=count,
                start_after_values=self._start_after_values,
            )

        def stream(self):
            assert self._order_fields == (
                ("updated_at", "DESCENDING"),
                ("__name__", None),
            )
            ordered = sorted(self._db.items, key=lambda pair: (-pair[1].updated_at.timestamp(), pair[0]))
            if self._start_after_values:
                cursor_time = self._start_after_values["updated_at"]
                cursor_ref = self._start_after_values["__name__"]
                cursor_id = cursor_ref.id
                cursor_key = (-cursor_time.timestamp(), cursor_id)
                ordered = [pair for pair in ordered if (-pair[1].updated_at.timestamp(), pair[0]) > cursor_key]
            if self._limit_count is not None:
                ordered = ordered[: self._limit_count]
            return [_Snapshot(doc_id, item) for doc_id, item in ordered]

    class _DocRef:
        def __init__(self, db, memory_id):
            self.id = memory_id
            self._db = db
            self.path = f"users/{uid}/memory_items/{memory_id}"

        def get(self):
            for doc_id, item in self._db.items:
                if doc_id == self.id:
                    return _Snapshot(doc_id, item)
            return type("Missing", (), {"exists": False, "id": self.id})()

    class _Collection:
        def __init__(self, db):
            self._db = db

        def document(self, memory_id):
            return _DocRef(self._db, memory_id)

        def order_by(self, field_path, direction=None):
            return _Query(self._db).order_by(field_path, direction=direction)

    class _Db:
        def __init__(self, items):
            self.items = list(items)

        def collection(self, path):
            assert path.endswith("/memory_items")
            return _Collection(self)

        def document(self, path):
            memory_id = path.rsplit("/", 1)[-1]
            return _DocRef(self, memory_id)

    db = _Db(rows)
    direction = type("_Direction", (), {"name": "DESCENDING"})()
    monkeypatch.setattr(adapter.firestore.Query, "DESCENDING", direction)
    monkeypatch.setattr(adapter, "UNIVERSAL_CANONICAL_LIST_SCAN_QUERY", UNIVERSAL_CANONICAL_LIST_SCAN_QUERY)
    return adapter, db


def _canonical_scan_memory_item(
    uid: str,
    memory_id: str,
    *,
    now: datetime,
    day: int,
    processing_state=None,
    tier=None,
    status=None,
    canonical_memory_id=None,
    superseded_by=None,
    doc_id=None,
    payload_memory_id=None,
):
    from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
    from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState

    if processing_state is None:
        processing_state = ProcessingState.processed
    if tier is None:
        tier = MemoryLayer.short_term
    if status is None:
        status = MemoryItemStatus.active
    stamp = now - timedelta(hours=day)
    evidence = MemoryEvidence(
        evidence_id=f"evidence-{memory_id}",
        source_id=f"source-{memory_id}",
        source_type="conversation",
        source_version="v1",
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    item = MemoryItem(
        memory_id=payload_memory_id or memory_id,
        uid=uid,
        version=1,
        content=f"content-{memory_id}",
        tier=tier,
        status=status,
        processing_state=processing_state,
        source_state=SourceState.active,
        created_at=stamp,
        updated_at=stamp,
        captured_at=stamp,
        expires_at=now + timedelta(days=30) if tier == MemoryLayer.short_term else None,
        evidence=[evidence],
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        promotion={},
        account_generation=1,
        canonical_memory_id=canonical_memory_id,
        superseded_by=superseded_by,
        ledger_commit_id=("ledger-root" if tier == MemoryLayer.long_term else None),
        ledger_sequence=(1 if tier == MemoryLayer.long_term else None),
    )
    return doc_id or memory_id, item


def test_read_canonical_scan_page_multihop_superseded_intermediate(monkeypatch):
    from models.product_memory import MemoryItemStatus, MemoryLayer

    uid = "uid-scan-multihop"
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    # A (active alias) -> superseded B -> active long-term C
    alias_doc, alias_item = _canonical_scan_memory_item(uid, "alias-a", now=now, day=0, canonical_memory_id="mid-b")
    mid_doc, mid_item = _canonical_scan_memory_item(
        uid,
        "mid-b",
        now=now,
        day=1,
        status=MemoryItemStatus.superseded,
        canonical_memory_id="root-c",
    )
    root_doc, root_item = _canonical_scan_memory_item(uid, "root-c", now=now, day=2, tier=MemoryLayer.long_term)
    adapter, db = _canonical_scan_page_fixture(
        monkeypatch,
        uid=uid,
        rows=[(alias_doc, alias_item), (mid_doc, mid_item), (root_doc, root_item)],
        now=now,
    )

    slots, exhausted = adapter.read_canonical_scan_page(
        uid,
        limit=10,
        db_client=db,
        include_pending_processing=False,
        now=now,
    )
    assert exhausted is True
    # Alias suppressed via multi-hop walk through non-visible B; B filtered; C emitted.
    assert [memory.id if memory else None for memory, _ in slots] == [None, None, "root-c"]
    assert [cursor[1] for _, cursor in slots] == ["alias-a", "mid-b", "root-c"]


def test_read_canonical_scan_page_lineage_malformed_id_fail_closed(monkeypatch):
    uid = "uid-scan-malformed"
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    alias_doc, alias_item = _canonical_scan_memory_item(
        uid, "alias-a", now=now, day=0, canonical_memory_id="broken-target"
    )
    # Document id authority is "broken-target"; payload claims a different memory_id.
    broken_doc, broken_item = _canonical_scan_memory_item(
        uid,
        "broken-target",
        now=now,
        day=1,
        doc_id="broken-target",
        payload_memory_id="payload-other",
    )
    other_doc, other_item = _canonical_scan_memory_item(uid, "other-visible", now=now, day=2)
    adapter, db = _canonical_scan_page_fixture(
        monkeypatch,
        uid=uid,
        rows=[(alias_doc, alias_item), (broken_doc, broken_item), (other_doc, other_item)],
        now=now,
    )

    slots, exhausted = adapter.read_canonical_scan_page(
        uid,
        limit=10,
        db_client=db,
        include_pending_processing=False,
        now=now,
    )
    assert exhausted is True
    # Broken target fails closed as a scan slot; lineage mismatch cannot prove a
    # survivor, so the alias remains visible.
    assert [memory.id if memory else None for memory, _ in slots] == [
        "alias-a",
        None,
        "other-visible",
    ]
    assert [cursor[1] for _, cursor in slots] == ["alias-a", "broken-target", "other-visible"]


def test_read_canonical_scan_page_lineage_cycle_and_hop_bound(monkeypatch):
    from models.product_memory import MemoryItemStatus, MemoryLayer

    uid = "uid-scan-cycle-bound"
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)

    # Cycle A <-> B: walk must terminate; shared root prefers the lexicographic min.
    cycle_a_doc, cycle_a_item = _canonical_scan_memory_item(
        uid, "cycle-a", now=now, day=0, canonical_memory_id="cycle-b"
    )
    cycle_b_doc, cycle_b_item = _canonical_scan_memory_item(
        uid, "cycle-b", now=now, day=1, canonical_memory_id="cycle-a"
    )

    # Bound: A -> B -> C -> D(long-term). With max hops=2 the walk stops at C and
    # cannot prove D wins, so A stays visible. With the default bound it suppresses.
    chain_a_doc, chain_a_item = _canonical_scan_memory_item(
        uid, "chain-a", now=now, day=2, canonical_memory_id="chain-b"
    )
    chain_b_doc, chain_b_item = _canonical_scan_memory_item(
        uid,
        "chain-b",
        now=now,
        day=3,
        status=MemoryItemStatus.superseded,
        canonical_memory_id="chain-c",
    )
    chain_c_doc, chain_c_item = _canonical_scan_memory_item(
        uid,
        "chain-c",
        now=now,
        day=4,
        status=MemoryItemStatus.superseded,
        canonical_memory_id="chain-d",
    )
    chain_d_doc, chain_d_item = _canonical_scan_memory_item(uid, "chain-d", now=now, day=5, tier=MemoryLayer.long_term)

    rows = [
        (cycle_a_doc, cycle_a_item),
        (cycle_b_doc, cycle_b_item),
        (chain_a_doc, chain_a_item),
        (chain_b_doc, chain_b_item),
        (chain_c_doc, chain_c_item),
        (chain_d_doc, chain_d_item),
    ]
    adapter, db = _canonical_scan_page_fixture(monkeypatch, uid=uid, rows=rows, now=now)

    # Default bound reaches long-term D through two superseded intermediates.
    slots, exhausted = adapter.read_canonical_scan_page(
        uid,
        limit=20,
        db_client=db,
        include_pending_processing=False,
        now=now,
    )
    assert exhausted is True
    emitted = [memory.id if memory else None for memory, _ in slots]
    assert emitted[0] == "cycle-a"  # cycle root / winner stays
    assert emitted[1] is None  # cycle-b suppressed against cycle-a
    assert emitted[2] is None  # chain-a suppressed once D is reachable
    assert emitted[3] is None  # chain-b non-visible
    assert emitted[4] is None  # chain-c non-visible
    assert emitted[5] == "chain-d"

    # Tight hop bound cannot reach D, so chain-a must not be suppressed.
    monkeypatch.setattr(adapter, "_CANONICAL_SCAN_LINEAGE_MAX_HOPS", 2)
    bounded_slots, _ = adapter.read_canonical_scan_page(
        uid,
        limit=20,
        db_client=db,
        include_pending_processing=False,
        now=now,
    )
    bounded_emitted = [memory.id if memory else None for memory, _ in bounded_slots]
    assert bounded_emitted[2] == "chain-a"
    assert bounded_emitted[5] == "chain-d"


def test_read_canonical_scan_page_uses_keyset_order_and_filters(monkeypatch):

    import os

    os.environ.setdefault(
        "ENCRYPTION_SECRET",
        "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
    )
    from database.firestore_index_registry import UNIVERSAL_CANONICAL_LIST_SCAN_QUERY
    from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
    from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
    from utils.memory import canonical_memory_adapter as adapter

    uid = "uid-scan"
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)

    def _item(memory_id: str, *, day: int, processing_state=ProcessingState.processed, tier=MemoryLayer.short_term):
        stamp = now - timedelta(hours=day)
        evidence = MemoryEvidence(
            evidence_id=f"evidence-{memory_id}",
            source_id=f"source-{memory_id}",
            source_type="conversation",
            source_version="v1",
            source_state=SourceState.active,
            artifact_preservation=ArtifactPreservationState.preserved,
        )
        return MemoryItem(
            memory_id=memory_id,
            uid=uid,
            version=1,
            content=f"content-{memory_id}",
            tier=tier,
            status=MemoryItemStatus.active,
            processing_state=processing_state,
            source_state=SourceState.active,
            created_at=stamp,
            updated_at=stamp,
            captured_at=stamp,
            expires_at=now + timedelta(days=30),
            evidence=[evidence],
            sensitivity_labels=[],
            visibility="private",
            user_asserted=False,
            promotion={},
            account_generation=1,
        )

    rows = [
        _item("newest-pending", day=0, processing_state=ProcessingState.pending),
        _item("visible-0", day=1),
        _item("visible-1", day=2),
        _item("visible-2", day=3),
    ]

    class _Snapshot:
        def __init__(self, item: MemoryItem):
            self.id = item.memory_id
            self._item = item

        def to_dict(self):
            return self._item.model_dump(mode="python")

    class _Query:
        def __init__(self, db, *, order_fields=(), limit_count=None, start_after_values=None):
            self._db = db
            self._order_fields = tuple(order_fields)
            self._limit_count = limit_count
            self._start_after_values = dict(start_after_values or {})

        def order_by(self, field_path, direction=None):
            direction_name = getattr(direction, "name", direction)
            return _Query(
                self._db,
                order_fields=(*self._order_fields, (field_path, direction_name)),
                limit_count=self._limit_count,
                start_after_values=self._start_after_values,
            )

        def start_after(self, values):
            return _Query(
                self._db,
                order_fields=self._order_fields,
                limit_count=self._limit_count,
                start_after_values=values,
            )

        def limit(self, count):
            return _Query(
                self._db,
                order_fields=self._order_fields,
                limit_count=count,
                start_after_values=self._start_after_values,
            )

        def stream(self):
            assert self._order_fields == (
                ("updated_at", "DESCENDING"),
                ("__name__", None),
            )
            ordered = sorted(self._db.items, key=lambda item: (-item.updated_at.timestamp(), item.memory_id))
            if self._start_after_values:
                cursor_time = self._start_after_values["updated_at"]
                cursor_ref = self._start_after_values["__name__"]
                cursor_id = cursor_ref.id
                cursor_key = (-cursor_time.timestamp(), cursor_id)
                ordered = [item for item in ordered if (-item.updated_at.timestamp(), item.memory_id) > cursor_key]
            if self._limit_count is not None:
                ordered = ordered[: self._limit_count]
            return [_Snapshot(item) for item in ordered]

    class _Collection:
        def __init__(self, db):
            self._db = db

        def document(self, memory_id):
            return type("Ref", (), {"id": memory_id})()

        def order_by(self, field_path, direction=None):
            return _Query(self._db).order_by(field_path, direction=direction)

    class _Db:
        def __init__(self, items):
            self.items = list(items)

        def collection(self, path):
            assert path.endswith("/memory_items")
            return _Collection(self)

    db = _Db(rows)
    direction = type("_Direction", (), {"name": "DESCENDING"})()
    monkeypatch.setattr(adapter.firestore.Query, "DESCENDING", direction)
    monkeypatch.setattr(
        adapter,
        "UNIVERSAL_CANONICAL_LIST_SCAN_QUERY",
        UNIVERSAL_CANONICAL_LIST_SCAN_QUERY,
    )

    slots, exhausted = adapter.read_canonical_scan_page(
        uid,
        limit=3,
        db_client=db,
        include_pending_processing=False,
        now=now,
    )
    assert exhausted is False
    assert [memory.id if memory else None for memory, _ in slots] == [None, "visible-0", "visible-1"]
    assert [cursor[1] for _, cursor in slots] == ["newest-pending", "visible-0", "visible-1"]

    next_slots, next_exhausted = adapter.read_canonical_scan_page(
        uid,
        limit=3,
        start_after=slots[-1][1],
        db_client=db,
        include_pending_processing=False,
        now=now,
    )
    assert next_exhausted is True
    assert [memory.id if memory else None for memory, _ in next_slots] == ["visible-2"]


def test_canonical_scan_failure_logs_underlying_exception_and_503s(service_mod, caplog):
    """The opaque 503 wrap must leave the underlying failure in logs.

    A Firestore FAILED_PRECONDITION (missing composite) and a uid/cursor
    ValueError must be distinguishable in logs even though the client always
    sees ``Canonical memory unavailable``.
    """
    import logging

    from fastapi import HTTPException

    service = service_mod.MemoryService(db_client=_Db())
    service_mod.read_canonical_scan_page = MagicMock(
        side_effect=RuntimeError("FAILED_PRECONDITION: The query requires an index")
    )
    service_mod.read_canonical_memories = MagicMock(
        side_effect=AssertionError("read_page must not full-fetch canonical memories")
    )
    service.history.read_updated_scan_page = MagicMock(return_value=([], True))
    service.history.read_created_scan_page = MagicMock(return_value=([], True))
    service.canonical_statuses = MagicMock(return_value={})

    with caplog.at_level(logging.ERROR, logger=service_mod.__name__):
        with pytest.raises(HTTPException) as exc_info:
            service.read_page("uid-test", limit=2, cursor=None)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Canonical memory unavailable"
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert "canonical list scan page failed" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "FAILED_PRECONDITION" in caplog.text


def test_building_index_failure_is_the_historical_unavailable_detail(service_mod):
    """Pin the detail the historical keyset scan raises while an index builds.

    ``routers.memories`` matches this exact string to fall the first page back
    to the legacy offset read (the 2026-08-18 5.5h GET /v3/memories outage), so
    a rename here would silently reopen it. Drives the real adapter with the
    Firestore error prod raised.
    """
    from fastapi import HTTPException
    from google.api_core import exceptions as gcloud_exceptions

    building_index = gcloud_exceptions.FailedPrecondition(
        "400 The query requires an index. That index is currently building and cannot be used yet."
    )
    adapter = service_mod.HistoricalMemoryAdapter(db_client=_Db())
    adapter_db = service_mod.memories_db
    original = adapter_db.scan_memories_updated_at_page
    adapter_db.scan_memories_updated_at_page = MagicMock(side_effect=building_index)
    try:
        with pytest.raises(HTTPException) as exc_info:
            adapter.read_updated_scan_page("uid-test", limit=100)
    finally:
        adapter_db.scan_memories_updated_at_page = original

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Historical memory unavailable"
    assert isinstance(exc_info.value.__cause__, gcloud_exceptions.FailedPrecondition)
