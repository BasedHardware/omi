"""Projection outbox discovery and its mixed-writer fallback."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import batch_pipeline_projection_outbox as rows
from database.batch_pipeline_leader import LeaseLost
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline.projection_discovery import ProjectionDiscovery
from utils.batch_pipeline.projection_outbox import ProjectionOutbox
from utils.batch_pipeline.serving import Serving


def pending(store, sid, *, stamped=True, at=1.0):
    row = {'segment_id': sid, 'projection_state': 'pending', 'committed_at': at, 'log_sequence': 1}
    if stamped:
        row.update(rows.arm(row, at))
    store.apply(('results', sid), row)


def coordinator(store, clock):
    projector = SimpleNamespace(store=SimpleNamespace(store=store))
    return ProjectionOutbox(store, projector, clock=clock)


@pytest.mark.asyncio
async def test_serving_wakes_the_new_revision_after_merge_returns():
    store = SimStore(CustomerData())
    outbox = coordinator(store, lambda: 10.0)
    outbox.loop = asyncio.get_running_loop()
    serving = Serving(store, outbox=outbox)
    pending(store, 'new')
    committed = store.run(lambda tx: tx.get('results', 'new'))
    serving.merge = Mock()
    serving.merge.commit_next.side_effect = [committed, None]
    await asyncio.to_thread(serving.drain_owner, 'synthetic-owner')
    assert outbox.queue.get_nowait() == rows.Obligation('new', 1)
    assert serving.merge.commit_next.call_count == 2


def test_hints_leave_queue_space_for_the_elected_scan():
    store = SimStore(CustomerData())
    outbox = coordinator(store, lambda: 10.0)
    outbox.queue = asyncio.Queue(maxsize=4)
    for i in range(4):
        outbox._enqueue(rows.Obligation(f'hint-{i}', 1), hinted=True)
    assert outbox.queue.qsize() == 2
    outbox._enqueue(rows.Obligation('lost-hint', 1))
    assert outbox.queue.qsize() == 3


@pytest.mark.asyncio
async def test_serving_shutdown_joins_outbox_workers(monkeypatch):
    store = SimStore(CustomerData())
    pending(store, 'pending')
    outbox = coordinator(store, lambda: 10.0)
    stop, started, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def deliver(_):
        started.set()
        try:
            await asyncio.Future()
        finally:
            finished.set()

    monkeypatch.setattr(outbox, 'deliver', deliver)
    task = asyncio.create_task(outbox.run(stop))
    try:
        await asyncio.wait_for(started.wait(), timeout=10)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=10)

    assert finished.is_set()
    assert outbox.loop is None and outbox.projector.outbox_followup_slots is None
    assert not outbox.queued


def test_projection_outbox_rechecks_leadership_after_page_query(monkeypatch):
    store = SimStore(CustomerData())
    pending(store, 'lost-wake')
    now = [10.0]
    first, second = (coordinator(store, lambda: now[0]) for _ in range(2))
    read = store.projection_outbox_page
    claimed = []

    def takeover(*args):
        page = read(*args)
        monkeypatch.setattr(store, 'projection_outbox_page', read)
        now[0] += 60
        claimed.extend(second.scan(10))
        return page

    monkeypatch.setattr(store, 'projection_outbox_page', takeover)
    with pytest.raises(LeaseLost):
        first.scan(10)
    assert [row.key.segment_id for row in claimed] == ['lost-wake']
    assert first.scan(10) == []


def test_projection_outbox_skip_keeps_raw_page_cursor_and_observer(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    store = SimStore(CustomerData())
    pending(store, 'covered')
    pending(store, 'old-writer', stamped=False, at=2.0)
    now = [10.0]
    outbox = coordinator(store, lambda: now[0])
    observed = []
    discovery = ProjectionDiscovery(
        store, outbox_coverage=outbox.has_coverage, on_page=lambda ids, mode: observed.append((ids, mode))
    )
    assert outbox.has_coverage() is False
    outbox.scan(10)
    now[0] += 5
    assert discovery.next(limit=1) == []
    assert discovery.after == (1.0, 'covered')
    assert observed == [(['covered'], 'legacy')]
    assert discovery.next(limit=1) == ['old-writer']
    monkeypatch.setenv('BATCH_PROJECTION_OUTBOX', 'off')
    discovery.after = None
    assert discovery.next(limit=2) == ['covered', 'old-writer']
    assert outbox.scan(10) == []
    assert store.run(lambda tx: tx.get('results', 'covered'))[rows.DUE_FIELD] == 1.0

    def rearm_under_rollback(tx):
        entry = tx.get('results', 'covered')
        tx.patch('results', 'covered', rows.arm(entry, now[0]))

    store.run(rearm_under_rollback)
    monkeypatch.setenv('BATCH_PROJECTION_OUTBOX', 'on')
    assert outbox.has_coverage() is True
    assert outbox.scan(10) == []
    assert rows.claim(store, rows.Obligation('covered', 1), lambda: now[0]) is None
    discovery.after = None
    assert discovery.next(limit=2) == ['covered', 'old-writer']


def test_projection_outbox_missing_query_cannot_enable_legacy_filter(monkeypatch):
    store = SimStore(CustomerData())
    pending(store, 'covered')
    outbox = coordinator(store, lambda: 10.0)

    def unavailable(*_):
        raise RuntimeError('synthetic missing index')

    monkeypatch.setattr(store, 'projection_outbox_page', unavailable)
    with pytest.raises(RuntimeError, match='missing index'):
        outbox.scan(10)
    assert outbox.has_coverage() is False


def test_projection_outbox_lease_error_does_not_read_a_page(monkeypatch):
    store = SimStore(CustomerData())
    outbox = coordinator(store, lambda: 10.0)

    def unavailable(*_):
        raise RuntimeError('synthetic lease error')

    def forbidden(*_):
        pytest.fail('a strict follower cannot scan')

    monkeypatch.setattr(store, 'run', unavailable)
    monkeypatch.setattr(store, 'projection_outbox_page', forbidden)
    assert outbox.scan(10) == []
    assert outbox.has_coverage() is False
