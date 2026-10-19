"""A2 DualStore: Firestore-primary results, best-effort Postgres mirror, read parity, and fail-closed selection."""

from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

import database.batch_pipeline_store as batch_store
from database.jobstore import dual_store
from database.jobstore.dual_store import SHADOW_PARITY_TOTAL, DualStore, ShadowParityOutcome, compare
from testing.pipeline_sim.store import CustomerData, SimStore


def count(table: str, op: str, outcome: str) -> float:
    return SHADOW_PARITY_TOTAL.labels(table=table, op=op, outcome=outcome)._value.get()


class FakeConn:
    def __init__(self, shadow: 'FakeShadow'):
        self.shadow = shadow
        self.statements: list[str] = []

    def execute(self, sql: str, *args):
        self.statements.append(sql)

    @contextmanager
    def transaction(self):
        staged = dict(self.shadow.rows)
        try:
            yield
        except BaseException:
            self.shadow.rows = staged  # rollback
            raise


class FakePool:
    def __init__(self, shadow: 'FakeShadow'):
        self.shadow = shadow
        self.gate: threading.Event | None = None
        self.fail: BaseException | None = None
        self.waits: list[float] = []

    @contextmanager
    def connection(self, timeout: float = 30.0):
        self.waits.append(timeout)
        if self.gate is not None:
            self.gate.wait(5)
        if self.fail is not None:
            raise self.fail
        yield FakeConn(self.shadow)


class FakeShadow:
    def __init__(self, namespace: str = 'batch_pipeline_dev'):
        self.namespace = namespace
        self.rows: dict[tuple[str, str], dict] = {}
        self.pool = FakePool(self)
        self.write_error: BaseException | None = None

    def read_doc(self, conn, table: str, key: str) -> dict:
        return dict(self.rows.get((table, key), {}))

    def write_doc(self, conn, table: str, key: str, value: dict) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.rows[(table, key)] = value

    def delete_doc(self, conn, table: str, key: str) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.rows.pop((table, key), None)


@pytest.fixture
def stores(monkeypatch):
    monkeypatch.delenv('JOBSTORE_SHADOW_WRITES', raising=False)
    primary = SimStore(CustomerData())
    shadow = FakeShadow()
    store = DualStore(primary, shadow)
    yield primary, shadow, store
    store.drain(5)


def put(store, table, key, value):
    store.run(lambda tx: tx.put(table, key, value))
    assert store.drain(5)


def test_writes_mirror_after_commit_and_reads_match(stores):
    primary, shadow, store = stores
    before = count('queues', 'write', 'mirrored'), count('queues', 'read', 'match')
    put(store, 'queues', 'q1', {'n': 1, 'at': datetime(2026, 10, 19, tzinfo=timezone.utc)})
    assert shadow.rows[('queues', 'q1')] == primary.rows[('queues', 'q1')]
    store.run(lambda tx: tx.get('queues', 'q1'))
    assert store.drain(5)
    assert count('queues', 'write', 'mirrored') == before[0] + 1
    assert count('queues', 'read', 'match') == before[1] + 1


def test_result_is_the_primarys_and_customer_documents_never_mirror(stores):
    primary, shadow, store = stores
    assert store.run(lambda tx: (tx.put('content', 'u/c', {'x': 1}), 'ok')[1]) == 'ok'
    assert store.drain(5)
    assert ('content', 'u/c') in primary.rows and not shadow.rows


def test_read_parity_outcomes(stores):
    primary, shadow, store = stores
    put(store, 'owners', 'o1', {'v': 1})
    shadow.rows[('owners', 'o1')] = {'v': 2}  # drift
    primary.rows[('owners', 'o2')] = {'v': 1}  # written before the shadow started
    shadow.rows[('owners', 'o3')] = {'v': 1}  # Postgres-only
    before = {o: count('owners', 'read', o) for o in ('mismatch', 'missing', 'extra')}
    store.run(lambda tx: [tx.get('owners', k) for k in ('o1', 'o2', 'o3')])
    assert store.drain(5)
    assert {o: count('owners', 'read', o) - before[o] for o in before} == {'mismatch': 1, 'missing': 1, 'extra': 1}


def test_reads_after_own_write_are_not_pre_images(stores):
    _, _, store = stores
    before = count('gpus', 'read', 'missing')
    store.run(lambda tx: (tx.put('gpus', 'g', {'a': 1}), tx.get('gpus', 'g')))
    assert store.drain(5)
    assert count('gpus', 'read', 'missing') == before


def test_a_failed_body_mirrors_nothing(stores):
    _, shadow, store = stores

    def body(tx):
        tx.put('queues', 'q', {'a': 1})
        raise RuntimeError('boom')

    with pytest.raises(RuntimeError):
        store.run(body)
    assert store.drain(5) and not shadow.rows


def test_only_the_committed_attempt_is_mirrored():
    class RetryingPrimary(SimStore):
        def run(self, body):
            from testing.pipeline_sim.store import SimTransaction

            body(SimTransaction(self))  # an aborted attempt, never flushed
            return super().run(body)

    calls = iter(['first', 'second'])
    shadow = FakeShadow()
    store = DualStore(RetryingPrimary(CustomerData()), shadow)
    store.run(lambda tx: tx.put('queues', next(calls), {'a': 1}))
    assert store.drain(5)
    assert set(shadow.rows) == {('queues', 'second')}


def test_kill_switch_off_skips_the_mirror(stores, monkeypatch):
    _, shadow, store = stores
    monkeypatch.setenv('JOBSTORE_SHADOW_WRITES', 'false')
    before = count('queues', 'write', 'skipped')
    put(store, 'queues', 'q', {'a': 1})
    assert not shadow.rows and count('queues', 'write', 'skipped') == before + 1


@pytest.mark.parametrize(
    'failure, outcome',
    [(TimeoutError('pool'), 'timeout'), (type('Canceled', (Exception,), {'sqlstate': '57014'})(), 'timeout'),
     (RuntimeError('down'), 'error')],
)  # fmt: skip
def test_shadow_failures_are_counted_never_raised(stores, failure, outcome):
    primary, shadow, store = stores
    shadow.write_error = failure
    before = count('jobs', 'write', outcome)
    assert store.run(lambda tx: (tx.put('queues', 'x', {'a': 1}), 7)[1]) == 7
    put(store, 'owners', 'o', {'a': 1})
    assert ('owners', 'o') in primary.rows and not shadow.rows
    assert count('owners', 'write', outcome) >= 1 and count('jobs', 'write', outcome) == before


def test_mirror_is_bounded(stores):
    _, shadow, store = stores
    conn_statements = []
    real = FakeConn.execute

    def spy(self, sql, *args):
        conn_statements.append(sql)
        return real(self, sql, *args)

    FakeConn.execute = spy
    try:
        put(store, 'queues', 'q', {'a': 1})
    finally:
        FakeConn.execute = real
    assert shadow.pool.waits == [0.2]
    assert conn_statements == ['SET LOCAL statement_timeout = 200']


def test_full_queue_drops_without_blocking_the_caller():
    shadow = FakeShadow()
    shadow.pool.gate = threading.Event()
    store = DualStore(SimStore(CustomerData()), shadow, queue_limit=1)
    before = count('artifacts', 'write', 'dropped')
    for i in range(4):
        store.run(lambda tx, i=i: tx.put('artifacts', f'r{i}', {'i': i}))
    shadow.pool.gate.set()
    assert store.drain(5)
    # One in flight on the worker, one queued; the rest dropped.
    assert count('artifacts', 'write', 'dropped') - before >= 2
    assert len(shadow.rows) <= 2


def test_mirror_thread_never_sees_request_context():
    marker: contextvars.ContextVar[str | None] = contextvars.ContextVar('request_uid', default=None)
    seen = []
    shadow = FakeShadow()
    real_write = shadow.write_doc
    shadow.write_doc = lambda *a: (seen.append(marker.get()), real_write(*a))  # type: ignore[method-assign]
    store = DualStore(SimStore(CustomerData()), shadow)
    marker.set('caller-state')
    store.run(lambda tx: tx.put('queues', 'q', {'a': 1}))
    assert store.drain(5)
    assert seen == [None]


def test_namespace_must_match():
    with pytest.raises(ValueError):
        DualStore(SimStore(CustomerData()), FakeShadow('batch_pipeline_prod'))


def test_compare():
    at = datetime(2026, 10, 19, 1, 2, 3, tzinfo=timezone.utc)
    assert compare({}, {}) is ShadowParityOutcome.MATCH
    assert compare({'a': 1, 'b': at}, {'b': at, 'a': 1}) is ShadowParityOutcome.MATCH
    assert compare({'a': 1}, {'a': 1.5}) is ShadowParityOutcome.MISMATCH
    assert compare({'a': {1}}, {'a': 1}) is ShadowParityOutcome.UNCOMPARABLE


class TestSelection:
    def primary(self, namespace='batch_pipeline_dev'):
        return SimStore(CustomerData(), namespace=namespace)

    def configure(self, monkeypatch, mode='shadow'):
        monkeypatch.setattr(dual_store, '_SHADOWED', {})
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', mode)
        monkeypatch.setenv('JOBSTORE_PG_HOST', '10.0.0.1')
        monkeypatch.setenv('JOBSTORE_PG_DATABASE', 'jobstore_staging')
        monkeypatch.setenv('JOBSTORE_PG_USER', 'svc@example.iam')

    def test_default_is_firestore_only(self, monkeypatch):
        monkeypatch.delenv('BATCH_JOBSTORE_MODE', raising=False)
        primary = self.primary()
        assert dual_store.shadow_from_env(primary) is primary

    @pytest.mark.parametrize('mode', ['firestore', 'postgres_primary', 'postgres', 'bogus'])
    def test_other_modes_do_not_shadow(self, monkeypatch, mode):
        self.configure(monkeypatch, mode)
        primary = self.primary()
        assert dual_store.shadow_from_env(primary) is primary

    def test_prod_namespace_is_refused(self, monkeypatch):
        self.configure(monkeypatch)
        primary = self.primary('batch_pipeline_prod')
        assert dual_store.shadow_from_env(primary) is primary

    def test_unconfigured_fails_closed(self, monkeypatch):
        self.configure(monkeypatch)
        monkeypatch.delenv('JOBSTORE_PG_HOST')
        primary = self.primary()
        assert dual_store.shadow_from_env(primary) is primary

    def test_missing_driver_fails_closed(self, monkeypatch):
        self.configure(monkeypatch)
        real = dual_store.importlib.util.find_spec
        monkeypatch.setattr(
            dual_store.importlib.util, 'find_spec', lambda name, *a: None if name == 'psycopg' else real(name, *a)
        )
        primary = self.primary()
        assert dual_store.shadow_from_env(primary) is primary

    def test_shadow_mode_wraps_without_dialing(self, monkeypatch):
        self.configure(monkeypatch)
        primary = self.primary()
        store = dual_store.shadow_from_env(primary)
        assert isinstance(store, DualStore) and store.primary is primary
        assert store.shadow.namespace == 'batch_pipeline_dev'
        assert store.namespace == 'batch_pipeline_dev'  # delegated

    def test_one_shadow_per_namespace(self, monkeypatch):
        self.configure(monkeypatch)
        first = dual_store.shadow_from_env(self.primary())
        assert dual_store.shadow_from_env(self.primary()) is first
        assert dual_store.shadow_from_env(self.primary('batch_pipeline_test_other')) is not first


class TestRefresh:
    """Writers outside Store.run (projection apply, purge) re-copy their documents after commit."""

    def test_refresh_copies_a_bypass_write_and_deletes_a_bypass_delete(self, stores):
        primary, shadow, store = stores
        put(store, 'queues', 'gone', {'a': 1})
        primary.rows[('jobs', 'j')] = {'client_status': 'completed'}  # written outside Store.run
        primary.rows.pop(('queues', 'gone'))  # deleted outside Store.run
        before = count('jobs', 'refresh', 'mirrored')
        store.refresh([('jobs', 'j'), ('queues', 'gone'), ('content', 'u/c')])
        assert store.drain(5)
        assert shadow.rows == {('jobs', 'j'): {'client_status': 'completed'}}
        assert count('jobs', 'refresh', 'mirrored') == before + 1

    def test_refresh_failures_are_counted_never_raised(self, stores):
        primary, shadow, store = stores
        shadow.write_error = RuntimeError('down')
        primary.rows[('owners', 'o')] = {'a': 1}
        before = count('owners', 'refresh', 'error')
        store.refresh([('owners', 'o')])
        assert store.drain(5)
        assert count('owners', 'refresh', 'error') == before + 1 and not shadow.rows

    def test_refresh_respects_the_kill_switch(self, stores, monkeypatch):
        primary, shadow, store = stores
        monkeypatch.setenv('JOBSTORE_SHADOW_WRITES', 'off')
        primary.rows[('owners', 'o')] = {'a': 1}
        before = count('owners', 'refresh', 'skipped')
        store.refresh([('owners', 'o')])
        assert store.drain(5) and not shadow.rows
        assert count('owners', 'refresh', 'skipped') == before + 1


class TestMirrorRefreshHook:
    def test_firestore_mode_is_a_strict_no_op(self, monkeypatch):
        monkeypatch.delenv('BATCH_JOBSTORE_MODE', raising=False)
        monkeypatch.setattr(batch_store, 'FirestoreStore', lambda *a, **k: pytest.fail('constructed a store'))
        monkeypatch.setattr(dual_store, 'shadow_from_env', lambda *a: pytest.fail('consulted the shadow'))
        dual_store.mirror_refresh('batch_pipeline_dev', [('jobs', 'j')])

    def test_shadow_mode_refreshes_through_the_process_shadow(self, monkeypatch):
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
        monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
        primary, shadow = SimStore(CustomerData()), FakeShadow()
        store = DualStore(primary, shadow)
        monkeypatch.setattr(dual_store, 'shadow_from_env', lambda _primary: store)
        primary.rows[('jobs', 'j')] = {'a': 1}
        dual_store.mirror_refresh('batch_pipeline_dev', [('jobs', 'j')])
        assert store.drain(5)
        assert shadow.rows == {('jobs', 'j'): {'a': 1}}

    def test_hook_never_raises(self, monkeypatch):
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
        monkeypatch.setattr(dual_store, 'shadow_from_env', lambda _primary: (_ for _ in ()).throw(RuntimeError('x')))
        dual_store.mirror_refresh('batch_pipeline_dev', [('jobs', 'j')])


class TestLightHook:
    """database.batch_pipeline_shadow_hook: what projection and purge import."""

    def test_firestore_mode_never_reaches_the_job_store(self, monkeypatch):
        from database import batch_pipeline_shadow_hook as hook

        monkeypatch.delenv('BATCH_JOBSTORE_MODE', raising=False)
        monkeypatch.setattr(dual_store, 'mirror_refresh', lambda *a: pytest.fail('reached the job store'))
        hook.mirror_refresh('batch_pipeline_dev', [('jobs', 'j')])

    def test_prod_is_refused_even_in_shadow_mode(self, monkeypatch):
        from database import batch_pipeline_shadow_hook as hook

        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
        monkeypatch.setattr(dual_store, 'mirror_refresh', lambda *a: pytest.fail('reached the job store'))
        hook.mirror_refresh('batch_pipeline_prod', [('jobs', 'j')])

    def test_shadow_mode_delegates_and_never_raises(self, monkeypatch):
        from database import batch_pipeline_shadow_hook as hook

        calls = []
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
        monkeypatch.setattr(dual_store, 'mirror_refresh', lambda ns, keys: calls.append((ns, keys)))
        hook.mirror_refresh('batch_pipeline_dev', iter([('jobs', 'j')]))
        assert calls == [('batch_pipeline_dev', [('jobs', 'j')])]
        monkeypatch.setattr(dual_store, 'mirror_refresh', lambda *a: (_ for _ in ()).throw(RuntimeError('x')))
        hook.mirror_refresh('batch_pipeline_dev', [('jobs', 'j')])
