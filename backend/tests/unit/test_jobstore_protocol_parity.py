"""Every batch Store backend implements the whole protocol the scheduler and merge call (plan A3 step 1).

The doc-mode Postgres store drifted behind ``FirestoreStore`` as merge and capacity grew new reads
(``first_ready_pending``, ``fresh_pending``, ``held_merge_owners``, ``longest_ready_pending``,
``projection_successor``, ``ready_for_capacity``): a Postgres primary would have failed on first use.
This guard runs in the unit shards, without a database, so the next new read fails here instead.
"""

from __future__ import annotations

import inspect
from unittest.mock import Mock

import pytest

from database import batch_pipeline_store as firestore_store
from database.batch_pipeline_projection_finish_backfill import BACKFILL_KEY, BACKFILL_VERSION
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


def test_pg_sim_forwards_the_due_page_cursor():
    store = object.__new__(PgSimStore)
    store.pg = Mock()
    store.pg.projection_page.return_value = (['a'], (10.0, 3.0, 'a'))
    assert store.projection_page(1, after=(5.0,), states=('ready',), due_before=10.0) == (['a'], (10.0, 3.0, 'a'))
    store.pg.projection_page.assert_called_once_with(1, after=(5.0,), states=('ready',), due_before=10.0)


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
