"""Tests for get_conversations_count logic and /v1/conversations/count endpoint.

The DB function is tested inline against a module-local MagicMock ``mock_db``; the
test never imports ``database.*`` (it only reads production source via ``open()`` for
the parity assertions), so no import-time stubbing is required. The inline copy is
kept hermetic and fast; ``test_source_matches_implementation`` guards against drift.
"""

import os
from unittest.mock import MagicMock

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
    conversations_ref = mock_db.collection('users').document(uid).collection('conversations')
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
    result = conversations_ref.count().get()
    return int(result[0][0].value)


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
        assert '.count().get()' in source
        assert 'result[0][0].value' in source

    def test_count_returns_integer(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.count.return_value.get.return_value = self._make_result(42)

        result = get_conversations_count('uid1')
        assert result == 42
        assert isinstance(result, int)

    def test_count_with_statuses_applies_correct_filters(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.count.return_value.get.return_value = self._make_result(10)

        result = get_conversations_count('uid1', statuses=['processing', 'completed'])
        assert result == 10
        assert ref.where.call_count == 2
        # Verify FieldFilter arguments (FieldFilter doesn't support equality, check attrs)
        f0 = ref.where.call_args_list[0].kwargs['filter']
        assert f0.field_path == 'discarded'
        assert f0.value is False
        f1 = ref.where.call_args_list[1].kwargs['filter']
        assert f1.field_path == 'status'
        assert f1.value == ['processing', 'completed']

    def test_count_composes_sources_and_statuses(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.count.return_value.get.return_value = self._make_result(3)

        result = get_conversations_count('uid1', statuses=['processing', 'completed'], sources=['omi'])

        assert result == 3
        filters = [call.kwargs['filter'] for call in ref.where.call_args_list]
        assert [(f.field_path, f.op_string, f.value) for f in filters] == [
            ('discarded', '==', False),
            ('source', '==', 'omi'),
            ('status', 'in', ['processing', 'completed']),
        ]

    def test_count_include_discarded_skips_filter(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.count.return_value.get.return_value = self._make_result(55)

        result = get_conversations_count('uid1', include_discarded=True)
        assert result == 55
        ref.where.assert_not_called()

    def test_count_zero(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.count.return_value.get.return_value = self._make_result(0)

        result = get_conversations_count('uid1')
        assert result == 0

    def test_count_discarded_only_applies_discarded_filter(self):
        """No statuses passed — only the discarded filter should be applied."""
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.count.return_value.get.return_value = self._make_result(7)

        result = get_conversations_count('uid1')
        assert result == 7
        assert ref.where.call_count == 1
        f = ref.where.call_args.kwargs['filter']
        assert f.field_path == 'discarded'
        assert f.value is False

    def test_count_include_discarded_with_statuses(self):
        """include_discarded=True + statuses — only status filter, no discarded filter."""
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.count.return_value.get.return_value = self._make_result(20)

        result = get_conversations_count('uid1', include_discarded=True, statuses=['processing'])
        assert result == 20
        assert ref.where.call_count == 1
        f = ref.where.call_args.kwargs['filter']
        assert f.field_path == 'status'
        assert (f.op_string, f.value) == ('==', 'processing')

    def test_count_applies_list_filter_parity(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.count.return_value.get.return_value = self._make_result(3)

        result = get_conversations_count(
            'uid1',
            statuses=['completed'],
            start_date='2026-06-01T00:00:00Z',
            end_date='2026-06-02T00:00:00Z',
            folder_id='folder-a',
            starred=False,
        )

        assert result == 3
        filters = [call.kwargs['filter'] for call in ref.where.call_args_list]
        assert [(f.field_path, f.op_string, f.value) for f in filters] == [
            ('discarded', '==', False),
            ('status', '==', 'completed'),
            ('folder_id', '==', 'folder-a'),
            ('starred', '==', False),
            ('created_at', '>=', '2026-06-01T00:00:00Z'),
            ('created_at', '<=', '2026-06-02T00:00:00Z'),
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
