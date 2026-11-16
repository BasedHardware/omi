"""A full record-drain page that admitted nothing keeps the idle wait (2026-11-07 store:due loop)."""

import asyncio
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore


def _store(n):
    store = MemoryStore()
    for i in range(n):
        store.rows['jobs', f's{i}'] = {
            'owner_id': f'synthetic-{i}',
            'segment_id': f's{i}',
            'state': 'record_pending',
            'available_at': 0,
            'enqueued_at': 0,
        }
    return store


@pytest.fixture
def drain(monkeypatch):
    from utils.batch_pipeline import live

    monkeypatch.setenv('RECORD_DRAIN_BATCH', '2')
    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '1')
    monkeypatch.delenv('RECORD_DRAIN_IDLE_WITHOUT_PROGRESS', raising=False)
    monkeypatch.setattr(live.time, 'time', lambda: 100000.0)
    return live


def _admission(live, monkeypatch, admit_ids):
    async def admission(store, pending):
        if pending['segment_id'] in admit_ids:
            store.rows['jobs', pending['segment_id']]['state'] = 'ready'
            return
        raise ValueError(live.BARRIER_NOT_CLOSED)

    monkeypatch.setattr(live, 'admit_recording', admission)


def test_a_full_page_that_admitted_nothing_keeps_the_idle_wait(drain, monkeypatch):
    _admission(drain, monkeypatch, set())
    assert asyncio.run(drain.drain_recordings(_store(2))) is False


def test_a_full_page_with_progress_continues(drain, monkeypatch):
    _admission(drain, monkeypatch, {'s0'})
    assert asyncio.run(drain.drain_recordings(_store(2))) is True


def test_kill_switch_restores_rescanning_full_pages(drain, monkeypatch):
    monkeypatch.setenv('RECORD_DRAIN_IDLE_WITHOUT_PROGRESS', 'off')
    _admission(drain, monkeypatch, set())
    assert asyncio.run(drain.drain_recordings(_store(2))) is True


def test_a_partial_page_never_continues(drain, monkeypatch):
    _admission(drain, monkeypatch, {'s0'})
    assert asyncio.run(drain.drain_recordings(_store(1))) is False


def test_a_noop_return_is_not_progress(drain, monkeypatch):
    # Luna BLOCKING: a normal return that leaves the row record_pending (an unchanged
    # partial inventory poll) must not make a full page look productive.
    async def noop(store, pending):
        return None

    monkeypatch.setattr(drain, 'admit_recording', noop)
    assert asyncio.run(drain.drain_recordings(_store(2))) is False


def test_a_peer_dead_letter_is_not_progress(drain, monkeypatch):
    # A concurrent peer can settle the row while this pass is admitting it; that is
    # not an admission, so the page still keeps the idle wait.
    async def peer_dead_letter(store, pending):
        store.rows['jobs', pending['segment_id']]['state'] = 'dead'

    monkeypatch.setattr(drain, 'admit_recording', peer_dead_letter)
    assert asyncio.run(drain.drain_recordings(_store(2))) is False


def test_a_dead_letter_expiry_is_not_progress(drain, monkeypatch):
    # The defer transaction also reports dead-letter expiry; that is not an admission,
    # so a page that only aged rows out must still keep the idle wait.
    _admission(drain, monkeypatch, set())
    store = _store(2)
    for i in range(2):
        store.rows['jobs', f's{i}']['record_dead_letter_deadline_at'] = 99999.0
    counter = Mock()
    assert asyncio.run(drain.drain_recordings(store, metrics=Mock(record_dead_letter=counter))) is False
    assert [store.rows['jobs', f's{i}']['state'] for i in range(2)] == ['dead', 'dead']
    assert counter.inc.call_count == 2
