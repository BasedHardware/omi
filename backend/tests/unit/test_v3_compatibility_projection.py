from __future__ import annotations

from datetime import datetime, timezone

import pytest

from database.memory_collections import MemoryCollections
from database.memory_compatibility_projection import read_v3_compatibility_projection_page
from utils.memory.v3.projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3ProjectionCursor,
    V3ProjectionFailureReason,
    V3ProjectionReadError,
    V3ProjectionReadRequest,
)


class FakeSnapshot:
    def __init__(self, doc_id, data, exists=True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class FakeDocument:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self):
        self.db.document_reads.append(self.path)
        data = self.db.docs.get(self.path)
        return FakeSnapshot(self.path.rsplit('/', 1)[-1], data, exists=data is not None)


class FakeQuery:
    def __init__(self, db, path):
        self.db = db
        self.path = path
        self.limit_value = None
        self.start_after_cursor = None

    def order_by(self, *args, **kwargs):
        self.db.query_order_by.append((args, kwargs))
        return self

    def start_after(self, cursor):
        self.start_after_cursor = cursor
        self.db.query_start_after.append(cursor)
        return self

    def limit(self, value):
        self.limit_value = value
        self.db.query_limits.append(value)
        return self

    def stream(self):
        prefix = f'{self.path}/'
        rows = []
        for path, data in self.db.docs.items():
            if not path.startswith(prefix) or '/' in path[len(prefix) :]:
                continue
            rows.append(FakeSnapshot(path.rsplit('/', 1)[-1], data))
        rows.sort(key=lambda snap: (snap.to_dict()['created_at'], snap.id), reverse=True)
        if self.start_after_cursor is not None:
            created_at = self.start_after_cursor['created_at']
            memory_id = self.start_after_cursor['__name__']
            rows = [snap for snap in rows if (snap.to_dict()['created_at'], snap.id) < (created_at, memory_id)]
        return rows[: self.limit_value]


class FakeDb:
    def __init__(self, docs):
        self.docs = docs
        self.document_reads = []
        self.collection_reads = []
        self.query_limits = []
        self.query_order_by = []
        self.query_start_after = []
        self.legacy_reader_called = False
        self.writes = []

    def document(self, path):
        assert '/memory_items/' not in path
        return FakeDocument(self, path)

    def collection(self, path):
        assert '/memory_items' not in path
        self.collection_reads.append(path)
        return FakeQuery(self, path)


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


def _db(*items, state=_DEFAULT_STATE):
    paths = MemoryCollections(uid=UID)
    docs = {}
    if state is _DEFAULT_STATE:
        docs[paths.v3_compatibility_projection_state] = _state()
    elif state is not None:
        docs[paths.v3_compatibility_projection_state] = state
    for memory_id, item in items:
        docs[f'{paths.v3_compatibility_projection_items}/{memory_id}'] = item
    return FakeDb(docs)


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


def _reason_for(db, request=None):
    with pytest.raises(V3ProjectionReadError) as exc:
        read_v3_compatibility_projection_page(db_client=db, request=request or _request())
    return exc.value.reason


def test_ready_projection_returns_memorydb_compatible_dicts_without_memory_body_fields_and_no_legacy_fallback():
    db = _db(('mem-a', _payload('mem-a')))

    page = read_v3_compatibility_projection_page(db_client=db, request=_request())

    assert [item['id'] for item in page.items] == ['mem-a']
    assert page.items[0]['content'] == 'content mem-a'
    assert 'projection_generation' not in page.items[0]
    assert page.next_cursor is None
    assert page.projection_generation == PROJECTION_GENERATION
    assert db.collection_reads == [MemoryCollections(uid=UID).v3_compatibility_projection_items]
    assert db.query_limits == [3]
    assert db.legacy_reader_called is False
    assert db.writes == []


def test_ready_empty_projection_returns_empty_list():
    db = _db(state=_state(empty_projection=True))

    page = read_v3_compatibility_projection_page(db_client=db, request=_request())

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
def test_missing_malformed_or_unfenced_projection_state_fails_closed(state, reason):
    assert _reason_for(_db(state=state)) == reason


def test_caller_supplied_expected_generation_is_not_copied_from_projection_state():
    db = _db(('mem-a', _payload('mem-a')), state=_state(account_generation=ACCOUNT_GENERATION))

    assert _reason_for(db, _request(expected_account_generation=ACCOUNT_GENERATION + 1)) == (
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
def test_invalid_projection_item_fails_whole_page(item, reason):
    assert _reason_for(_db(('mem-a', item))) == reason


def test_archive_tombstone_deleted_and_stale_short_term_items_are_not_returned_by_default():
    visible = _payload('visible')
    archived = _payload('archived', archive=True)
    deleted = _payload('deleted', deleted=True)
    tombstoned = _payload('tombstoned', tombstoned=True)
    stale = _payload('stale', short_term_stale=True)
    db = _db(
        ('visible', visible), ('archived', archived), ('deleted', deleted), ('tombstoned', tombstoned), ('stale', stale)
    )

    page = read_v3_compatibility_projection_page(db_client=db, request=_request(limit=10))

    assert [item['id'] for item in page.items] == ['visible']


def test_stable_keyset_pagination_by_created_at_desc_then_memory_id_desc_reads_limit_plus_one():
    t3 = datetime(2026, 1, 3, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db = _db(
        ('a', _payload('a', created_at=t1)),
        ('b', _payload('b', created_at=t2)),
        ('c', _payload('c', created_at=t2)),
        ('d', _payload('d', created_at=t3)),
    )

    first = read_v3_compatibility_projection_page(db_client=db, request=_request(limit=2))
    second = read_v3_compatibility_projection_page(db_client=db, request=_request(limit=2, cursor=first.next_cursor))

    assert [item['id'] for item in first.items] == ['d', 'c']
    assert isinstance(first.next_cursor, V3ProjectionCursor)
    assert [item['id'] for item in second.items] == ['b', 'a']
    assert second.next_cursor is None
    assert db.query_limits == [3, 3]
    assert db.query_start_after == [{'created_at': t2, '__name__': 'c'}]


def test_offset_is_unsupported_in_memory_projection_reader_even_for_legacy_zero_override():
    assert _reason_for(_db(), _request(offset=0, limit=5000)) == V3ProjectionFailureReason.OFFSET_UNSUPPORTED
