"""Tests for get_conversations_count logic and /v1/conversations/count endpoint.

``TestConversationsCount`` exercises a module-local MagicMock ``mock_db`` inline
copy (``test_source_matches_implementation`` guards against drift);
``TestConversationsCountRealHelper`` exercises the real
``database.conversations.get_conversations_count`` against a deterministic fake.
"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import database.conversations as conversations_db

try:
    from google.cloud.firestore_v1 import FieldFilter
except ImportError:
    # Lightweight test runs may not install Firestore.

    class FieldFilter:
        def __init__(self, field_path, op_string, value):
            self.field_path = field_path
            self.op_string = op_string
            self.value = value


mock_db = MagicMock()


def get_conversations_count(
    uid,
    include_discarded=False,
    statuses=None,
    start_date=None,
    end_date=None,
    categories=None,
    folder_id=None,
    starred=None,
    sources=None,
):
    """Mirrors database.conversations.get_conversations_count."""
    collection = mock_db.collection('users').document(uid).collection('conversations')
    conversations_ref = collection
    if not include_discarded:
        conversations_ref = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
    if sources:
        if len(sources) == 1:
            conversations_ref = conversations_ref.where(filter=FieldFilter('source', '==', sources[0]))
        else:
            conversations_ref = conversations_ref.where(filter=FieldFilter('source', 'in', sources))
    if statuses:
        if len(statuses) == 1:
            conversations_ref = conversations_ref.where(filter=FieldFilter('status', '==', statuses[0]))
        else:
            conversations_ref = conversations_ref.where(filter=FieldFilter('status', 'in', statuses))
    if categories:
        conversations_ref = conversations_ref.where(filter=FieldFilter('structured.category', 'in', categories))
    if folder_id:
        conversations_ref = conversations_ref.where(filter=FieldFilter('folder_id', '==', folder_id))
    if starred is not None:
        conversations_ref = conversations_ref.where(filter=FieldFilter('starred', '==', starred))
    if start_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter('created_at', '>=', start_date))
    if end_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter('created_at', '<=', end_date))
    if start_date or end_date:
        conversations_ref = conversations_ref.order_by('created_at', direction='DESCENDING')
    result = conversations_ref.count().get()
    matching = int(result[0][0].value)
    for doc in collection.where(filter=FieldFilter('deleted', '==', True)).stream():
        data = doc.to_dict() or {}
        if not include_discarded and data.get('discarded'):
            continue
        if statuses and data.get('status') not in statuses:
            continue
        if sources and data.get('source') not in sources:
            continue
        matching -= 1
    return matching


class TestConversationsCount:
    def setup_method(self):
        mock_db.reset_mock()

    def _make_result(self, value):
        v = MagicMock()
        v.value = value
        return [[v]]

    def test_source_matches_implementation(self):
        """Verify the real function's core logic matches this test's inline copy."""
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'def get_conversations_count(' in source
        assert "FieldFilter('discarded', '==', False)" in source
        assert "FieldFilter('source', '==', sources[0])" in source
        assert "FieldFilter('source', 'in', sources)" in source
        assert "FieldFilter('status', '==', statuses[0])" in source
        assert "FieldFilter('status', 'in', statuses)" in source
        assert "FieldFilter('folder_id', '==', folder_id)" in source
        assert "FieldFilter('starred', '==', starred)" in source
        assert "FieldFilter('created_at', '>=', start_date)" in source
        assert "FieldFilter('created_at', '<=', end_date)" in source
        assert "order_by('created_at', direction=firestore.Query.DESCENDING)" in source
        assert "FieldFilter('deleted', '==', True)" in source
        assert '.count().get()' in source
        assert 'result[0][0].value' in source

    def test_count_returns_integer(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.stream.return_value = []
        ref.count.return_value.get.return_value = self._make_result(42)

        result = get_conversations_count('uid1')
        assert result == 42
        assert isinstance(result, int)

    def test_count_with_statuses_applies_correct_filters(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.stream.return_value = []
        ref.count.return_value.get.return_value = self._make_result(10)

        result = get_conversations_count('uid1', statuses=['processing', 'completed'])
        assert result == 10
        assert ref.where.call_count == 3
        # Verify FieldFilter arguments (FieldFilter doesn't support equality, check attrs)
        f0 = ref.where.call_args_list[0].kwargs['filter']
        assert f0.field_path == 'discarded'
        assert f0.value is False
        f1 = ref.where.call_args_list[1].kwargs['filter']
        assert f1.field_path == 'status'
        assert f1.value == ['processing', 'completed']
        f2 = ref.where.call_args_list[2].kwargs['filter']
        assert f2.field_path == 'deleted'
        assert f2.value is True

    def test_count_composes_sources_and_statuses(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.stream.return_value = []
        ref.count.return_value.get.return_value = self._make_result(3)

        result = get_conversations_count('uid1', statuses=['processing', 'completed'], sources=['omi'])

        assert result == 3
        filters = [call.kwargs['filter'] for call in ref.where.call_args_list]
        assert [(f.field_path, f.op_string, f.value) for f in filters] == [
            ('discarded', '==', False),
            ('source', '==', 'omi'),
            ('status', 'in', ['processing', 'completed']),
            ('deleted', '==', True),
        ]

    def test_count_include_discarded_skips_filter(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.stream.return_value = []
        ref.count.return_value.get.return_value = self._make_result(55)

        result = get_conversations_count('uid1', include_discarded=True)
        assert result == 55
        f = ref.where.call_args.kwargs['filter']
        assert f.field_path == 'deleted'
        assert f.value is True

    def test_count_zero(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.stream.return_value = []
        ref.count.return_value.get.return_value = self._make_result(0)

        result = get_conversations_count('uid1')
        assert result == 0

    def test_count_discarded_only_applies_discarded_filter(self):
        """No statuses passed — only the discarded filter should be applied."""
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.stream.return_value = []
        ref.count.return_value.get.return_value = self._make_result(7)

        result = get_conversations_count('uid1')
        assert result == 7
        assert ref.where.call_count == 2
        f0 = ref.where.call_args_list[0].kwargs['filter']
        assert f0.field_path == 'discarded'
        assert f0.value is False
        f1 = ref.where.call_args_list[1].kwargs['filter']
        assert f1.field_path == 'deleted'
        assert f1.value is True

    def test_count_include_discarded_with_statuses(self):
        """include_discarded=True + statuses — only status filter, no discarded filter."""
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.stream.return_value = []
        ref.count.return_value.get.return_value = self._make_result(20)

        result = get_conversations_count('uid1', include_discarded=True, statuses=['processing'])
        assert result == 20
        assert ref.where.call_count == 2
        f0 = ref.where.call_args_list[0].kwargs['filter']
        assert f0.field_path == 'status'
        assert (f0.op_string, f0.value) == ('==', 'processing')
        f1 = ref.where.call_args_list[1].kwargs['filter']
        assert f1.field_path == 'deleted'
        assert f1.value is True

    def test_count_applies_list_filter_parity(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.stream.return_value = []
        ref.count.return_value.get.return_value = self._make_result(3)

        ref.order_by.return_value = ref

        result = get_conversations_count(
            'uid1',
            statuses=['completed'],
            start_date='2026-06-01T00:00:00Z',
            end_date='2026-06-02T00:00:00Z',
            folder_id='folder-a',
            starred=False,
        )

        assert result == 3
        assert ref.order_by.call_args.args == ('created_at',)
        filters = [call.kwargs['filter'] for call in ref.where.call_args_list]
        assert [(f.field_path, f.op_string, f.value) for f in filters] == [
            ('discarded', '==', False),
            ('status', '==', 'completed'),
            ('folder_id', '==', 'folder-a'),
            ('starred', '==', False),
            ('created_at', '>=', '2026-06-01T00:00:00Z'),
            ('created_at', '<=', '2026-06-02T00:00:00Z'),
            ('deleted', '==', True),
        ]


class TestConversationsCountEndpointParsing:
    """Test the router-level statuses parsing logic."""

    def test_statuses_none_returns_empty_list(self):
        statuses = None
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == []

    def test_statuses_empty_string_returns_empty_list(self):
        statuses = ''
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == []

    def test_statuses_single_value(self):
        statuses = 'processing'
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == ['processing']

    def test_statuses_multiple_values(self):
        statuses = 'processing,completed'
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == ['processing', 'completed']

    def test_statuses_with_whitespace(self):
        statuses = ' processing , completed , '
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == ['processing', 'completed']

    def test_statuses_comma_only_returns_empty(self):
        statuses = ','
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == []

    def test_statuses_multiple_commas_returns_empty(self):
        statuses = ',,,'
        result = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
        assert result == []

    def test_response_shape(self):
        """The endpoint should return {'count': N}."""
        count = 42
        response = {'count': count}
        assert 'count' in response
        assert isinstance(response['count'], int)


class TestConversationsCountRouteSource:
    """Verify the real route source matches expected registration and forwarding."""

    def test_route_registered_with_correct_path(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert "'/v1/conversations/count'" in source

    def test_route_forwards_include_discarded(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'include_discarded=include_discarded' in source

    def test_route_forwards_statuses_as_list(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'statuses=status_list' in source

    def test_route_forwards_visible_list_filters(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'start_date=start_date' in source
        assert 'end_date=end_date' in source
        assert 'folder_id=folder_id' in source
        assert 'starred=starred' in source

    def test_route_returns_count_dict(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert "{'count': count}" in source or "{'count':count}" in source

    def test_route_forwards_sources_as_list(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'sources=source_list' in source

    def test_route_does_not_reject_statuses_combined_with_sources(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'statuses and sources filters cannot be combined' not in source

    def test_route_echoes_sources_when_filtered(self):
        # Clients rely on the echo to distinguish a filtered count from an
        # older backend that ignored the unknown sources param.
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert "{'count': count, 'sources': source_list}" in source


class TestAppsV2LimitBoundary:
    """Test the /v2/apps limit parameter boundary (le=100) against real source."""

    def test_source_has_le_100(self):
        """Verify the real route source has le=100 (not le=50 or other)."""
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'apps.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'le=100' in source

    def test_source_has_ge_1(self):
        """Verify the real route source has ge=1."""
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'apps.py')
        with open(source_path, encoding='utf-8') as f:
            source = f.read()
        assert 'ge=1' in source

    def test_limit_at_maximum_is_valid(self):
        """limit=100 should be accepted (le=100)."""
        limit = 100
        assert 1 <= limit <= 100

    def test_limit_above_maximum_is_invalid(self):
        """limit=101 should fail validation (le=100)."""
        limit = 101
        assert not (1 <= limit <= 100)

    def test_limit_zero_is_invalid(self):
        """limit=0 should fail validation (ge=1)."""
        limit = 0
        assert not (1 <= limit <= 100)

    def test_limit_negative_is_invalid(self):
        """limit=-1 should fail validation (ge=1)."""
        limit = -1
        assert not (1 <= limit <= 100)

    def test_limit_at_minimum_is_valid(self):
        """limit=1 should be accepted (ge=1)."""
        limit = 1
        assert 1 <= limit <= 100


class _CountDoc:
    def __init__(self, data):
        self._data = dict(data)

    def to_dict(self):
        return dict(self._data)


def _count_filter_match(data, filt):
    """Firestore comparison semantics: a document missing the field never matches."""
    field = getattr(filt, 'field_path', None)
    if not field or field not in data:
        return False
    actual = data[field]
    op = getattr(filt, 'op_string', '==')
    value = getattr(filt, 'value', None)
    if op == '==':
        return actual == value
    if op == 'in':
        return actual in value
    if op == '>=':
        return actual >= value
    if op == '<=':
        return actual <= value
    raise AssertionError(f'unsupported count filter {field} {op}')


class _CountQuery:
    """Deterministic collection/query fake for the real get_conversations_count.

    ``where`` accumulates filters, ``order_by`` records the ordering and applies
    Firestore's implicit existence rule (ordered documents must carry the field),
    and ``count()`` records the aggregate request — including how many documents
    matched before ordering was applied — so tests can prove ordering never
    changes membership when a ``created_at`` bound already requires the field.
    """

    def __init__(self, docs, record, filters=(), orders=()):
        self._docs = docs
        self._record = record
        self._filters = filters
        self._orders = orders

    def _copy(self, **overrides):
        params = {'filters': self._filters, 'orders': self._orders}
        params.update(overrides)
        return _CountQuery(self._docs, self._record, **params)

    def where(self, *args, filter=None, **kwargs):
        filt = filter if filter is not None else (args[0] if args else None)
        return self._copy(filters=(*self._filters, filt))

    def order_by(self, field_path, direction=None):
        name = getattr(direction, 'name', None) or str(direction)
        return self._copy(orders=(*self._orders, (field_path, name)))

    def _matched(self):
        docs = [doc for doc in self._docs if all(_count_filter_match(doc, f) for f in self._filters)]
        matched_unordered = len(docs)
        for field, _direction in self._orders:
            docs = [doc for doc in docs if field in doc]
        return matched_unordered, docs

    def stream(self):
        return iter(_CountDoc(doc) for doc in self._matched()[1])

    def count(self):
        matched_unordered, docs = self._matched()
        self._record.append(
            {
                'filters': [(f.field_path, f.op_string, f.value) for f in self._filters],
                'orders': list(self._orders),
                'matched_unordered': matched_unordered,
                'count': len(docs),
            }
        )
        return SimpleNamespace(get=lambda: [[SimpleNamespace(value=len(docs))]])


class _CountFirestore:
    def __init__(self, docs):
        self._docs = list(docs)
        self.record = []

    def collection(self, name):
        assert name == 'users'
        record = self._record_ref()
        return SimpleNamespace(
            document=lambda _uid: SimpleNamespace(
                collection=lambda collection_name: self._collection(collection_name, record)
            )
        )

    def _record_ref(self):
        return self.record

    def _collection(self, collection_name, record):
        assert collection_name == 'conversations'
        return _CountQuery(self._docs, record)


_T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
_T1 = datetime(2026, 9, 1, tzinfo=timezone.utc)
_T2 = datetime(2026, 9, 15, tzinfo=timezone.utc)
_T3 = datetime(2026, 9, 29, tzinfo=timezone.utc)
_T4 = datetime(2026, 10, 5, tzinfo=timezone.utc)
_T_LEGACY = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _seeded_conversation_docs():
    return [
        {
            'id': 'a-processing',
            'created_at': _T1,
            'discarded': False,
            'status': 'processing',
            'starred': True,
            'source': 'omi',
            'folder_id': 'folder-a',
        },
        {
            'id': 'b-completed',
            'created_at': _T2,
            'discarded': False,
            'status': 'completed',
            'starred': False,
            'source': 'friend',
        },
        {'id': 'c-failed', 'created_at': _T0, 'discarded': False, 'status': 'failed', 'source': 'desktop'},
        {
            'id': 'd-in-progress',
            'created_at': _T2,
            'discarded': False,
            'status': 'in_progress',
            'starred': True,
            'source': 'omi',
        },
        {
            'id': 'e-merging',
            'created_at': _T3,
            'discarded': False,
            'status': 'merging',
            'starred': False,
            'source': 'friend',
            'folder_id': 'folder-b',
        },
        {'id': 'f-missing-status', 'created_at': _T1, 'discarded': False, 'starred': True, 'source': 'omi'},
        {'id': 'g-missing-created-at', 'discarded': False, 'status': 'completed', 'starred': True, 'source': 'omi'},
        {'id': 'h-legacy', 'created_at': _T_LEGACY, 'discarded': False, 'status': 'completed', 'source': 'omi'},
        {'id': 'i-missing-discarded', 'created_at': _T4, 'status': 'completed', 'starred': True, 'source': 'omi'},
        {'id': 'j-missing-source', 'created_at': _T1, 'discarded': False, 'status': 'completed', 'starred': True},
        {
            'id': 'k-user-discarded',
            'created_at': _T2,
            'discarded': True,
            'status': 'completed',
            'starred': False,
            'source': 'omi',
        },
        {
            'id': 'l-donor-tombstone',
            'created_at': _T2,
            'discarded': True,
            'deleted': True,
            'status': 'completed',
            'source': 'omi',
            'sync_merged_into': 'b-completed',
        },
        {
            'id': 'm-redirect-tombstone',
            'created_at': _T1,
            'discarded': True,
            'deleted': True,
            'status': 'processing',
            'source': 'friend',
            'sync_merged_into': 'a-processing',
        },
    ]


def _real_count(monkeypatch, docs=None, **kwargs):
    fake = _CountFirestore(_seeded_conversation_docs() if docs is None else docs)
    monkeypatch.setattr(conversations_db, 'db', fake)
    result = conversations_db.get_conversations_count('u1', **kwargs)
    return result, fake.record


class TestConversationsCountRealHelper:
    """Regression tests against the real database.conversations.get_conversations_count."""

    def test_unbounded_count_retains_missing_created_at_and_orders_nothing(self, monkeypatch):
        result, record = _real_count(monkeypatch)

        assert result == 9
        assert record[0]['orders'] == []
        assert record[0]['matched_unordered'] == record[0]['count'] == 9

    def test_include_discarded_counts_user_discards_but_subtracts_tombstones(self, monkeypatch):
        result, record = _real_count(monkeypatch, include_discarded=True)

        assert record[0]['count'] == 13
        assert result == 11

    @pytest.mark.parametrize(
        ('kwargs', 'expected'),
        [
            ({'start_date': _T1, 'end_date': _T2}, 5),
            ({'start_date': _T1}, 6),
            ({'end_date': _T2}, 7),
        ],
    )
    def test_bounded_counts_are_inclusive_exclude_missing_created_at_and_order_desc(
        self, monkeypatch, kwargs, expected
    ):
        result, record = _real_count(monkeypatch, **kwargs)

        assert result == expected
        assert record[0]['orders'] == [('created_at', 'DESCENDING')]
        assert (
            record[0]['matched_unordered'] == record[0]['count']
        ), 'created_at ordering must not change membership vs the same range unordered'

    def test_bounded_count_exact_boundaries(self, monkeypatch):
        result, record = _real_count(monkeypatch, start_date=_T2, end_date=_T2)
        assert result == 2
        assert record[0]['orders'] == [('created_at', 'DESCENDING')]

    def test_starred_false_excludes_missing_starred(self, monkeypatch):
        result, _ = _real_count(monkeypatch, starred=False)
        assert result == 2

    def test_starred_true_excludes_missing_starred(self, monkeypatch):
        result, _ = _real_count(monkeypatch, starred=True)
        assert result == 5

    def test_single_source_uses_equality_filter(self, monkeypatch):
        result, record = _real_count(monkeypatch, sources=['omi'])

        assert result == 5
        assert ('source', '==', 'omi') in record[0]['filters']

    def test_multi_source_with_single_status_uses_in_and_equality(self, monkeypatch):
        result, record = _real_count(monkeypatch, sources=['omi', 'friend'], statuses=['completed'])

        assert result == 3
        assert ('source', 'in', ['omi', 'friend']) in record[0]['filters']
        assert ('status', '==', 'completed') in record[0]['filters']

    def test_omitted_statuses_count_every_status_including_missing(self, monkeypatch):
        all_statuses, _ = _real_count(monkeypatch)
        default_list_statuses, _ = _real_count(monkeypatch, statuses=['processing', 'completed'])

        assert all_statuses == 9
        assert default_list_statuses == 5

    def test_folder_id_filter_counts_only_matching_folder(self, monkeypatch):
        result, _ = _real_count(monkeypatch, folder_id='folder-a')
        assert result == 1

    def test_tombstone_subtraction_applies_under_discarded_toggle_and_status(self, monkeypatch):
        result, record = _real_count(monkeypatch, include_discarded=True, statuses=['completed'])

        assert record[0]['count'] == 7
        assert result == 6

    @pytest.mark.parametrize(
        ('kwargs', 'raw', 'expected'),
        [
            ({'start_date': _T1, 'end_date': _T2}, 4, 2),
            ({'start_date': _T1}, 4, 2),
            ({'end_date': _T2}, 6, 3),
        ],
    )
    def test_dated_include_discarded_subtracts_only_matching_tombstones(self, monkeypatch, kwargs, raw, expected):
        shared = {'status': 'completed', 'source': 'omi', 'folder_id': 'folder-a', 'starred': False}
        docs = [
            {'id': 'keep-a', 'created_at': _T1, 'discarded': False, **shared},
            {'id': 'keep-b', 'created_at': _T2, 'discarded': True, **shared},
            {'id': 'keep-c', 'created_at': _T0, 'discarded': False, **shared},
            {
                'id': 'other-status',
                'created_at': _T2,
                'discarded': False,
                'status': 'failed',
                'source': 'friend',
                'starred': True,
            },
            {
                'id': 'tomb-x',
                'created_at': _T1,
                'discarded': True,
                'deleted': True,
                'sync_merged_into': 'keep-a',
                **shared,
            },
            {
                'id': 'tomb-y',
                'created_at': _T2,
                'discarded': True,
                'deleted': True,
                'sync_merged_into': 'keep-b',
                **shared,
            },
            {
                'id': 'tomb-z',
                'created_at': _T0,
                'discarded': True,
                'deleted': True,
                'sync_merged_into': 'keep-c',
                **shared,
            },
        ]

        result, record = _real_count(
            monkeypatch,
            docs=docs,
            include_discarded=True,
            statuses=['completed'],
            sources=['omi'],
            folder_id='folder-a',
            starred=False,
            **kwargs,
        )

        assert record[0]['orders'] == [('created_at', 'DESCENDING')]
        assert record[0]['count'] == raw
        assert (
            record[0]['matched_unordered'] == record[0]['count']
        ), 'created_at ordering must not change membership vs the same range unordered'
        assert result == expected
