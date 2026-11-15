"""Index discovery is a hint: routing, sweeps, authority and transport bounds."""

from __future__ import annotations

from contextlib import contextmanager
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import rpc_deadline
from database.jobstore import index_store
from database.jobstore.connection import Pool
from database.jobstore.index_store import IndexStore, BoundedPostgresReader, connection_deadline


@pytest.fixture
def setup(monkeypatch):
    primary = SimpleNamespace(namespace='batch_pipeline_dev', due=Mock(return_value=['firestore']))
    shadow = SimpleNamespace(namespace=primary.namespace, pool=Mock())
    mirror = SimpleNamespace(primary=primary, shadow=shadow)
    clock = [100.0]
    enabled = [True]
    store = IndexStore(
        mirror,
        enabled_queries=index_store.INDEX_QUERIES,
        enabled=lambda: enabled[0],
        sweep_interval_s=60,
        clock=lambda: clock[0],
    )
    read = Mock(return_value=['postgres'])
    monkeypatch.setattr(store._index, 'due', read)
    fallback = Mock()
    monkeypatch.setattr(index_store, 'record_fallback', fallback)
    return SimpleNamespace(
        store=store,
        mirror=mirror,
        primary=primary,
        shadow=shadow,
        clock=clock,
        enabled=enabled,
        read=read,
        fallback=fallback,
    )


@pytest.mark.parametrize('state', ['leased', 'retry', 'result_ready'])
def test_first_read_and_each_safety_interval_expose_dropped_mirror_rows(setup, state):
    setup.primary.due.return_value = ['lost-mirror-row']
    setup.read.return_value = []
    assert setup.store.due(state, 200) == ['lost-mirror-row']
    setup.read.assert_not_called()
    assert setup.store.due(state, 201) == []
    setup.clock[0] += 59.99
    assert setup.store.due(state, 202) == []
    setup.clock[0] += 0.01
    assert setup.store.due(state, 203) == ['lost-mirror-row']
    assert setup.primary.due.call_count == 2


def test_sweep_cadence_is_per_query_and_uses_monotonic_clock(setup):
    assert setup.store.due('leased', 1) == ['firestore']
    assert setup.store.due('retry', -10) == ['firestore']
    assert setup.store.due('result_ready', 999999) == ['firestore']
    assert setup.store.due('retry', -100) == ['postgres']
    setup.clock[0] += 60
    assert setup.store.due('leased', 2) == ['firestore']
    assert setup.store.due('retry', 2) == ['firestore']


def test_failed_sweep_stays_due_and_never_uses_postgres(setup):
    setup.primary.due.side_effect = RuntimeError('Firestore unavailable')
    for _ in range(2):
        with pytest.raises(RuntimeError, match='Firestore unavailable'):
            setup.store.due('retry', 100)
    setup.read.assert_not_called()
    assert not setup.store._last_sweep


@pytest.mark.parametrize('error', [RuntimeError('pg down'), TimeoutError('deadline')])
def test_index_errors_fall_back_and_record_successful_primary_source(setup, error):
    setup.store.due('retry', 200)
    setup.read.side_effect = error
    assert setup.store.due('retry', 200, 9) == ['firestore']
    setup.primary.due.assert_called_with('retry', 200, 9)
    setup.fallback.assert_called_once()
    event = setup.fallback.call_args.kwargs
    assert event['from_mode'] == 'postgres_index'
    assert event['to_mode'] == 'firestore'
    assert event['reason'] == ('timeout' if isinstance(error, TimeoutError) else 'unavailable')
    assert event['outcome'] == 'recovered'


def test_statement_timeout_is_classified_and_primary_failure_is_exhausted(setup):
    setup.store.due('retry', 200)
    error = RuntimeError('statement cancelled')
    error.sqlstate = '57014'
    setup.read.side_effect = error
    setup.primary.due.side_effect = LookupError('primary failed')
    with pytest.raises(LookupError, match='primary failed'):
        setup.store.due('retry', 200)
    assert setup.fallback.call_args.kwargs['reason'] == 'timeout'
    assert setup.fallback.call_args.kwargs['outcome'] == 'exhausted'


def test_live_kill_switch_has_no_index_work_even_before_first_sweep(setup):
    setup.enabled[0] = False
    assert setup.store.due('leased', 100) == ['firestore']
    setup.enabled[0] = True
    assert setup.store.due('leased', 101) == ['postgres']
    setup.enabled[0] = False
    assert setup.store.due('leased', 102) == ['firestore']
    assert setup.read.call_count == 1
    setup.shadow.pool.assert_not_called()


def test_kill_switch_changed_during_pg_read_discards_the_hint(setup):
    setup.store.due('retry', 100)

    def kill(*args):
        setup.enabled[0] = False
        return ['postgres']

    setup.read.side_effect = kill
    assert setup.store.due('retry', 101) == ['firestore']


def test_unselected_and_excluded_states_never_use_the_index(setup):
    store = IndexStore(setup.mirror, enabled_queries={'due_retry'})
    store._index.due = setup.read
    for state in ('leased', 'result_ready', 'record_pending', 'record_recovery_wait', 'future_state'):
        assert store.due(state, 10, 500) == ['firestore']
        setup.primary.due.assert_called_with(state, 10, 500)
    setup.read.assert_not_called()
    setup.shadow.pool.assert_not_called()


def test_unknown_query_is_rejected_and_empty_allowlist_does_no_pg_work(setup):
    with pytest.raises(ValueError, match='audited'):
        IndexStore(setup.mirror, enabled_queries={'projection_page'})
    with pytest.raises(ValueError, match='audited'):
        IndexStore(setup.mirror, enabled_queries={'control_candidates'})
    store = IndexStore(setup.mirror, enabled_queries=set())
    store._index.due = setup.read
    assert store.due('retry', 10) == ['firestore']
    setup.read.assert_not_called()


def test_cursor_page_and_other_reads_keep_the_entire_primary_contract(setup):
    # This includes the exact cursor and empty/short-page semantics. The
    # wrapper must never make this shared method an index-discovery hint.
    cursor = (12.5, 'opaque-cursor')
    result = (['row'], cursor)
    setup.mirror.projection_page = Mock(return_value=result)
    setup.mirror.oldest = Mock(return_value=123)
    setup.mirror.control_candidates = Mock(return_value=['shard'])
    ready_rows = [{'segment_id': 'ready', 'merge_pending': True}]
    setup.mirror.ready_pending = Mock(return_value=ready_rows)
    assert setup.store.projection_page(1, after=cursor, due_before=99) is result
    setup.mirror.projection_page.assert_called_once_with(1, after=cursor, due_before=99)
    assert setup.store.oldest(1) == 123
    assert setup.store.control_candidates(0, 'batch', 100) == ['shard']
    assert setup.store.ready_pending('synthetic-owner-key', 1, after=cursor) is ready_rows
    setup.mirror.ready_pending.assert_called_once_with('synthetic-owner-key', 1, after=cursor)
    setup.read.assert_not_called()


def test_all_mutations_and_transactions_delegate_to_existing_mirror(setup):
    for name in ('run', 'acquire_pull_claim', 'quarantine_fenced', 'purge_owner', 'refresh'):
        method = Mock(return_value=object())
        setattr(setup.mirror, name, method)
        assert getattr(setup.store, name) is method
        assert getattr(setup.store, name)('synthetic') is method.return_value
    setup.read.assert_not_called()


def test_due_does_not_accept_cursor_or_new_query_shapes(setup):
    with pytest.raises(TypeError):
        setup.store.due('retry', 100, after=('cursor',))
    setup.primary.due.assert_not_called()
    setup.read.assert_not_called()


def test_same_namespace_is_required(setup):
    setup.shadow.namespace = 'batch_pipeline_test_other'
    with pytest.raises(ValueError, match='namespace'):
        IndexStore(setup.mirror, enabled_queries={'due_retry'})


@pytest.mark.parametrize('value', [0, -1, float('inf'), float('nan')])
def test_sweep_interval_must_be_positive_finite(setup, value):
    with pytest.raises(ValueError, match='sweep'):
        IndexStore(setup.mirror, enabled_queries={'due_retry'}, sweep_interval_s=value)


@pytest.mark.parametrize('value', [0, -1, 5.01, float('inf'), float('nan')])
def test_read_budget_is_finite_and_bounded(setup, value):
    with pytest.raises(ValueError, match='budget'):
        IndexStore(setup.mirror, enabled_queries={'due_retry'}, read_budget_s=value)


class PollingConnection:
    def __init__(self):
        self.closed = False
        self.statements = []
        self.stall = False

    def wait(self, generator, interval=None):
        try:
            next(generator)
            while True:
                time.sleep(interval or 0.01)
                generator.send(0)
        except StopIteration as result:
            return result.value

    @contextmanager
    def transaction(self):
        yield

    def execute(self, statement):
        self.statements.append(statement)
        if self.stall:
            self.wait(self.stalled())

    @staticmethod
    def stalled():
        while True:
            yield 1

    def close(self):
        self.closed = True


def test_stalled_driver_wait_exits_deadline_closes_generator_and_restores_method():
    conn = PollingConnection()
    original_wait = conn.wait
    closed = []

    def stalled():
        try:
            while True:
                yield 1
        finally:
            closed.append(True)

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        with connection_deadline(conn, started + 0.025):
            conn.wait(stalled())
    assert time.monotonic() - started < 0.25
    assert closed == [True]
    assert conn.wait == original_wait


def test_deadline_already_expired_never_starts_driver_operation():
    conn = PollingConnection()
    began = []

    def operation():
        began.append(True)
        yield 1

    with pytest.raises(TimeoutError):
        with connection_deadline(conn, time.monotonic() - 1):
            conn.wait(operation())
    assert began == []


def test_pool_timeout_is_finite_warm_only_and_never_dials(monkeypatch):
    dial = Mock(side_effect=AssertionError('index attempted a dial'))
    pool = Pool('', size=1, connect=dial)
    reader = BoundedPostgresReader(SimpleNamespace(namespace='batch_pipeline_dev', pool=pool), 0.025)
    with pytest.raises(TimeoutError, match='warm connection'):
        with reader._read_conn():
            pytest.fail('cold pool must not yield')
    dial.assert_not_called()
    assert pool._slots.acquire(blocking=False)
    pool._slots.release()


def test_deadline_discards_connection_and_releases_pool_slot():
    pool = Pool('', size=1, connect=Mock(side_effect=AssertionError('dial')))
    conn = PollingConnection()
    conn.stall = True
    pool._idle.put(conn)
    reader = BoundedPostgresReader(SimpleNamespace(namespace='batch_pipeline_dev', pool=pool), 0.025)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        with reader._read_conn():
            pytest.fail('stalled BEGIN/SET must not yield')
    assert time.monotonic() - started < 0.25
    assert conn.closed
    assert pool._idle.empty()
    assert pool._slots.acquire(blocking=False)
    pool._slots.release()


def test_read_only_statement_timeout_and_outer_deadline():
    pool = Pool('', size=1, connect=Mock(side_effect=AssertionError('dial')))
    conn = PollingConnection()
    pool._idle.put(conn)
    reader = BoundedPostgresReader(SimpleNamespace(namespace='batch_pipeline_dev', pool=pool), 5)
    with rpc_deadline.rpc_deadline(time.monotonic() + 0.1):
        with reader._read_conn():
            pass
    assert conn.statements[0] == 'SET TRANSACTION READ ONLY'
    timeout = int(conn.statements[1].rsplit(' ', 1)[1])
    assert 1 <= timeout <= 100
    assert not conn.closed
    assert pool._idle.qsize() == 1
    with rpc_deadline.rpc_deadline(time.monotonic() - 1):
        with pytest.raises(TimeoutError):
            with reader._read_conn():
                pytest.fail('outer deadline must stop before checkout')
    pool.close()


def test_source_metric_labels_are_finite_even_for_unknown_states(setup):
    before = index_store.INDEX_READS_TOTAL.labels(
        query='due_retry', source='postgres', reason='index', outcome='returned'
    )._value.get()
    setup.store.due('retry', 100)
    setup.store.due('retry', 100)
    assert (
        index_store.INDEX_READS_TOTAL.labels(
            query='due_retry', source='postgres', reason='index', outcome='returned'
        )._value.get()
        == before + 1
    )
    setup.store.due('arbitrary-user-text', 100)
    for metric in index_store.INDEX_READS_TOTAL.collect():
        for sample in metric.samples:
            assert sample.labels['query'] in index_store.INDEX_QUERIES | {'other'}
            assert sample.labels['source'] in {'firestore', 'postgres'}
            assert sample.labels['reason'] in {value.value for value in index_store.IndexReadReason}
            assert sample.labels['outcome'] in {value.value for value in index_store.IndexReadOutcome}


def test_optional_async_parity_observer_sees_each_successful_answer(setup):
    observed = Mock()
    store = IndexStore(
        setup.mirror,
        enabled_queries={'due_retry'},
        clock=lambda: setup.clock[0],
        observe=observed,
    )
    store._index.due = setup.read
    assert store.due('retry', 100, 7) == ['firestore']
    assert store.due('retry', 101, 7) == ['postgres']
    assert observed.call_count == 2
    observed.assert_called_with('due', ('retry', 101, 7), {})
    assert setup.primary.due.call_count == 1
    observed.side_effect = RuntimeError('parity queue failed')
    assert store.due('retry', 102, 7) == ['postgres']
    assert setup.primary.due.call_count == 1
