"""Jobstore SQL composition quotes identifiers and keeps every runtime value bound."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

from psycopg import sql as psycopg_sql
import pytest

from database.jobstore import backfill, outbox_pg, postgres_store as pg
from database.jobstore.postgres_store import PostgresStore
from database.outbox import Claim, OutboxKind
from testing.pipeline_sim import postgres_store as sim_pg

HOSTILE_IDENTIFIER = 'jobs"; DROP TABLE outbox; --'
HOSTILE_FIELD = '0"; DROP TABLE outbox; --'
HOSTILE_VALUE = "batch_pipeline_test_bound'; DROP TABLE outbox; --"


def statement(query) -> str:
    return query.as_string() if hasattr(query, 'as_string') else query


class Result:
    def __init__(self, *, one=None, rows=()):
        self.one, self.rows = one, list(rows)

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[tuple[str, tuple]] = []
        self.queries = []

    @contextmanager
    def transaction(self):
        yield

    def execute(self, query, params=()):
        self.queries.append(query)
        self.calls.append((statement(query), params))
        return self.results.pop(0) if self.results else Result()


class Pool:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def connection(self, timeout: float = 30.0):
        yield self.conn


def make_store(conn, *, hostile_namespace=True):
    store = PostgresStore('batch_pipeline_test_sql', pool=Pool(conn), customer_client=None)
    if hostile_namespace:
        store.namespace = HOSTILE_VALUE
    return store


def make_outbox(conn):
    return outbox_pg.PostgresOutbox(OutboxKind.ENRICHMENT, make_store(conn))


def quoted(identifier):
    return psycopg_sql.Identifier(identifier).as_string()


def assert_bound(call, expected):
    text, params = call
    assert params == expected
    for value in expected:
        if isinstance(value, str) and value:
            assert value not in text


class HostilePriority(int):
    def __format__(self, format_spec):
        return HOSTILE_FIELD


# P1: due() quotes the selected due column twice.
def test_due_quotes_identifier_and_binds_values(monkeypatch):
    conn = RecordingConnection()
    monkeypatch.setattr(pg, '_DUE_FIELDS', {'leased': HOSTILE_IDENTIFIER})
    assert make_store(conn).due('leased', 123.0) == []
    text, _ = conn.calls[0]
    assert text.count(quoted(HOSTILE_IDENTIFIER)) == 2
    assert_bound(conn.calls[0], (HOSTILE_VALUE, 'leased', 123.0, 100))


# P3: control_candidates() quotes every priority/pool-derived column reference.
def test_control_candidates_quotes_identifiers_and_binds_values():
    conn = RecordingConnection()
    assert make_store(conn).control_candidates(HostilePriority(0), 'live', 123.0) == []
    p, at = f'p{HostilePriority(0)}', f'p{HostilePriority(0)}_live_at'
    text, _ = conn.calls[0]
    assert text.count(quoted(f'{p}_service')) == 3
    assert quoted(f'{p}_active') in text
    assert text.count(quoted(at)) == 2
    assert_bound(conn.calls[0], (HOSTILE_VALUE, 123.0, 1))


# P4: read_doc() quotes a typed table and keeps keys and namespaces as parameters.
def test_read_doc_quotes_identifier_and_binds_values(monkeypatch):
    conn = RecordingConnection(Result(one=({'ok': True},)))
    store = make_store(conn)
    monkeypatch.setattr(pg, '_TYPED', {HOSTILE_IDENTIFIER})
    assert store.read_doc(conn, HOSTILE_IDENTIFIER, HOSTILE_VALUE, lock=True) == {'ok': True}
    text, _ = conn.calls[0]
    assert quoted(HOSTILE_IDENTIFIER) in text
    assert text.endswith('FOR UPDATE')
    assert_bound(conn.calls[0], (HOSTILE_VALUE, HOSTILE_VALUE))


# P7: write_doc() quotes a typed table and keeps the document and keys as parameters.
def test_write_doc_quotes_identifier_and_binds_values(monkeypatch):
    conn = RecordingConnection()
    store = make_store(conn)
    monkeypatch.setattr(pg, '_TYPED', {HOSTILE_IDENTIFIER})
    monkeypatch.setattr(pg, 'jsonb', lambda value: HOSTILE_VALUE)
    store.write_doc(conn, HOSTILE_IDENTIFIER, HOSTILE_VALUE, {'payload': 'document'})
    text, _ = conn.calls[0]
    assert quoted(HOSTILE_IDENTIFIER) in text
    assert_bound(conn.calls[0], (HOSTILE_VALUE, HOSTILE_VALUE, HOSTILE_VALUE))


# P8: delete_doc() quotes a typed table and keeps keys and namespaces as parameters.
def test_delete_doc_quotes_identifier_and_binds_values(monkeypatch):
    conn = RecordingConnection()
    store = make_store(conn)
    monkeypatch.setattr(pg, '_TYPED', {HOSTILE_IDENTIFIER})
    store.delete_doc(conn, HOSTILE_IDENTIFIER, HOSTILE_VALUE)
    text, _ = conn.calls[0]
    assert quoted(HOSTILE_IDENTIFIER) in text
    assert_bound(conn.calls[0], (HOSTILE_VALUE, HOSTILE_VALUE))


# P9: service_frontier_in() quotes the priority-derived column.
def test_service_frontier_quotes_identifier_and_binds_values():
    conn = RecordingConnection(Result(one=(None,)))
    assert make_store(conn).service_frontier_in(conn, HostilePriority(0)) == 0.0
    text, _ = conn.calls[0]
    assert quoted(f'p{HostilePriority(0)}_service') in text
    assert_bound(conn.calls[0], (HOSTILE_VALUE,))


# P10: purge_namespace() routes every cleanup table through Identifier.
def test_purge_namespace_quotes_identifiers_and_binds_values(monkeypatch):
    conn = RecordingConnection()
    real_sql = pg.sql()
    hostile_sql = SimpleNamespace(SQL=real_sql.SQL, Identifier=lambda _name: real_sql.Identifier(HOSTILE_IDENTIFIER))
    monkeypatch.setattr(pg, 'sql', lambda: hostile_sql)
    make_store(conn).purge_namespace()
    assert len(conn.calls) == 5
    for call in conn.calls:
        text, _ = call
        assert quoted(HOSTILE_IDENTIFIER) in text
        assert_bound(call, (HOSTILE_VALUE,))


# B1: postgres_keys() quotes a typed table and binds its namespace.
def test_postgres_keys_quotes_identifier_and_binds_values(monkeypatch):
    conn = RecordingConnection()
    monkeypatch.setattr(backfill, '_TYPED', {HOSTILE_IDENTIFIER})
    assert backfill.postgres_keys(conn, HOSTILE_VALUE, HOSTILE_IDENTIFIER) == set()
    text, _ = conn.calls[0]
    assert quoted(HOSTILE_IDENTIFIER) in text
    assert_bound(conn.calls[0], (HOSTILE_VALUE,))


def outbound_row():
    return (1, HOSTILE_VALUE, {}, 'policy', 0.0, 1, 'wake', HOSTILE_VALUE, 0.0)


# O1: claim() composes the fixed RETURNING list while binding the lease values.
def test_outbox_claim_composes_returning_and_binds_values(monkeypatch):
    conn = RecordingConnection(Result(rows=[(1, HOSTILE_VALUE, {})]), Result(one=outbound_row()))
    monkeypatch.setattr(outbox_pg, '_token', lambda: HOSTILE_VALUE)
    assert len(make_outbox(conn).claim(1, 50.0, now=10.0)) == 1
    assert isinstance(conn.queries[1], psycopg_sql.Composable)
    text, _ = conn.calls[1]
    assert f'RETURNING {outbox_pg._COLUMNS}' in text
    assert_bound(conn.calls[1], (HOSTILE_VALUE, 60.0, 1))


# O3: claim_key() composes the fixed RETURNING list while binding the new lease.
def test_outbox_claim_key_composes_returning_and_binds_values(monkeypatch):
    selected = (1, HOSTILE_VALUE, {}, 'policy', 0.0, 0, 'wake', HOSTILE_VALUE, 0.0, None)
    conn = RecordingConnection(Result(one=selected), Result(one=outbound_row()))
    monkeypatch.setattr(outbox_pg, '_token', lambda: HOSTILE_VALUE)
    assert isinstance(make_outbox(conn).claim_key('1', 'wake', 50.0, now=10.0), Claim)
    assert isinstance(conn.queries[1], psycopg_sql.Composable)
    text, _ = conn.calls[1]
    assert f'RETURNING {outbox_pg._COLUMNS}' in text
    assert_bound(conn.calls[1], (HOSTILE_VALUE, 60.0, 1))


# O4: _fenced_update() composes only LiteralString fragments; all claim data stays bound.
def test_outbox_fenced_update_composes_fragments_and_binds_values():
    conn = RecordingConnection(Result(one=(1,)))
    claim = Claim(
        kind=OutboxKind.ENRICHMENT,
        row_id='1',
        lease_token=HOSTILE_VALUE,
        wake_token='wake',
        attempt=1,
        lease_until=10.0,
        owner_id=HOSTILE_VALUE,
        payload={},
        policy_id='policy',
    )
    assert make_outbox(conn).heartbeat(claim, 50.0, now=10.0)
    assert isinstance(conn.queries[0], psycopg_sql.Composable)
    text, _ = conn.calls[0]
    assert 'SET lease_until = %s' in text
    assert 'AND lease_until > %s' in text
    assert_bound(conn.calls[0], (60.0, 1, HOSTILE_VALUE, HOSTILE_VALUE, 10.0))


# S1: the simulator quotes each FROM identifier, SQL-quotes its projected table value, and binds namespaces.
def test_sim_rows_all_quotes_identifier_literal_and_binds_values(monkeypatch):
    conn = RecordingConnection()
    monkeypatch.setattr(sim_pg, '_TYPED', (HOSTILE_IDENTIFIER,))
    holder = SimpleNamespace(pg=SimpleNamespace(namespace=HOSTILE_VALUE, pool=Pool(conn)))
    assert sim_pg.PgRows(holder)._all() == {}
    text, _ = conn.calls[0]
    assert quoted(HOSTILE_IDENTIFIER) in text
    assert psycopg_sql.Literal(HOSTILE_IDENTIFIER).as_string() in text
    assert_bound(conn.calls[0], (HOSTILE_VALUE, HOSTILE_VALUE))


# S2: the simulator delete quotes a typed table and keeps keys and namespaces as parameters.
def test_sim_delete_quotes_identifier_and_binds_values(monkeypatch):
    conn = RecordingConnection()
    monkeypatch.setattr(sim_pg, '_TYPED', (HOSTILE_IDENTIFIER,))
    store = object.__new__(sim_pg.PgSimStore)
    store.pg = SimpleNamespace(namespace=HOSTILE_VALUE, pool=Pool(conn))
    store.delete(HOSTILE_IDENTIFIER, HOSTILE_VALUE)
    text, _ = conn.calls[0]
    assert quoted(HOSTILE_IDENTIFIER) in text
    assert_bound(conn.calls[0], (HOSTILE_VALUE, HOSTILE_VALUE))


@pytest.mark.parametrize(
    'module',
    [
        'database.jobstore.connection',
        'database.jobstore.postgres_store',
        'database.jobstore.outbox_pg',
        'database.jobstore.backfill',
        'testing.pipeline_sim.postgres_store',
    ],
)
def test_jobstore_imports_without_psycopg(module):
    """A clean interpreter can import every changed caller with psycopg explicitly unavailable."""
    backend = Path(__file__).resolve().parents[2]
    script = f'''
import importlib.abc
import sys

class BlockPsycopg(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "psycopg" or fullname.startswith("psycopg."):
            raise ModuleNotFoundError("psycopg intentionally unavailable", name=fullname)
        return None

sys.meta_path.insert(0, BlockPsycopg())
import {module}
assert "psycopg" not in sys.modules
'''
    subprocess.run([sys.executable, '-c', script], cwd=backend, check=True)
