"""Projection outbox discovery and its mixed-writer fallback."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from database import batch_pipeline_projection_outbox as rows
from database.batch_pipeline_leader import LeaseLost
from database.batch_pipeline_projection_followup_clock import DUE_FIELD as FOLLOWUP_DUE_FIELD
from database.firestore_transaction_retry import FirestoreAborted
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline.leader import PROJECTION_OUTBOX_SCAN, TABLE
from utils.batch_pipeline.projection_discovery import ProjectionDiscovery
from utils.batch_pipeline.projection_outbox import ProjectionOutbox
from utils.batch_pipeline.serving import Serving


def pending(store, sid, *, stamped=True, at=1.0, **fields):
    row = {'segment_id': sid, 'projection_state': 'pending', 'committed_at': at, 'log_sequence': 1, **fields}
    if stamped:
        row.update(rows.arm(row, at))
    store.apply(('results', sid), row)


def coordinator(store, clock):
    projector = SimpleNamespace(
        store=SimpleNamespace(store=store), owes_drains=False, owes_followups=False, owes_index=False
    )
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


def test_coverage_witness_refreshes_only_when_needed_and_clears_on_stale_debt():
    store = SimStore(CustomerData())
    now = [100.0]
    outbox = coordinator(store, lambda: now[0])
    pending(store, 'healthy', at=98.0)
    updates = []

    def watch(key, old, new):
        if key == (TABLE, PROJECTION_OUTBOX_SCAN):
            updates.append(new.get('projection_scan_ready_until'))

    store.observers.append(watch)
    outbox.scan(10)
    assert updates[-1] == 130.0 and outbox.has_coverage()
    now[0] = 105.0
    updates.clear()
    outbox.scan(10)
    assert updates == [] and outbox.has_coverage()

    now[0] = 126.0
    outbox.scan(10)
    assert updates[-1] == 156.0 and outbox.has_coverage()
    pending(store, 'stale')
    now[0] = 128.0
    outbox.scan(10)
    assert updates[-1] == 0.0
    now[0] = 131.0  # A follower can cache the previous witness for one scan interval.
    assert not outbox.has_coverage()

    store.apply(('results', 'stale'), {})
    now[0] = 136.0
    outbox.scan(10)
    assert updates[-1] == 166.0 and outbox.has_coverage()


@pytest.mark.asyncio
async def test_outbox_uses_followup_due_and_owns_retry_settlement(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_BACKOFF_SECONDS', '240')
    store = SimStore(CustomerData())
    now = [10.0]
    outbox = coordinator(store, lambda: now[0])
    key = rows.Obligation('ready', 1)
    pending(store, key.segment_id, projection_state='ready', **{FOLLOWUP_DUE_FIELD: 45.0})
    assign = Mock(return_value='followup')
    monkeypatch.setattr(outbox, '_assign_or_project', assign)
    runner = outbox.followups
    finish = AsyncMock(return_value='incomplete')
    monkeypatch.setattr(runner, '_run', finish)
    runner.due_clock.entries[key.segment_id] = {'projection_state': 'ready'}
    legacy_settle = Mock()
    monkeypatch.setattr(runner.due_clock, 'settle', legacy_settle)

    await outbox.deliver(key)
    assign.assert_not_called()
    row = store.run(lambda tx: tx.get('results', key.segment_id))
    assert row[rows.DUE_FIELD] == row[FOLLOWUP_DUE_FIELD] == 45.0
    assert row[rows.TOKEN_FIELD] is None

    now[0] = 45.0
    await outbox.deliver(key)
    finish.assert_awaited_once_with(key.segment_id)
    legacy_settle.assert_not_called()
    assert not runner.due_clock.entries
    row = store.run(lambda tx: tx.get('results', key.segment_id))
    assert row[rows.DUE_FIELD] == 285.0 and row[FOLLOWUP_DUE_FIELD] == 45.0
    assert row[rows.TOKEN_FIELD] is None and row[rows.REASON_FIELD] == 'incomplete'

    now[0] += 60.0
    await outbox.deliver(key)
    finish.assert_awaited_once()
    assert store.run(lambda tx: tx.get('results', key.segment_id)) == row


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['pending', 'ready'])
async def test_outbox_retries_firestore_commit_contention_before_the_generic_backoff(monkeypatch, state):
    customer = CustomerData()
    customer.add_user('synthetic-owner')
    store = SimStore(customer)
    now = [10.0]
    outbox = coordinator(store, lambda: now[0])
    key = rows.Obligation('covered', 1)
    store.apply(('jobs', key.segment_id), {'owner_id': 'synthetic-owner', 'privacy_generation': 0})
    pending(store, key.segment_id, projection_state=state)
    outbox.scan(10)
    assert ProjectionDiscovery(store, outbox_coverage=outbox.has_coverage).next() == []

    def project(key, token):
        if now[0] == 10.0:
            raise ValueError('Failed to commit transaction in 5 attempts.') from FirestoreAborted('contention')

        def complete(tx):
            row = tx.get('results', key.segment_id)
            assert rows.holds_claim(row, key, token, now[0])
            tx.put('results', key.segment_id, {**row, 'projection_state': 'completed'})

        store.run(complete)
        return 'incomplete'

    monkeypatch.setattr(outbox, '_assign_or_project', project)
    await outbox.deliver(key)
    row = store.run(lambda tx: tx.get('results', key.segment_id))
    assert (row[rows.REASON_FIELD], row[rows.DUE_FIELD], row[rows.TOKEN_FIELD]) == ('contention', 20.0, None)

    now[0] = 20.0
    assert [entry.key for entry in outbox.scan(10)] == [key]
    await outbox.deliver(key)
    row = store.run(lambda tx: tx.get('results', key.segment_id))
    assert (row['projection_state'], row[rows.REASON_FIELD], row[rows.DUE_FIELD]) == ('completed', 'completed', None)


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
