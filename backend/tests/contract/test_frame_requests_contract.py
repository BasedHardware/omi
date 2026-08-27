"""Dual-backend contract for the frame-request queue (ADR-0044 facade + ADR-0002 store port).

`database/frame_requests.py` arrived with upstream in the +30 merge as a NEW file, so it merged cleanly
and only the coverage ratchet (ADR-0030 audit) noticed it had no dual-backend cover. It is the queue
behind on-demand screen capture: the device is asked for a frame, uploads it, and the pixels are later
purged. Three at-risk shapes, and each one guards something that is not cosmetic:

    transaction   `enqueue_frame_request` reads the prior attempts for (device, generation, dedupe key)
                  INSIDE the transaction and returns the live one instead of enqueuing again. Without
                  it a retried request asks the user's device for the same frame twice.

    batch         `delete_frame_requests_for_conversation` deletes a page of rows in one batch, paging
                  until empty behind a hard fence. It is a deletion path: a batch that silently drops
                  writes turns a privacy claim into a partially fulfilled one.

    cursor        `list_all_frame_request_storage_ids` pages with `order_by('__name__') + start_after`
                  to enumerate every stored object id for a wipe. A cursor the facade translates badly
                  repeats or skips a page — and a skipped page is pixels that survive account deletion.

What this suite does NOT hold, measured rather than assumed: it makes no concurrency claim. The
in-transaction read cannot be proven without contention, and the two backends deliberately disagree
about read locks (ADR-0070). A contract suite asserts the intersection: same dedupe decisions, same
rows deleted, same enumeration across page boundaries.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)


def _client():
    """The client this backend deploys, resolved through the accessor ``bind_store`` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


@pytest.fixture
def queue(bind_store):
    run = uuid.uuid4().hex[:8]
    uid, device_id = f'uid-{run}', f'device-{run}'
    collection = f'users/{uid}/frame_requests'

    yield {'uid': uid, 'device_id': device_id, 'collection': collection, 'store': bind_store}

    for document in bind_store.query(collection):
        bind_store.delete(f'{collection}/{document.id}')
    for document in bind_store.query(f'users/{uid}/conversation_keyframe_jobs'):
        bind_store.delete(f'users/{uid}/conversation_keyframe_jobs/{document.id}')
    bind_store.delete(f'users/{uid}')


def _enqueue(queue, *, dedupe_key='intent-1', conversation_id=None, now=NOW, **kwargs):
    import database.frame_requests as frame_requests

    return frame_requests.enqueue_frame_request(
        queue['uid'],
        device_id=queue['device_id'],
        dedupe_key=dedupe_key,
        conversation_id=conversation_id,
        account_generation=1,
        now=now,
        firestore_client=_client(),
        **kwargs,
    )


def _rows(queue):
    return list(queue['store'].query(queue['collection']))


def _seed_row(queue, index, *, conversation_id, storage_id=None):
    """Write one queue row directly.

    Used only where a test needs several rows sharing a conversation: the module allows one ACTIVE
    request per conversation, so the enqueue path cannot produce that shape, and the behaviour under
    test (the batch delete, the cursor) reads rows rather than creating them.
    """
    payload = {
        'request_id': f'frame-{index:04d}',
        'uid': queue['uid'],
        'device_id': queue['device_id'],
        'account_generation': 1,
        'conversation_id': conversation_id,
        'state': 'requested',
        'created_at': NOW + timedelta(seconds=index),
    }
    if storage_id is not None:
        payload['storage_id'] = storage_id
    queue['store'].set(f"{queue['collection']}/frame-{index:04d}", payload)


# --- transaction: the dedupe that keeps a device from being asked twice ----------------------------


def test_enqueuing_creates_one_request(queue):
    request, deduplicated = _enqueue(queue)

    assert deduplicated is False
    assert request.uid == queue['uid']
    assert request.device_id == queue['device_id']
    assert request.state.value == 'requested'
    assert request.attempt_number == 0
    assert len(_rows(queue)) == 1


def test_the_same_intent_returns_the_live_request_instead_of_enqueuing_again(queue):
    """The read inside the transaction is what sees the first attempt. Both backends must return it,
    and neither may add a second row — the device would be asked for the same frame twice."""
    first, _ = _enqueue(queue)
    second, deduplicated = _enqueue(queue, now=NOW + timedelta(seconds=5))

    assert deduplicated is True
    assert second.request_id == first.request_id
    assert len(_rows(queue)) == 1


def test_a_different_intent_is_a_different_request(queue):
    first, _ = _enqueue(queue, dedupe_key='intent-1')
    second, deduplicated = _enqueue(queue, dedupe_key='intent-2')

    assert deduplicated is False
    assert second.request_id != first.request_id
    assert len(_rows(queue)) == 2


def test_the_same_intent_for_a_different_conversation_is_not_deduplicated(queue):
    """The dedupe identity hashes the conversation and screenshot alongside the caller's key, so one
    reused intent cannot collapse two different targets into a single capture."""
    first, _ = _enqueue(queue, dedupe_key='intent-1', conversation_id='conv-a')
    second, deduplicated = _enqueue(queue, dedupe_key='intent-1', conversation_id='conv-b')

    assert deduplicated is False
    assert second.request_id != first.request_id


def test_a_terminal_attempt_does_not_block_a_new_one(queue):
    """Dedupe covers the ACTIVE lifetime. Once the previous attempt reached a terminal state the same
    intent must be able to ask again, or a single cancelled capture would poison that intent forever.
    """
    import database.frame_requests as frame_requests
    from models.frame_request import FrameRequestState

    first, _ = _enqueue(queue)
    frame_requests.transition_frame_request(
        queue['uid'],
        first.request_id,
        next_state=FrameRequestState.cancelled,
        device_id=queue['device_id'],
        account_generation=1,
        terminal_reason='user_cancelled',
        now=NOW + timedelta(seconds=1),
        firestore_client=_client(),
    )

    second, deduplicated = _enqueue(queue, now=NOW + timedelta(seconds=2))

    assert deduplicated is False
    assert second.request_id != first.request_id
    assert second.attempt_number == 1


# --- cursor: enumerating every stored object id for a wipe -----------------------------------------


def test_the_storage_id_enumeration_crosses_page_boundaries_exactly_once(queue):
    """`order_by('__name__') + start_after` over more rows than one page holds. A cursor the facade
    translates badly repeats a page or skips one — and a skipped page is pixels that survive a wipe.

    The page size is deliberately smaller than the row count so the cursor is actually exercised.
    """
    import database.frame_requests as frame_requests

    expected = set()
    for index in range(7):
        request, _ = _enqueue(queue, dedupe_key=f'intent-{index}', now=NOW + timedelta(seconds=index))
        storage_id = f'temporary-{index:02d}'
        queue['store'].set(f"{queue['collection']}/{request.request_id}", {'storage_id': storage_id}, merge=True)
        expected.add(storage_id)

    found = frame_requests.list_all_frame_request_storage_ids(queue['uid'], page_size=2, firestore_client=_client())

    assert sorted(found) == sorted(expected)
    assert len(found) == len(set(found)), 'a page was returned twice'


def test_the_enumeration_is_scoped_to_one_conversation_when_asked(queue):
    import database.frame_requests as frame_requests

    # One ACTIVE request per conversation is an invariant of the module (`attach_frame_request_to_
    # conversation` refuses a second), so the rows that share a conversation are seeded through the
    # store: what is under test here is the cursor, not the enqueue admission.
    for index, conversation_id in enumerate(('conv-a', 'conv-a', 'conv-b')):
        _seed_row(queue, index, conversation_id=conversation_id, storage_id=f'temporary-{index}')

    found = frame_requests.list_all_frame_request_storage_ids(
        queue['uid'], conversation_id='conv-a', page_size=2, firestore_client=_client()
    )

    assert sorted(found) == ['temporary-0', 'temporary-1']


def test_a_storage_id_that_could_address_another_object_is_refused(queue):
    """The ids are opaque by contract. One carrying a path separator would let a caller-supplied value
    reach an object outside the owner's prefix, so the enumeration drops it on both backends."""
    import database.frame_requests as frame_requests

    request, _ = _enqueue(queue)
    queue['store'].set(f"{queue['collection']}/{request.request_id}", {'storage_id': '../other/secret'}, merge=True)

    assert frame_requests.list_all_frame_request_storage_ids(queue['uid'], firestore_client=_client()) == []


# --- batch: the conversation-scoped deletion -------------------------------------------------------


def test_deleting_a_conversations_requests_removes_every_page(queue):
    """More rows than one batch page holds, so the paging loop runs more than once. The count it
    returns is the privacy claim: it must equal what actually disappeared, on both backends."""
    import database.frame_requests as frame_requests

    for index in range(5):
        _seed_row(queue, index, conversation_id='conv-a')
    _seed_row(queue, 9, conversation_id='conv-b')

    deleted = frame_requests.delete_frame_requests_for_conversation(
        queue['uid'], conversation_id='conv-a', batch_size=2, firestore_client=_client()
    )

    assert deleted == 5
    remaining = _rows(queue)
    assert len(remaining) == 1
    assert remaining[0].data['conversation_id'] == 'conv-b'


def test_deleting_a_conversation_with_no_requests_is_zero_not_an_error(queue):
    import database.frame_requests as frame_requests

    _seed_row(queue, 0, conversation_id='conv-b')

    assert (
        frame_requests.delete_frame_requests_for_conversation(
            queue['uid'], conversation_id='conv-a', firestore_client=_client()
        )
        == 0
    )
    assert len(_rows(queue)) == 1
