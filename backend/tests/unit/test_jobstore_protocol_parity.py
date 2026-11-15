"""Every batch Store backend implements the whole protocol the scheduler and merge call (plan A3 step 1).

The doc-mode Postgres store drifted behind ``FirestoreStore`` as merge and capacity grew new reads
(``first_ready_pending``, ``fresh_pending``, ``held_merge_owners``, ``longest_ready_pending``,
``projection_successor``, ``ready_for_capacity``): a Postgres primary would have failed on first use.
This guard runs in the unit shards, without a database, so the next new read fails here instead.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, Mock

import pytest

from database import batch_pipeline_store as firestore_store
from database.batch_pipeline_projection_finish_backfill import BACKFILL_KEY, BACKFILL_VERSION
from database.batch_pipeline_projection_followup_backfill import (
    BACKFILL_KEY as FOLLOWUP_BACKFILL_KEY,
    BACKFILL_VERSION as FOLLOWUP_BACKFILL_VERSION,
)
from database.jobstore.postgres_store import PostgresStore, PostgresTransaction
from testing.pipeline_sim.postgres_store import PgSimStore
from testing.pipeline_sim.store import SimStore, SimTransaction


def _public(cls) -> set[str]:
    return {name for name, value in vars(cls).items() if callable(value) and not name.startswith('_')}


def _protocol(cls) -> set[str]:
    return {name for name in vars(cls) if not name.startswith('_')}


# Every public read the Firestore store serves, plus the declared protocols.
STORE_METHODS = sorted(_protocol(firestore_store.Store) | (_public(firestore_store.FirestoreStore) - {'client'}))
TRANSACTION_METHODS = sorted(_protocol(firestore_store.Transaction) | _public(firestore_store.FirestoreTransaction))


def _parameters(function) -> list[str]:
    return [name for name in inspect.signature(function).parameters if name != 'self']


@pytest.mark.parametrize('backend', [PostgresStore, SimStore, PgSimStore], ids=lambda cls: cls.__name__)
@pytest.mark.parametrize('method', STORE_METHODS)
def test_every_store_backend_serves_the_firestore_store_surface(backend, method):
    assert hasattr(backend, method), f'{backend.__name__} lacks {method}'
    reference = getattr(firestore_store.FirestoreStore, method, None)
    if reference is not None and method != 'run':
        assert _parameters(getattr(backend, method)) == _parameters(reference), method


@pytest.mark.parametrize('backend', [PostgresTransaction, SimTransaction], ids=lambda cls: cls.__name__)
@pytest.mark.parametrize('method', [name for name in TRANSACTION_METHODS if name != 'flush'])
def test_every_transaction_backend_serves_the_firestore_transaction_surface(backend, method):
    assert hasattr(backend, method), f'{backend.__name__} lacks {method}'
    assert _parameters(getattr(backend, method)) == _parameters(getattr(firestore_store.FirestoreTransaction, method))


@pytest.mark.parametrize('backend', [PostgresStore, SimStore, PgSimStore], ids=lambda cls: cls.__name__)
def test_projection_page_signature_matches_firestore(backend):
    assert inspect.signature(backend.projection_page, eval_str=True) == inspect.signature(
        firestore_store.FirestoreStore.projection_page, eval_str=True
    )


@pytest.mark.parametrize('clock', ['due_before', 'followup_due_before'])
def test_pg_sim_forwards_the_due_page_cursor(clock):
    store = object.__new__(PgSimStore)
    store.pg = Mock()
    store.pg.projection_page.return_value = (['a'], (10.0, 3.0, 'a'))
    cutoffs = dict(due_before=None, followup_due_before=None)
    cutoffs[clock] = 10.0
    assert store.projection_page(1, after=(5.0,), states=('ready',), **cutoffs) == (['a'], (10.0, 3.0, 'a'))
    store.pg.projection_page.assert_called_once_with(1, after=(5.0,), states=('ready',), **cutoffs)


@pytest.mark.parametrize('backend', [PostgresStore, SimStore])
@pytest.mark.parametrize(
    'marker,complete',
    [
        ({}, False),
        ({'version': BACKFILL_VERSION, 'complete': False}, False),
        ({'version': BACKFILL_VERSION - 1, 'complete': True}, False),
        ({'version': BACKFILL_VERSION, 'complete': True}, True),
    ],
)
def test_finish_marker_is_read_from_the_backend_control_store(backend, marker, complete):
    store = object.__new__(backend)
    transaction = Mock()
    transaction.get.return_value = marker
    store.run = Mock(side_effect=lambda body: body(transaction))
    assert store.projection_finish_backfill_complete() is complete
    transaction.get.assert_called_once_with('control', BACKFILL_KEY)


def test_pg_sim_forwards_finish_marker_to_postgres():
    store = object.__new__(PgSimStore)
    store.pg = Mock()
    store.pg.projection_finish_backfill_complete.return_value = False
    assert store.projection_finish_backfill_complete() is False
    store.pg.projection_finish_backfill_complete.assert_called_once_with()


def test_pg_sim_forwards_the_independent_record_ready_page():
    store = object.__new__(PgSimStore)
    store.pg = Mock()
    store.pg.ready_pending.return_value = [{'segment_id': 'independent'}]
    assert store.ready_pending('synthetic-owner', 160) == [{'segment_id': 'independent'}]
    store.pg.ready_pending.assert_called_once_with('synthetic-owner', 160, after=None)


def test_every_serving_read_is_in_the_executable_parity_census():
    from database.jobstore.serving_parity import STORE_QUERIES, TRANSACTION_QUERIES

    mutations = {
        'run',
        'acquire_pull_claim',
        'quarantine_fenced',
        'cancel_fenced_recovery',
        'defer_privacy_blocked_record',
    }
    assert STORE_QUERIES == _public(firestore_store.FirestoreStore) - mutations - {'client'}
    assert TRANSACTION_QUERIES == _public(firestore_store.FirestoreTransaction) - {
        'put',
        'patch',
        'defer_set',
        'check_privacy',
        'flush',
    }


@pytest.mark.parametrize('backend', [PostgresStore, SimStore])
@pytest.mark.parametrize(
    'marker,complete',
    [
        ({}, False),
        ({'version': FOLLOWUP_BACKFILL_VERSION, 'complete': False}, False),
        ({'version': FOLLOWUP_BACKFILL_VERSION - 1, 'complete': True}, False),
        ({'version': FOLLOWUP_BACKFILL_VERSION, 'complete': True}, True),
    ],
)
def test_followup_marker_is_read_from_its_backend_and_independent_key(backend, marker, complete):
    store = object.__new__(backend)
    transaction = Mock()
    transaction.get.return_value = marker
    store.run = Mock(side_effect=lambda body: body(transaction))
    assert store.projection_followup_backfill_complete() is complete
    transaction.get.assert_called_once_with('control', FOLLOWUP_BACKFILL_KEY)
    assert FOLLOWUP_BACKFILL_KEY != BACKFILL_KEY


def test_pg_sim_forwards_followup_marker_to_postgres():
    store = object.__new__(PgSimStore)
    store.pg = Mock()
    store.pg.projection_followup_backfill_complete.return_value = False
    assert store.projection_followup_backfill_complete() is False
    store.pg.projection_followup_backfill_complete.assert_called_once_with()


@pytest.mark.parametrize('backend', [PostgresStore, SimStore])
def test_projection_page_rejects_combining_independent_clocks(backend):
    with pytest.raises(ValueError, match='cannot be combined'):
        object.__new__(backend).projection_page(due_before=10.0, followup_due_before=20.0)


def test_sim_followup_clock_filters_and_resumes_equal_clock_rows_independently():
    store = object.__new__(SimStore)
    store.rows = {
        ('results', 'b'): dict(
            projection_state='ready', committed_at=3.0, projection_followup_due_at=10.0, projection_finish_due_at=90.0
        ),
        ('results', 'a'): dict(
            projection_state='ready', committed_at=3.0, projection_followup_due_at=10.0, projection_finish_due_at=90.0
        ),
        ('results', 'future'): dict(
            projection_state='ready', committed_at=1.0, projection_followup_due_at=20.0, projection_finish_due_at=1.0
        ),
        ('results', 'legacy'): dict(projection_state='ready', committed_at=0.0, projection_finish_due_at=1.0),
    }
    ids, after = store.projection_page(1, states=('ready',), followup_due_before=10.0)
    assert ids == ['a'] and after == (10.0, 3.0, 'a')
    assert store.projection_page(2, after=after, states=('ready',), followup_due_before=10.0) == (['b'], None)
    assert store.projection_page(10, states=('ready',), due_before=10.0) == (['legacy', 'future'], None)
    assert store.projection_page(10, states=('ready',))[0] == ['legacy', 'future', 'a', 'b']


@pytest.mark.parametrize(
    'clock,field', [('due_before', 'projection_finish_due_at'), ('followup_due_before', 'projection_followup_due_at')]
)
@pytest.mark.parametrize('after,expected_params', [((5.0,), (5.0,)), ((5.0, 2.0, 'a'), (5.0, 2.0, 'a'))])
def test_postgres_selected_clock_governs_filter_order_and_cursor(clock, field, after, expected_params):
    store = object.__new__(PostgresStore)
    store.namespace = 'batch_pipeline_test_clock'
    connection = MagicMock()
    connection.execute.return_value.fetchall.return_value = [('b', 3.0, 10.0)]
    store._read_conn = MagicMock()
    store._read_conn.return_value.__enter__.return_value = connection
    assert store.projection_page(1, after=after, states=('ready',), **{clock: 10.0}) == (['b'], (10.0, 3.0, 'b'))
    statement, params = connection.execute.call_args.args
    selected = f"(doc->>'{field}')::float8"
    other = 'projection_finish_due_at' if clock == 'followup_due_before' else 'projection_followup_due_at'
    assert f'{selected} <= %s' in statement and other not in statement
    assert f'ORDER BY {selected}, committed_at, key COLLATE "C"' in statement
    assert (
        f'{selected} >= %s' if len(after) == 1 else f'({selected}, committed_at, key COLLATE "C") > (%s, %s, %s)'
    ) in statement
    assert params == (store.namespace, ['ready'], 10.0, *expected_params, 1)
