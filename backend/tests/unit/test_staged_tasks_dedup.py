"""Tests for the promote_staged_task duplicate guard.

The promotion path used to call ``database.action_items.create_action_item``
unconditionally, which allocates a fresh Firestore document id on every call.
A user re-mentioning the same task in multiple conversations would extract
into a new staged task each time and accumulate 5–6 duplicate action_items
within a few hours. The fix:

1. ``database.action_items.get_active_action_item_by_description`` —
   case-insensitive normalized lookup against the live ``action_items``
   collection (skips deleted, ignores Firestore's case-sensitive equality
   limitation).
2. ``database.staged_tasks.promote_staged_task`` — short-circuits when the
   helper returns an existing item: closes the staged task with
   ``promotion_skipped='duplicate'`` + ``promoted_to=<existing.id>`` and
   returns the existing record instead of creating a new one.

These tests cover the contract of both pieces.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from database import action_items as action_items_db
from database import staged_tasks as staged_tasks_db
from tests.store_fakes import FakeDocumentStore

# ---------------------------------------------------------------------------
# _normalize_description
# ---------------------------------------------------------------------------


def test_normalize_strips_whitespace_and_lowercases():
    assert action_items_db._normalize_description('  Foo Bar  ') == 'foo bar'


def test_normalize_strips_screen_prefix():
    assert action_items_db._normalize_description('[screen] Email John') == 'email john'


def test_normalize_strips_screen_suffix():
    assert action_items_db._normalize_description('Email John [screen]') == 'email john'


def test_normalize_handles_none_and_empty():
    assert action_items_db._normalize_description(None) == ''
    assert action_items_db._normalize_description('') == ''


# ---------------------------------------------------------------------------
# get_active_action_item_by_description
# ---------------------------------------------------------------------------


def _make_doc(doc_id, data):
    return (doc_id, data)


def _stub_action_items_query(monkeypatch, docs):
    """Seed the active-action-items collection through the ``_store()`` seam."""
    store = FakeDocumentStore()
    for doc_id, data in docs:
        store._docs[f'users/uid/action_items/{doc_id}'] = dict(data)
    monkeypatch.setattr(action_items_db, '_store', lambda: store)


def test_returns_none_when_no_active_items(monkeypatch):
    _stub_action_items_query(monkeypatch, [])
    assert action_items_db.get_active_action_item_by_description('uid', 'whatever') is None


def test_returns_existing_match_case_insensitive(monkeypatch):
    docs = [
        _make_doc('AAA', {'description': 'Email John', 'completed': False}),
    ]
    _stub_action_items_query(monkeypatch, docs)

    result = action_items_db.get_active_action_item_by_description('uid', '  EMAIL JOHN  ')
    assert result is not None
    assert result['id'] == 'AAA'


def test_skips_deleted_items(monkeypatch):
    docs = [
        _make_doc('AAA', {'description': 'Email John', 'completed': False, 'deleted': True}),
        _make_doc('BBB', {'description': 'Email John', 'completed': False}),
    ]
    _stub_action_items_query(monkeypatch, docs)

    result = action_items_db.get_active_action_item_by_description('uid', 'email john')
    assert result is not None
    assert result['id'] == 'BBB'


def test_returns_none_when_only_unrelated_items(monkeypatch):
    docs = [
        _make_doc('AAA', {'description': 'Buy groceries', 'completed': False}),
        _make_doc('BBB', {'description': 'Call dentist', 'completed': False}),
    ]
    _stub_action_items_query(monkeypatch, docs)
    assert action_items_db.get_active_action_item_by_description('uid', 'email john') is None


def test_normalizes_screen_marker_on_both_sides(monkeypatch):
    """An existing AI-tagged item with [screen] suffix should match an
    incoming staged task whose description omits the marker — and vice versa."""
    docs = [
        _make_doc('AAA', {'description': 'Email John [screen]', 'completed': False}),
    ]
    _stub_action_items_query(monkeypatch, docs)
    assert action_items_db.get_active_action_item_by_description('uid', 'Email John') is not None


# ---------------------------------------------------------------------------
# promote_staged_task — dedup guard
# ---------------------------------------------------------------------------


def _seed_staged(monkeypatch, top):
    """Seed a FakeDocumentStore with ``top`` (a single active staged task) and
    wire it through the ``_store()`` seam. Returns ``(store, path)`` so a test can
    assert on the stored document's resulting state."""
    store = FakeDocumentStore()
    path = f'users/uid/staged_tasks/{top["id"]}'
    store.set(path, {'completed': False, **top})
    monkeypatch.setattr(staged_tasks_db, '_store', lambda: store)
    return store, path


def test_promote_skips_when_active_duplicate_exists(monkeypatch):
    store, path = _seed_staged(
        monkeypatch,
        {'id': 'staged-1', 'description': 'Follow up on Volt', 'relevance_score': 1},
    )

    existing = {'id': 'existing-action-1', 'description': 'Follow up on Volt', 'completed': False}
    monkeypatch.setattr(
        action_items_db,
        'get_active_action_item_by_description',
        lambda uid, desc: existing,
    )

    create_called = []
    monkeypatch.setattr(
        action_items_db,
        'create_action_item',
        lambda uid, data: create_called.append(data) or 'should-not-be-called',
    )

    result = staged_tasks_db.promote_staged_task('uid')

    assert result == existing
    assert create_called == [], "create_action_item must not be called when a duplicate exists"
    stored = store.get(path).to_dict()
    assert stored.get('completed') is True
    assert stored.get('promotion_skipped') == 'duplicate'
    assert stored.get('promoted_to') == 'existing-action-1'


def test_promote_creates_when_no_duplicate(monkeypatch):
    store, path = _seed_staged(
        monkeypatch,
        {'id': 'staged-2', 'description': 'New unique task', 'relevance_score': 1},
    )

    monkeypatch.setattr(
        action_items_db,
        'get_active_action_item_by_description',
        lambda uid, desc: None,
    )

    monkeypatch.setattr(
        action_items_db,
        'create_action_item',
        lambda uid, data: 'fresh-id-1',
    )
    monkeypatch.setattr(
        action_items_db,
        'get_action_item',
        lambda uid, action_id: {'id': action_id, 'description': 'New unique task'},
    )

    result = staged_tasks_db.promote_staged_task('uid')

    assert result == {'id': 'fresh-id-1', 'description': 'New unique task'}
    stored = store.get(path).to_dict()
    # The skip marker stays absent, while the canonical reconciliation target is durable.
    assert 'promotion_skipped' not in stored
    assert stored['promoted_to'] == 'fresh-id-1'
    # The normal completed/promoted_at update still fires.
    assert stored.get('completed') is True
    assert isinstance(stored.get('promoted_at'), datetime)


def test_existing_reservation_never_recreates_task_closed_after_begin(monkeypatch):
    store, path = _seed_staged(
        monkeypatch,
        {'id': 'staged-existing', 'description': 'Deleted by user', 'relevance_score': 1},
    )
    monkeypatch.setattr(
        action_items_db,
        'get_active_action_item_by_description',
        lambda uid, desc: None,
    )
    monkeypatch.setattr(
        action_items_db,
        'create_action_item',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('deleted task must not be recreated')),
    )

    result = staged_tasks_db.promote_staged_task(
        'uid',
        action_item_id='task-deleted-after-begin',
        reservation_kind='existing',
    )

    assert result == {'id': 'task-deleted-after-begin'}
    stored = store.get(path).to_dict()
    assert stored['completed'] is True
    assert stored['promoted_to'] == 'task-deleted-after-begin'
    assert stored['promotion_skipped'] == 'duplicate_target_closed'


def test_promote_merges_missing_fields_on_dedup(monkeypatch):
    """When dedup hits, fields the existing action_item is MISSING that the
    staged task carries (e.g. a due_at from a later conversation) should be
    merged onto the existing item rather than silently dropped."""
    _seed_staged(
        monkeypatch,
        {
            'id': 'staged-3',
            'description': 'Email John',
            'relevance_score': 1,
            'due_at': '2026-05-01T10:00:00Z',
            'priority': 'high',
            'category': 'work',
        },
    )

    existing = {
        'id': 'existing-id-3',
        'description': 'Email John',
        'completed': False,
        'priority': 'low',  # already set — must NOT be overwritten
        # due_at and category missing — both should be merged in
    }
    monkeypatch.setattr(
        action_items_db,
        'get_active_action_item_by_description',
        lambda uid, desc: existing,
    )

    update_calls = []
    monkeypatch.setattr(
        action_items_db,
        'update_action_item',
        lambda uid, action_id, data: update_calls.append((action_id, data)) or True,
    )
    monkeypatch.setattr(action_items_db, 'create_action_item', lambda uid, data: 'should-not-be-called')

    result = staged_tasks_db.promote_staged_task('uid')

    assert result['id'] == 'existing-id-3'
    assert len(update_calls) == 1
    target_id, merged = update_calls[0]
    assert target_id == 'existing-id-3'
    assert merged.get('due_at') == '2026-05-01T10:00:00Z'
    assert merged.get('category') == 'work'
    # priority was already set on existing — must not be overwritten
    assert 'priority' not in merged
    # The merged fields must also be reflected on the returned dict so the
    # caller doesn't need to re-fetch.
    assert result['due_at'] == '2026-05-01T10:00:00Z'
    assert result['category'] == 'work'


def test_promote_dedup_no_merge_when_existing_already_has_fields(monkeypatch):
    """If the existing action_item already has every field the staged task
    carries, the merge step should be a no-op (no update_action_item call)."""
    _seed_staged(
        monkeypatch,
        {
            'id': 'staged-4',
            'description': 'Email John',
            'relevance_score': 1,
            'due_at': '2026-05-01T10:00:00Z',
            'priority': 'high',
        },
    )

    existing = {
        'id': 'existing-id-4',
        'description': 'Email John',
        'completed': False,
        'due_at': '2026-04-30T10:00:00Z',  # already set
        'priority': 'low',  # already set
    }
    monkeypatch.setattr(
        action_items_db,
        'get_active_action_item_by_description',
        lambda uid, desc: existing,
    )

    update_calls = []
    monkeypatch.setattr(
        action_items_db,
        'update_action_item',
        lambda uid, action_id, data: update_calls.append((action_id, data)) or True,
    )
    monkeypatch.setattr(action_items_db, 'create_action_item', lambda uid, data: 'should-not-be-called')

    result = staged_tasks_db.promote_staged_task('uid')

    assert result == existing
    assert update_calls == [], "no merge call expected when existing has all fields"


def test_create_staged_task_uses_normalized_dedup(monkeypatch):
    """Regression for the normalization-divergence review note: an "[screen]"-
    prefixed description should match an existing staged task whose
    description omits the marker, so we don't end up with two staged
    candidates that resolve to the same action_item."""
    store = FakeDocumentStore()
    store.set(
        'users/uid/staged_tasks/staged-existing',
        {'description': 'Email John', 'completed': False},
    )
    monkeypatch.setattr(staged_tasks_db, '_store', lambda: store)

    result = staged_tasks_db.create_staged_task('uid', '[screen] Email John')
    assert result['id'] == 'staged-existing'
    # No new doc written — the collection still holds only the pre-existing row.
    assert store.list_ids('users/uid/staged_tasks') == ['staged-existing']


def test_promote_returns_none_when_no_staged(monkeypatch):
    store = FakeDocumentStore()  # empty — no staged tasks
    monkeypatch.setattr(staged_tasks_db, '_store', lambda: store)

    assert staged_tasks_db.promote_staged_task('uid') is None
