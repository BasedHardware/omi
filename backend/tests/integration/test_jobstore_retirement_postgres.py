"""Real local PG cursor/page rollback and overlapping leaders; synthetic primary only."""

from concurrent.futures import ThreadPoolExecutor
import os
from types import SimpleNamespace
import uuid

import pytest

from database.jobstore.connection import Pool
from database.jobstore.dual_store import DualStore
from database.jobstore.postgres_store import PostgresStore
from database.jobstore.reconcile import process_page
from database.jobstore.retirement_cursor import CursorPage, CursorScope
from testing.store_fixtures import postgres_connect
from tests.unit.test_jobstore_reconcile import Client

pytestmark = pytest.mark.integration


@pytest.fixture
def stores():
    assert not os.getenv('OMI_TEST_POSTGRES_IAM'), 'local PG only'
    # Do not accept a remote DSN inherited from a different task.
    psycopg = pytest.importorskip('psycopg')
    supplied = os.getenv('OMI_TEST_POSTGRES_DSN')
    if supplied:
        host = psycopg.conninfo.conninfo_to_dict(supplied).get('host', '')
        assert host and all(h.startswith('/') or h in {'localhost', '127.0.0.1', '::1'} for h in host.split(','))
    ns = 'batch_pipeline_test_retirement_' + uuid.uuid4().hex[:12]
    pool = Pool('', size=3, connect=postgres_connect())
    shadow = PostgresStore(ns, pool=pool, customer_client=None)
    primary = SimpleNamespace(namespace=ns, client=Client(ns))
    dual = DualStore(primary, shadow, inline=True)
    scope = CursorScope.for_target(ns, 'copy', 'jobs', True, ('local', 'synthetic', 'postgres'))
    try:
        # Warm both connections so concurrent pages never dial.
        with pool.connection() as first, pool.connection() as second:
            for key in ('a', 'b', 'c'):
                shadow.write_doc(first, 'jobs', key, {'state': 'retry', 'segment_id': key})
        yield SimpleNamespace(pool=pool, dual=dual, shadow=shadow, scope=scope)
    finally:
        with pool.connection() as conn:
            conn.execute('DELETE FROM jobstore_retirement_cursor WHERE namespace = %s', (ns,))
        shadow.purge_namespace()
        pool.close()


def run(stores, **options):
    cursor = CursorPage(stores.scope)
    return process_page(
        stores.dual,
        source='copy',
        table='jobs',
        max_rows=1,
        apply=True,
        load_cursor=cursor.load,
        advance=cursor.advance,
        **options
    )


def state(stores):
    with stores.pool.connection() as conn:
        row = conn.execute(
            'SELECT cursor, version, passes, rotation_completed_at FROM jobstore_retirement_cursor '
            'WHERE namespace = %s',
            (stores.scope.namespace,),
        ).fetchone()
        keys = conn.execute(
            'SELECT key FROM jobs WHERE namespace = %s ORDER BY key', (stores.scope.namespace,)
        ).fetchall()
    return row, keys


def test_cursor_and_retirement_commit_or_roll_back_together(stores):
    run(stores)
    before = state(stores)
    checkpoint = CursorPage(stores.scope)

    def fail(conn, result):
        checkpoint.advance(conn, result)
        conn.execute('SELECT 1 / 0')

    with pytest.raises(Exception):
        process_page(
            stores.dual, source='copy', table='jobs', max_rows=1, apply=True, load_cursor=checkpoint.load, advance=fail
        )
    assert state(stores) == before
    run(stores)
    row, keys = state(stores)
    assert row[1] == 2 and keys == [('c',)]
    run(stores)
    run(stores)
    row, keys = state(stores)
    assert row[:3] == (None, 4, 1) and row[3] is not None and keys == []


def test_fail_open_leaders_lock_and_reread_checkpoint_without_skips(stores):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run(stores), range(2)))
    row, keys = state(stores)
    assert row[1:3] == (2, 0) and keys == [('c',)]
    assert sum(page.counts.deleted for page in results) == 2
    assert len({page.cursor for page in results}) == 2


def test_cursor_statement_exhaustion_rolls_back_page_and_new_checkpoint(stores):
    with pytest.raises(RuntimeError, match='statement budget'):
        run(stores, max_statements=10)
    row, keys = state(stores)
    assert row is None and len(keys) == 3


def test_real_cursor_cas_refusal_rolls_back_retirement_and_version(stores):
    run(stores)
    before = state(stores)
    checkpoint = CursorPage(stores.scope)

    def changed_version(conn, result):
        conn.execute(
            'UPDATE jobstore_retirement_cursor SET version = version + 1 WHERE namespace = %s',
            (stores.scope.namespace,),
        )
        checkpoint.advance(conn, result)

    with pytest.raises(RuntimeError, match='compare-and-set'):
        process_page(
            stores.dual,
            source='copy',
            table='jobs',
            max_rows=1,
            apply=True,
            load_cursor=checkpoint.load,
            advance=changed_version,
        )
    assert state(stores) == before
