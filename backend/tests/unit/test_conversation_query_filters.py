"""Tests for Firestore query filter logic in get_conversations / get_conversations_without_photos.

Verifies:
1. Single-element 'in' lists are converted to '==' (Firestore optimization)
2. Dual 'in' filters are avoided (Firestore limitation: max one 'in' per query)
3. FailedPrecondition fallback handles missing composite indexes gracefully
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from google.api_core.exceptions import FailedPrecondition
from google.cloud.firestore_v1 import FieldFilter


class FakeQuery:
    """Tracks chained .where() and .order_by() calls to verify filter construction."""

    def __init__(self, stream_result=None, should_fail=False):
        self.filters = []
        self.order_by_fields = []
        self._limit = None
        self._offset = None
        self._stream_result = stream_result or []
        self._should_fail = should_fail

    def where(self, filter=None):
        self.filters.append(filter)
        return self

    def order_by(self, field, direction=None):
        self.order_by_fields.append((field, direction))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def offset(self, n):
        self._offset = n
        return self

    def stream(self):
        if self._should_fail:
            raise FailedPrecondition("The query requires an index")
        return self._stream_result


class FakeDoc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


def _get_filter_ops(fake_query):
    """Extract (field_path, op_string, value) from FieldFilter objects."""
    ops = []
    for f in fake_query.filters:
        if isinstance(f, FieldFilter):
            ops.append((f.field_path, f.op_string, f.value))
    return ops


def _build_query_for(uid, fake_query, mock_db):
    """Wire up mock_db to return fake_query for the conversations subcollection."""
    mock_db.collection.return_value.document.return_value.collection.return_value = fake_query


def _import_conversations():
    """Import the conversations module with mocked Firestore client."""
    # Remove cached module so it re-imports with our mock
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith('database.conversations'):
            del sys.modules[mod_name]

    import database.conversations as conv_mod

    return conv_mod


class TestConversationQueryFilters(unittest.TestCase):
    """Verify get_conversations builds correct Firestore queries."""

    def setUp(self):
        """Import conversations module (relies on conftest or env for db mock)."""
        # We access the module-level db object which is already initialized
        import database.conversations as conv_mod

        self.conv_mod = conv_mod
        self.original_db = conv_mod.db

    def tearDown(self):
        self.conv_mod.db = self.original_db

    def _run_get_conversations_without_photos(self, mock_db, fake_query, **kwargs):
        """Run get_conversations_without_photos with mocked db, bypassing decorators."""
        self.conv_mod.db = mock_db
        _build_query_for('uid123', fake_query, mock_db)

        # Access the unwrapped function (underneath @prepare_for_read decorator)
        fn = self.conv_mod.get_conversations_without_photos.__wrapped__
        return fn('uid123', **kwargs)

    def test_single_status_uses_equality_not_in(self):
        """Single-element statuses list should use '==' instead of 'in'."""
        mock_db = MagicMock()
        fake_query = FakeQuery()
        _build_query_for('uid123', fake_query, mock_db)
        self.conv_mod.db = mock_db

        fn = self.conv_mod.get_conversations_without_photos.__wrapped__
        fn('uid123', statuses=['completed'])

        ops = _get_filter_ops(fake_query)
        status_ops = [(f, o, v) for f, o, v in ops if f == 'status']
        self.assertEqual(len(status_ops), 1)
        self.assertEqual(status_ops[0][1], '==', "Single status should use '==' not 'in'")
        self.assertEqual(status_ops[0][2], 'completed')

    def test_multiple_statuses_uses_in(self):
        """Multi-element statuses list should use 'in'."""
        mock_db = MagicMock()
        fake_query = FakeQuery()
        _build_query_for('uid123', fake_query, mock_db)
        self.conv_mod.db = mock_db

        fn = self.conv_mod.get_conversations_without_photos.__wrapped__
        fn('uid123', statuses=['completed', 'in_progress'])

        ops = _get_filter_ops(fake_query)
        status_ops = [(f, o, v) for f, o, v in ops if f == 'status']
        self.assertEqual(len(status_ops), 1)
        self.assertEqual(status_ops[0][1], 'in')

    def test_single_category_uses_equality(self):
        """Single-element categories list should use '==' instead of 'in'."""
        mock_db = MagicMock()
        fake_query = FakeQuery()
        _build_query_for('uid123', fake_query, mock_db)
        self.conv_mod.db = mock_db

        fn = self.conv_mod.get_conversations_without_photos.__wrapped__
        fn('uid123', categories=['science'])

        ops = _get_filter_ops(fake_query)
        cat_ops = [(f, o, v) for f, o, v in ops if f == 'structured.category']
        self.assertEqual(len(cat_ops), 1)
        self.assertEqual(cat_ops[0][1], '==')

    def test_dual_in_avoided_categories_filtered_client_side(self):
        """When both statuses and categories need 'in', categories should not appear in Firestore query."""
        mock_db = MagicMock()
        fake_query = FakeQuery(
            stream_result=[
                FakeDoc({'id': '1', 'structured': {'category': 'science'}, 'status': 'completed'}),
                FakeDoc({'id': '2', 'structured': {'category': 'health'}, 'status': 'completed'}),
                FakeDoc({'id': '3', 'structured': {'category': 'other'}, 'status': 'in_progress'}),
            ]
        )
        _build_query_for('uid123', fake_query, mock_db)
        self.conv_mod.db = mock_db

        fn = self.conv_mod.get_conversations_without_photos.__wrapped__
        result = fn(
            'uid123',
            statuses=['completed', 'in_progress'],
            categories=['science', 'health'],
        )

        # Verify no 'structured.category' filter in Firestore query
        ops = _get_filter_ops(fake_query)
        cat_ops = [o for f, o, v in ops if f == 'structured.category']
        self.assertEqual(len(cat_ops), 0, "Categories should be filtered client-side when statuses uses 'in'")

        # Only docs with matching categories should be returned
        self.assertEqual(len(result), 2)
        returned_ids = {r['id'] for r in result}
        self.assertEqual(returned_ids, {'1', '2'})

    def test_mcp_sse_query_pattern(self):
        """Simulate the exact MCP SSE call pattern: statuses=["completed"] + categories."""
        mock_db = MagicMock()
        fake_query = FakeQuery(
            stream_result=[
                FakeDoc({'id': '1', 'structured': {'category': 'science'}, 'status': 'completed'}),
            ]
        )
        _build_query_for('uid123', fake_query, mock_db)
        self.conv_mod.db = mock_db

        fn = self.conv_mod.get_conversations_without_photos.__wrapped__
        fn(
            'uid123',
            limit=20,
            offset=0,
            include_discarded=False,
            statuses=['completed'],
            categories=['science', 'health'],
        )

        ops = _get_filter_ops(fake_query)
        # status should use '==' (single element), categories should use 'in' (multi element)
        status_ops = [(f, o, v) for f, o, v in ops if f == 'status']
        cat_ops = [(f, o, v) for f, o, v in ops if f == 'structured.category']
        self.assertEqual(status_ops[0][1], '==', "Single status should use '=='")
        self.assertEqual(cat_ops[0][1], 'in', "Multi categories should use 'in' since status freed the slot")

    def test_failed_precondition_fallback(self):
        """FailedPrecondition should trigger client-side fallback, not crash."""
        mock_db = MagicMock()

        # First query fails with FailedPrecondition
        failing_query = FakeQuery(should_fail=True)

        # Fallback query succeeds
        fallback_query = FakeQuery(
            stream_result=[
                FakeDoc(
                    {
                        'id': '1',
                        'discarded': False,
                        'status': 'completed',
                        'structured': {'category': 'science'},
                        'created_at': datetime(2026, 1, 1),
                    }
                ),
                FakeDoc(
                    {
                        'id': '2',
                        'discarded': True,
                        'status': 'completed',
                        'structured': {'category': 'science'},
                        'created_at': datetime(2026, 1, 2),
                    }
                ),
            ]
        )

        # First call returns failing_query, second call returns fallback_query
        call_count = [0]

        def fake_collection(name):
            call_count[0] += 1
            mock_chain = MagicMock()
            if call_count[0] <= 1:
                mock_chain.document.return_value.collection.return_value = failing_query
            else:
                mock_chain.document.return_value.collection.return_value = fallback_query
            return mock_chain

        mock_db.collection.side_effect = fake_collection
        self.conv_mod.db = mock_db

        fn = self.conv_mod.get_conversations_without_photos.__wrapped__
        result = fn(
            'uid123',
            include_discarded=False,
            statuses=['completed'],
            categories=['science'],
        )

        # Should return only non-discarded conversations
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], '1')


if __name__ == '__main__':
    unittest.main()
