"""Index hints over loopback Firestore/Postgres, including the actual driver wait.

Use OMI_REQUIRE_STORE_BACKENDS=all with the isolated emulator harness. These
proofs measure local discovery and Firestore transaction authority only.
"""

from __future__ import annotations

from contextlib import contextmanager
import time
from types import SimpleNamespace

import pytest

from database.jobstore.connection import Pool
from database.jobstore.dual_store import DualStore
from database.jobstore.index_store import INDEX_QUERIES, IndexStore, BoundedPostgresReader
from database.jobstore.postgres_store import PostgresStore
from testing.store_fixtures import BackendUnavailable, build_backend, postgres_connect, required_backends
from utils.batch_pipeline.scheduler import Scheduler

pytestmark = pytest.mark.integration


@pytest.fixture
def indexed(monkeypatch):
    monkeypatch.delenv('JOBSTORE_SHADOW_WRITES', raising=False)
    monkeypatch.delenv('JOBSTORE_SHADOW_QUERY_PARITY', raising=False)
    harness = build_backend('emulator')
    try:
        connect = postgres_connect()
    except BackendUnavailable as exc:
        harness.close()
        if 'postgres' in required_backends():
            pytest.fail(f'required postgres backend unavailable: {exc}')
        pytest.skip(str(exc))
    pool = Pool('', size=1, connect=connect)
    shadow = PostgresStore(harness.namespace, pool=pool, customer_client=None)
    with pool.connection():
        pass
    mirror = DualStore(harness.store, shadow, inline=True, budget_s=2)
    clock = [100.0]
    enabled = [True]
    index = IndexStore(
        mirror,
        enabled_queries=INDEX_QUERIES,
        enabled=lambda: enabled[0],
        sweep_interval_s=60,
        read_budget_s=0.1,
        clock=lambda: clock[0],
    )
    yield SimpleNamespace(
        index=index,
        mirror=mirror,
        primary=harness.store,
        shadow=shadow,
        pool=pool,
        connect=connect,
        clock=clock,
        enabled=enabled,
        harness=harness,
    )
    shadow.purge_namespace()
    pool.close()
    harness.close()


def _job(key, state, at):
    return {
        'segment_id': key,
        'owner_id': 'synthetic-owner',
        'owner_key': 'synthetic-owner-key',
        'state': state,
        'priority': 1,
        'merge_pending': False,
        'capture_at': at,
        'lease_until': at,
        'available_at': at,
        'enqueued_at': at,
    }


def _seed(indexed, rows, *, primary=True, shadow=True):
    # Synthetic fixture writes let a test intentionally model a dropped or
    # stale mirror copy without changing the product's mutation path.
    if primary:
        for key, row in rows:
            indexed.primary.client.collection(f'{indexed.primary.namespace}_jobs').document(key).set(row)
    if shadow:
        with indexed.pool.connection() as conn:
            for key, row in rows:
                indexed.shadow.write_doc(conn, 'jobs', key, row)


@pytest.mark.parametrize('state', ['leased', 'retry', 'result_ready'])
def test_actual_due_sql_keeps_primary_order_and_limit(indexed, state):
    rows = [(key, _job(key, state, at)) for key, at in [('z', 2), ('ä', 1), ('a', 1), ('B', 1)]]
    _seed(indexed, rows)
    for limit in (0, 1, 2, 100, 500):
        expected = indexed.primary.due(state, 2, limit)
        assert indexed.index.due(state, 2, limit) == expected  # first call sweeps
        assert indexed.index.due(state, 2, limit) == expected  # actual PG SQL
    assert indexed.index.due(state, 0) == []


def test_dropped_copy_reappears_on_safety_sweep(indexed):
    _seed(indexed, [('lost', _job('lost', 'retry', 1))], shadow=False)
    assert indexed.index.due('retry', 2) == ['lost']
    assert indexed.index.due('retry', 2) == []
    indexed.clock[0] += 60
    assert indexed.index.due('retry', 2) == ['lost']


def test_stale_due_hint_cannot_authorize_recovery_mutation(indexed):
    _seed(indexed, [('stale', _job('stale', 'retry', 100))], shadow=False)
    _seed(indexed, [('stale', _job('stale', 'retry', 1))], primary=False)
    assert indexed.index.due('retry', 2) == []  # prime the sweep
    assert indexed.index.due('leased', 2) == []
    assert indexed.index.due('retry', 2) == ['stale']
    assert Scheduler(indexed.index).recover(2) == 0
    job = indexed.primary.run(lambda tx: tx.get('jobs', 'stale'))
    assert job['state'] == 'retry'
    assert job['available_at'] == 100


def test_real_pg_statement_deadline_falls_back_and_discards_connection(indexed):
    _seed(indexed, [('due', _job('due', 'retry', 1))])
    assert indexed.index.due('retry', 2) == ['due']
    with indexed.pool.connection() as conn:
        failed_connection = conn
    locker = indexed.connect()
    try:
        with locker.transaction():
            locker.execute('LOCK TABLE jobs IN ACCESS EXCLUSIVE MODE')
            started = time.monotonic()
            assert indexed.index.due('retry', 2) == ['due']
            assert time.monotonic() - started < 1
            assert failed_connection.closed
            assert indexed.pool._idle.empty()
    finally:
        locker.close()
    # A discarded connection is never redialed from the index caller.
    assert indexed.index.due('retry', 2) == ['due']
    assert indexed.pool._idle.empty()


def test_actual_psycopg_stalled_socket_wait_exits_and_discards(indexed):
    reader = BoundedPostgresReader(indexed.shadow, 0.05)
    stopped = []
    checked_out = []

    def stalled():
        try:
            while True:
                # psycopg's socket has no pending result. Its real waiting
                # implementation must still send readiness=0 on the interval.
                yield 1
        finally:
            stopped.append(True)

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        with reader._read_conn() as conn:
            checked_out.append(conn)
            conn.wait(stalled())
    assert time.monotonic() - started < 0.5
    assert stopped == [True]
    assert checked_out[0].closed
    assert indexed.pool._idle.empty()


def test_killed_index_and_record_pending_never_acquire_postgres(indexed, monkeypatch):
    _seed(indexed, [('due', _job('due', 'retry', 1)), ('record', _job('record', 'record_pending', 1))])

    @contextmanager
    def forbidden(*args, **kwargs):
        pytest.fail('disabled/excluded read entered the Postgres pool')
        yield

    with monkeypatch.context() as patch:
        patch.setattr(indexed.pool, 'connection', forbidden)
        indexed.enabled[0] = False
        assert indexed.index.due('retry', 2) == ['due']
        indexed.enabled[0] = True
        assert indexed.index.due('record_pending', 2, 500) == ['record']
