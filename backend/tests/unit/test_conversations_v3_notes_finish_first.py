"""The v3 notes drain settles the owner's manual Finishes before other pending rows."""

from datetime import datetime, timedelta, timezone
import importlib
from unittest.mock import AsyncMock

import pytest

from database import conversations_v3_leases as leases
from utils.conversations.v3 import notes_order, service

AT = datetime(2026, 11, 27, 20, tzinfo=timezone.utc)


def _row(cid, *, manual=False, finished=0, **updates):
    return {
        'id': cid,
        'v3_derived': True,
        'manual_end': manual,
        'kind': 'conversation',
        'finished_at': AT + timedelta(seconds=finished),
        'v3_process_pending': True,
        **updates,
    }


@pytest.fixture
def drain(monkeypatch):
    created = importlib.import_module('utils.conversations.v3.created')
    monkeypatch.setattr(created, 'deliver', AsyncMock())

    async def blocking(_pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    order = []
    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'python_owns_finalization', lambda row: True)
    monkeypatch.setattr(leases, 'acquire', lambda uid, key: 'token-' + key)
    monkeypatch.setattr(leases, 'release', lambda *a: None)
    monkeypatch.setattr(service, '_load_processing_row', lambda uid, cid: {'id': cid, 'v3_process_pending': True})

    async def process(uid, row, token):
        order.append(row['id'])

    monkeypatch.setattr(service, '_process_leased', process)
    return order


@pytest.mark.asyncio
async def test_finishes_drain_first_newest_first_and_the_rest_keep_scan_order(drain, monkeypatch):
    rows = [
        _row('a'),
        _row('b', manual=True, finished=10),
        _row('c', kind='background', manual=True, finished=99),  # passive: never a Finish
        _row('d'),
        _row('e', manual=True, finished=30),
    ]
    monkeypatch.setattr(service, 'pending_processing', lambda uid: rows)
    before = service.metrics.NOTES_FINISH_FIRST._value.get()

    await service.drain_processing('u')

    assert drain == ['e', 'b', 'a', 'c', 'd']
    assert service.metrics.NOTES_FINISH_FIRST._value.get() == before + 1


@pytest.mark.asyncio
async def test_no_finish_or_already_first_keeps_the_scan_order_uncounted(drain, monkeypatch):
    rows = [_row('b', manual=True, finished=10), _row('a'), _row('d')]
    monkeypatch.setattr(service, 'pending_processing', lambda uid: rows)
    before = service.metrics.NOTES_FINISH_FIRST._value.get()

    await service.drain_processing('u')
    monkeypatch.setattr(service, 'pending_processing', lambda uid: [_row('x'), _row('y')])
    await service.drain_processing('u')

    assert drain == ['b', 'a', 'd', 'x', 'y']
    assert service.metrics.NOTES_FINISH_FIRST._value.get() == before


@pytest.mark.asyncio
async def test_kill_switch_keeps_the_scan_order(drain, monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_NOTES_FINISH_FIRST', 'off')
    rows = [_row('a'), _row('b', manual=True)]
    monkeypatch.setattr(service, 'pending_processing', lambda uid: rows)

    await service.drain_processing('u')

    assert drain == ['a', 'b']


def test_missing_rows_and_finish_times_keep_their_place():
    rows = [None, _row('a'), _row('b', manual=True, finished_at=None), _row('c', manual=True, finished=5)]

    ordered = notes_order.finish_first(rows)

    assert [row and row['id'] for row in ordered] == ['c', 'b', None, 'a']
