"""Dual-backend contract for action items (ADR-0044 facade + ADR-0002 store port).

`database/action_items.py` is joint-top of the uncovered worklist (ADR-0060): four of the eight shapes
the facade has to *translate* rather than pass through, and nothing drove any of them against both
backends.

    aggregation   get_action_items_count_by_conversation: a bare .count() AND a .count() behind a
                  second equality filter, then a streamed subtraction for soft-deleted rows
    projection    get_action_item_ids: .select([]) -- the ids-only projection, whose whole point is to
                  return documents with NO fields; get_visible_action_item_ids: .select([...]) with a
                  pushed-down FieldFilter, where an absent field must NOT match
    batch         delete_action_items_batch and batch_set_sync_requested: db.batch() over many
                  documents, with a 499-document chunk boundary
    transaction   create_action_item: reads (a control document, and a filtered+limited query) inside
                  @firestore.transactional before writing -- the idempotency path

The unit suites drive all of this through the in-memory fake, which implements the shapes in Python and
therefore cannot disagree with itself. This runs the real chain -- action_items.py -> the client each
posture deploys -> the live backend -- against a Firestore emulator and a real Mongo replica set, and
asserts the two agree. Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``.

Every test must appear TWICE in the run. A per-backend SKIPPED means the suite proved half of what its
name claims, which is how two of these suites sat dead for months (BACKLOG L30).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

BASE = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

CONVERSATION = 'conv-fixed'


def _item(item_id: str, index: int, **overrides):
    data = {
        'id': item_id,
        'description': f'task {index}',
        'completed': False,
        'created_at': BASE + timedelta(minutes=index),
        'updated_at': BASE + timedelta(minutes=index),
        'conversation_id': CONVERSATION,
        'due_at': None,
        'sort_order': float(index),
        'account_generation': 0,
    }
    data.update(overrides)
    return data


@pytest.fixture
def seeded(bind_store):
    """A user with five action items: two completed, one soft-deleted, one deleted+completed.

    Ids are unique per run and every seeded path is torn down -- the contract suites share one live
    emulator and one live Mongo database, so a leaked document fails whichever suite runs next.
    """
    run = uuid.uuid4().hex[:8]
    uid = f'ai-{run}'
    ids = [f'i{i}-{run}' for i in range(5)]
    paths = [f'users/{uid}/action_items/{item_id}' for item_id in ids]

    bind_store.set(paths[0], _item(ids[0], 0))
    bind_store.set(paths[1], _item(ids[1], 1, completed=True))
    bind_store.set(paths[2], _item(ids[2], 2, completed=True))
    bind_store.set(paths[3], _item(ids[3], 3, deleted=True))
    bind_store.set(paths[4], _item(ids[4], 4, deleted=True, completed=True))

    yield {'uid': uid, 'ids': ids, 'store': bind_store}

    for path in paths:
        bind_store.delete(path)


# --- aggregation --------------------------------------------------------------------------------


def test_the_conversation_badge_counts_agree(seeded):
    """Two .count() calls -- one bare, one behind a second equality filter -- minus a streamed count of
    the soft-deleted rows. Five documents seeded, two of them deleted (one of those completed), so the
    badge must read 3 total / 2 completed / 1 incomplete on either backend."""
    import database.action_items as action_items_db

    counts = action_items_db.get_action_items_count_by_conversation(seeded['uid'], CONVERSATION)

    assert counts == {'total': 3, 'completed': 2, 'incomplete': 1}


def test_a_conversation_with_no_items_counts_zero_not_none(seeded):
    """The empty aggregation is its own case: .count() on a query matching nothing must yield 0, and a
    backend that returned an empty result set instead of a zero row would surface here as a TypeError
    rather than a wrong badge."""
    import database.action_items as action_items_db

    assert action_items_db.get_action_items_count_by_conversation(seeded['uid'], 'no-such-conv') == {
        'total': 0,
        'completed': 0,
        'incomplete': 0,
    }


# --- projection ---------------------------------------------------------------------------------


def test_the_ids_only_projection_returns_every_document(seeded):
    """``.select([])`` asks for documents with NO fields. The ids must still all be there -- this feeds
    account deletion and the vector purge, so a projection that drops rows leaks data that the user
    asked to be gone."""
    import database.action_items as action_items_db

    assert sorted(action_items_db.get_action_item_ids(seeded['uid'])) == sorted(seeded['ids'])


def test_the_visible_projection_pushes_the_filter_and_keeps_absent_fields_out(seeded):
    """``.select(['completed','deleted'])`` with a pushed-down equality on ``completed``, and ``deleted``
    filtered in Python on purpose: an equality filter never matches a document where the field is
    ABSENT, and most rows have no ``deleted`` field at all. A backend that treated a missing field as
    False would return the soft-deleted rows here."""
    import database.action_items as action_items_db

    incomplete = action_items_db.get_visible_action_item_ids(seeded['uid'], completed=False)
    completed = action_items_db.get_visible_action_item_ids(seeded['uid'], completed=True)

    assert incomplete == [seeded['ids'][0]], 'the soft-deleted incomplete row must not be listed'
    assert sorted(completed) == sorted(seeded['ids'][1:3]), 'the deleted+completed row must not be listed'


# --- batch ---------------------------------------------------------------------------------------


def test_a_batch_delete_removes_every_id_it_was_given(seeded):
    import database.action_items as action_items_db

    targets = seeded['ids'][:3]
    returned = action_items_db.delete_action_items_batch(seeded['uid'], targets)

    assert sorted(returned) == sorted(targets)
    assert sorted(action_items_db.get_action_item_ids(seeded['uid'])) == sorted(seeded['ids'][3:])


def test_a_batch_delete_of_an_unknown_id_is_not_an_error(seeded):
    """The docstring says so, and downstream vector and FCM cleanup rely on it: deleting an id that is
    not there must behave the same on both backends rather than raising on one."""
    import database.action_items as action_items_db

    returned = action_items_db.delete_action_items_batch(seeded['uid'], ['ghost', seeded['ids'][0]])

    assert sorted(returned) == sorted(['ghost', seeded['ids'][0]])
    assert seeded['ids'][0] not in action_items_db.get_action_item_ids(seeded['uid'])


def test_a_batch_update_writes_every_document_in_one_commit(seeded):
    import database.action_items as action_items_db

    targets = seeded['ids'][:3]
    action_items_db.batch_set_sync_requested(seeded['uid'], targets)

    for item_id in targets:
        stored = seeded['store'].get(f"users/{seeded['uid']}/action_items/{item_id}")
        assert stored is not None and stored.data.get('sync_requested') is True
    untouched = seeded['store'].get(f"users/{seeded['uid']}/action_items/{seeded['ids'][3]}")
    assert untouched is not None and 'sync_requested' not in untouched.data


def test_a_batch_spanning_the_chunk_boundary_commits_every_document(bind_store):
    """The 499-document chunk boundary is a Firestore limit the code implements by hand: it commits and
    opens a NEW batch. 600 documents crosses it, and a chunking bug loses the tail silently -- the
    function returns the ids it was given either way."""
    import database.action_items as action_items_db

    run = uuid.uuid4().hex[:8]
    uid = f'ai-bulk-{run}'
    ids = [f'b{i}-{run}' for i in range(600)]
    for index, item_id in enumerate(ids):
        bind_store.set(f'users/{uid}/action_items/{item_id}', _item(item_id, index))
    assert len(action_items_db.get_action_item_ids(uid)) == 600, 'precondition: all 600 seeded'

    try:
        action_items_db.delete_action_items_batch(uid, ids)
        assert action_items_db.get_action_item_ids(uid) == []
    finally:
        for item_id in ids:
            bind_store.delete(f'users/{uid}/action_items/{item_id}')


# --- transaction --------------------------------------------------------------------------------


def test_the_same_idempotency_key_returns_the_first_id_instead_of_creating_a_second(seeded):
    """The transaction reads a control document AND a filtered, limited query before writing. This is
    the invariant the whole shape exists for: a retried create must not produce a duplicate task."""
    import database.action_items as action_items_db

    uid = seeded['uid']
    key = f'key-{uuid.uuid4().hex[:8]}'
    payload = {'description': 'retried task', 'completed': False, 'conversation_id': CONVERSATION}

    first = action_items_db.create_action_item(uid, dict(payload), idempotency_key=key)
    second = action_items_db.create_action_item(uid, dict(payload), idempotency_key=key)

    try:
        assert second == first, 'a retry must return the existing id, not allocate a new document'
        assert len([i for i in action_items_db.get_action_item_ids(uid) if i not in seeded['ids']]) == 1
    finally:
        seeded['store'].delete(f'users/{uid}/action_items/{first}')


def test_a_different_key_does_create_a_second_item(seeded):
    """The other direction, so the test above cannot pass by a create that never happens."""
    import database.action_items as action_items_db

    uid = seeded['uid']
    payload = {'description': 'task', 'completed': False, 'conversation_id': CONVERSATION}

    first = action_items_db.create_action_item(uid, dict(payload), idempotency_key=f'k1-{uuid.uuid4().hex[:6]}')
    second = action_items_db.create_action_item(uid, dict(payload), idempotency_key=f'k2-{uuid.uuid4().hex[:6]}')

    try:
        assert second != first
    finally:
        seeded['store'].delete(f'users/{uid}/action_items/{first}')
        seeded['store'].delete(f'users/{uid}/action_items/{second}')


def test_a_completed_item_does_not_absorb_a_later_create_with_the_same_key(seeded):
    """The dedup query filters ``completed == False``: once the user has ticked the task off, the same
    key must create a NEW one rather than silently returning the finished one. Two equality filters
    combined inside a transaction -- exactly the shape a facade can get wrong."""
    import database.action_items as action_items_db

    uid = seeded['uid']
    key = f'key-{uuid.uuid4().hex[:8]}'
    payload = {'description': 'recurring task', 'completed': False, 'conversation_id': CONVERSATION}

    first = action_items_db.create_action_item(uid, dict(payload), idempotency_key=key)
    action_items_db.mark_action_item_completed(uid, first, True)
    second = action_items_db.create_action_item(uid, dict(payload), idempotency_key=key)

    try:
        assert second != first, 'a completed item must not absorb the next create'
    finally:
        seeded['store'].delete(f'users/{uid}/action_items/{first}')
        seeded['store'].delete(f'users/{uid}/action_items/{second}')


def test_a_soft_deleted_item_does_not_absorb_a_later_create_with_the_same_key(seeded):
    """``deleted`` is checked in Python inside the transaction loop, not pushed into the query -- the
    same absent-field reasoning as the projection above. A retired task must not swallow a new one."""
    import database.action_items as action_items_db

    uid = seeded['uid']
    key = f'key-{uuid.uuid4().hex[:8]}'
    payload = {'description': 'retired task', 'completed': False, 'conversation_id': CONVERSATION}

    first = action_items_db.create_action_item(uid, dict(payload), idempotency_key=key)
    action_items_db.delete_action_item(uid, first)  # soft delete
    second = action_items_db.create_action_item(uid, dict(payload), idempotency_key=key)

    try:
        assert second != first, 'a soft-deleted item must not absorb the next create'
    finally:
        seeded['store'].delete(f'users/{uid}/action_items/{first}')
        seeded['store'].delete(f'users/{uid}/action_items/{second}')


def test_reusing_a_reserved_document_id_returns_it_without_rewriting(seeded):
    """The other transactional read: ``doc_ref.get(transaction=...)`` on a caller-reserved id. A
    crash-retried create must be deterministic, and must not overwrite what is already stored."""
    import database.action_items as action_items_db

    uid = seeded['uid']
    reserved = f'res-{uuid.uuid4().hex[:8]}'

    first = action_items_db.create_action_item(uid, {'description': 'original'}, document_id=reserved)
    second = action_items_db.create_action_item(uid, {'description': 'CHANGED'}, document_id=reserved)

    try:
        assert first == reserved and second == reserved
        stored = action_items_db.get_action_item(uid, reserved)
        assert stored is not None and stored['description'] == 'original', 'the retry must not rewrite'
    finally:
        seeded['store'].delete(f'users/{uid}/action_items/{reserved}')
