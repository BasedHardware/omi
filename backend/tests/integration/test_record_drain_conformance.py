"""PL-423: recording selection leases survive replica races and worker loss.

The production drainer and transaction bodies run on old Firestore, replacement
Postgres and the simulator. Only the audio-admission boundary and clock are
injected. Require OMI_REQUIRE_STORE_BACKENDS=all for complete qualification.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from threading import Barrier
from types import SimpleNamespace

import pytest

from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline import live

pytestmark = pytest.mark.integration
T0 = 1_000_000.0


@pytest.fixture
def h(store_backend, monkeypatch):
    store_backend.seed_user('o')
    monkeypatch.setenv('RECORD_DRAIN_BATCH', '2')
    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '1')
    monkeypatch.setenv('RECORD_DRAIN_LEASE_SECONDS', '300')
    # Replace the module reference, not Python's shared time module: emulator
    # retries and RPC deadlines must continue to use real wall time.
    monkeypatch.setattr(live, 'time', SimpleNamespace(time=lambda: T0, monotonic=lambda: T0))
    monkeypatch.setattr(live.random, 'shuffle', lambda rows: None)
    return store_backend


def read(h):
    return h.store.run(lambda tx: tx.get('jobs', 'record'))


def change(h, **fields):
    def body(tx):
        row = tx.get('jobs', 'record')
        tx.put('jobs', 'record', {**row, **fields})

    h.store.run(body)


def seed(h):
    row = {
        'segment_id': 'record',
        'owner_id': h.uid('o'),
        'owner_key': 'synthetic-owner',
        'state': 'record_pending',
        'available_at': T0,
        'enqueued_at': T0 - 30,
        'capture_at': T0 - 60,
        'privacy_generation': 0,
        'record_content_id': 'synthetic-retained-record',
        'raw_audio_ref': {'uri': 'gs://synthetic/retained', 'generation': '7'},
        'policy_id': 'pl423-admitted-policy',
    }
    h.store.run(lambda tx: tx.put('jobs', 'record', row))
    return deepcopy(read(h))


@pytest.mark.asyncio
async def test_pl423_stale_replica_pages_admit_the_record_once(h, monkeypatch):
    before = seed(h)
    due = h.store.due
    selected = Barrier(3, timeout=10)

    def same_page(*args, **kwargs):
        page = due(*args, **kwargs)
        assert page == ['record']
        # All replicas really selected the row before any claim. The store's
        # transaction isolation, rather than a process-local busy set, wins.
        selected.wait()
        return page

    calls = []

    async def admission(store, pending):
        calls.append(pending['segment_id'])
        assert read(h)['available_at'] == T0 + 300
        await asyncio.sleep(0)
        raise ValueError('retained capture tail not durable yet')

    monkeypatch.setattr(h.store, 'due', same_page)
    monkeypatch.setattr(live, 'admit_recording', admission)
    await asyncio.wait_for(asyncio.gather(*(live.drain_recordings(h.store) for _ in range(3))), timeout=20)
    assert calls == ['record']
    assert read(h) == {**before, 'available_at': T0 + 60}
    assert due('record_pending', T0 + 59, 2) == []
    assert due('record_pending', T0 + 60, 2) == ['record']


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['no-admission', 'admitted', 'longer-defer'])
async def test_pl423_completion_releases_only_its_selection_lease(h, monkeypatch, outcome):
    before = seed(h)
    later = T0 + 900
    calls = []

    async def admission(store, pending):
        calls.append(pending['segment_id'])
        assert read(h)['available_at'] == T0 + 300
        if outcome == 'admitted':
            change(h, state='ready')
        elif outcome == 'longer-defer':
            change(h, available_at=later)

    monkeypatch.setattr(live, 'admit_recording', admission)
    await live.drain_recordings(h.store)
    expected = {**before, 'available_at': T0 + 60}
    if outcome == 'admitted':
        expected.update(state='ready', available_at=T0 + 300)
    elif outcome == 'longer-defer':
        expected['available_at'] = later
    assert read(h) == expected
    await live.drain_recordings(h.store)
    assert calls == ['record']


@pytest.mark.asyncio
async def test_pl423_old_worker_cannot_release_a_successor_replica_lease(h, monkeypatch):
    before = seed(h)
    entered = [asyncio.Event(), asyncio.Event()]
    release = [asyncio.Event(), asyncio.Event()]
    calls = []

    async def admission(store, pending):
        index = len(calls)
        calls.append(pending['segment_id'])
        assert index < 2
        entered[index].set()
        await release[index].wait()

    monkeypatch.setattr(live, 'admit_recording', admission)
    tasks = [asyncio.create_task(live.drain_recordings(h.store))]
    try:
        await asyncio.wait_for(entered[0].wait(), timeout=10)
        assert read(h) == {**before, 'available_at': T0 + 300}
        monkeypatch.setattr(live, 'time', SimpleNamespace(time=lambda: T0 + 300, monotonic=lambda: T0 + 300))
        tasks.append(asyncio.create_task(live.drain_recordings(h.store)))
        await asyncio.wait_for(entered[1].wait(), timeout=10)
        assert read(h) == {**before, 'available_at': T0 + 600}
        release[0].set()
        await asyncio.wait_for(tasks[0], timeout=10)
        assert read(h) == {**before, 'available_at': T0 + 600}
        assert h.store.due('record_pending', T0 + 360, 2) == []
    finally:
        for event in release:
            event.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    assert calls == ['record', 'record']
    assert read(h) == {**before, 'available_at': T0 + 360}


@pytest.mark.asyncio
async def test_pl423_worker_loss_retains_custody_until_a_restart_reclaims_expired_lease(h, monkeypatch):
    before = seed(h)

    async def lost_worker(store, pending):
        assert read(h)['available_at'] == T0 + 300
        raise asyncio.CancelledError()

    monkeypatch.setattr(live, 'admit_recording', lost_worker)
    with pytest.raises(asyncio.CancelledError):
        await live.drain_recordings(h.store)
    assert read(h) == {**before, 'available_at': T0 + 300}
    assert h.store.due('record_pending', T0 + 299, 2) == []

    calls = []

    async def restarted_worker(store, pending):
        calls.append(pending['segment_id'])
        assert read(h)['available_at'] == T0 + 600
        change(h, state='ready')

    # A new drainer invocation has no surviving local busy-owner state.
    monkeypatch.setattr(live, 'time', SimpleNamespace(time=lambda: T0 + 300, monotonic=lambda: T0 + 300))
    monkeypatch.setattr(live, 'admit_recording', restarted_worker)
    await live.drain_recordings(h.store)
    await live.drain_recordings(h.store)
    assert calls == ['record']
    assert read(h) == {**before, 'state': 'ready', 'available_at': T0 + 600}
