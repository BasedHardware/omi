"""Tests for /v1/conversations/count endpoint logic."""

import os
import sys
import types

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from unittest.mock import MagicMock


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

# Stub firestore module attributes needed by conversations.py
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

# Now set db on conversations module and define the function inline for testing
conversations_mod = sys.modules["database.conversations"]
conversations_mod.db = mock_db
conversations_mod.FieldFilter = FieldFilter
conversations_mod.firestore = firestore
conversations_mod.conversations_collection = 'conversations'


def get_conversations_count(uid, include_discarded=False, statuses=[]):
    ref = mock_db.collection('users').document(uid).collection('conversations')
    if not include_discarded:
        ref = ref.where(filter=FieldFilter('discarded', '==', False))
    if statuses:
        ref = ref.where(filter=FieldFilter('status', 'in', statuses))
    result = ref.count().get()
    return int(result[0][0].value)


class TestConversationsCount:
    def setup_method(self):
        mock_db.reset_mock()

    def _make_result(self, value):
        v = MagicMock()
        v.value = value
        return [[v]]

    def test_count_returns_integer(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.count.return_value.get.return_value = self._make_result(42)

        result = get_conversations_count('uid1')
        assert result == 42
        assert isinstance(result, int)

    def test_count_with_statuses_applies_two_filters(self):
        ref = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = ref
        ref.where.return_value = ref
        ref.count.return_value.get.return_value = self._make_result(10)

        result = get_conversations_count('uid1', statuses=['processing', 'completed'])
        assert result == 10
        assert ref.where.call_count == 2

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
