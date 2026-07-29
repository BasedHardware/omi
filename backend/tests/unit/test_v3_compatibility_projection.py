from __future__ import annotations

from datetime import datetime, timezone

import pytest

import database.memory_compatibility_projection as projection_module
from database.memory_collections import MemoryCollections
from database.memory_compatibility_projection import read_v3_compatibility_projection_page
from tests.store_fakes import FakeDocumentStore
from utils.memory.v3.projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3ProjectionCursor,
    V3ProjectionFailureReason,
    V3ProjectionReadError,
    V3ProjectionReadRequest,
)


UID = 'projection-user'
OTHER_UID = 'other-user'
ACCOUNT_GENERATION = 7
PROJECTION_GENERATION = 11
PROJECTION_COMMIT_ID = 'commit-11'
SOURCE_COMMIT_ID = 'source-11'
FENCE = 'fence-11'
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _state(**overrides):
    doc = {
        'uid': UID,
        'schema_version': V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        'source': 'memory_items_projection',
        'ready': True,
        'account_generation': ACCOUNT_GENERATION,
        'projection_generation': PROJECTION_GENERATION,
        'source_commit_id': SOURCE_COMMIT_ID,
        'source_version': 'memory',
        'projection_commit_id': PROJECTION_COMMIT_ID,
        'projection_version': 'v3_memorydb_compatibility',
        'source_evidence_fence': FENCE,
        'projection_evidence_fence': FENCE,
        'freshness_fence_generation': PROJECTION_GENERATION,
        'tombstone_fence_generation': PROJECTION_GENERATION,
        'vector_cleanup_fence_generation': PROJECTION_GENERATION,
        'write_convergence_complete': True,
        'delete_convergence_complete': True,
        'tombstone_convergence_complete': True,
        'empty_projection': False,
    }
    doc.update(overrides)
    return doc


def _payload(memory_id, *, created_at=NOW, content=None, **overrides):
    doc = {
        'uid': UID,
        'memory_id': memory_id,
        'schema_version': V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        'source': 'memory_items_projection',
        'account_generation': ACCOUNT_GENERATION,
        'projection_generation': PROJECTION_GENERATION,
        'source_commit_id': SOURCE_COMMIT_ID,
        'projection_commit_id': PROJECTION_COMMIT_ID,
        'projection_evidence_fence': FENCE,
        'freshness_fence_generation': PROJECTION_GENERATION,
        'tombstone_fence_generation': PROJECTION_GENERATION,
        'write_convergence_complete': True,
        'delete_convergence_complete': True,
        'tombstone_convergence_complete': True,
        'deleted': False,
        'tombstoned': False,
        'archive': False,
        'short_term_stale': False,
        'memorydb': {
            'id': memory_id,
            'uid': UID,
            'content': content or f'content {memory_id}',
            'category': 'system',
            'visibility': 'private',
            'tags': [],
            'created_at': created_at,
            'updated_at': created_at,
            'reviewed': False,
            'user_review': None,
            'manually_added': False,
            'edited': False,
            'conversation_id': None,
            'data_protection_level': 'standard',
        },
        'created_at': created_at,
    }
    doc.update(overrides)
    return doc


_DEFAULT_STATE = object()


def _docs(*items, state=_DEFAULT_STATE):
    """Seed a path->data dict for the neutral store (state doc + item documents)."""
    paths = MemoryCollections(uid=UID)
    docs = {}
    if state is _DEFAULT_STATE:
        docs[paths.v3_compatibility_projection_state] = _state()
    elif state is not None:
        docs[paths.v3_compatibility_projection_state] = state
    for memory_id, item in items:
        docs[f'{paths.v3_compatibility_projection_items}/{memory_id}'] = item
    return docs


@pytest.fixture
def install_store(monkeypatch):
    def _install(docs):
        store = FakeDocumentStore(backing=docs)
        monkeypatch.setattr(projection_module, "_store", lambda: store)
        return store

    return _install


def _request(**overrides):
    params = {
        'uid': UID,
        'limit': 2,
        'expected_account_generation': ACCOUNT_GENERATION,
        'cursor': None,
        'offset': None,
        'include_archive': False,
    }
    params.update(overrides)
    return V3ProjectionReadRequest(**params)


def _reason_for(install_store, docs, request=None):
    install_store(docs)
    with pytest.raises(V3ProjectionReadError) as exc:
        read_v3_compatibility_projection_page(request=request or _request())
    return exc.value.reason


def test_ready_projection_returns_memorydb_compatible_dicts_without_memory_body_fields_and_no_legacy_fallback(
    install_store,
):
    install_store(_docs(('mem-a', _payload('mem-a'))))

    page = read_v3_compatibility_projection_page(request=_request())

    assert [item['id'] for item in page.items] == ['mem-a']
    assert page.items[0]['content'] == 'content mem-a'
    assert 'projection_generation' not in page.items[0]
    assert page.next_cursor is None
    assert page.projection_generation == PROJECTION_GENERATION


def test_ready_empty_projection_returns_empty_list(install_store):
    install_store(_docs(state=_state(empty_projection=True)))

    page = read_v3_compatibility_projection_page(request=_request())

    assert page.items == []
    assert page.empty_projection is True
    assert page.next_cursor is None


@pytest.mark.parametrize(
    ('state', 'reason'),
    [
        (None, V3ProjectionFailureReason.MISSING_PROJECTION_STATE),
        ({'uid': UID}, V3ProjectionFailureReason.UNSUPPORTED_PROJECTION_SCHEMA),
        (_state(uid=OTHER_UID), V3ProjectionFailureReason.UID_MISMATCH),
        (_state(source='unexpected'), V3ProjectionFailureReason.SOURCE_MISMATCH),
        (_state(account_generation=ACCOUNT_GENERATION + 1), V3ProjectionFailureReason.ACCOUNT_GENERATION_MISMATCH),
        (_state(projection_generation=PROJECTION_GENERATION + 1), V3ProjectionFailureReason.FENCE_MISMATCH),
        (_state(projection_commit_id='other'), V3ProjectionFailureReason.FENCE_MISMATCH),
        (_state(write_convergence_complete=False), V3ProjectionFailureReason.INCOMPLETE_CONVERGENCE),
        (_state(delete_convergence_complete=False), V3ProjectionFailureReason.INCOMPLETE_CONVERGENCE),
        (_state(tombstone_convergence_complete=False), V3ProjectionFailureReason.INCOMPLETE_CONVERGENCE),
        (_state(ready=False), V3ProjectionFailureReason.PROJECTION_NOT_READY),
    ],
)
def test_missing_malformed_or_unfenced_projection_state_fails_closed(install_store, state, reason):
    assert _reason_for(install_store, _docs(state=state)) == reason


def test_caller_supplied_expected_generation_is_not_copied_from_projection_state(install_store):
    docs = _docs(('mem-a', _payload('mem-a')), state=_state(account_generation=ACCOUNT_GENERATION))

    assert _reason_for(install_store, docs, _request(expected_account_generation=ACCOUNT_GENERATION + 1)) == (
        V3ProjectionFailureReason.ACCOUNT_GENERATION_MISMATCH
    )


@pytest.mark.parametrize(
    ('item', 'reason'),
    [
        (_payload('mem-a', uid=OTHER_UID), V3ProjectionFailureReason.ITEM_FENCE_MISMATCH),
        (_payload('mem-a', projection_generation=99), V3ProjectionFailureReason.ITEM_FENCE_MISMATCH),
        (_payload('mem-a', projection_commit_id='old'), V3ProjectionFailureReason.ITEM_FENCE_MISMATCH),
        (_payload('mem-a', write_convergence_complete=False), V3ProjectionFailureReason.INCOMPLETE_CONVERGENCE),
        (_payload('mem-a', tombstone_convergence_complete=False), V3ProjectionFailureReason.INCOMPLETE_CONVERGENCE),
        (_payload('mem-a', memorydb={'id': 'mem-a'}), V3ProjectionFailureReason.INVALID_PROJECTION_PAYLOAD),
    ],
)
def test_invalid_projection_item_fails_whole_page(install_store, item, reason):
    assert _reason_for(install_store, _docs(('mem-a', item))) == reason


def test_archive_tombstone_deleted_and_stale_short_term_items_are_not_returned_by_default(install_store):
    visible = _payload('visible')
    archived = _payload('archived', archive=True)
    deleted = _payload('deleted', deleted=True)
    tombstoned = _payload('tombstoned', tombstoned=True)
    stale = _payload('stale', short_term_stale=True)
    install_store(
        _docs(
            ('visible', visible),
            ('archived', archived),
            ('deleted', deleted),
            ('tombstoned', tombstoned),
            ('stale', stale),
        )
    )

    page = read_v3_compatibility_projection_page(request=_request(limit=10))

    assert [item['id'] for item in page.items] == ['visible']


def test_stable_keyset_pagination_by_created_at_desc_then_memory_id_desc_reads_limit_plus_one(install_store):
    t3 = datetime(2026, 1, 3, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    install_store(
        _docs(
            ('a', _payload('a', created_at=t1)),
            ('b', _payload('b', created_at=t2)),
            ('c', _payload('c', created_at=t2)),
            ('d', _payload('d', created_at=t3)),
        )
    )

    first = read_v3_compatibility_projection_page(request=_request(limit=2))
    second = read_v3_compatibility_projection_page(request=_request(limit=2, cursor=first.next_cursor))

    assert [item['id'] for item in first.items] == ['d', 'c']
    assert isinstance(first.next_cursor, V3ProjectionCursor)
    assert first.next_cursor.created_at == t2
    assert first.next_cursor.memory_id == 'c'
    assert [item['id'] for item in second.items] == ['b', 'a']
    assert second.next_cursor is None


def test_offset_is_unsupported_in_memory_projection_reader_even_for_legacy_zero_override(install_store):
    assert _reason_for(install_store, _docs(), _request(offset=0, limit=5000)) == (
        V3ProjectionFailureReason.OFFSET_UNSUPPORTED
    )
