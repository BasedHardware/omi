"""The idempotency-key invariant holds on BOTH backends, for different reasons (ADR-0085, BACKLOG L46).

`create_action_item` reads by idempotency key inside a transaction and then writes. Measured:

    Firestore   the transaction LOCKS what it read, so a concurrent writer gets 409 Aborted and only
                one row is created
    Mongo       no read lock. Both transactions read "nothing there", both commit, and the user ends up
                with two identical tasks

The read being inside the transaction was never what protected the invariant — the lock was. On the
backend we deploy by default it has to be a unique partial index instead, and the interesting part is
the FILTER: it cannot be `completed == false` alone, because the retire path marks
`deleted: true, completed: false` and the product then deliberately creates a NEW item with the same key.
Mongo's partialFilterExpression cannot express "and not deleted" ($exists:false and $ne are not allowed),
so the retire path clears the key instead and the filter requires a string.

These tests run the real chain against a live Mongo replica set and a live Firestore emulator. The
concurrency test only means something on Mongo — Firestore's emulator serialises differently — so it
asserts the OUTCOME (one live row per key) rather than the mechanism, which is the invariant either way.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.fixture
def user(bind_store, request):
    run = uuid.uuid4().hex[:8]
    uid = f'dedup-{run}'

    if request.node.callspec.params['bind_store'] == 'mongo':
        # The index is what makes the duplicate impossible; without it this suite would pass on Firestore
        # and quietly prove nothing on Mongo.
        from scripts.reconcile_mongo_indexes import create_unique_indexes

        create_unique_indexes(bind_store._db)

    yield {'uid': uid, 'run': run, 'store': bind_store, 'backend': request.node.callspec.params['bind_store']}

    for document in bind_store.query(f'users/{uid}/action_items'):
        bind_store.delete(document.path)


def _payload(description='task'):
    return {'description': description, 'completed': False, 'conversation_id': 'c1'}


def _live_rows(user, key):
    return [
        document
        for document in user['store'].query(f"users/{user['uid']}/action_items")
        if (document.data or {}).get('idempotency_key') == key and not (document.data or {}).get('deleted')
    ]


def test_sequential_creates_with_one_key_make_one_item(user):
    """The path that already worked: the in-transaction read sees the first write."""
    import database.action_items as action_items_db

    key = f"k-{user['run']}"

    first = action_items_db.create_action_item(user['uid'], _payload(), idempotency_key=key)
    second = action_items_db.create_action_item(user['uid'], _payload(), idempotency_key=key)

    assert second == first
    assert len(_live_rows(user, key)) == 1


def test_a_stale_in_transaction_read_still_makes_one_item(user, monkeypatch):
    """The case that FAILED on Mongo, reproduced deterministically instead of hoped for.

    A first attempt at this used two threads and passed with the index REMOVED — the threads never
    overlapped, so it proved nothing. What actually happens on Mongo is not a timing coincidence: the
    transaction takes no lock on what it reads, so a concurrent writer commits in between and the second
    transaction's read is simply STALE. That is what is simulated here — the in-transaction dedup read
    is forced to find nothing on both calls, exactly as both racers would see.

    With the read blind, the only thing left standing between the user and two identical tasks is the
    unique partial index. On Firestore there is no index and no lock in this simulation, so the second
    create legitimately makes a second row: this test asserts the OUTCOME per backend rather than
    pretending the two are the same, which is the honest thing a dual-backend suite can say here.
    """
    import database.action_items as action_items_db

    key = f"k-{user['run']}"
    first = action_items_db.create_action_item(user['uid'], _payload(), idempotency_key=key)

    monkeypatch.setattr(action_items_db, '_existing_live_id_in_transaction', lambda *a, **k: None)
    second = action_items_db.create_action_item(user['uid'], _payload(), idempotency_key=key)

    rows = _live_rows(user, key)
    if user['backend'] == 'mongo':
        assert second == first, 'the index refused the duplicate and the caller adopted the row that won'
        assert len(rows) == 1, f'{len(rows)} live rows share one idempotency key — the index did not hold'
    else:
        assert len(rows) == 2, 'Firestore has no such index; here the LOCK is what protects the invariant'


def test_the_unique_index_is_what_refuses_it_on_mongo(user):
    """One level lower, so the mechanism itself is pinned and not only its effect: writing a second live
    row with the same key straight through the store must be refused by the database, not by the app."""
    from database.store import errors as store_errors

    if user['backend'] != 'mongo':
        pytest.skip('the index is the Mongo-side mechanism; Firestore relies on the transaction lock')

    key = f"k-{user['run']}"
    base = {'idempotency_key': key, 'completed': False, 'description': 'x'}
    user['store'].set(f"users/{user['uid']}/action_items/a-{user['run']}", dict(base))

    with pytest.raises(store_errors.AlreadyExists):
        user['store'].set(f"users/{user['uid']}/action_items/b-{user['run']}", dict(base))


def test_a_completed_item_does_not_block_a_new_one(user):
    """The filter is scoped to `completed == false` for this reason: a recurring task is ticked off and
    the same key legitimately comes back. A total unique index would refuse it."""
    import database.action_items as action_items_db

    key = f"k-{user['run']}"

    first = action_items_db.create_action_item(user['uid'], _payload(), idempotency_key=key)
    action_items_db.mark_action_item_completed(user['uid'], first, True)
    second = action_items_db.create_action_item(user['uid'], _payload(), idempotency_key=key)

    assert second != first, 'a completed item must not absorb the next create, nor block it'


def test_a_retired_item_does_not_block_a_new_one(user):
    """THE case that a naive filter would have broken, and the reason the retire path clears the key.

    Retiring marks `deleted: true, completed: false`. The create path skips deleted rows on purpose and
    makes a new item — so if the retired row kept its key, the unique index would refuse a create the
    product performs deliberately. Clearing the key on retire is what makes the filter expressible.
    """
    import database.action_items as action_items_db

    key = f"k-{user['run']}"
    first = action_items_db.create_action_item(user['uid'], _payload(), idempotency_key=key)

    action_items_db.retire_action_items_for_conversation(user['uid'], 'c1', active_ids=[])

    retired = user['store'].get(f"users/{user['uid']}/action_items/{first}")
    assert retired.data.get('deleted') is True, 'precondition: the row is retired, not removed'
    assert not retired.data.get('idempotency_key'), 'the retired row must not keep the dedup key'

    second = action_items_db.create_action_item(user['uid'], _payload(), idempotency_key=key)

    assert second != first, 'the product creates a new item after a retire — that must not be refused'
    assert len(_live_rows(user, key)) == 1
