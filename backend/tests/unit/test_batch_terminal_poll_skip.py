"""Terminal discovery must not remove unready fresh heads or their bounded wait."""

from copy import copy, deepcopy
from types import SimpleNamespace

import pytest

from config.batch_pipeline import MERGE_POLL_TERMINAL_STATES, held_poll_skip_enabled
from database.batch_pipeline_store import first_pending, fresh_pending, is_queue_dispositioned
from database.firestore_index_registry import firebase_index_manifest
from utils.batch_pipeline.merge import _fresh_pick

TERMINAL = MERGE_POLL_TERMINAL_STATES
NONTERMINAL = (
    'ready',
    'leased',
    'retry',
    'result_ready',
    'record_pending',
    'held',
    'provider_pending',
    'provider_running',
    'vendor_held',
    'future_state',
)


class Query:
    """Record RPC shape and apply Firestore filtering before ordering/limit."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.reads = []
        self.filters = []
        self.orders = []
        self.count = None

    def collection(self, name):
        self.calls.append(('collection', name))
        return self

    def where(self, field, op, value):
        self.calls.append(('where', field, op, value))
        query = copy(self)
        query.filters = [*self.filters, (field, op, value)]
        return query

    def order_by(self, field):
        self.calls.append(('order_by', field))
        query = copy(self)
        query.orders = [*self.orders, field]
        return query

    def limit(self, count):
        self.calls.append(('limit', count))
        query = copy(self)
        query.count = count
        return query

    def stream(self, **kwargs):
        self.calls.append(('stream', kwargs))
        rows = self.rows
        for field, op, value in self.filters:
            rows = [r for r in rows if field in r and (r[field] == value if op == '==' else r[field] not in value)]
        rows = sorted(rows, key=lambda row: tuple(row[field] for field in self.orders))
        for row in rows[: self.count]:
            self.reads.append(row['segment_id'])
            yield SimpleNamespace(to_dict=lambda row=row: deepcopy(row))


def row(state, capture=1, **fields):
    return dict(
        state=state,
        segment_id=state,
        owner_key='owner',
        merge_pending=True,
        fresh_capture=True,
        capture_at=capture,
        **fields,
    )


@pytest.mark.parametrize('path', ['fresh', 'first'])
@pytest.mark.parametrize('setting', [None, 'false', '0', 'invalid'])
def test_off_exact_old_rpc_and_read_sequence(monkeypatch, path, setting):
    if setting is None:
        monkeypatch.delenv('BATCH_HELD_POLL_SKIP_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', setting)
    assert not held_poll_skip_enabled()
    query = Query([row('dead', 0), row('retry'), row('result_ready', 2)])
    expected = [
        ('collection', 'ns_jobs'),
        ('where', 'owner_key', '==', 'owner'),
        ('where', 'merge_pending', '==', True),
    ]
    if path == 'fresh':
        assert [r['state'] for r in fresh_pending(query, 'ns', 'owner', 32)] == ['dead', 'retry', 'result_ready']
        expected += [('where', 'fresh_capture', '==', True)]
    else:
        assert first_pending(query, 'ns', 'owner', transaction='tx')['state'] == 'dead'
    expected += [
        ('order_by', 'capture_at'),
        ('order_by', 'segment_id'),
        ('limit', 32 if path == 'fresh' else 1),
        ('stream', {} if path == 'fresh' else {'transaction': 'tx'}),
    ]
    assert query.calls == expected
    assert query.reads == (['dead', 'retry', 'result_ready'] if path == 'fresh' else ['dead'])


@pytest.mark.parametrize('state', NONTERMINAL)
def test_on_skips_terminal_reads_but_retains_each_nonterminal_head(monkeypatch, state):
    monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', 'true')
    assert not is_queue_dispositioned(row(state))
    rows = [*(row(terminal, 0) for terminal in TERMINAL), row(state)]
    query = Query(rows)
    assert [r['state'] for r in fresh_pending(query, 'ns', 'owner', 32)] == [state]
    assert query.reads == [state]
    query = Query(rows)
    assert first_pending(query, 'ns', 'owner', transaction='tx')['state'] == state
    assert query.reads == [state]
    assert ('where', 'state', 'not-in', list(TERMINAL)) in query.calls


@pytest.mark.parametrize('state', ['held', 'ready', 'retry', 'vendor_held'])
def test_fresh_head_wait_is_identical_for_held_and_decisionless_heads(monkeypatch, state):
    rows = [row(state), row('result_ready', 2, ready_at=10)]
    observations = []
    for enabled in ('false', 'true'):
        monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', enabled)
        pending = fresh_pending(Query(rows), 'ns', 'owner', 32)
        assert _fresh_pick(pending, 100, 300) == (None, None)
        observations.append(_fresh_pick(pending, 311, 300))
    assert observations[0] == observations[1]
    assert observations[0][1]['segment_ids'] == [state]


def test_both_index_shapes_are_in_the_generated_registry():
    manifest = firebase_index_manifest()['indexes']
    for stage in ('prod', 'dev'):
        for fresh in (False, True):
            fields = [
                'owner_key',
                'merge_pending',
                *(['fresh_capture'] if fresh else []),
                'capture_at',
                'segment_id',
                'state',
                '__name__',
            ]
            assert any(
                index['collectionGroup'] == f'batch_pipeline_{stage}_jobs'
                and index['queryScope'] == 'COLLECTION'
                and index['fields'] == [{'fieldPath': field, 'order': 'ASCENDING'} for field in fields]
                for index in manifest
            )


def test_excluded_set_is_the_terminal_union_and_nonterminal_complement():
    from tests.support.lifecycle_state_table import STATES
    from utils.batch_pipeline.provider_stt import PENDING, RUNNING, SUPERSEDED

    batch = {r.state for r in STATES if r.machine == 'batch'}
    lifecycle = {r.state for r in STATES if r.machine == 'batch' and r.terminal}
    dispositions = {state for state in batch if is_queue_dispositioned(row(state))}
    assert set(TERMINAL) == lifecycle | dispositions | {SUPERSEDED}
    known = batch | {PENDING, RUNNING, SUPERSEDED}
    assert known - set(TERMINAL) == set(NONTERMINAL) - {'held', 'future_state'}


@pytest.mark.parametrize('path', ['first', 'fresh'])
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('error_type', ['FailedPrecondition', 'InvalidArgument'])
def test_unavailable_on_query_falls_back_to_the_exact_off_query(monkeypatch, path, enabled, error_type):
    from google.api_core import exceptions

    class Unavailable(Query):
        def stream(self, **kwargs):
            if not enabled or any(field == 'state' for field, _, _ in self.filters):
                self.calls.append(('stream', kwargs))
                raise getattr(exceptions, error_type)('synthetic unavailable index or query')
            yield from super().stream(**kwargs)

    monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', str(enabled).lower())
    query = Unavailable([row('dead', 0), row('retry')])

    def read():
        if path == 'first':
            return [first_pending(query, 'ns', 'owner', transaction='tx')]
        return fresh_pending(query, 'ns', 'owner', 32)

    if not enabled:
        with pytest.raises(getattr(exceptions, error_type)):
            read()
    else:
        assert [r['state'] for r in read()] == (['dead'] if path == 'first' else ['dead', 'retry'])
        assert query.calls[-4:] == [
            ('order_by', 'capture_at'),
            ('order_by', 'segment_id'),
            ('limit', 1 if path == 'first' else 32),
            ('stream', {'transaction': 'tx'} if path == 'first' else {}),
        ]


def test_postgres_off_sql_and_parameter_sequence_are_unchanged(monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import MagicMock
    from database.jobstore.postgres_store import PostgresStore

    monkeypatch.delenv('BATCH_HELD_POLL_SKIP_ENABLED', raising=False)
    store = object.__new__(PostgresStore)
    store.namespace = 'ns'
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None
    conn.execute.return_value.fetchall.return_value = []

    @contextmanager
    def connection():
        yield conn

    monkeypatch.setattr(store, '_read_conn', connection)
    assert store.first_pending_in(conn, 'owner') is None
    conn.execute.assert_called_once_with(
        'SELECT key, doc FROM jobs WHERE namespace = %s AND owner_key = %s AND merge_pending '
        'ORDER BY capture_at, key COLLATE "C" LIMIT 1',
        ('ns', 'owner'),
    )
    conn.reset_mock()
    assert store.fresh_pending('owner', 32) == []
    conn.execute.assert_called_once_with(
        "SELECT doc FROM jobs WHERE namespace = %s AND owner_key = %s AND merge_pending "
        "AND doc->'fresh_capture' = 'true'::jsonb ORDER BY capture_at, key COLLATE \"C\" LIMIT %s",
        ('ns', 'owner', 32),
    )
    conn.reset_mock()
    monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', 'true')
    assert store.fresh_pending('owner', 32) == []
    assert 'state <> ALL(%s)' in conn.execute.call_args.args[0]
    assert conn.execute.call_args.args[1] == ('ns', 'owner', list(TERMINAL), 32)
    conn.reset_mock()
    assert store.first_pending_in(conn, 'owner') is None
    assert 'state <> ALL(%s)' in conn.execute.call_args.args[0]
    assert conn.execute.call_args.args[1] == ('ns', 'owner', list(TERMINAL))
