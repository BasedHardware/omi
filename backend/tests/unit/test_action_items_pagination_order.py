"""get_action_items must paginate AFTER the final sort, not on the Firestore query.

The query orders by due_at/created_at DESC and applied offset/limit at the Firestore level, but then
re-sorted the page client-side into a different order (due_at ascending, items without a due date
last). So offset/limit sliced the Firestore-ordered set and the re-sort only reordered that slice --
every page, even page 0 with a limit, returned the wrong items. A user paging their tasks could miss
soon-due items that were created earlier. Pagination now runs after the sort, so it matches the
returned order.

``database.action_items`` is import-pure (``database._client.db`` is a lazy proxy that does not
construct a client at import time), so no ``sys.modules`` stubbing is required. The query chain is
replaced per-test via ``monkeypatch.setattr(action_items, 'db', ...)`` -- the sanctioned Tier-2 seam.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import database.action_items as action_items

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Doc:
    def __init__(self, doc_id, created_at, due_at, completed=None):
        self.id = doc_id
        self._data = {'created_at': created_at, 'due_at': due_at}
        # Only stamp `completed` when the test cares about it, so the existing
        # all-active fixtures keep exercising the missing-field default path.
        if completed is not None:
            self._data['completed'] = completed

    def to_dict(self):
        return dict(self._data)


class _Query:
    """Firestore query stand-in. stream() returns docs sliced the way Firestore would if offset()/
    limit() were applied, so the pre-fix code (which paginates on the query) sees a pre-sliced set."""

    def __init__(self, docs):
        self._docs = docs
        self._offset = 0
        self._limit = None

    def where(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def offset(self, n):
        self._offset = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def stream(self):
        d = self._docs[self._offset :]
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

    assert [(family.value, mode.value, documents) for family, mode, documents in observed] == [
        ('action_items_list', 'unbounded', 5)
    ]


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
    out = action_items._prepare_action_item_for_read(dict(raw))
    assert out['completed'] is expected_completed
    assert out['status'] == expected_status
