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
        _row('c', kind='background', manual=True, finished=99, home_hidden=True),  # passive and hidden
        _row('d'),
        _row('e', manual=True, finished=30),
    ]
    monkeypatch.setattr(service, 'pending_processing', lambda uid: rows)
    before = service.metrics.NOTES_FINISH_FIRST._value.get()

    await service.drain_processing('u')

    assert drain == ['e', 'b', 'a', 'c', 'd']
    # Two Finishes (b and e) moved ahead of other rows; the counter counts Finishes, not drains.
    assert service.metrics.NOTES_FINISH_FIRST._value.get() == before + 2


@pytest.mark.asyncio
async def test_a_passive_finish_that_shows_on_home_drains_first(drain, monkeypatch):
    # A media or background manual end visible on Home settles without a model call: it leads the Finishes.
    rows = [
        _row('a'),
        _row('m', manual=True, finished=30),
        _row('p', kind='media', manual=True, finished=10, home_hidden=False),
        _row('q', kind='background', manual=True, finished=40, home_hidden=True),  # Home hides it
        _row('s', kind='background', manual=False, finished=50, home_hidden=False),  # not a Finish
    ]
    monkeypatch.setattr(service, 'pending_processing', lambda uid: rows)
    before = service.metrics.NOTES_FINISH_FIRST._value.get()

    await service.drain_processing('u')

    assert drain == ['p', 'm', 'a', 'q', 's']
    assert service.metrics.NOTES_FINISH_FIRST._value.get() == before + 2


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


def test_a_finish_without_finished_at_goes_last_among_finishes_and_missing_rows_keep_scan_order():
    rows = [None, _row('a'), _row('b', manual=True, finished_at=None), _row('c', manual=True, finished=5)]

    ordered = notes_order.finish_first(rows)

    assert [row and row['id'] for row in ordered] == ['c', 'b', None, 'a']
