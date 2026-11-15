"""Operator pages: bounded IO, current-source retirement and atomic checkpoints."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database.jobstore import cohort, reconcile as rec
from database.jobstore.dual_store import DualStore


class Ref:
    def __init__(self, client, collection, key):
        self.client, self.collection, self.id = client, collection, key
        self.path = f'{collection}/{key}'


class Snapshot:
    def __init__(self, ref, doc):
        self.reference, self.id, self.doc = ref, ref.id, doc
        self.exists = doc is not None

    def to_dict(self):
        return deepcopy(self.doc)


class Query:
    def __init__(self, client, name):
        self.client, self.name, self.bound, self.after = client, name, None, None

    def document(self, key):
        return Ref(self.client, self.name, key)

    def order_by(self, field):
        assert field == '__name__'
        return self

    def limit(self, count):
        self.bound = count
        return self

    def start_after(self, value):
        self.after = value['__name__'].id
        return self

    def get(self, *, timeout, retry):
        assert timeout > 0 and retry is None and self.bound is not None
        self.client.pages.append((self.name, self.bound, self.after))
        keys = sorted(key for collection, key in self.client.rows if collection == self.name)
        keys = [key for key in keys if self.after is None or key > self.after][: self.bound]
        return [Snapshot(self.document(key), self.client.rows[(self.name, key)]) for key in keys]


class Client:
    def __init__(self, namespace):
        self.namespace, self.rows, self.pages, self.rereads = namespace, {}, [], []
        self.on_read = None

    def collection(self, name):
        return Query(self, name)

    def get_all(self, refs, *, timeout, retry):
        assert timeout > 0 and retry is None
        self.rereads.append([ref.path for ref in refs])
        if self.on_read:
            self.on_read()
        return [Snapshot(ref, self.rows.get((ref.collection, ref.id))) for ref in refs]


class Conn:
    def __init__(self, shadow):
        self.shadow, self.sql, self.results = shadow, [], []

    def wait(self, generator, interval=None):
        raise AssertionError("synthetic connection has no socket wait")

    def execute(self, query, params=None):
        text = str(query)
        self.sql.append((text, params))
        if self.shadow.fail and self.shadow.fail(text):
            raise OSError('synthetic PG failure')
        if text.startswith('SELECT key FROM'):
            assert ' LIMIT ' in text and 'ORDER BY key COLLATE "C"' in text
            table = text.split(' FROM ')[1].split()[0]
            logical = params[1] if table == 'docs' else table
            after = params[-2] if ' > %s' in text else None
            keys = sorted(k for t, k in self.shadow.rows if t == logical and (after is None or k > after))
            self.results = [(key,) for key in keys[: params[-1]]]
        return self

    def fetchall(self):
        return self.results

    @contextmanager
    def transaction(self):
        before = deepcopy(self.shadow.rows)
        try:
            yield
        except BaseException:
            self.shadow.rows = before
            raise
        self.shadow.commits += 1


class Pool:
    def __init__(self, shadow):
        self.conn, self.options = Conn(shadow), []
        self.cold = False

    @contextmanager
    def connection(self, *, timeout, existing_only):
        assert timeout > 0 and existing_only is True
        self.options.append((timeout, existing_only))
        if self.cold:
            raise TimeoutError('job store observation requires a warm connection')
        yield self.conn


class Shadow:
    def __init__(self, namespace):
        self.namespace, self.rows, self.fail, self.commits = namespace, {}, None, 0
        self.pool = Pool(self)

    def read_doc(self, conn, table, key):
        conn.execute('SELECT doc FROM synthetic WHERE key = %s', (key,))
        return deepcopy(self.rows.get((table, key), {}))

    def write_doc(self, conn, table, key, doc):
        conn.execute('INSERT INTO synthetic VALUES (%s)', (key,))
        self.rows[(table, key)] = deepcopy(doc)

    def delete_doc(self, conn, table, key):
        conn.execute('DELETE FROM synthetic WHERE key = %s', (key,))
        self.rows.pop((table, key), None)


@pytest.fixture
def world(monkeypatch):
    namespace = 'batch_pipeline_prod'
    client = Client(namespace)
    primary = SimpleNamespace(namespace=namespace, client=client)
    shadow = Shadow(namespace)
    dual = DualStore(primary, shadow, inline=True)

    def classify(namespace, table, key, doc):
        if not doc:
            return 'absent'
        if 'owner_key' not in doc:
            return 'unknown_owner'
        return 'selected' if doc['owner_key'] == 'included' else 'excluded'

    monkeypatch.setattr(cohort, 'classify_document', classify)
    monkeypatch.setattr(rec, 'classify_document', classify)
    monkeypatch.setattr(
        cohort,
        'project_document',
        lambda ns, table, key, doc: doc if classify(ns, table, key, doc) == 'selected' else None,
    )
    monkeypatch.setattr(rec, 'project_document', cohort.project_document)
    return client, shadow, dual


def put(client, table, key, **values):
    client.rows[(f'{client.namespace}_{table}', key)] = {'owner_key': 'included', **values}


def page(dual, **options):
    return rec.process_page(dual, source='copy', table='jobs', **options)


def test_copy_pages_resume_and_end_without_unbounded_scan(world):
    client, shadow, dual = world
    for key in ('a', 'b', 'c', 'd', 'e'):
        shadow.rows[('jobs', key)] = {'old': True}
        put(client, 'jobs', key, value=key)
    cursor, total, ends = None, 0, []
    for _ in range(3):
        result = page(dual, cursor=cursor, max_rows=2, apply=True)
        total += result.counts.scanned
        ends.append(result.end_of_pass)
        cursor = result.cursor
    assert total == 5 and ends == [False, False, True] and cursor is None
    assert len(client.rereads) == 5
    assert all(row['owner_key'] == 'included' for row in shadow.rows.values())
    assert all('LIMIT' in query for query, _ in shadow.pool.conn.sql if query.startswith('SELECT key'))


def test_primary_pages_document_id_rpc_timeout_and_read_budget(world):
    client, shadow, dual = world
    for key in ('a', 'b', 'c'):
        put(client, 'owners', key)
    first = rec.process_page(dual, source='primary', table='owners', max_rows=20, max_primary_reads=4, apply=True)
    second = rec.process_page(
        dual, source='primary', table='owners', cursor=first.cursor, max_rows=20, max_primary_reads=4, apply=True
    )
    assert first.counts.primary_reads == 4 and second.counts.primary_reads == 2
    assert client.pages == [('batch_pipeline_prod_owners', 2, None), ('batch_pipeline_prod_owners', 2, 'b')]
    assert len(shadow.rows) == 3 and second.end_of_pass


def test_dry_run_classifies_without_writes_and_report_has_no_keys(world):
    client, shadow, dual = world
    for key in ('chosen', 'excluded', 'unknown', 'gone'):
        shadow.rows[('jobs', key)] = {'old': True}
    put(client, 'jobs', 'chosen', value=2)
    put(client, 'jobs', 'excluded', owner_key='excluded')
    client.rows[('batch_pipeline_prod_jobs', 'unknown')] = {'value': 1}
    before = deepcopy(shadow.rows)
    result = page(dual)
    assert (result.counts.selected, result.counts.excluded, result.counts.unknown_owner) == (1, 1, 1)
    assert result.counts.stale == 4 and result.counts.deleted == 3 and result.counts.copied == 0
    assert shadow.rows == before
    assert not any(query.startswith(('INSERT', 'DELETE')) for query, _ in shadow.pool.conn.sql)
    assert 'cursor' not in result.public_report()


def test_ttl_absence_retires_even_when_final_stamp_was_dropped(world):
    client, shadow, dual = world
    shadow.rows[('jobs', 'missing-stamp')] = {'owner_key': 'included'}
    shadow.rows[('jobs', 'stale-stamp')] = {'owner_key': 'included', 'expires_at': 'old-invalid-value'}
    result = page(dual, apply=True)
    assert result.counts.deleted == 2 and shadow.rows == {}


@pytest.mark.parametrize('expiry', [None, 0, 'malformed', datetime(2000, 1, 1, tzinfo=timezone.utc)])
def test_present_primary_and_legal_hold_never_expire_by_clock(world, expiry):
    client, shadow, dual = world
    put(client, 'jobs', 'held', expires_at=expiry, legal_hold=True)
    shadow.rows[('jobs', 'held')] = {'owner_key': 'included', 'expires_at': 'stale'}
    result = page(dual, apply=True)
    assert result.counts.deleted == 0
    assert shadow.rows[('jobs', 'held')]['legal_hold'] is True
    assert shadow.rows[('jobs', 'held')]['expires_at'] == expiry


def test_present_pull_claim_lease_clock_is_not_document_retention(world):
    client, shadow, dual = world
    put(client, 'pull_claims', 'claim', expires_at=0)
    shadow.rows[('pull_claims', 'claim')] = {'owner_key': 'included', 'expires_at': 0}
    result = rec.process_page(dual, source='copy', table='pull_claims', apply=True)
    assert result.counts.deleted == 0 and ('pull_claims', 'claim') in shadow.rows


def test_queued_candidate_uses_fresh_primary_for_cohort_shrink(world):
    client, shadow, dual = world
    put(client, 'jobs', 'a')
    shadow.rows[('jobs', 'a')] = {'owner_key': 'included'}
    client.on_read = lambda: put(client, 'jobs', 'a', owner_key='excluded')
    result = page(dual, apply=True)
    assert result.counts.excluded == 1 and result.counts.deleted == 1 and shadow.rows == {}


def test_pg_failure_rolls_back_entire_page_and_retry_previous_cursor(world):
    client, shadow, dual = world
    for key in ('a', 'b', 'c'):
        put(client, 'jobs', key)
        shadow.rows[('jobs', key)] = {'old': True}
    first = page(dual, max_rows=1, apply=True)
    before = deepcopy(shadow.rows)
    calls = 0

    def fail_second_insert(query):
        nonlocal calls
        calls += query.startswith('INSERT')
        return calls == 2

    shadow.fail = fail_second_insert
    with pytest.raises(OSError):
        page(dual, cursor=first.cursor, max_rows=2, apply=True)
    assert shadow.rows == before
    shadow.fail = None
    retry = page(dual, cursor=first.cursor, max_rows=2, apply=True)
    assert retry.counts.scanned == 2 and shadow.rows[('jobs', 'c')]['owner_key'] == 'included'


def test_statement_exhaustion_cannot_publish_success_or_partial_page(world):
    client, shadow, dual = world
    put(client, 'jobs', 'a')
    shadow.rows[('jobs', 'a')] = {'old': True}
    before = deepcopy(shadow.rows)
    with pytest.raises(RuntimeError, match='statement budget'):
        page(dual, max_statements=8, apply=True)
    assert shadow.rows == before


def test_expired_wall_deadline_rolls_back(world, monkeypatch):
    client, shadow, dual = world
    put(client, 'jobs', 'a')
    shadow.rows[('jobs', 'a')] = {'old': True}
    clock = [1.0]
    monkeypatch.setattr(rec.time, 'monotonic', lambda: clock[0])
    client.on_read = lambda: clock.__setitem__(0, 30.0)
    with pytest.raises(TimeoutError, match='deadline'):
        page(dual, budget_s=1, apply=True)
    assert shadow.rows == {('jobs', 'a'): {'old': True}}


def test_cold_connection_does_not_start_unbounded_auth(world):
    _, shadow, dual = world
    shadow.pool.cold = True
    with pytest.raises(TimeoutError, match='warm connection'):
        page(dual)


@pytest.mark.parametrize('cursor', ['not-base64', '', 'e30=', 3])
def test_invalid_cursor_fails_without_io_or_echo(world, cursor):
    client, shadow, dual = world
    with pytest.raises(ValueError, match='invalid reconciliation cursor'):
        page(dual, cursor=cursor)
    assert client.rereads == [] and shadow.pool.options == []


def test_cursor_cannot_cross_source_table_or_namespace(world):
    client, shadow, dual = world
    shadow.rows[('jobs', 'private-id')] = {'owner_key': 'included'}
    cursor = page(dual, max_rows=1).cursor
    assert cursor and 'private-id' not in cursor
    for source, table in [('primary', 'jobs'), ('copy', 'owners')]:
        with pytest.raises(ValueError, match='scope'):
            rec.process_page(dual, source=source, table=table, cursor=cursor)
    assert 'private-id' not in repr(page(dual, max_rows=1))


@pytest.mark.parametrize('table', ['jobs', 'results', 'control', 'owners'])
def test_copy_keys_have_typed_or_doc_scoped_ordered_limit(world, table):
    client, shadow, dual = world
    rec.process_page(dual, source='copy', table=table)
    query, params = next((q, p) for q, p in shadow.pool.conn.sql if q.startswith('SELECT key'))
    assert ('FROM docs' in query) == (table == 'owners')
    assert params[0] == client.namespace and params[-1] == 100
    if table == 'owners':
        assert params[1] == 'owners'


def test_transport_wait_deadline_bounds_stalled_socket_and_restores_method(world, monkeypatch):
    _, shadow, dual = world
    clock = [1.0]
    monkeypatch.setattr(rec.time, 'monotonic', lambda: clock[0])
    conn = shadow.pool.conn

    def socket_steps():
        while True:
            yield 1

    def driver_wait(generator, interval=None):
        assert interval <= 0.01
        next(generator)
        while True:
            clock[0] += 0.2
            generator.send(0)

    def stalled_execute(query, params=None):
        return conn.wait(socket_steps())

    conn.wait = driver_wait
    monkeypatch.setattr(conn, 'execute', stalled_execute)
    with pytest.raises(TimeoutError, match='deadline'):
        page(dual, budget_s=0.5)
    assert conn.wait is driver_wait
    assert clock[0] <= 1.7


def test_primary_deleted_after_discovery_cannot_recreate_copy(world):
    client, shadow, dual = world
    put(client, 'jobs', 'a')
    shadow.rows[('jobs', 'a')] = {'owner_key': 'included'}
    client.on_read = client.rows.clear
    result = rec.process_page(dual, source='primary', table='jobs', apply=True)
    assert result.counts.deleted == 1 and result.counts.copied == 0
    assert shadow.rows == {}


def test_primary_updated_after_discovery_copies_current_value(world):
    client, shadow, dual = world
    put(client, 'jobs', 'a', version=1)
    client.on_read = lambda: put(client, 'jobs', 'a', version=2)
    result = rec.process_page(dual, source='primary', table='jobs', apply=True)
    assert result.counts.copied == 1
    assert shadow.rows[('jobs', 'a')]['version'] == 2
