"""get_action_items must paginate AFTER the final sort, not on the Firestore query.

The query orders by due_at/created_at DESC and applied offset/limit at the Firestore level, but then
re-sorted the page client-side into a different order (due_at ascending, items without a due date
last). So offset/limit sliced the Firestore-ordered set and the re-sort only reordered that slice --
every page, even page 0 with a limit, returned the wrong items. A user paging their tasks could miss
soon-due items that were created earlier. Pagination now runs after the sort, so it matches the
returned order.

List reads are hard-capped (``FirestoreReadMode.BOUNDED``). ``database.action_items`` is import-pure (``database._client.db`` is a lazy proxy that does not
construct a client at import time), so no ``sys.modules`` stubbing is required. The query chain is
replaced per-test via ``monkeypatch.setattr(action_items, 'db', ...)`` -- the sanctioned Tier-2 seam.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import database.action_items as action_items

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Doc:
    def __init__(self, doc_id, created_at, due_at, completed=None, conversation_id=None):
        self.id = doc_id
        self._data = {'created_at': created_at, 'due_at': due_at}
        # Only stamp `completed` when the test cares about it, so the existing
        # all-active fixtures keep exercising the missing-field default path.
        if completed is not None:
            self._data['completed'] = completed
        if conversation_id is not None:
            self._data['conversation_id'] = conversation_id

    def to_dict(self):
        return dict(self._data)


class _Query:
    """Firestore query stand-in with completed equality filtering (production semantics)."""

    def __init__(self, docs, completed=None, conversation_id=None, order_by_fields=None):
        self._docs = docs
        self._completed = completed
        self._conversation_id = conversation_id
        self._order_by_fields = list(order_by_fields or [])
        self._offset = 0
        self._limit = None

    def where(self, *a, **k):
        filt = k.get('filter') if k else None
        completed = self._completed
        conversation_id = self._conversation_id
        if filt is not None:
            field = getattr(filt, 'field_path', None) or getattr(filt, 'field', None)
            value = getattr(filt, 'value', None)
            if field == 'completed':
                completed = value
            elif field == 'conversation_id':
                conversation_id = value
        q = _Query(
            self._docs,
            completed=completed,
            conversation_id=conversation_id,
            order_by_fields=self._order_by_fields,
        )
        q._offset = self._offset
        q._limit = self._limit
        return q

    def order_by(self, field, direction=None):
        q = _Query(
            self._docs,
            completed=self._completed,
            conversation_id=self._conversation_id,
            order_by_fields=self._order_by_fields + [(field, direction)],
        )
        q._offset = self._offset
        q._limit = self._limit
        return q

    def select(self, _fields):
        return self

    def offset(self, n):
        self._offset = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def stream(self):
        d = list(self._docs)
        if self._conversation_id is not None:
            d = [doc for doc in d if doc._data.get('conversation_id') == self._conversation_id]
        if self._completed is not None:
            # Firestore equality excludes missing/null completed fields.
            d = [doc for doc in d if doc._data.get('completed') is self._completed]
        for field, direction in self._order_by_fields:
            if field == 'due_at':
                d = [doc for doc in d if doc._data.get('due_at') is not None]
                d.sort(key=lambda doc: doc._data.get('due_at'))
            elif field == 'created_at':
                d.sort(
                    key=lambda doc: doc._data.get('created_at') or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True,
                )
        d = d[self._offset :]
        if self._limit is not None:
            d = d[: self._limit]
        return iter(d)


# Docs in created_at DESC order (the Firestore order for the default path). The due dates make the
# final sort order (soonest due first, no-due last) different from created_at DESC.
DOCS = [
    _Doc('A', BASE + timedelta(minutes=5), None),
    _Doc('B', BASE + timedelta(minutes=4), BASE + timedelta(days=10)),
    _Doc('C', BASE + timedelta(minutes=3), BASE + timedelta(days=1)),
    _Doc('D', BASE + timedelta(minutes=2), BASE + timedelta(days=5)),
    _Doc('E', BASE + timedelta(minutes=1), None),
]
# Firestore order: A, B, C, D, E ; final sorted order: C, D, B, A, E


@pytest.fixture
def fake_db(monkeypatch):
    db = MagicMock(name='db')
    monkeypatch.setattr(action_items, 'db', db)
    return db


def _ids(fake_db, **kwargs):
    query = _Query(list(DOCS))
    fake_db.collection.return_value.document.return_value.collection.return_value = query
    return [item['id'] for item in action_items.get_action_items('uid1', **kwargs)]


def test_full_order_no_pagination(fake_db):
    assert _ids(fake_db) == ['C', 'D', 'B', 'A', 'E']


def test_first_page_returns_soonest_due_not_newest_created(fake_db):
    # offset=0, limit=2 -> first two of the final order (soonest due), not the two newest-created.
    assert _ids(fake_db, limit=2, offset=0) == ['C', 'D']


def test_second_page_continues_final_order(fake_db):
    # offset=2, limit=2 -> the next two of the final order.
    assert _ids(fake_db, limit=2, offset=2) == ['B', 'A']


def test_non_positive_limit_does_not_truncate(fake_db):
    # A defensive guard: limit <= 0 must not silently return an empty/garbage slice (e.g. [:0] or a
    # negative slice). Such a limit means "no page cap", so the full sorted order is returned.
    assert _ids(fake_db, limit=0) == ['C', 'D', 'B', 'A', 'E']
    assert _ids(fake_db, limit=-5) == ['C', 'D', 'B', 'A', 'E']


# Docs mixing completed + active. A completed task with an EARLIER due date must still sort
# after every active task. Regression: for a user with 100+ old completed (due-dated) tasks,
# active tasks were pushed past the client's first page (limit=100) on the default
# completed=None fetch, so the task list rendered empty / all-done.
MIXED = [
    _Doc('done_soon', BASE, BASE + timedelta(days=1), completed=True),
    _Doc('active_late', BASE, BASE + timedelta(days=9), completed=False),
    _Doc('active_none', BASE, None, completed=False),
    _Doc('done_late', BASE, BASE + timedelta(days=5), completed=True),
]


def _mixed_ids(fake_db, **kwargs):
    query = _Query(list(MIXED))
    fake_db.collection.return_value.document.return_value.collection.return_value = query
    return [item['id'] for item in action_items.get_action_items('uid1', **kwargs)]


def test_incomplete_items_sort_before_completed(fake_db):
    # Active first (by due, no-due last), then completed (by due) — never a completed item ahead
    # of an active one, even when the completed item is due sooner.
    assert _mixed_ids(fake_db) == ['active_late', 'active_none', 'done_soon', 'done_late']


def test_first_page_surfaces_active_items(fake_db):
    # The core regression guard: a small first page must contain the active items, not be crowded
    # out by sooner-due completed tasks.
    page = _mixed_ids(fake_db, limit=2, offset=0)
    assert page == ['active_late', 'active_none']


def test_list_observes_every_scanned_document(fake_db, monkeypatch):
    observed = []
    monkeypatch.setattr(action_items, 'record_firestore_read', lambda *args: observed.append(args))

    _ids(fake_db, limit=2)

    assert len(observed) == 1
    family, mode, documents = observed[0]
    assert family.value == 'action_items_list'
    assert mode.value == 'bounded'
    assert documents >= 5


@pytest.mark.parametrize(
    "raw,expected_completed,expected_status",
    [
        ({'completed': None}, False, 'active'),  # explicit null (legacy/partial write)
        ({}, False, 'active'),  # missing entirely
        ({'completed': True}, True, 'completed'),
        ({'completed': False}, False, 'active'),
    ],
)
def test_completed_normalized_to_bool(raw, expected_completed, expected_status):
    out = action_items.prepare_action_item_for_read(dict(raw))
    assert out['completed'] is expected_completed
    assert out['status'] == expected_status


def test_large_active_task_pagination_no_duplicates_or_skips(fake_db):
    """Regression test for #21225: 200 active tasks with ids t000..t199 (ascending)
    and due dates reversed so t199 is due soonest. Offset pagination must return
    globally soonest-due tasks on page 1, and page 2 must continue with zero
    duplicates or omitted tasks across pages."""
    large_docs = [
        _Doc(
            f't{i:03d}',
            created_at=BASE + timedelta(minutes=i),
            due_at=BASE + timedelta(days=200 - i),
            completed=False,
        )
        for i in range(200)
    ]
    query = _Query(large_docs)
    fake_db.collection.return_value.document.return_value.collection.return_value = query

    page1 = [item['id'] for item in action_items.get_action_items('uid1', limit=100, offset=0)]
    page2 = [item['id'] for item in action_items.get_action_items('uid1', limit=100, offset=100)]

    assert len(page1) == 100
    assert len(page2) == 100
    # Page 1 contains soonest-due first: t199 is due in 1 day, t198 in 2 days, etc.
    assert page1[:3] == ['t199', 't198', 't197']
    assert page1[-1] == 't100'
    assert page2[0] == 't099'
    assert page2[-1] == 't000'

    # Exactly 0 duplicates across pages
    assert set(page1).intersection(set(page2)) == set()
    # All 200 tasks returned across the 2 pages
    assert set(page1).union(set(page2)) == {f't{i:03d}' for i in range(200)}


def test_conversation_scoped_query_skips_ordered_prefix_ordering(fake_db):
    """When conversation_id is provided, queries fall back to single-query bounded
    scan without order_by('created_at', DESCENDING) to avoid missing composite index
    FailedPrecondition in Firestore on (conversation_id, completed, created_at DESC)."""
    docs = [
        _Doc(
            'c1_task1', BASE + timedelta(minutes=1), BASE + timedelta(days=2), completed=False, conversation_id='conv-1'
        ),
        _Doc('c1_task2', BASE + timedelta(minutes=2), None, completed=False, conversation_id='conv-1'),
        _Doc(
            'c2_task', BASE + timedelta(minutes=3), BASE + timedelta(days=1), completed=False, conversation_id='conv-2'
        ),
    ]
    query = _Query(docs)
    tracked_queries = []

    orig_where = query.where

    def _tracking_where(*args, **kwargs):
        sub_q = orig_where(*args, **kwargs)
        tracked_queries.append(sub_q)
        return sub_q

    query.where = _tracking_where
    fake_db.collection.return_value.document.return_value.collection.return_value = query

    items = action_items.get_action_items('uid1', conversation_id='conv-1')
    assert [i['id'] for i in items] == ['c1_task1', 'c1_task2']
    # Verify no orderBy was applied to Firestore queries for conversation_id scoped call
    for q in tracked_queries:
        assert q._order_by_fields == []
