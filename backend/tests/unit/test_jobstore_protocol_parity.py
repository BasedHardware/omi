"""Every batch Store backend implements the whole protocol the scheduler and merge call (plan A3 step 1).

The doc-mode Postgres store drifted behind ``FirestoreStore`` as merge and capacity grew new reads
(``first_ready_pending``, ``fresh_pending``, ``held_merge_owners``, ``longest_ready_pending``,
``projection_successor``, ``ready_for_capacity``): a Postgres primary would have failed on first use.
This guard runs in the unit shards, without a database, so the next new read fails here instead.
"""

from __future__ import annotations

import inspect

import pytest

from database import batch_pipeline_store as firestore_store
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
