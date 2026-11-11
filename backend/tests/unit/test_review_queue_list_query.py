"""Bounded serving-query contract for the memory review queue."""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from google.cloud.firestore_v1 import Query
from google.api_core.exceptions import AlreadyExists, FailedPrecondition

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from database import read_boundary, review_queue


class _Snapshot:
    def __init__(self, doc_id: str, data: dict[str, Any] | None, *, reference=None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = reference
        self.update_time = reference._database.versions.get(reference.path, 1) if reference else 1

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Document:
    def __init__(self, database, path: str):
        self._database = database
        self.path = path
        self.id = path.rsplit('/', 1)[-1]

    def get(self):
        if '/memory_items/' in self.path:
            raise AssertionError('review queue listing must batch canonical source reads')
        return _Snapshot(self.id, self._database.store.get(self.path), reference=self)

    def set(self, payload):
        if self._database.fail_cursor_writes and '/memory_state/' in self.path:
            raise RuntimeError('cursor write failed')
        self._database.store[self.path] = dict(payload)
        self._database.write_log.append(('set', self.path, dict(payload)))

    def update(self, payload, *, option=None):
        if self._database.before_update:
            self._database.before_update(self)
        if option is not None and option._last_update_time != self._database.versions.get(self.path, 1):
            raise FailedPrecondition('document changed')
        if self._database.fail_review_updates and '/memory_review_queue/' in self.path:
            raise RuntimeError('review self-heal failed')
        self._database.store[self.path].update(payload)
        self._database.write_log.append(('update', self.path, dict(payload)))
        self._database.versions[self.path] = self._database.versions.get(self.path, 1) + 1

    def create(self, payload):
        if self.path in self._database.store:
            raise AlreadyExists('document exists')
        self.set(payload)

    def delete(self):
        if self._database.fail_cursor_writes and '/memory_state/' in self.path:
            raise RuntimeError('cursor write failed')
        self._database.store.pop(self.path, None)
        self._database.write_log.append(('delete', self.path, {}))


class _Query:
    def __init__(
        self,
        database,
        path: str,
        *,
        filters=(),
        order_fields=(),
        limit_count=None,
        cursor_id=None,
        selected_fields=None,
    ):
        self._database = database
        self._path = path
        self._filters = tuple(filters)
        self._order_fields = tuple(order_fields)
        self._limit_count = limit_count
        self._cursor_id = cursor_id
        self._selected_fields = selected_fields

    def _clone(self, **changes):
        return _Query(
            self._database,
            self._path,
            filters=changes.get('filters', self._filters),
            order_fields=changes.get('order_fields', self._order_fields),
            limit_count=changes.get('limit_count', self._limit_count),
            cursor_id=changes.get('cursor_id', self._cursor_id),
            selected_fields=changes.get('selected_fields', self._selected_fields),
        )

    def select(self, fields):
        return self._clone(selected_fields=tuple(fields))

    def where(self, *, filter):
        return self._clone(filters=(*self._filters, (filter.field_path, filter.op_string, filter.value)))

    def order_by(self, field_path, *, direction=Query.ASCENDING):
        return self._clone(order_fields=(*self._order_fields, (field_path, direction)))

    def limit(self, limit_count):
        return self._clone(limit_count=limit_count)

    def start_after(self, snapshot):
        if isinstance(snapshot, dict):
            cursor_value = snapshot['__name__']
            if not isinstance(cursor_value, _Document):
                raise AssertionError('document-id cursor must use a collection DocumentReference')
            self._database.document_cursor_log.append(cursor_value.path)
            cursor_id = cursor_value.id
        else:
            cursor_id = snapshot.id
        return self._clone(cursor_id=cursor_id)

    def document(self, doc_id):
        return _Document(self._database, f'{self._path}/{doc_id}')

    def stream(self):
        if self._limit_count is None:
            raise AssertionError('review queue listing must apply a server-side limit')
        rows = []
        prefix = f'{self._path}/'
        for path, data in self._database.store.items():
            if not path.startswith(prefix) or '/' in path[len(prefix) :]:
                continue
            if not all(self._matches(data, *query_filter) for query_filter in self._filters):
                continue
            ordered_data_fields = {
                field_path for field_path, _direction in self._order_fields if field_path != '__name__'
            }
            if any(field_path not in data for field_path in ordered_data_fields):
                continue
            rows.append(
                _Snapshot(
                    path[len(prefix) :],
                    deepcopy(data),
                    reference=_Document(self._database, path),
                )
            )
        for field_path, direction in reversed(self._order_fields):
            rows.sort(
                key=lambda snapshot: snapshot.id if field_path == '__name__' else snapshot.to_dict().get(field_path),
                reverse=direction == Query.DESCENDING,
            )
        if self._cursor_id is not None:
            cursor_index = next(index for index, snapshot in enumerate(rows) if snapshot.id == self._cursor_id)
            rows = rows[cursor_index + 1 :]
        page = rows[: self._limit_count]
        self._database.query_log.append(
            {
                'filters': self._filters,
                'order_fields': self._order_fields,
                'limit': self._limit_count,
                'cursor_id': self._cursor_id,
                'returned_ids': [snapshot.id for snapshot in page],
                **({'selected_fields': self._selected_fields} if self._selected_fields is not None else {}),
            }
        )
        if self._selected_fields is not None:
            for snapshot in page:
                snapshot._data = {key: value for key, value in snapshot._data.items() if key in self._selected_fields}
        return page

    @staticmethod
    def _matches(data, field_path, operator, expected):
        if operator != '==':
            raise AssertionError(f'unexpected operator {operator}')
        return data.get(field_path) == expected


class _UserDocument:
    def __init__(self, database, uid: str):
        self._database = database
        self._uid = uid

    def collection(self, name):
        return _Query(self._database, f'users/{self._uid}/{name}')


class _Users:
    def __init__(self, database):
        self._database = database

    def document(self, uid):
        return _UserDocument(self._database, uid)


class _Firestore:
    def __init__(self, store):
        self.store = store
        self.query_log = []
        self.batch_get_log = []
        self.write_log = []
        self.document_cursor_log = []
        self.fail_review_updates = False
        self.fail_cursor_writes = False
        self.versions = {}
        self.before_update = None

    def collection(self, name):
        assert name == 'users'
        return _Users(self)

    def get_all(self, refs):
        refs = list(refs)
        self.batch_get_log.append([ref.id for ref in refs])
        return [_Snapshot(ref.id, self.store.get(ref.path), reference=ref) for ref in refs]


def _review(
    review_id: str,
    *,
    impact: float,
    created_at: datetime,
    status: str = 'pending',
    canonical: bool = False,
):
    item = {
        'review_id': review_id,
        'fact_id': f'memory-{review_id}',
        'candidate': {'id': f'memory-{review_id}', 'content': review_id},
        'conflict_with': [],
        'status': status,
        'impact': impact,
        'created_at': created_at,
    }
    if canonical:
        item.update(
            {
                'authority': 'canonical_memory',
                'source_commit_id': f'commit-{review_id}',
                'source_item_revision': 1,
                'source_content_hash': f'hash-{review_id}',
            }
        )
    return item


def _queue_store(uid: str, items):
    return {f'users/{uid}/memory_review_queue/{item["review_id"]}': item for item in items}


def test_expire_is_paged_non_destructive_and_idempotent(monkeypatch):
    uid = 'uid-expiration-test'
    cutoff = datetime(2026, 7, 20, tzinfo=timezone.utc)
    rows = [
        _review('a-legacy', impact=0.5, created_at=cutoff - timedelta(days=1)),
        _review('b-canonical', impact=0.5, created_at=cutoff - timedelta(days=1), canonical=True),
        _review('c-pending-review', impact=0.5, created_at=cutoff - timedelta(days=1), status='pending_review'),
        _review('d-accepted', impact=0.5, created_at=cutoff - timedelta(days=1), status='accepted'),
        _review('e-cutoff', impact=0.5, created_at=cutoff),
        _review('f-new', impact=0.5, created_at=cutoff + timedelta(days=1)),
        _review('g-expired', impact=0.5, created_at=cutoff - timedelta(days=1), status='expired'),
        _review('h-missing-time', impact=0.5, created_at=cutoff),
        _review('i-naive-time', impact=0.5, created_at=cutoff.replace(tzinfo=None)),
    ]
    rows[-2].pop('created_at')
    store = _queue_store(uid, rows)
    for collection in ('memory_items', 'memories', 'memory_commits', 'short_term_memories', 'memory_corrections'):
        store[f'users/{uid}/{collection}/protected'] = {'unchanged': True}
    database = _Firestore(store)
    before = deepcopy(store)
    monkeypatch.setattr(review_queue, 'REVIEW_EXPIRE_PAGE_SIZE', 2)
    monkeypatch.setattr(review_queue, 'db', database)

    def expire(**kwargs):
        return review_queue.expire_review_conflicts(uid, created_before=cutoff, firestore_client=database, **kwargs)

    assert expire() == {'pending': {'legacy': 1, 'canonical_memory': 1}, 'pending_review': {'legacy': 1}}
    assert database.store == before
    assert database.write_log == []
    assert len(database.query_log) == 5
    assert all(query['limit'] == 2 for query in database.query_log)
    assert all(query['selected_fields'] == ('status', 'authority', 'created_at') for query in database.query_log)

    assert expire(dry_run=False) == {'expired': {'legacy': 2, 'canonical_memory': 1}}
    assert len(database.write_log) == 3
    for _, path, update in database.write_log:
        assert '/memory_review_queue/' in path
        assert set(update) == {'status', 'resolved_at', 'updated_at', 'reason', 'permitted_uses'}
        assert update['reason'] == review_queue.REVIEW_EXPIRE_REASON
        assert update['permitted_uses'] == []
        assert update['resolved_at'] == update['updated_at']
        assert update['resolved_at'].tzinfo is not None
        assert database.store[path] == {**before[path], **update}
    changed_paths = {path for _, path, _ in database.write_log}
    assert {path: row for path, row in database.store.items() if path not in changed_paths} == {
        path: row for path, row in before.items() if path not in changed_paths
    }
    after = deepcopy(database.store)
    assert expire(dry_run=False) == {}
    assert expire() == {}
    assert database.store == after
    assert len(database.write_log) == 3
    assert review_queue.resolve_review_conflict(uid, 'b-canonical', 'accept')['status'] == 'already_resolved'
    assert review_queue.resolve_review_conflict(uid, 'a-legacy', 'timeout')['status'] == 'already_resolved'


@pytest.mark.parametrize('status', ['pending', 'pending_review'])
def test_expired_rows_hidden_from_ranked_and_sparse_pending_lists(monkeypatch, status):
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    expired = _review('expired', impact=1.0, created_at=now, status='expired', canonical=True)
    sparse = _review('sparse-expired', impact=1.0, created_at=now, status='expired')
    sparse.pop('impact')
    database = _Firestore(
        _queue_store('test', [expired, sparse, _review('pending', impact=0.5, created_at=now, status=status)])
    )
    monkeypatch.setattr(review_queue, 'db', database)
    assert [row['review_id'] for row in review_queue.list_review_conflicts('test', status=status)] == ['pending']
    assert database.write_log == []
    assert database.batch_get_log == []


def test_expire_does_not_overwrite_concurrent_resolution():
    cutoff = datetime(2026, 7, 20, tzinfo=timezone.utc)
    database = _Firestore(_queue_store('test', [_review('r', impact=0.5, created_at=cutoff - timedelta(days=1))]))

    def concurrent_resolution(reference):
        database.store[reference.path]['status'] = 'accepted'
        database.versions[reference.path] = 2

    database.before_update = concurrent_resolution
    with pytest.raises(FailedPrecondition):
        review_queue.expire_review_conflicts('test', created_before=cutoff, dry_run=False, firestore_client=database)
    assert database.store['users/test/memory_review_queue/r']['status'] == 'accepted'
    assert database.write_log == []


def test_expire_rejects_naive_cutoff_before_acquiring_client(monkeypatch):
    def unexpected_client():
        raise AssertionError('must validate before IO')

    monkeypatch.setattr(review_queue, 'get_firestore_client', unexpected_client)
    with pytest.raises(ValueError, match='timezone-aware'):
        review_queue.expire_review_conflicts('test', created_before=datetime(2026, 7, 20))


@pytest.mark.parametrize('status', ['expired', 'unknown', '', None])
def test_action_policy_fails_closed(status):
    assert review_queue.ACTION_POLICY['expired'] == set()
    assert review_queue.permitted_uses(status) == set()
    assert review_queue.can_use_for_action(status, 'irreversible') is False
    assert review_queue.can_use_for_action(status, 'answer') is False


def test_legacy_producer_replay_preserves_expired_review():
    database = _Firestore({})
    first = review_queue.create_review_conflict(
        'test', fact={'id': 'memory-test'}, conflict_with=[], db_client=database
    )
    path = f'users/test/memory_review_queue/{first["review_id"]}'
    database.store[path].update({'status': 'expired', 'permitted_uses': []})
    before = deepcopy(database.store)
    assert (
        review_queue.create_review_conflict('test', fact={'id': 'memory-test'}, conflict_with=[], db_client=database)[
            'status'
        ]
        == 'expired'
    )
    assert database.store == before
    assert len(database.write_log) == 1


def test_list_review_conflicts_applies_server_status_order_and_limit(monkeypatch):
    uid = 'uid-bounded-review-list'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    database = _Firestore(
        _queue_store(
            uid,
            [
                _review('accepted', impact=1.0, created_at=now, status='accepted'),
                _review('high', impact=0.9, created_at=now - timedelta(minutes=2)),
                _review('middle', impact=0.5, created_at=now),
                _review('low', impact=0.1, created_at=now + timedelta(minutes=2)),
            ],
        )
    )
    monkeypatch.setattr(review_queue, 'db', database)

    result = review_queue.list_review_conflicts(uid, status='pending', limit=2)

    assert [item['review_id'] for item in result] == ['high', 'middle']
    assert database.query_log == [
        {
            'filters': (('status', '==', 'pending'),),
            'order_fields': (
                ('impact', Query.DESCENDING),
                ('created_at', Query.DESCENDING),
                ('__name__', Query.DESCENDING),
            ),
            'limit': 2,
            'cursor_id': None,
            'returned_ids': ['high', 'middle'],
        },
        {
            'filters': (('status', '==', 'pending'),),
            'order_fields': (('__name__', Query.DESCENDING),),
            'limit': review_queue.REVIEW_LIST_LEGACY_SCAN_LIMIT,
            'cursor_id': None,
            'returned_ids': ['middle', 'low', 'high'],
        },
    ]
    assert database.batch_get_log == []


def test_list_review_conflicts_fills_after_a_stale_canonical_page_with_one_batch_read(monkeypatch):
    uid = 'uid-stale-review-page'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    database = _Firestore(
        _queue_store(
            uid,
            [
                _review('stale-high', impact=1.0, created_at=now, canonical=True),
                _review('stale-next', impact=0.9, created_at=now, canonical=True),
                _review('valid-high', impact=0.8, created_at=now),
                _review('valid-next', impact=0.7, created_at=now),
            ],
        )
    )
    monkeypatch.setattr(review_queue, 'db', database)

    result = review_queue.list_review_conflicts(uid, status='pending', limit=2)

    assert [item['review_id'] for item in result] == ['valid-high', 'valid-next']
    assert [entry['returned_ids'] for entry in database.query_log] == [
        ['stale-high', 'stale-next'],
        ['valid-high', 'valid-next'],
        ['valid-next', 'valid-high'],
    ]
    assert [entry['limit'] for entry in database.query_log] == [
        2,
        2,
        review_queue.REVIEW_LIST_LEGACY_SCAN_LIMIT,
    ]
    assert database.query_log[1]['cursor_id'] == 'stale-next'
    assert database.batch_get_log == [['memory-stale-high', 'memory-stale-next']]


def test_list_review_conflicts_tombstones_malformed_canonical_source_through_read_boundary(
    monkeypatch,
    caplog,
):
    uid = 'uid-malformed-canonical-review-source'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    secret = 'private malformed canonical memory content'
    review = _review('malformed-source', impact=1.0, created_at=now, canonical=True)
    store = _queue_store(uid, [review])
    store[f'users/{uid}/memory_items/memory-malformed-source'] = {
        'memory_id': 'memory-malformed-source',
        'content': secret,
    }
    database = _Firestore(store)
    monkeypatch.setattr(review_queue, 'db', database)

    with patch.object(read_boundary, 'record_fallback') as fallback:
        result = review_queue.list_review_conflicts(uid, status='pending', limit=1)

    stored = database.store[f'users/{uid}/memory_review_queue/malformed-source']
    assert result == []
    assert stored['status'] == 'tombstoned'
    assert stored['reason'] == 'canonical_review_source_invalid'
    assert stored['candidate'] == {'id': 'memory-malformed-source'}
    assert fallback.call_count == 1
    assert f'users/{uid}/memory_items/memory-malformed-source' in caplog.text
    assert secret not in caplog.text


def test_list_review_conflicts_self_heals_stale_prefix_and_progresses_on_retry(monkeypatch):
    uid = 'uid-stale-review-bound'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    stale_items = [
        _review(
            f'stale-{index:02d}',
            impact=1.0 - index / 100,
            created_at=now,
            canonical=True,
        )
        for index in range(3)
    ]
    valid = _review('valid-after-stale-prefix', impact=0.5, created_at=now)
    database = _Firestore(_queue_store(uid, [*stale_items, valid]))
    monkeypatch.setattr(review_queue, 'db', database)

    first = review_queue.list_review_conflicts(uid, status='pending', limit=1)
    first_query_count = len(database.query_log)
    second = review_queue.list_review_conflicts(uid, status='pending', limit=1)

    assert first == []
    assert [item['review_id'] for item in second] == ['valid-after-stale-prefix']
    assert first_query_count == 1 + review_queue.REVIEW_LIST_STALE_PAGE_ALLOWANCE + 1
    assert all(
        database.store[f'users/{uid}/memory_review_queue/{item["review_id"]}']['status'] == 'tombstoned'
        for item in stale_items
    )
    assert all(
        'content' not in database.store[f'users/{uid}/memory_review_queue/{item["review_id"]}']['candidate']
        for item in stale_items
    )
    assert len(database.batch_get_log) == len(stale_items)


def test_list_review_conflicts_keeps_bounded_legacy_rows_missing_rank_fields(monkeypatch):
    uid = 'uid-legacy-review-list'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    legacy = _review('legacy-high', impact=0.9, created_at=now)
    legacy.pop('created_at')
    database = _Firestore(
        _queue_store(
            uid,
            [
                legacy,
                _review('modern-low', impact=0.1, created_at=now),
            ],
        )
    )
    monkeypatch.setattr(review_queue, 'db', database)

    result = review_queue.list_review_conflicts(uid, status='pending', limit=2)

    assert [item['review_id'] for item in result] == ['legacy-high', 'modern-low']
    assert [entry['returned_ids'] for entry in database.query_log] == [
        ['modern-low'],
        ['modern-low', 'legacy-high'],
    ]
    assert database.query_log[-1]['limit'] == review_queue.REVIEW_LIST_LEGACY_SCAN_LIMIT


def test_list_review_conflicts_rotates_bounded_legacy_scan_past_modern_prefix(monkeypatch):
    uid = 'uid-legacy-review-rotation'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    legacy = _review('a-legacy-high', impact=0.9, created_at=now)
    legacy.pop('created_at')
    modern = [
        _review(f'z-modern-{index:03d}', impact=0.1, created_at=now)
        for index in range(review_queue.REVIEW_LIST_LEGACY_SCAN_LIMIT)
    ]
    database = _Firestore(_queue_store(uid, [legacy, *modern]))
    monkeypatch.setattr(review_queue, 'db', database)

    first = review_queue.list_review_conflicts(uid, status='pending', limit=1)
    first_query_count = len(database.query_log)
    second = review_queue.list_review_conflicts(uid, status='pending', limit=1)
    third = review_queue.list_review_conflicts(uid, status='pending', limit=1)

    assert [item['review_id'] for item in first] == ['z-modern-099']
    assert [item['review_id'] for item in second] == ['a-legacy-high']
    assert [item['review_id'] for item in third] == ['a-legacy-high']
    assert database.store[f'users/{uid}/memory_review_queue/a-legacy-high']['created_at'] == (
        review_queue.REVIEW_LIST_LEGACY_CREATED_AT_SENTINEL
    )
    assert first_query_count == 2
    assert database.query_log[1]['limit'] == review_queue.REVIEW_LIST_LEGACY_SCAN_LIMIT
    assert [entry['cursor_id'] for entry in database.query_log if entry['cursor_id'] is not None] == ['z-modern-000']
    assert database.document_cursor_log == [f'users/{uid}/memory_review_queue/z-modern-000']
    cursor_writes = [entry for entry in database.write_log if '/memory_state/review_queue_legacy_scan_' in entry[1]]
    assert [entry[0] for entry in cursor_writes] == ['set', 'delete', 'set']
    assert all('/memory_review_queue/' not in entry[1] for entry in cursor_writes)


def test_list_review_conflicts_self_heal_failure_fails_closed(monkeypatch):
    uid = 'uid-stale-review-write-failure'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    stale = _review('stale-private', impact=1.0, created_at=now, canonical=True)
    database = _Firestore(_queue_store(uid, [stale]))
    database.fail_review_updates = True
    monkeypatch.setattr(review_queue, 'db', database)

    with pytest.raises(RuntimeError, match='review self-heal failed'):
        review_queue.list_review_conflicts(uid, status='pending', limit=1)

    stored = database.store[f'users/{uid}/memory_review_queue/stale-private']
    assert stored['status'] == 'pending'
    assert stored['candidate']['content'] == 'stale-private'


def test_list_review_conflicts_cursor_write_failure_is_not_silent(monkeypatch):
    uid = 'uid-legacy-review-cursor-failure'
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    legacy = _review('a-legacy', impact=0.9, created_at=now)
    legacy.pop('created_at')
    modern = [
        _review(f'z-modern-{index:03d}', impact=0.1, created_at=now)
        for index in range(review_queue.REVIEW_LIST_LEGACY_SCAN_LIMIT)
    ]
    database = _Firestore(_queue_store(uid, [legacy, *modern]))
    database.fail_cursor_writes = True
    monkeypatch.setattr(review_queue, 'db', database)

    with pytest.raises(RuntimeError, match='cursor write failed'):
        review_queue.list_review_conflicts(uid, status='pending', limit=1)

    assert database.store[f'users/{uid}/memory_review_queue/a-legacy']['status'] == 'pending'
