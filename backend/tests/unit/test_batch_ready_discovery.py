"""Owner-grain discovery, durable progress and the held-backlog saturation regression."""

import logging
import time
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import FailedPrecondition

from database.batch_pipeline_store import FirestoreStore
from testing.pipeline_sim.store import CustomerData, SimStore
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from tests.unit.test_batch_terminal_poll_skip import Query
from utils.batch_pipeline import ready_discovery
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.batch_pipeline.serving import Serving

SWITCH = 'BATCH_PIPELINE_READY_DISCOVERY_CURSOR_ENABLED'
BUDGET = 'BATCH_PIPELINE_READY_DISCOVERY_OWNERS_PER_TICK'


def stock(sim=False, count=5000):
    customer = CustomerData()
    store = SimStore(customer) if sim else MemoryStore()
    owners = sorted(['synthetic-a', 'synthetic-b', 'synthetic-c'], key=owner_key)
    for n, owner in enumerate(owners):
        customer.add_user(owner)
        Scheduler(store).enqueue(item(f's{n}', owner=owner), 10000)
        base = dict(
            store.rows['jobs', f's{n}'],
            state='result_ready',
            ready_at=1,
            available_at=0,
            fresh_capture=n == 2,
            stt_route={'stt_route': 'provider'},
            result={'uri': 'synthetic'},
        )
        for i in range(1 if n == 2 else count):
            row = dict(base, segment_id=f's{n}' if i == 0 else f's{n}-{i}')
            if sim:
                store.apply(('jobs', row['segment_id']), row)
            else:
                store.rows['jobs', row['segment_id']] = row
    return store, owners


@pytest.mark.parametrize('backend', ['memory', 'sim', 'firestore'])
def test_ready_owners_skips_blocks_and_filters(backend, monkeypatch):
    store, owners = stock(backend == 'sim', 5)
    for n, fields in enumerate([{'state': 'leased'}, {'merge_pending': False}]):
        row = dict(store.rows['jobs', 's0'], owner_key=f'z{n}', **fields)
        store.rows['jobs', f'ignored{n}'] = row
    query = Query([v for (t, _), v in store.rows.items() if t == 'jobs'])
    if backend == 'firestore':
        monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
        store = FirestoreStore('batch_pipeline_dev', firestore_client=query)
    expected = [(owner_key(o), o) for o in owners]
    assert store.ready_owners(None, 2) == expected[:2]
    assert store.ready_owners(expected[1][0], 2) == expected[2:]
    assert store.ready_owners(expected[-1][0], 2) == []
    if backend == 'firestore':
        assert len(query.reads) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('sim', [False, True])
@pytest.mark.parametrize('pump', [False, True])
@pytest.mark.parametrize('enabled', [False, True])
async def test_quiet_owner_commits_within_one_pass_without_markers(monkeypatch, sim, pump, enabled):
    monkeypatch.setenv(SWITCH, str(enabled))
    monkeypatch.setenv(BUDGET, '1')
    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED', 'false')
    store, _ = stock(sim)
    service = Pump(Scheduler(store), Mock()) if pump else Serving(store)
    for _ in range(3):
        await tick(service)
    assert (store.rows['jobs', 's2']['state'] == 'committed') == enabled
    assert not any(t == 'merge_holds' for t, _ in store.rows)
    assert sum(v['state'] == 'result_ready' for (t, _), v in store.rows.items() if t == 'jobs') == 10001 - enabled


async def tick(service):
    if isinstance(service, Pump):
        service._last_recovery = float('-inf')
        await service._maintain()
    else:
        service._maintain(recover_quarantine=False)


@pytest.mark.asyncio
async def test_restart_resumes_and_empty_page_wraps(monkeypatch, caplog):
    monkeypatch.setenv(BUDGET, '1')
    store, owners = stock(count=1)
    for n in range(5):
        service = Serving(store)
        service.drain_owner = Mock()
        with caplog.at_level(logging.INFO):
            await tick(service)
        state = store.rows['merge_discovery', 'cursor']
        if n == 0:
            started = state['pass_started_at']
        if n == 3:
            assert state['after_owner_key'] is None and state['pass_started_at'] > started
            service.drain_owner.assert_not_called()
        else:
            service.drain_owner.assert_called_once_with(owners[n % 4])
            assert state['after_owner_key'] == owner_key(owners[n % 4])
    assert 'owners=0 more=0 wrapped=1 source=serving' in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('pump', [False, True])
@pytest.mark.parametrize('operation', ['get', 'put', 'index'])
async def test_cursor_failure_uses_old_page_and_preserves_marker_reoffer(monkeypatch, caplog, pump, operation):
    store, _ = stock(count=1)
    fallback = Mock()
    monkeypatch.setattr(ready_discovery, 'record_fallback', fallback)
    if operation == 'index':
        store.ready_owners = Mock(side_effect=FailedPrecondition('synthetic'))
    else:
        original = getattr(MemoryTransaction, operation)

        def fail(tx, table, *args):
            if table == 'merge_discovery':
                raise TimeoutError('synthetic')
            return original(tx, table, *args)

        monkeypatch.setattr(MemoryTransaction, operation, fail)
    service = Pump(Scheduler(store), Mock()) if pump else Serving(store)
    store.due = Mock(wraps=store.due)
    with caplog.at_level(logging.INFO):
        await tick(service)
    store.due.assert_any_call('result_ready', pytest.approx(time.time(), abs=2), 100)
    assert store.rows['jobs', 's2']['state'] == 'committed'
    assert 'event=batch_merge action=ready_cursor outcome=retry exception_type=' in caplog.text
    fallback.assert_called_once()
    assert caplog.text.count('action=ready_cursor owners=') == 1
    if operation == 'index':
        assert service.ready_discovery.retry_at > time.monotonic() + 299
        await tick(service)
        store.ready_owners.assert_called_once()
