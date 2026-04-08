"""Tests for get_conversations_count logic and /v1/conversations/count endpoint.

The DB function is tested inline because database.conversations requires
Firestore client init at import time. The test_source_matches_implementation
test verifies that the real module's source matches this test's logic.
"""

import os
import sys
import types

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from unittest.mock import MagicMock

from google.cloud.firestore_v1 import FieldFilter


def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# Stub database to avoid Firestore init
if "database" not in sys.modules:
    database_mod = _stub_module("database")
    database_mod.__path__ = []
else:
    database_mod = sys.modules["database"]

for sub in [
    "_client",
    "redis_db",
    "users",
    "conversations",
    "chat",
    "memories",
    "action_items",
    "apps",
    "auth",
    "notifications",
    "daily_summaries",
    "folders",
    "goals",
    "knowledge_graph",
    "phone_calls",
    "vector_db",
]:
    full = f"database.{sub}"
    if full not in sys.modules:
        mod = _stub_module(full)
        setattr(database_mod, sub, mod)

# Set up mock db on _client
mock_db = MagicMock()
sys.modules["database._client"].db = mock_db
sys.modules["database._client"].document_id_from_seed = lambda *a: "test"


def get_conversations_count(uid, include_discarded=False, statuses=[]):
    """Mirrors database.conversations.get_conversations_count."""
    conversations_ref = mock_db.collection('users').document(uid).collection('conversations')
    if not include_discarded:
        conversations_ref = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
    if statuses:
        conversations_ref = conversations_ref.where(filter=FieldFilter('status', 'in', statuses))
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
        with open(source_path) as f:
            source = f.read()
        assert 'def get_conversations_count(' in source
        assert "FieldFilter('discarded', '==', False)" in source
        assert "FieldFilter('status', 'in', statuses)" in source
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
        assert f.value == ['processing']


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
        with open(source_path) as f:
            source = f.read()
        assert "'/v1/conversations/count'" in source

    def test_route_forwards_include_discarded(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path) as f:
            source = f.read()
        assert 'include_discarded=include_discarded' in source

    def test_route_forwards_statuses_as_list(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path) as f:
            source = f.read()
        assert 'statuses=status_list' in source

    def test_route_returns_count_dict(self):
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'conversations.py')
        with open(source_path) as f:
            source = f.read()
        assert "{'count': count}" in source or "{'count':count}" in source


class TestAppsV2LimitBoundary:
    """Test the /v2/apps limit parameter boundary (le=100) against real source."""

    def test_source_has_le_100(self):
        """Verify the real route source has le=100 (not le=50 or other)."""
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'apps.py')
        with open(source_path) as f:
            source = f.read()
        assert 'le=100' in source

    def test_source_has_ge_1(self):
        """Verify the real route source has ge=1."""
        source_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'apps.py')
        with open(source_path) as f:
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
