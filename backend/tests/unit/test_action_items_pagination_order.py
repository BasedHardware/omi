"""get_action_items must paginate AFTER the final sort, not on the storage query.

The query orders by due_at/created_at DESC and applied offset/limit at the storage level, but then
re-sorted the page in-process into a different order (due_at ascending, items without a due date
last). So offset/limit sliced the storage-ordered set and the re-sort only reordered that slice --
every page, even page 0 with a limit, returned the wrong items. A user paging their tasks could miss
soon-due items that were created earlier. Pagination now runs after the sort, so it matches the
returned order.

List reads are hard-capped (``FirestoreReadMode.BOUNDED``). ``database.action_items`` reads through
the neutral storage port; the store is replaced per-test with a ``FakeDocumentStore`` seeded at the
user's ``action_items`` path via ``monkeypatch.setattr(action_items, '_store', ...)``.
"""

from datetime import datetime, timedelta, timezone

import pytest

import database.action_items as action_items
from tests.store_fakes import FakeDocumentStore

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)

_UID = 'uid1'


def _seed(store, docs):
    for doc_id, data in docs:
        store._docs[f'users/{_UID}/action_items/{doc_id}'] = dict(data)


def _doc(created_at, due_at, completed=None):
    # Only stamp `completed` when the test cares about it, so the all-active fixtures keep
    # exercising the missing-field default path (server equality excludes missing-field docs).
    data = {'created_at': created_at, 'due_at': due_at}
    if completed is not None:
        data['completed'] = completed
    return data


# Docs in created_at DESC order (the storage order for the default path). The due dates make the
# final sort order (soonest due first, no-due last) different from created_at DESC.
DOCS = [
    ('A', _doc(BASE + timedelta(minutes=5), None)),
    ('B', _doc(BASE + timedelta(minutes=4), BASE + timedelta(days=10))),
    ('C', _doc(BASE + timedelta(minutes=3), BASE + timedelta(days=1))),
    ('D', _doc(BASE + timedelta(minutes=2), BASE + timedelta(days=5))),
    ('E', _doc(BASE + timedelta(minutes=1), None)),
]
# storage order: A, B, C, D, E ; final sorted order: C, D, B, A, E


@pytest.fixture
def fake_store(monkeypatch):
    store = FakeDocumentStore()
    monkeypatch.setattr(action_items, '_store', lambda: store)
    return store


def _ids(fake_store, **kwargs):
    _seed(fake_store, DOCS)
    return [item['id'] for item in action_items.get_action_items(_UID, **kwargs)]


def test_full_order_no_pagination(fake_store):
    assert _ids(fake_store) == ['C', 'D', 'B', 'A', 'E']


def test_first_page_returns_soonest_due_not_newest_created(fake_store):
    # offset=0, limit=2 -> first two of the final order (soonest due), not the two newest-created.
    assert _ids(fake_store, limit=2, offset=0) == ['C', 'D']


def test_second_page_continues_final_order(fake_store):
    # offset=2, limit=2 -> the next two of the final order.
    assert _ids(fake_store, limit=2, offset=2) == ['B', 'A']


def test_non_positive_limit_does_not_truncate(fake_store):
    # A defensive guard: limit <= 0 must not silently return an empty/garbage slice (e.g. [:0] or a
    # negative slice). Such a limit means "no page cap", so the full sorted order is returned.
    assert _ids(fake_store, limit=0) == ['C', 'D', 'B', 'A', 'E']
    assert _ids(fake_store, limit=-5) == ['C', 'D', 'B', 'A', 'E']


# Docs mixing completed + active. A completed task with an EARLIER due date must still sort
# after every active task. Regression: for a user with 100+ old completed (due-dated) tasks,
# active tasks were pushed past the client's first page (limit=100) on the default
# completed=None fetch, so the task list rendered empty / all-done.
MIXED = [
    ('done_soon', _doc(BASE, BASE + timedelta(days=1), completed=True)),
    ('active_late', _doc(BASE, BASE + timedelta(days=9), completed=False)),
    ('active_none', _doc(BASE, None, completed=False)),
    ('done_late', _doc(BASE, BASE + timedelta(days=5), completed=True)),
]


def _mixed_ids(fake_store, **kwargs):
    _seed(fake_store, MIXED)
    return [item['id'] for item in action_items.get_action_items(_UID, **kwargs)]


def test_incomplete_items_sort_before_completed(fake_store):
    # Active first (by due, no-due last), then completed (by due) — never a completed item ahead
    # of an active one, even when the completed item is due sooner.
    assert _mixed_ids(fake_store) == ['active_late', 'active_none', 'done_soon', 'done_late']


def test_first_page_surfaces_active_items(fake_store):
    # The core regression guard: a small first page must contain the active items, not be crowded
    # out by sooner-due completed tasks.
    page = _mixed_ids(fake_store, limit=2, offset=0)
    assert page == ['active_late', 'active_none']


def test_list_observes_every_scanned_document(fake_store, monkeypatch):
    observed = []
    monkeypatch.setattr(action_items, 'record_firestore_read', lambda *args: observed.append(args))

    _ids(fake_store, limit=2)

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
    out = action_items._prepare_action_item_for_read(dict(raw))
    assert out['completed'] is expected_completed
    assert out['status'] == expected_status
