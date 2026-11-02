"""A6 backfill (staging dry run): census, idempotent copy of the primary's current state, and fail-closed CLI."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

import database.batch_pipeline_store  # noqa: F401  (read_current imports it lazily; import it outside the timed calls)

from database.jobstore import __main__ as cli
from database.jobstore import backfill as bf
from database.jobstore.dual_store import DualStore
from testing.pipeline_sim.store import CustomerData, SimStore


class Conn:
    def execute(self, sql, *args):
        return None

    @contextmanager
    def transaction(self):
        yield


class Pool:
    @contextmanager
    def connection(self, timeout: float = 30.0):
        yield Conn()


class Shadow:
    def __init__(self):
        self.namespace = 'batch_pipeline_dev'
        self.rows: dict[tuple[str, str], dict] = {}
        self.pool = Pool()
        self.writes = 0

    def read_doc(self, conn, table, key):
        return dict(self.rows.get((table, key), {}))

    def write_doc(self, conn, table, key, value):
        self.writes += 1
        self.rows[(table, key)] = dict(value)

    def delete_doc(self, conn, table, key):
        self.rows.pop((table, key), None)


class Snap:
    def __init__(self, key, doc):
        self.id, self._doc = key, doc

    def to_dict(self):
        return dict(self._doc)


@pytest.fixture
def world(monkeypatch):
    primary, shadow = SimStore(CustomerData()), Shadow()
    dual = DualStore(primary, shadow, inline=True)

    def pages(client, collection, page_size):
        table = collection.removeprefix('batch_pipeline_dev_')
        snaps = [Snap(key, doc) for (t, key), doc in sorted(primary.rows.items()) if t == table]
        for start in range(0, len(snaps), page_size):
            yield snaps[start : start + page_size]

    monkeypatch.setattr(bf, '_pages', pages)
    monkeypatch.setattr(bf, 'postgres_keys', lambda conn, ns, table: {k for t, k in shadow.rows if t == table})
    return primary, shadow, dual


def seed(primary, shadow):
    primary.rows[('owners', 'same')] = {'v': 1}
    shadow.rows[('owners', 'same')] = {'v': 1}
    primary.rows[('owners', 'drift')] = {'v': 2}
    shadow.rows[('owners', 'drift')] = {'v': 1}
    primary.rows[('owners', 'old')] = {'v': 3}  # written before the shadow started
    shadow.rows[('owners', 'pg_only')] = {'v': 4}


def test_dry_run_is_a_census_and_writes_nothing(world):
    primary, shadow, dual = world
    seed(primary, shadow)
    report = bf.backfill(dual, None, ['owners'], apply=False, page_size=2)
    assert report['owners'] == {
        'firestore': 3, 'match': 1, 'mismatch': 1, 'missing': 1, 'uncomparable': 0,
        'postgres_only': 1, 'copied': 0, 'copy_errors': 0,
    }  # fmt: skip
    assert shadow.writes == 0


def test_apply_copies_missing_and_differing_and_a_rerun_is_clean(world):
    primary, shadow, dual = world
    seed(primary, shadow)
    first = bf.backfill(dual, None, ['owners'], apply=True, page_size=2)['owners']
    assert (first['copied'], first['copy_errors']) == (2, 0)
    assert shadow.rows[('owners', 'drift')] == {'v': 2} and shadow.rows[('owners', 'old')] == {'v': 3}
    again = bf.backfill(dual, None, ['owners'], apply=True, page_size=2)['owners']
    assert (again['match'], again['missing'], again['mismatch'], again['copied']) == (3, 0, 0, 0)
    assert shadow.rows[('owners', 'pg_only')] == {'v': 4}  # counted, never deleted


def test_apply_copies_the_current_state_not_the_census_snapshot(world, monkeypatch):
    primary, shadow, dual = world
    primary.rows[('jobs', 'j')] = {'state': 'ready'}
    real = bf._pages

    def pages_then_advance(client, collection, page_size):
        for page in real(client, collection, page_size):
            primary.rows[('jobs', 'j')] = {'state': 'leased'}  # a live write after the census snapshot
            yield page

    monkeypatch.setattr(bf, '_pages', pages_then_advance)
    bf.backfill(dual, None, ['jobs'], apply=True)
    assert shadow.rows[('jobs', 'j')] == {'state': 'leased'}


def test_copy_failures_are_counted_per_page(world):
    primary, shadow, dual = world
    primary.rows[('queues', 'q')] = {'n': 1}
    shadow.write_doc = lambda *a: (_ for _ in ()).throw(RuntimeError('down'))  # type: ignore[method-assign]
    report = bf.backfill(dual, None, ['queues'], apply=True)['queues']
    assert (report['missing'], report['copied'], report['copy_errors']) == (1, 0, 1)


def test_customer_tables_are_refused(world):
    _, _, dual = world
    with pytest.raises(ValueError):
        bf.backfill_table(dual, None, 'conversations', apply=False)


class TestCli:
    def test_unknown_table_is_refused(self, monkeypatch):
        assert cli.main(['backfill', 'batch_pipeline_prod', '--tables', 'jobs,content']) == 2

    @pytest.mark.parametrize(
        'deployment, database_id', [('', 'staging'), ('staging', ''), ('staging', '(default)'), ('prod', 'staging')]
    )
    def test_outside_staging_on_the_staging_db_it_refuses_before_any_connection(
        self, monkeypatch, deployment, database_id
    ):
        monkeypatch.setenv('OMI_DEPLOYMENT', deployment)
        monkeypatch.setenv('FIRESTORE_DATABASE_ID', database_id)
        monkeypatch.setattr(cli, 'iam_connector', lambda *a: pytest.fail('dialed Postgres'))
        assert cli.main(['backfill', 'batch_pipeline_prod']) == 2
