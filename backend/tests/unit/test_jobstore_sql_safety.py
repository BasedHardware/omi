"""Every dynamic identifier in the Postgres job store is quoted and every value is bound.

The job store already allowlists the tables, columns and states it will touch, so these are
defence-in-depth checks on the SQL construction itself: a hostile table, column, state, namespace or
value must never reach a statement as text. A fake connection records the composed statement and its
parameters, so the assertions are about query shape, not a live database.
"""

from __future__ import annotations

import ast
from contextlib import contextmanager
from pathlib import Path

import pytest

from database.jobstore import backfill, dual_store, outbox_pg, postgres_store
from database.jobstore.connection import sql
from database.outbox import Claim, OutboxKind

HOSTILE = "jobs; DROP TABLE jobs; --"


def render(statement) -> str:
    return statement.as_string(None) if hasattr(statement, 'as_string') else statement


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Conn:
    """A connection that records each statement and returns the next queued result set."""

    def __init__(self, *results):
        self.results = list(results)
        self.statements: list[tuple[str, object]] = []

    @contextmanager
    def transaction(self):
        yield

    def execute(self, statement, params=()):
        self.statements.append((render(statement), params))
        return Result(self.results.pop(0) if self.results else ())


class Pool:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def connection(self, timeout: float = 30.0):
        yield self.conn


def store(conn, namespace: str = 'batch_pipeline_test_sql') -> postgres_store.PostgresStore:
    return postgres_store.PostgresStore(namespace, pool=Pool(conn), customer_client=None)


def outbox(conn) -> outbox_pg.PostgresOutbox:
    return outbox_pg.PostgresOutbox(OutboxKind.ENRICHMENT, store(conn))


# -- postgres_store -------------------------------------------------------------------------------


def test_due_quotes_the_allowlisted_column_and_binds_every_value():
    conn = Conn([('k1',)])
    assert store(conn).due('leased', 10.0, limit=5) == ['k1']
    statement, params = conn.statements[0]
    assert '"lease_until"' in statement
    assert statement.count('%s') == 4
    assert params == ('batch_pipeline_test_sql', 'leased', 10.0, 5)


def test_due_rejects_an_unknown_state_before_any_sql():
    conn = Conn()
    with pytest.raises(ValueError):
        store(conn).due(HOSTILE, 0.0)
    assert conn.statements == []


def test_control_candidates_quotes_priority_columns_and_binds_values():
    conn = Conn([('c1', 1.0)])
    assert store(conn).control_candidates(2, 'live', 5.0) == ['c1']
    statement, params = conn.statements[0]
    assert '"p2_service"' in statement
    assert '"p2_active"' in statement
    assert '"p2_live_at"' in statement
    assert params == ('batch_pipeline_test_sql', 5.0, 1)


@pytest.mark.parametrize(
    'priority,pool',
    [(3, 'batch'), (-1, 'batch'), (0, 'prod'), (0, "batch'; DROP TABLE control; --")],
)
def test_control_candidates_rejects_unbounded_priority_or_pool(priority, pool):
    conn = Conn()
    with pytest.raises(ValueError):
        store(conn).control_candidates(priority, pool, 0.0)
    assert conn.statements == []


def test_typed_document_tables_are_quoted_identifiers():
    conn = Conn([({'a': 1},)])
    assert store(conn).read_doc(conn, 'jobs', 'k') == {'a': 1}
    statement, params = conn.statements[0]
    assert statement.startswith('SELECT doc FROM "jobs"')
    assert params == ('batch_pipeline_test_sql', 'k')


def test_unknown_table_never_reaches_the_statement_as_an_identifier():
    conn = Conn([()])
    store(conn).read_doc(conn, HOSTILE, 'k')
    statement, params = conn.statements[0]
    assert 'FROM docs' in statement
    assert HOSTILE not in statement
    assert params == ('batch_pipeline_test_sql', HOSTILE, 'k')


def test_write_and_delete_quote_typed_tables_and_bind_unknown_ones():
    conn = Conn([], [])
    store(conn).write_doc(conn, 'results', 'k', {'a': 1})
    store(conn).delete_doc(conn, 'results', 'k')
    insert, delete = conn.statements
    assert insert[0].startswith('INSERT INTO "results"')
    assert delete[0] == 'DELETE FROM "results" WHERE namespace = %s AND key = %s'

    conn = Conn([], [])
    store(conn).write_doc(conn, HOSTILE, 'k', {'a': 1})
    store(conn).delete_doc(conn, HOSTILE, 'k')
    for statement, params in conn.statements:
        assert HOSTILE not in statement
        assert 'FROM docs' in statement or 'INTO docs' in statement
        assert HOSTILE in params


def test_service_frontier_quotes_the_priority_column():
    conn = Conn([(3.0,)])
    assert store(conn).service_frontier_in(conn, 1) == 3.0
    statement, params = conn.statements[0]
    assert '"p1_service"' in statement
    assert params == ('batch_pipeline_test_sql',)


def test_service_frontier_rejects_an_unbounded_priority():
    conn = Conn()
    with pytest.raises(ValueError):
        store(conn).service_frontier_in(conn, 3)
    assert conn.statements == []


def test_purge_namespace_quotes_every_table_and_refuses_a_non_test_namespace():
    conn = Conn()
    store(conn).purge_namespace()
    assert [statement for statement, _ in conn.statements] == [
        f'DELETE FROM "{table}" WHERE namespace = %s' for table in ('jobs', 'results', 'control', 'docs', 'outbox')
    ]
    with pytest.raises(RuntimeError):
        store(conn, 'batch_pipeline_prod').purge_namespace()


def test_first_pending_in_composes_the_state_fragment():
    conn = Conn([('k', {})])
    store(conn).first_pending_in(conn, 'ok', result_ready=True)
    statement, params = conn.statements[0]
    assert "state = 'result_ready'" in statement
    assert params == ('batch_pipeline_test_sql', 'ok')


def test_projection_page_binds_states_and_cursor():
    conn = Conn([])
    store(conn).projection_page(10, after=(1.0, 'k'))
    statement, params = conn.statements[0]
    assert 'projection_state = ANY(%s)' in statement
    assert params[0] == 'batch_pipeline_test_sql'
    assert params[-1] == 10


def test_projection_successor_binds_previous_segment():
    conn = Conn([])
    store(conn).projection_successor('ok', HOSTILE)
    statement, params = conn.statements[0]
    assert 'DROP TABLE' not in statement
    assert params['previous'] == HOSTILE


# -- outbox ---------------------------------------------------------------------------------------


def test_outbox_claim_composes_returning_columns_and_binds_values():
    conn = Conn([(1, 'o', {})], [(1, 'o', {}, None, 0.0, 0, 'w', 'l', 0.0)])
    claims = outbox(conn).claim(1, 30.0, now=10.0)
    assert [claim.row_id for claim in claims] == ['1']
    select, update = conn.statements
    assert 'FROM outbox' in select[0]
    assert 'RETURNING id, owner_id, payload' in update[0]
    assert update[1][1:] == (40.0, 1)


def test_outbox_fenced_update_composes_sets_and_guard():
    conn = Conn([(1,)])
    claim = Claim(
        kind=OutboxKind.ENRICHMENT,
        row_id='1',
        lease_token='t',
        wake_token='w',
        attempt=1,
        lease_until=0.0,
        owner_id='o',
        payload={},
        policy_id=None,
    )
    assert outbox(conn).heartbeat(claim, 30.0, now=10.0) is True
    statement, params = conn.statements[0]
    assert 'SET lease_until = %s' in statement
    assert 'AND lease_until > %s' in statement
    assert params == (40.0, 1, 'batch_pipeline_test_sql', 't', 10.0)


def test_outbox_sweep_composes_the_actionable_predicate():
    conn = Conn([(1, 'o', {})], [])
    outbox(conn).sweep(now=10.0, limit=5)
    for statement, _ in conn.statements:
        assert 'lease_until > 0 AND lease_until <= %s' in statement
        assert 'wake_pending AND lease_until <= %s' in statement


# -- backfill -------------------------------------------------------------------------------------


def test_backfill_quotes_typed_tables_and_binds_unknown_ones():
    conn = Conn([('k1',)])
    assert backfill.postgres_keys(conn, 'ns', 'jobs') == {'k1'}
    statement, params = conn.statements[0]
    assert statement == 'SELECT key FROM "jobs" WHERE namespace = %s'
    assert params == ('ns',)

    conn = Conn([('k1',)])
    assert backfill.postgres_keys(conn, 'ns', HOSTILE) == {'k1'}
    statement, params = conn.statements[0]
    assert 'FROM docs' in statement
    assert HOSTILE not in statement
    assert params == ('ns', HOSTILE)


# -- dual_store -----------------------------------------------------------------------------------


def test_owner_rows_binds_owner_values_and_quotes_no_identifier():
    class Shadow:
        namespace = 'batch_pipeline_test_sql'

    dual = object.__new__(dual_store.DualStore)
    dual.shadow = Shadow()
    conn = Conn([], [], [], [])
    dual.owner_rows(conn, HOSTILE)
    owner_statements = [(statement, params) for statement, params in conn.statements if 'owner_key' in statement]
    assert len(owner_statements) == 3
    for statement, params in owner_statements:
        assert HOSTILE not in statement
        assert HOSTILE in params


def test_statement_timeout_is_a_literal_not_interpolated_text():
    assert sql.SQL('SET LOCAL statement_timeout = {}').format(sql.Literal(200)).as_string(None) == (
        'SET LOCAL statement_timeout = 200'
    )


def test_identifier_quoting_neutralises_a_hostile_name():
    composed = sql.SQL('SELECT 1 FROM {}').format(sql.Identifier('a"; DROP TABLE x; --')).as_string(None)
    assert composed == 'SELECT 1 FROM "a""; DROP TABLE x; --"'


# -- package invariant ----------------------------------------------------------------------------


def test_no_jobstore_module_passes_an_fstring_to_execute():
    offenders = []
    for path in sorted(Path(postgres_store.__file__).parent.glob('*.py')):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == 'execute'):
                continue
            if any(isinstance(arg, ast.JoinedStr) for arg in node.args):
                offenders.append(f'{path.name}:{node.lineno}')
    assert offenders == []
