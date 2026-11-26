"""Terminal discovery must not remove unready fresh heads or their bounded wait."""

from copy import copy, deepcopy
from types import SimpleNamespace

import pytest

from database.batch_pipeline_store import first_pending, fresh_pending
from database.firestore_index_registry import firebase_index_manifest
from utils.batch_pipeline.merge import _fresh_pick


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

    def order_by(self, field, direction='ASCENDING'):
        self.calls.append(('order_by', field))
        query = copy(self)
        query.orders = [*self.orders, field]
        query.descending = direction == 'DESCENDING'
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
            rows = [
                r
                for r in rows
                if field in r
                and (
                    r[field] == value
                    if op == '=='
                    else (
                        r[field] > value
                        if op == '>'
                        else r[field] <= value if op == '<=' else r[field] is not None and r[field] not in value
                    )
                )
            ]
        rows = sorted(
            rows, key=lambda row: tuple(row[field] for field in self.orders), reverse=getattr(self, 'descending', False)
        )
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
def test_pending_queries_preserve_capture_order_and_read_sequence(path):
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


@pytest.mark.parametrize('state', ['held', 'ready', 'retry', 'vendor_held'])
def test_fresh_head_wait_preserves_held_and_decisionless_heads(state):
    rows = [row(state), row('result_ready', 2, ready_at=10)]
    pending = fresh_pending(Query(rows), 'ns', 'owner', 32)
    assert _fresh_pick(pending, 100, 300) == (None, None)
    assert _fresh_pick(pending, 311, 300)[1]['segment_ids'] == [state]


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


def test_postgres_poll_sql_and_parameter_sequence(monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import MagicMock
    from database.jobstore.postgres_store import PostgresStore

    store = object.__new__(PostgresStore)
    store.namespace = 'ns'
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None
    conn.execute.return_value.fetchall.return_value = []

    @contextmanager
    def connection():
        yield conn

    def assert_execute(text, params):
        conn.execute.assert_called_once()
        query, actual_params = conn.execute.call_args.args
        assert (query if isinstance(query, str) else query.as_string(None)) == text
        assert actual_params == params

    monkeypatch.setattr(store, '_read_conn', connection)
    assert store.first_pending_in(conn, 'owner') is None
    assert_execute(
        'SELECT key, doc FROM jobs WHERE namespace = %s AND owner_key = %s AND merge_pending '
        'ORDER BY capture_at, key COLLATE "C" LIMIT 1',
        ('ns', 'owner'),
    )
    conn.reset_mock()
    assert store.fresh_pending('owner', 32) == []
    assert_execute(
        "SELECT doc FROM jobs WHERE namespace = %s AND owner_key = %s AND merge_pending "
        "AND doc->'fresh_capture' = 'true'::jsonb ORDER BY capture_at, key COLLATE \"C\" LIMIT %s",
        ('ns', 'owner', 32),
    )


@pytest.mark.parametrize('state', ['missing', None])
def test_missing_and_null_pending_state_stays_visible(state):
    legacy = row(state)
    legacy['segment_id'] = 'legacy'
    if state == 'missing':
        del legacy['state']
    expected = [legacy]
    assert fresh_pending(Query([legacy]), 'ns', 'owner', 32) == expected
    assert first_pending(Query([legacy]), 'ns', 'owner') == legacy


@pytest.mark.parametrize('counts, output, status', [([7, 7, 5, 5], 'PASS (0)\n', 0), ([7, 7, 5, 3], 'FAIL (2)\n', 1)])
def test_census_cli_combines_both_collections_and_only_aggregates(monkeypatch, capsys, counts, output, status):
    import runpy
    from pathlib import Path
    from unittest.mock import MagicMock, call
    from google.cloud import firestore
    from scripts import batch_pipeline_poll_state_census as tool

    client = MagicMock()
    query = client.collection.return_value
    query.where.return_value = query
    query.count.return_value.get.side_effect = [[[SimpleNamespace(value=n)]] for n in counts]
    monkeypatch.setattr(firestore, 'Client', lambda **kwargs: client)
    monkeypatch.setattr(firestore, 'transactional', lambda function: function)
    monkeypatch.setattr('sys.argv', ['census', '--project', 'demo-omi-isolated-tests'])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(Path(tool.__file__)), run_name='__main__')
    assert exit_info.value.code == status
    assert capsys.readouterr().out == output
    assert client.collection.call_args_list == [call('batch_pipeline_prod_jobs'), call('batch_pipeline_dev_jobs')]
    assert client.transaction.call_args_list == [call(read_only=True), call(read_only=True)]
    assert query.count.return_value.get.call_args_list == [call(transaction=client.transaction.return_value)] * 4
    assert not query.stream.called and not query.get.called
    for index, invocation in enumerate(query.where.call_args_list):
        actual = invocation.kwargs['filter']
        assert (actual.field_path, actual.op_string, actual.value) == (
            ('merge_pending', '==', True) if index % 2 == 0 else ('state', 'in', tool.KNOWN_STATES)
        )


def test_a_ready_provider_row_without_ready_at_waits_on_its_settle_instant(monkeypatch):
    """2026-11-13: ready fresh provider rows without ready_at never passed an unready fresh head."""
    provider = {'stt_route': {'stt_route': 'provider'}, 'provider_intent': {'settled_at': 10}}
    rows = [row('vendor_held', 1), dict(row('result_ready', 2), **provider)]
    assert _fresh_pick(rows, 100, 300) == (None, None)  # settled 90 s ago
    picked, skipped = _fresh_pick(rows, 311, 300)
    assert picked['state'] == 'result_ready' and skipped['segment_ids'] == ['vendor_held'] and skipped['waited'] == 301
    # The settle instant stands in only for provider rows, and only while membership is on.
    assert _fresh_pick([row('retry', 1), row('result_ready', 2, provider_intent={'settled_at': 10})], 311, 300) == (
        None,
        None,
    )
    monkeypatch.setenv('BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED', 'false')
    assert _fresh_pick(rows, 311, 300) == (None, None)
