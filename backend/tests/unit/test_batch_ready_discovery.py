"""Owner-grain discovery, durable progress and the held-backlog saturation regression."""

import logging
import time
from types import SimpleNamespace
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


@pytest.mark.parametrize('sim', [False, True])
def test_stale_serving_page_preserves_pump_progress_and_reaches_fresh(monkeypatch, sim):
    monkeypatch.setenv(SWITCH, 'true')
    monkeypatch.setenv(BUDGET, '1')
    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED', 'false')
    store, owners = stock(sim)
    service = Serving(store)
    serving = ready_discovery.ReadyDiscovery(store, 'serving')
    pump = ready_discovery.ReadyDiscovery(store, 'pump')
    stale = serving.page()
    for expected in owners[:2]:
        page = pump.page()
        assert [owner for _, owner in pump.owners(page)] == [expected]
        service.drain_owner(expected)
        assert pump.finish(page)
    progress = store.run(lambda tx: tx.get('merge_discovery', 'cursor'))
    assert progress['after_owner_key'] == owner_key(owners[1])
    for _, owner in serving.owners(stale):
        service.drain_owner(owner)
    assert serving.finish(stale)
    assert store.run(lambda tx: tx.get('merge_discovery', 'cursor')) == progress
    page = pump.page()
    assert [owner for _, owner in pump.owners(page)] == owners[2:]
    service.drain_owner(owners[2])
    assert pump.finish(page)
    assert store.rows['jobs', 's2']['state'] == 'committed'
    assert store.rows['jobs', 's0']['state'] == store.rows['jobs', 's1']['state'] == 'result_ready'


def test_stale_wrap_cannot_replace_a_new_pass_with_the_same_start_time(monkeypatch):
    monkeypatch.setenv(BUDGET, '1')
    monkeypatch.setattr(ready_discovery, 'time', SimpleNamespace(monotonic=time.monotonic, time=lambda: 10.0))
    store, _ = stock(count=1)
    pump = ready_discovery.ReadyDiscovery(store, 'pump')
    serving = ready_discovery.ReadyDiscovery(store, 'serving')

    def advance():
        page = pump.page()
        list(pump.owners(page))
        assert pump.finish(page)

    advance()
    advance()
    stale = serving.page()
    advance()  # Wrap the first pass.
    advance()
    advance()  # Same position and pass_started_at, but in a new pass.
    progress = store.run(lambda tx: tx.get('merge_discovery', 'cursor'))
    list(serving.owners(stale))
    assert stale['wrapped'] == 1
    assert serving.finish(stale)
    assert store.run(lambda tx: tx.get('merge_discovery', 'cursor')) == progress
    assert stale['wrapped'] == 0, 'a rejected stale write must not claim a published wrap'


@pytest.mark.parametrize('revision', [None, True, -1, '1'])
def test_malformed_cursor_revision_falls_back_without_writing(revision):
    store = MemoryStore()
    original = {'revision': revision}
    store.rows['merge_discovery', 'cursor'] = original.copy()
    assert ready_discovery.ReadyDiscovery(store, 'serving').page() is None
    assert store.rows['merge_discovery', 'cursor'] == original


def stock(sim=False, count=51):
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
    assert store.ready_owners(None, 1, descending=True) == expected[-1:]
    assert store.ready_owners(None, 3, ceiling_owner_key=expected[1][0]) == expected[:2]
    if backend == 'firestore':
        assert len(query.reads) == 6


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
    # Two held owners with 51 rows each fill the old 100-row page, so one tick shows the old path's miss;
    # the cursor visits one owner per tick and needs all three.
    for _ in range(3 if enabled else 1):
        await tick(service)
    assert (store.rows['jobs', 's2']['state'] == 'committed') == enabled
    assert not any(t == 'merge_holds' for t, _ in store.rows)
    assert sum(v['state'] == 'result_ready' for (t, _), v in store.rows.items() if t == 'jobs') == 103 - enabled


async def tick(service):
    if isinstance(service, Pump):
        service._last_recovery = float('-inf')
        await service._maintain()
    else:
        service._maintain(recover_quarantine=False)


@pytest.mark.asyncio
async def test_restart_resumes_and_last_owner_wraps(monkeypatch, caplog):
    monkeypatch.setenv(BUDGET, '1')
    store, owners = stock(count=1)
    for n in range(4):
        service = Serving(store)
        service.drain_owner = Mock()
        with caplog.at_level(logging.INFO):
            await tick(service)
        state = store.rows['merge_discovery', 'cursor']
        if n == 0:
            started = state['pass_started_at']
        service.drain_owner.assert_called_once_with(owners[n % 3])
        if n == 2:
            assert state['after_owner_key'] is None and state['ceiling_owner_key'] is None
        else:
            assert state['after_owner_key'] == owner_key(owners[n % 3])
        if n == 3:
            assert state['pass_started_at'] > started
    assert 'owners=1 more=0 wrapped=1 source=serving' in caplog.text


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
    assert (
        f'event=batch_merge action=ready_cursor outcome={"retry" if operation == "index" else "error"} exception_type='
        in caplog.text
    )
    assert fallback.call_args.kwargs['reason'] == ('unavailable' if operation == 'index' else 'other')
    if operation != 'index':
        assert any(r.levelno == logging.ERROR and 'outcome=error' in r.message for r in caplog.records)
    fallback.assert_called_once()
    assert caplog.text.count('action=ready_cursor owners=') == 1
    if operation == 'index':
        assert service.ready_discovery.retry_at > time.monotonic() + 299
        await tick(service)
        store.ready_owners.assert_called_once()


@pytest.mark.parametrize('budget', [1, 2])
def test_new_owners_do_not_extend_pass_and_behind_cursor_waits(monkeypatch, budget):
    monkeypatch.setenv(BUDGET, str(budget))
    store = MemoryStore()
    for key in ('b', 'd', 'f'):
        store.rows['jobs', key] = dict(owner_key=key, owner_id='synthetic', state='result_ready', merge_pending=True)
    discovery = ready_discovery.ReadyDiscovery(store, 'test')
    seen = []
    for n in range((3 + budget - 1) // budget):
        page = discovery.page()
        seen.extend(key for key, _ in discovery.owners(page))
        assert discovery.finish(page)
        assert page['wrapped'] == (n == (3 + budget - 1) // budget - 1)
        for key in ('a', f'z{n}'):
            store.rows['jobs', key] = dict(store.rows['jobs', 'b'], owner_key=key)
    assert seen == ['b', 'd', 'f']
    assert store.rows['merge_discovery', 'cursor']['ceiling_owner_key'] is None
    seen = []
    while True:
        page = discovery.page()
        seen.extend(key for key, _ in discovery.owners(page))
        discovery.finish(page)
        if page['wrapped']:
            break
    assert seen == sorted(key for table, key in store.rows if table == 'jobs')


@pytest.mark.asyncio
@pytest.mark.parametrize('pump', [False, True])
@pytest.mark.parametrize('slow', ['query', 'drain'])
async def test_tick_deadline_preserves_undrained_owners(monkeypatch, caplog, pump, slow):
    from types import SimpleNamespace

    store, owners = stock(count=1)
    clock = [0]
    monkeypatch.setattr(ready_discovery, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=time.time))
    monkeypatch.setenv('BATCH_PIPELINE_READY_DISCOVERY_TICK_SECONDS', '1')
    service = Pump(Scheduler(store), Mock()) if pump else Serving(store)
    visited = []

    def drain(owner):
        visited.append(owner)
        if slow == 'drain':
            clock[0] += 1

    original = store.ready_owners

    def seek(*args, **kwargs):
        result = original(*args, **kwargs)
        if slow == 'query' and not kwargs.get('descending'):
            clock[0] += 1
        return result

    store.ready_owners = seek
    if pump:

        async def async_drain(owner):
            drain(owner)

        service.drain_owner = async_drain
    else:
        service.drain_owner = drain
    with caplog.at_level(logging.INFO):
        await tick(service)
    state = store.rows['merge_discovery', 'cursor']
    assert visited == (owners[:1] if slow == 'drain' else [])
    assert state['after_owner_key'] == (owner_key(owners[0]) if visited else None)
    assert 'budget_spent=1' in caplog.text
    store.ready_owners = original
    await tick(service)
    assert visited == (owners[:2] if slow == 'drain' else owners)


def test_missing_owner_count_and_empty_ceiling(caplog):
    store, _ = stock(count=1)
    for (table, _), row in store.rows.items():
        if table == 'jobs':
            row.pop('owner_id')
    discovery = ready_discovery.ReadyDiscovery(store, 'test')
    with caplog.at_level(logging.INFO):
        page = discovery.page()
        assert list(discovery.owners(page)) == []
        assert discovery.finish(page)
        store.rows.clear()
        page = discovery.page()
        assert list(discovery.owners(page)) == []
        assert discovery.finish(page)
    assert 'missing_owner_id=3' in caplog.text
    assert 'owners=0 more=0 wrapped=1' in caplog.text


def test_a_cursor_read_that_spends_the_tick_defers_the_ceiling_query(monkeypatch, caplog):
    """The pass start (one descending query) must not run after the tick budget is gone."""
    from types import SimpleNamespace

    store, owners = stock(count=1)
    clock = [0]
    monkeypatch.setattr(ready_discovery, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=time.time))
    monkeypatch.setenv('BATCH_PIPELINE_READY_DISCOVERY_TICK_SECONDS', '1')
    service = Serving(store)
    service.drain_owner = Mock()
    seeks = []
    original, run = store.ready_owners, store.run
    store.ready_owners = lambda *args, **kwargs: seeks.append(kwargs) or original(*args, **kwargs)

    def slow_read(body):
        result = run(body)
        clock[0] += 1  # every store transaction, the cursor read included, uses a whole budget
        return result

    monkeypatch.setattr(store, 'run', slow_read)
    with caplog.at_level(logging.INFO):
        service._maintain(recover_quarantine=False)
    assert not seeks and not service.drain_owner.called
    state = store.rows['merge_discovery', 'cursor']
    assert not state.get('ceiling_owner_key') and not state.get('after_owner_key')
    assert 'owners=0 more=1 wrapped=0' in caplog.text and 'budget_spent=1' in caplog.text
    # The next tick, inside its budget, starts the pass.
    monkeypatch.setattr(store, 'run', run)
    service._maintain(recover_quarantine=False)
    assert seeks and seeks[0].get('descending') is True
    service.drain_owner.assert_called()


@pytest.mark.parametrize('permanent', [True, False])
def test_a_permanent_api_error_is_logged_as_an_error_not_an_outage(permanent, caplog):
    from google.api_core.exceptions import PermissionDenied, ServiceUnavailable

    discovery = ready_discovery.ReadyDiscovery(Mock(), 'serving')
    with caplog.at_level(logging.WARNING):
        discovery.retry(PermissionDenied('no') if permanent else ServiceUnavailable('later'))
    assert ('outcome=error' in caplog.text) == permanent
    assert ('outcome=retry' in caplog.text) != permanent
