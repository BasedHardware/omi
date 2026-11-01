"""A2 DualStore: Firestore-primary results, best-effort Postgres mirror, read parity, and fail-closed selection."""

from __future__ import annotations

import contextvars
import threading
import time
from unittest.mock import Mock
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
    assert conn_statements == [
        'SET LOCAL statement_timeout = 200',
        'SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))',  # per-key, inside the bounded transaction
    ]


def _held(store):
    """Hold this store's mirrors (as if its worker were busy) and return the captured commit views."""
    views = []
    store._after_commit = views.append
    return views


def test_a_late_mirror_of_an_older_commit_cannot_overwrite_a_newer_one():
    # M1 L12-1: two committers can queue in the reverse of the commit order (or run on two instances).
    primary, shadow = SimStore(CustomerData()), FakeShadow()
    store = DualStore(primary, shadow, inline=True)
    views = _held(store)
    store.run(lambda tx: tx.put('owners', 'o', {'v': 1}))
    store.run(lambda tx: tx.put('owners', 'o', {'v': 2}))
    del store._after_commit
    for view in reversed(views):  # the newer commit's mirror lands first, the older one last
        store._after_commit(view)
    assert shadow.rows[('owners', 'o')] == {'v': 2}


def test_a_late_mirror_cannot_resurrect_a_purged_document():
    primary, shadow = SimStore(CustomerData()), FakeShadow()
    store = DualStore(primary, shadow, inline=True)
    views = _held(store)
    store.run(lambda tx: tx.put('control', 'c', {'v': 1}))
    del store._after_commit
    primary.rows.pop(('control', 'c'))  # a purge outside Store.run, then its refresh
    store.refresh([('control', 'c')])
    store._after_commit(views[0])  # the pre-purge commit's mirror arrives late
    assert ('control', 'c') not in shadow.rows


def test_mirror_locks_every_key_in_one_sorted_order():
    primary, shadow = SimStore(CustomerData()), FakeShadow()
    store = DualStore(primary, shadow, inline=True)
    locked = []
    real = FakeConn.execute

    def spy(self, sql, *args):
        if 'advisory' in sql:
            locked.append(args[0][0])
        return real(self, sql, *args)

    FakeConn.execute = spy
    try:
        store.run(
            lambda tx: (
                tx.put('queues', 'b', {'a': 1}),
                tx.put('owners', 'z', {'a': 1}),
                tx.put('queues', 'a', {'a': 1}),
            )
        )
    finally:
        FakeConn.execute = real
    ns = shadow.namespace
    assert locked == [f'{ns}/owners/z', f'{ns}/queues/a', f'{ns}/queues/b']


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
        monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
        monkeypatch.delenv('FIRESTORE_DATABASE_ID', raising=False)
        primary = self.primary('batch_pipeline_prod')
        assert dual_store.shadow_from_env(primary) is primary

    def test_prod_namespace_on_the_staging_db_id_without_the_staging_flag_is_refused(self, monkeypatch):
        self.configure(monkeypatch)
        monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
        monkeypatch.setenv('FIRESTORE_DATABASE_ID', 'staging')
        primary = self.primary('batch_pipeline_prod')
        assert dual_store.shadow_from_env(primary) is primary

    def test_staging_on_the_staging_db_admits_the_prod_namespace(self, monkeypatch):
        """L02-2: staging keeps the worker namespace batch_pipeline_prod; its A2 parity read must measure."""
        self.configure(monkeypatch)
        monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
        monkeypatch.setenv('FIRESTORE_DATABASE_ID', 'staging')
        primary = self.primary('batch_pipeline_prod')
        store = dual_store.shadow_from_env(primary)
        assert isinstance(store, DualStore) and store.primary is primary
        assert store.shadow.namespace == 'batch_pipeline_prod'

    @pytest.mark.parametrize('database_id', [None, '', '(default)', 'prod', ' Staging'])
    def test_staging_flag_on_a_non_staging_db_is_refused(self, monkeypatch, database_id):
        self.configure(monkeypatch)
        monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
        if database_id is None:
            monkeypatch.delenv('FIRESTORE_DATABASE_ID', raising=False)
        else:
            monkeypatch.setenv('FIRESTORE_DATABASE_ID', database_id)
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

    @pytest.mark.parametrize(
        'deployment, database_id',
        [(None, None), (None, 'staging'), ('staging', None), ('staging', '(default)')],
        ids=['prod', 'staging-db-id-without-flag', 'staging-flag-without-db-id', 'staging-flag-on-default-db'],
    )
    def test_prod_namespace_is_refused_outside_the_staging_db(self, monkeypatch, deployment, database_id):
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
        for name, value in (('OMI_DEPLOYMENT', deployment), ('FIRESTORE_DATABASE_ID', database_id)):
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)
        monkeypatch.setattr(batch_store, 'FirestoreStore', lambda *a, **k: pytest.fail('constructed a store'))
        monkeypatch.setattr(dual_store, 'shadow_from_env', lambda *a: pytest.fail('consulted the shadow'))
        dual_store.mirror_refresh('batch_pipeline_prod', [('jobs', 'j')])

    def test_staging_on_the_staging_db_refreshes_the_prod_namespace(self, monkeypatch):
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
        monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
        monkeypatch.setenv('FIRESTORE_DATABASE_ID', 'staging')
        monkeypatch.setenv('OMI_ENV_STAGE', 'prod')  # staging takes prod code paths
        primary, shadow = SimStore(CustomerData(), namespace='batch_pipeline_prod'), FakeShadow('batch_pipeline_prod')
        store = DualStore(primary, shadow)
        monkeypatch.setattr(dual_store, '_SHADOWED', {})
        monkeypatch.setattr(dual_store, 'shadow_from_env', lambda _primary: store)
        primary.rows[('jobs', 'j')] = {'a': 1}
        dual_store.mirror_refresh('batch_pipeline_prod', [('jobs', 'j')])
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
        monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
        monkeypatch.delenv('FIRESTORE_DATABASE_ID', raising=False)
        monkeypatch.setattr(dual_store, 'mirror_refresh', lambda *a: pytest.fail('reached the job store'))
        hook.mirror_refresh('batch_pipeline_prod', [('jobs', 'j')])

    def test_staging_flag_on_a_non_staging_db_is_refused(self, monkeypatch):
        from database import batch_pipeline_shadow_hook as hook

        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
        monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
        monkeypatch.setenv('FIRESTORE_DATABASE_ID', '(default)')
        monkeypatch.setattr(dual_store, 'mirror_refresh', lambda *a: pytest.fail('reached the job store'))
        hook.mirror_refresh('batch_pipeline_prod', [('jobs', 'j')])

    def test_staging_on_the_staging_db_delegates_the_prod_namespace(self, monkeypatch):
        from database import batch_pipeline_shadow_hook as hook

        calls = []
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
        monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
        monkeypatch.setenv('FIRESTORE_DATABASE_ID', 'staging')
        monkeypatch.setattr(dual_store, 'mirror_refresh', lambda ns, keys: calls.append((ns, keys)))
        hook.mirror_refresh('batch_pipeline_prod', [('jobs', 'j')])
        assert calls == [('batch_pipeline_prod', [('jobs', 'j')])]

    def test_shadow_mode_delegates_and_never_raises(self, monkeypatch):
        from database import batch_pipeline_shadow_hook as hook

        calls = []
        monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
        monkeypatch.setattr(dual_store, 'mirror_refresh', lambda ns, keys: calls.append((ns, keys)))
        hook.mirror_refresh('batch_pipeline_dev', iter([('jobs', 'j')]))
        assert calls == [('batch_pipeline_dev', [('jobs', 'j')])]
        monkeypatch.setattr(dual_store, 'mirror_refresh', lambda *a: (_ for _ in ()).throw(RuntimeError('x')))
        hook.mirror_refresh('batch_pipeline_dev', [('jobs', 'j')])


class TestParityDiagnostics:
    """Non-matching reads are logged with a hashed key and field names only; failures name their phase."""

    @pytest.fixture(autouse=True)
    def fresh_window(self, monkeypatch):
        monkeypatch.setattr(dual_store, '_diag_window', [0.0, 0])

    @staticmethod
    def lines(caplog) -> list[str]:
        return [r.getMessage() for r in caplog.records if 'event=jobstore_shadow_parity' in r.getMessage()]

    def test_a_drifted_read_logs_hash_and_field_names_never_the_key_or_values(self, stores, caplog):
        primary, shadow, store = stores
        put(store, 'owners', 'uid-SECRET-1', {'lease_until': 5.0, 'token': 'tok-SECRET'})
        shadow.rows[('owners', 'uid-SECRET-1')] = {'lease_until': 6.0, 'token': 'tok-SECRET'}
        caplog.set_level('WARNING', logger='database.jobstore.dual_store')
        store.run(lambda tx: tx.get('owners', 'uid-SECRET-1'))
        assert store.drain(5)
        (line,) = self.lines(caplog)
        expected_hash = dual_store.key_hash('batch_pipeline_dev', 'owners', 'uid-SECRET-1')
        assert line == (
            'event=jobstore_shadow_parity outcome=mismatch namespace=batch_pipeline_dev table=owners '
            f'key={expected_hash} fields=lease_until current=shadow_differs'
        )
        assert 'SECRET' not in ' '.join(r.getMessage() for r in caplog.records)

    def test_mirror_lag_reproduces_a_mismatch_marked_shadow_current(self, caplog):
        """Hypothesis: a hot key written again before the earlier commit's mirror runs. That mirror copies the
        primary's CURRENT state (L12-1), so the next commit's pre-image is older than Postgres: a mismatch even
        though Postgres equals Firestore. One process, one mirror thread: no second replica needed."""
        primary, shadow = SimStore(CustomerData()), FakeShadow()
        store = DualStore(primary, shadow, inline=True)
        views = _held(store)
        store.run(lambda tx: tx.put('control', 'c', {'p0_service': 1.0}))
        store.run(lambda tx: tx.put('control', 'c', {'p0_service': tx.get('control', 'c')['p0_service'] + 1}))
        del store._after_commit
        before = count('control', 'read', 'mismatch')
        caplog.set_level('WARNING', logger='database.jobstore.dual_store')
        for view in views:  # in commit order
            store._after_commit(view)
        assert count('control', 'read', 'mismatch') == before + 1
        assert shadow.rows[('control', 'c')] == primary.rows[('control', 'c')]
        (line,) = self.lines(caplog)
        assert 'table=control' in line and 'fields=p0_service' in line and line.endswith('current=shadow_current')

    def test_missing_is_logged_and_rate_limited(self, stores, caplog, monkeypatch):
        primary, _, store = stores
        monkeypatch.setattr(dual_store, 'DIAG_LINES_PER_MINUTE', 2)
        for i in range(4):
            primary.rows[('jobs', f'j{i}')] = {'state': 'ready'}
        caplog.set_level('WARNING', logger='database.jobstore.dual_store')
        store.run(lambda tx: [tx.get('jobs', f'j{i}') for i in range(4)])
        assert store.drain(5)
        lines = self.lines(caplog)
        assert len(lines) == 2 and all('outcome=missing' in x and 'fields=state' in x for x in lines)

    def test_differing_fields_hide_dynamic_names_and_cap_the_list(self):
        assert dual_store.differing_fields({'a': 1, 'b': 2}, {'a': 1, 'b': 3}) == 'b'
        assert dual_store.differing_fields({'uid-ABC/x': 1}, {}) == 'other'
        many = {f'f{i:02d}': i for i in range(10)}
        assert dual_store.differing_fields(many, {}) == ','.join(f'f{i:02d}' for i in range(8)) + ',+2'
        assert dual_store.differing_fields({'a': {1}}, {'a': 1}) == 'a'

    def test_refresh_failure_names_phase_and_error_class(self, stores, caplog, monkeypatch):
        primary, _, store = stores
        aborted = type('Aborted', (Exception,), {})('409 Aborted due to cross-transaction contention')
        monkeypatch.setattr(primary, 'run', lambda body: (_ for _ in ()).throw(aborted))
        caplog.set_level('WARNING', logger='database.jobstore.dual_store')
        store.refresh([('jobs', 'j'), ('results', 'j')])
        assert store.drain(5)
        assert any(
            r.getMessage() == 'event=jobstore_shadow op=refresh outcome=error error=Aborted error_class=contention '
            'phase=primary_read namespace=batch_pipeline_dev tables=jobs,results'
            for r in caplog.records
        )

    def test_read_current_on_firestore_is_one_get_all_outside_any_transaction(self):
        class Snap:
            def __init__(self, path, doc):
                self.reference, self.exists, self._doc = type('R', (), {'path': path})(), doc is not None, doc

            def to_dict(self):
                return self._doc

        class Client:
            def __init__(self):
                self.calls = []

            def collection(self, name):
                return type('C', (), {'document': lambda _, key: type('R', (), {'path': f'{name}/{key}'})()})()

            def get_all(self, refs):
                self.calls.append([r.path for r in refs])
                return [Snap('batch_pipeline_dev_jobs/a', {'s': 1}), Snap('batch_pipeline_dev_jobs/b', None)]

            def transaction(self):
                pytest.fail('read_current must not open a transaction')

        client = Client()
        primary = object.__new__(batch_store.FirestoreStore)
        primary.namespace, primary._client = 'batch_pipeline_dev', client
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv('OMI_ENV_STAGE', 'dev')
            got = dual_store.read_current(primary, [('jobs', 'a'), ('jobs', 'b')])
        assert got == {('jobs', 'a'): {'s': 1}, ('jobs', 'b'): {}}
        assert client.calls == [['batch_pipeline_dev_jobs/a', 'batch_pipeline_dev_jobs/b']]


def test_mirror_and_refresh_reread_the_primary_lock_free(monkeypatch):
    """The copy's primary read is read_current (a get_all on Firestore), never a read-write transaction."""
    primary, shadow = SimStore(CustomerData()), FakeShadow()
    store = DualStore(primary, shadow, inline=True)
    reads = []
    real = dual_store.read_current
    monkeypatch.setattr(dual_store, 'read_current', lambda p, keys: (reads.append(list(keys)), real(p, keys))[1])
    store.run(lambda tx: tx.put('queues', 'q', {'n': 1}))
    primary.rows[('owners', 'o')] = {'v': 1}
    store.refresh([('owners', 'o')])
    assert reads == [[('queues', 'q')], [('owners', 'o')]]
    assert shadow.rows == {('queues', 'q'): {'n': 1}, ('owners', 'o'): {'v': 1}}


class TestConvergence:
    """Lead ruling a2d720: a non-matching read is lag if Postgres equals the primary within the window, else divergence."""

    @staticmethod
    def converged(table, outcome):
        return dual_store.SHADOW_CONVERGENCE_TOTAL.labels(table=table, outcome=outcome)._value.get()

    @staticmethod
    def all_tracked():
        return sum(
            s.value
            for m in dual_store.SHADOW_CONVERGENCE_TOTAL.collect()
            for s in m.samples
            if s.name.endswith('_total')
        )

    def test_mirror_lag_converges_and_records_its_lag(self):
        primary, shadow = SimStore(CustomerData()), FakeShadow()
        store = DualStore(primary, shadow, inline=True)
        views = _held(store)
        store.run(lambda tx: tx.put('control', 'c', {'p0_service': 1.0}))
        store.run(lambda tx: tx.put('control', 'c', {'p0_service': tx.get('control', 'c')['p0_service'] + 1}))
        del store._after_commit
        before = count('control', 'read', 'mismatch'), self.converged('control', 'converged')
        lag_before = dual_store.SHADOW_CONVERGENCE_SECONDS.labels(table='control')._sum.get()
        for view in views:
            store._after_commit(view)
        # The parity counter still counts the mismatch; convergence classifies it as lag.
        assert (count('control', 'read', 'mismatch'), self.converged('control', 'converged')) == (
            before[0] + 1,
            before[1] + 1,
        )
        assert dual_store.SHADOW_CONVERGENCE_SECONDS.labels(table='control')._sum.get() >= lag_before

    def test_a_copy_that_never_catches_up_diverges(self, caplog):
        primary, shadow = SimStore(CustomerData()), FakeShadow()
        store = DualStore(primary, shadow, inline=True)
        primary.rows[('owners', 'o')] = {'v': 2}
        shadow.rows[('owners', 'o')] = {'v': 1}  # a lost mirror write; this read-only commit does not rewrite it
        before = self.converged('owners', 'diverged')
        caplog.set_level('WARNING', logger='database.jobstore.dual_store')
        store.run(lambda tx: tx.get('owners', 'o'))
        assert self.converged('owners', 'diverged') == before + 1
        assert any(
            'op=converge outcome=diverged' in r.getMessage() and 'fields=v' in r.getMessage() for r in caplog.records
        )

    def test_threaded_tracker_rechecks_until_the_late_mirror_lands(self):
        primary, shadow = SimStore(CustomerData()), FakeShadow()
        store = DualStore(primary, shadow)
        store.convergence_delays = (0.0, 0.05, 0.1, 2.0)
        primary.rows[('queues', 'q')] = {'n': 2}
        shadow.rows[('queues', 'q')] = {'n': 1}  # behind: another process's mirror has not landed yet
        before = self.converged('queues', 'converged'), self.converged('queues', 'diverged')
        real_read = shadow.read_doc
        calls = []

        def read_doc(conn, table, key):  # the late mirror lands after the first convergence check
            calls.append(key)
            if len(calls) >= 3:
                shadow.rows[('queues', 'q')] = {'n': 2}
            return real_read(conn, table, key)

        shadow.read_doc = read_doc  # type: ignore[method-assign]
        store.run(lambda tx: tx.get('queues', 'q'))
        assert store.drain(5) and store.drain_convergence(5)
        assert (self.converged('queues', 'converged'), self.converged('queues', 'diverged')) == (
            before[0] + 1,
            before[1],
        )

    def test_threaded_tracker_gives_up_after_the_window(self):
        primary, shadow = SimStore(CustomerData()), FakeShadow()
        store = DualStore(primary, shadow)
        store.convergence_delays = (0.0, 0.02, 0.04)
        primary.rows[('jobs', 'j')] = {'state': 'ready'}  # never mirrored: missing, and it stays missing
        before = self.converged('jobs', 'diverged')
        store.run(lambda tx: tx.get('jobs', 'j'))
        assert store.drain(5) and store.drain_convergence(5)
        assert self.converged('jobs', 'diverged') == before + 1

    def test_a_torn_pair_never_counts_as_converged(self):
        """Grok #22965 B1: Postgres changes between the two reads of one observation; the last step diverges."""
        primary, shadow = SimStore(CustomerData()), FakeShadow()
        store = DualStore(primary, shadow, inline=True)
        primary.rows[('queues', 'q')] = {'n': 1}
        reads = iter([{'n': 1}, {'n': 9}])  # matches Firestore on the first read only
        shadow.read_doc = lambda conn, table, key: next(reads)  # type: ignore[method-assign]
        before = self.converged('queues', 'converged'), self.converged('queues', 'diverged')
        store._check_convergence((0.0, 1, 'queues', 'q', time.monotonic(), len(store.convergence_delays) - 1))
        assert (self.converged('queues', 'converged'), self.converged('queues', 'diverged')) == (
            before[0],
            before[1] + 1,
        )

    def test_a_late_observation_never_counts_as_converged(self):
        """Grok #22965 B1: a check that runs after the window (tracker backlog) is a divergence, even if equal."""
        primary, shadow = SimStore(CustomerData()), FakeShadow()
        store = DualStore(primary, shadow, inline=True)
        primary.rows[('queues', 'q')] = {'n': 1}
        shadow.rows[('queues', 'q')] = {'n': 1}
        before = self.converged('queues', 'converged'), self.converged('queues', 'diverged')
        store._check_convergence((0.0, 1, 'queues', 'q', time.monotonic() - 30.0, 0))
        assert (self.converged('queues', 'converged'), self.converged('queues', 'diverged')) == (
            before[0],
            before[1] + 1,
        )

    def test_an_unexpected_failure_counts_error_and_keeps_the_tracker(self, monkeypatch):
        primary, shadow = SimStore(CustomerData()), FakeShadow()
        store = DualStore(primary, shadow, inline=True)
        monkeypatch.setattr(dual_store, 'compare', Mock(side_effect=RecursionError('deep')))
        before = self.converged('queues', 'error')
        store._check_convergence((0.0, 1, 'queues', 'q', time.monotonic(), 0))  # never raises
        assert self.converged('queues', 'error') == before + 1

    def test_a_full_tracker_drops_and_counts(self, monkeypatch):
        monkeypatch.setattr(dual_store, 'CONVERGENCE_QUEUE_LIMIT', 0)
        primary, shadow = SimStore(CustomerData()), FakeShadow()
        store = DualStore(primary, shadow)
        primary.rows[('gpus', 'g')] = {'a': 1}
        before = self.converged('gpus', 'dropped')
        store.run(lambda tx: tx.get('gpus', 'g'))
        assert store.drain(5)
        assert self.converged('gpus', 'dropped') == before + 1

    def test_matching_reads_are_not_tracked(self, stores):
        primary, shadow, store = stores
        put(store, 'queues', 'm', {'a': 1})
        totals = self.all_tracked()
        store.run(lambda tx: tx.get('queues', 'm'))
        assert store.drain(5) and store.drain_convergence(5)
        assert self.all_tracked() == totals
