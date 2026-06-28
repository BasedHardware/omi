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

import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock


# Stub heavy deps before importing the modules under test.
def _ensure_module(name):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
    return sys.modules[name]


for mod_name in [
    'firebase_admin',
    'firebase_admin.auth',
    'google',
    'google.cloud',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query',
]:
    _ensure_module(mod_name)


class _FakeFirestoreClient:
    def collection(self, *a, **kw):
        return MagicMock()

    def batch(self):
        return MagicMock()


sys.modules['google.cloud.firestore'].Client = _FakeFirestoreClient
sys.modules['google.cloud.firestore'].SERVER_TIMESTAMP = object()
sys.modules['google.cloud.firestore'].Query = MagicMock()


class _FieldFilter:
    def __init__(self, field, op, value):
        self.field = field
        self.op = op
        self.value = value


sys.modules['google.cloud.firestore'].FieldFilter = _FieldFilter
sys.modules['google.cloud.firestore_v1'].FieldFilter = _FieldFilter
sys.modules['google.cloud.firestore_v1.base_query'].FieldFilter = _FieldFilter
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

# Stub the firestore client singleton so importing the modules doesn't try
# to authenticate against real Firestore.
fake_db = MagicMock()
client_stub = types.ModuleType('database._client')
client_stub.db = fake_db
sys.modules['database._client'] = client_stub


from database import action_items as action_items_db  # noqa: E402
from database import staged_tasks as staged_tasks_db  # noqa: E402

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
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    return doc


def _stub_action_items_query(monkeypatch, docs):
    """Stub db.collection(...).document(uid).collection(action_items).where(...).stream() to yield docs."""
    fake_query = MagicMock()
    fake_query.stream.return_value = iter(docs)

    fake_subcol = MagicMock()
    fake_subcol.where.return_value = fake_query

    fake_user_doc = MagicMock()
    fake_user_doc.collection.return_value = fake_subcol

    fake_users = MagicMock()
    fake_users.document.return_value = fake_user_doc

    monkeypatch.setattr(action_items_db, 'db', MagicMock(collection=MagicMock(return_value=fake_users)))


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


def _stub_top_staged(monkeypatch, top):
    """Stub _user_col(uid, 'staged_tasks') so the top-staged-task query
    returns ``top`` (a single doc dict) and update()/document() are spies."""
    staged_doc = _make_doc(top['id'], top)

    fake_query = MagicMock()
    fake_query.where.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.stream.return_value = iter([staged_doc])

    update_calls = {}
    fake_doc_ref = MagicMock()

    def update(payload):
        update_calls.update(payload)

    fake_doc_ref.update.side_effect = update

    fake_col = MagicMock()
    fake_col.where.return_value = fake_query
    fake_col.document.return_value = fake_doc_ref

    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: fake_col)
    return update_calls


def test_promote_skips_when_active_duplicate_exists(monkeypatch):
    update_calls = _stub_top_staged(
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
    assert update_calls.get('completed') is True
    assert update_calls.get('promotion_skipped') == 'duplicate'
    assert update_calls.get('promoted_to') == 'existing-action-1'


def test_promote_creates_when_no_duplicate(monkeypatch):
    update_calls = _stub_top_staged(
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
    # The skip-marker fields must NOT be set on the happy path.
    assert 'promotion_skipped' not in update_calls
    assert 'promoted_to' not in update_calls
    # The normal completed/promoted_at update still fires.
    assert update_calls.get('completed') is True
    assert isinstance(update_calls.get('promoted_at'), datetime)


def test_promote_merges_missing_fields_on_dedup(monkeypatch):
    """When dedup hits, fields the existing action_item is MISSING that the
    staged task carries (e.g. a due_at from a later conversation) should be
    merged onto the existing item rather than silently dropped."""
    _stub_top_staged(
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
    _stub_top_staged(
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
    existing_doc = _make_doc(
        'staged-existing',
        {'description': 'Email John', 'completed': False},
    )

    fake_col = MagicMock()
    fake_col.stream.return_value = iter([existing_doc])

    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: fake_col)

    result = staged_tasks_db.create_staged_task('uid', '[screen] Email John')
    assert result['id'] == 'staged-existing'
    fake_col.document.assert_not_called()  # no new doc written


def test_promote_returns_none_when_no_staged(monkeypatch):
    fake_query = MagicMock()
    fake_query.where.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.stream.return_value = iter([])

    fake_col = MagicMock()
    fake_col.where.return_value = fake_query

    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: fake_col)

    assert staged_tasks_db.promote_staged_task('uid') is None
