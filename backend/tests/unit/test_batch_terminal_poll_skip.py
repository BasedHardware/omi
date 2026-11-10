"""Terminal discovery must not remove unready fresh heads or their bounded wait."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from config.batch_pipeline import MERGE_POLL_STATES, held_poll_skip_enabled
from database.batch_pipeline_store import first_pending, fresh_pending, is_queue_dispositioned
from database.firestore_index_registry import firebase_index_manifest
from utils.batch_pipeline.merge import _fresh_pick

TERMINAL = ('committed', 'dead', 'quarantined', 'privacy_blocked')


class Query:
    """Record RPC shape and apply Firestore filtering before ordering/limit."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.reads = []

    def collection(self, name):
        self.calls.append(('collection', name))
        return self

    def where(self, field, op, value):
        self.calls.append(('where', field, op, value))
        return self

    def order_by(self, field):
        self.calls.append(('order_by', field))
        return self

    def limit(self, count):
        self.calls.append(('limit', count))
        return self

    def stream(self, **kwargs):
        self.calls.append(('stream', kwargs))
        rows = self.rows
        for call in self.calls:
            if call[0] == 'where':
                _, field, op, value = call
                rows = [r for r in rows if field in r and (r[field] == value if op == '==' else r[field] in value)]
        orders = [call[1] for call in self.calls if call[0] == 'order_by']
        rows = sorted(rows, key=lambda row: tuple(row[field] for field in orders))
        count = next(call[1] for call in self.calls if call[0] == 'limit')
        for row in rows[:count]:
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


@pytest.mark.parametrize('state', MERGE_POLL_STATES)
def test_on_skips_terminal_reads_but_retains_each_nonterminal_head(monkeypatch, state):
    monkeypatch.setenv('BATCH_HELD_POLL_SKIP_ENABLED', 'true')
    assert not is_queue_dispositioned(row(state))
    rows = [*(row(terminal, 0) for terminal in TERMINAL), row(state)]
    for terminal in TERMINAL:
        assert is_queue_dispositioned(row(terminal))
    query = Query(rows)
    assert [r['state'] for r in fresh_pending(query, 'ns', 'owner', 32)] == [state]
    assert query.reads == [state]
    query = Query(rows)
    assert first_pending(query, 'ns', 'owner', transaction='tx')['state'] == state
    assert query.reads == [state]
    assert ('where', 'state', 'in', list(MERGE_POLL_STATES)) in query.calls


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
                'state',
                'capture_at',
                'segment_id',
                '__name__',
            ]
            assert any(
                index['collectionGroup'] == f'batch_pipeline_{stage}_jobs'
                and index['queryScope'] == 'COLLECTION'
                and index['fields'] == [{'fieldPath': field, 'order': 'ASCENDING'} for field in fields]
                for index in manifest
            )
