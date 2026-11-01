"""Doc-mode Postgres transactions lock documents the way Firestore's server transactions do (plan A3 step 1).

A fake connection records the statements; the real-Postgres behaviour (no lost update, one creator per
missing key, four concurrent schedulers leasing every job once) is in
``tests/integration/test_store_conformance.py``.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from database.firestore_transaction_retry import FirestoreContentionExhausted
from database.jobstore import postgres_store as pg


class Result:
    def __init__(self, row=None, rows=()):
        self.row, self.rows = row, list(rows)

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class Conn:
    def __init__(self, docs=None, fail=None):
        self.docs = docs or {}
        self.fail = fail
        self.sql: list[str] = []

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, params=()):
        self.sql.append(sql)
        if self.fail and self.fail[0] in sql:
            raise self.fail[1]
        if sql.startswith('SELECT doc FROM'):
            key = params[-1]
            return Result((self.docs[key],) if key in self.docs else None)
        return Result()


class Pool:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def connection(self, timeout: float = 30.0):
        yield self.conn


class SqlError(Exception):
    def __init__(self, sqlstate):
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def store(conn):
    return pg.PostgresStore('batch_pipeline_test_lock', pool=Pool(conn), customer_client=None)


def test_transactions_run_read_committed_with_a_bounded_lock_wait():
    conn = Conn()
    store(conn).run(lambda tx: None)
    assert conn.sql[:2] == ['SET TRANSACTION ISOLATION LEVEL READ COMMITTED', "SET LOCAL lock_timeout = '2s'"]


def test_get_locks_an_existing_row_and_a_missing_key_by_name():
    conn = Conn(docs={'present': {'n': 1}})

    def body(tx):
        assert tx.get('owners', 'present') == {'n': 1}
        assert tx.get('owners', 'absent') == {}
        assert tx.get('owners', 'present') == {'n': 1}  # cached: no second lock

    store(conn).run(body)
    reads = [sql for sql in conn.sql if 'FROM docs' in sql or 'advisory' in sql]
    assert all(sql.endswith('FOR UPDATE') for sql in reads if 'FROM docs' in sql)
    assert sum('pg_advisory_xact_lock' in sql for sql in reads) == 1  # only the missing key
    # The missing key is re-read under its name lock, so an insert committed before it is seen.
    assert [('advisory' in sql) for sql in reads] == [False, False, True, False]


def test_blind_write_takes_the_document_lock_before_writing():
    conn = Conn()
    store(conn).run(lambda tx: tx.put('gpus', 'g1', {'token': 't'}))
    lock = next(i for i, sql in enumerate(conn.sql) if 'pg_advisory_xact_lock' in sql)
    write = next(i for i, sql in enumerate(conn.sql) if sql.startswith('INSERT INTO docs'))
    assert lock < write


@pytest.mark.parametrize('sqlstate', ['40001', '40P01', '55P03'])
def test_conflicts_retry_then_raise_the_typed_contention_error(sqlstate, monkeypatch):
    monkeypatch.setattr(pg.time, 'sleep', lambda seconds: None)
    calls = []

    def body(tx):
        calls.append(1)
        raise SqlError(sqlstate)

    with pytest.raises(FirestoreContentionExhausted):
        store(Conn()).run(body)
    assert len(calls) == pg.MAX_SERIALIZATION_RETRIES


def test_a_queried_row_that_changed_before_its_lock_restarts_the_body(monkeypatch):
    monkeypatch.setattr(pg.time, 'sleep', lambda seconds: None)
    attempts = []

    def body(tx):
        attempts.append(1)
        if len(attempts) == 1:
            # The query saw an older version than the locked read returns.
            tx.store.read_doc = lambda conn, table, key, lock=False: {'segment_id': key, 'state': 'leased'}
            return tx._locked_query_row('s1', {'segment_id': 's1', 'state': 'ready'})
        return 'second'

    assert store(Conn()).run(body) == 'second'
    assert len(attempts) == 2


def test_other_errors_are_not_retried():
    calls = []

    def body(tx):
        calls.append(1)
        raise KeyError('boom')

    with pytest.raises(KeyError):
        store(Conn()).run(body)
    assert calls == [1]
