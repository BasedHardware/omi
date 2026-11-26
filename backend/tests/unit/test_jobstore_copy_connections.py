"""Real local pools bound cold erasure concurrency without consuming mirror capacity."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Event, Lock

import pytest

from database.jobstore import connection, copy_connections, dual_store


class Connector:
    def __init__(self):
        self.lock = Lock()
        self.open = self.peak = self.dials = 0
        self.fail_dial = False
        self.fail_statement = False

    def __call__(self):
        with self.lock:
            self.dials += 1
            if self.fail_dial:
                self.fail_dial = False
                raise OSError('synthetic connection failure')
            self.open += 1
            self.peak = max(self.peak, self.open)
        return Conn(self)


class Conn:
    def __init__(self, connector):
        self.connector = connector
        self.closed = False

    def close(self):
        with self.connector.lock:
            assert not self.closed
            self.closed = True
            self.connector.open -= 1

    def execute(self, *_args):
        with self.connector.lock:
            if self.connector.fail_statement:
                self.connector.fail_statement = False
                raise RuntimeError('synthetic SQL failure')
        return self

    @contextmanager
    def transaction(self):
        yield


@pytest.fixture
def configured(monkeypatch):
    connector = Connector()
    monkeypatch.setattr(copy_connections, '_pools', None)
    monkeypatch.setattr(connection, 'iam_connector', lambda *_args: connector)
    monkeypatch.setattr(connection, 'configure', lambda conn: conn)
    monkeypatch.setattr(dual_store, '_SHADOWED', {})
    monkeypatch.setattr(dual_store, 'PURGE_SETTLE_S', 0)
    monkeypatch.setattr(dual_store.importlib.util, 'find_spec', lambda _name: object())
    monkeypatch.setattr(dual_store.DualStore, 'owner_rows', lambda *_args: [])
    for name, value in {
        'JOBSTORE_PG_HOST': 'synthetic-target',
        'JOBSTORE_PG_DATABASE': 'synthetic-database',
        'JOBSTORE_PG_USER': 'synthetic-runtime',
        'BATCH_JOBSTORE_MODE': 'firestore',
        'JOBSTORE_SHADOW_WRITES': 'off',
        'JOBSTORE_PRODUCTION_MIRROR': 'off',
        'JOBSTORE_SHADOW_NAMESPACES': '',
    }.items():
        monkeypatch.setenv(name, value)
    yield connector
    pools = copy_connections._pools
    if pools is not None:
        pools.normal.close()
        pools.erasure.close()
    assert connector.open == 0


def test_factory_is_lazy_and_refuses_a_second_process_target(configured):
    first = dual_store._configured_copy(dual_store._ErasurePrimary('batch_pipeline_prod'))
    second = dual_store._configured_copy(dual_store._ErasurePrimary('batch_pipeline_dev'))
    assert first.shadow.pool is second.shadow.pool
    assert first.erasure_pool is second.erasure_pool
    assert configured.dials == 0
    with pytest.raises(RuntimeError, match='restart required'):
        copy_connections.copy_pools('other-target', 'synthetic-database', 'synthetic-runtime')
    assert configured.dials == 0


@pytest.mark.parametrize('cached', [False, True])
def test_normal_saturation_leaves_one_connection_for_many_cold_purges(configured, monkeypatch, cached):
    first = dual_store._configured_copy(dual_store._ErasurePrimary('batch_pipeline_prod'))
    if cached:
        dual_store._SHADOWED['batch_pipeline_prod'] = first
    entered, release = Event(), Event()
    start = Barrier(9)

    def census(*_args):
        entered.set()
        assert release.wait(3)
        return []

    monkeypatch.setattr(dual_store.DualStore, 'owner_rows', census)

    def purge(index):
        start.wait(timeout=3)
        namespace = 'batch_pipeline_prod' if index % 2 else 'batch_pipeline_dev'
        return dual_store.purge_owner(namespace, f'synthetic-owner-{index}')

    with first.shadow.pool.connection(), first.shadow.pool.connection():
        with pytest.raises(TimeoutError):
            with first.shadow.pool.connection(timeout=0):
                pytest.fail('normal work consumed the erasure reserve')
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(purge, i) for i in range(8)]
            try:
                start.wait(timeout=3)
                assert entered.wait(3)
                assert configured.peak == 3  # two normal sessions plus the reserved erasure session
            finally:
                release.set()
            assert [future.result(timeout=3) for future in futures] == [0] * 8
    assert configured.dials == 3
    # A cold invocation must not close pools borrowed by another namespace or cached mirror.
    with first.shadow.pool.connection(), first.erasure_pool.connection():
        assert configured.dials == 3
        with pytest.raises(TimeoutError):
            with first.erasure_pool.connection(timeout=0):
                pytest.fail('concurrent erasure exceeded the reserved session')
    assert dual_store.purge_owner('batch_pipeline_prod', 'synthetic-retry') == 0


@pytest.mark.parametrize('failure', ['fail_dial', 'fail_statement'])
def test_cold_erasure_failure_raises_and_releases_capacity_for_retry(configured, failure):
    setattr(configured, failure, True)
    with pytest.raises((OSError, RuntimeError), match='synthetic'):
        dual_store.purge_owner('batch_pipeline_prod', 'synthetic-owner')
    assert configured.open == 0
    assert dual_store.purge_owner('batch_pipeline_prod', 'synthetic-owner') == 0
    assert configured.open == configured.peak == 1


@pytest.mark.parametrize('error', [RuntimeError, KeyboardInterrupt])
def test_failed_connection_configuration_closes_each_raw_connection(configured, monkeypatch, error):
    def fail_configuration(_conn):
        raise error('synthetic configuration failure')

    monkeypatch.setattr(connection, 'configure', fail_configuration)
    for _ in range(5):
        with pytest.raises(error, match='configuration failure'):
            dual_store.purge_owner('batch_pipeline_prod', 'synthetic-owner')
        assert configured.open == 0
        assert configured.peak == 1
    assert configured.dials == 5
    monkeypatch.setattr(connection, 'configure', lambda conn: conn)
    assert dual_store.purge_owner('batch_pipeline_prod', 'synthetic-owner') == 0
    assert configured.open == configured.peak == 1


def test_partial_purge_and_cancellation_do_not_consume_the_erasure_reserve(configured, monkeypatch):
    remaining = {('jobs', 'synthetic-erased')}
    monkeypatch.setattr(dual_store.DualStore, 'owner_rows', lambda *_args: sorted(remaining))
    failed = False

    def copy(_self, _conn, keys):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError('synthetic partial purge failure')
        remaining.difference_update(keys)

    monkeypatch.setattr(dual_store.DualStore, 'copy_current', copy)
    with pytest.raises(RuntimeError, match='partial purge'):
        dual_store.purge_owner('batch_pipeline_prod', 'synthetic-owner')
    assert remaining and configured.open == 0
    assert dual_store.purge_owner('batch_pipeline_prod', 'synthetic-owner') == 1
    assert not remaining
    pools = copy_connections.copy_pools('synthetic-target', 'synthetic-database', 'synthetic-runtime')
    with pytest.raises(KeyboardInterrupt):
        with pools.erasure.connection():
            raise KeyboardInterrupt
    assert configured.open == 0
    assert dual_store.purge_owner('batch_pipeline_dev', 'synthetic-owner') == 0
    assert configured.peak == 1
