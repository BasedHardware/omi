"""
Tests for the limit-based branching in GET /v1/conversations.
limit=1 uses full get_conversations() (in-progress recovery needs transcripts).
limit>1 uses get_conversations_lite() (list view optimization).
Imports the REAL router function via module stubbing to avoid Firestore init.
"""

import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _ensure_mock_module(name: str):
    """Ensure a MagicMock module exists in sys.modules."""
    if name not in sys.modules:
        mod = MagicMock()
        mod.__path__ = []
        mod.__name__ = name
        mod.__loader__ = None
        mod.__spec__ = None
        mod.__package__ = name if '.' not in name else name.rsplit('.', 1)[0]
        sys.modules[name] = mod
    return sys.modules[name]


# Stub database and utility modules to avoid Firestore init
_ensure_mock_module("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], '__path__', [])
for sub in [
    "_client",
    "redis_db",
    "auth",
    "users",
    "memories",
    "conversations",
    "apps",
    "vector_db",
    "action_items",
    "mcp_api_key",
]:
    _ensure_mock_module(f"database.{sub}")

for name in [
    "utils",
    "utils.apps",
    "utils.llm",
    "utils.llm.memories",
    "utils.conversations",
    "utils.conversations.process_conversation",
    "utils.conversations.search",
    "utils.conversations.location",
    "utils.llm.conversation_processing",
    "utils.llm.external_integrations",
    "utils.notifications",
    "utils.webhooks",
    "utils.retrieval",
    "utils.retrieval.rag",
    "utils.other",
    "utils.other.hume",
    "utils.other.endpoints",
    "utils.other.storage",
    "utils.encryption",
    "utils.speaker_identification",
    "utils.app_integrations",
    "dependencies",
]:
    _ensure_mock_module(name)

# Force reimport so routers.conversations picks up stubs
if "routers.conversations" in sys.modules:
    del sys.modules["routers.conversations"]

from routers.conversations import get_conversations  # noqa: E402


class TestConversationsRouterBranching:
    @patch('routers.conversations.conversations_db')
    def test_limit_1_uses_full_hydration(self, mock_db):
        """limit=1 calls get_conversations() for in-progress recovery (needs transcripts)."""
        mock_db.get_conversations.return_value = [{'id': 'c1', 'is_locked': False}]

        result = get_conversations(
            limit=1,
            offset=0,
            statuses="in_progress",
            include_discarded=False,
            start_date=None,
            end_date=None,
            folder_id=None,
            starred=None,
            uid='test_uid',
        )

        mock_db.get_conversations.assert_called_once()
        mock_db.get_conversations_lite.assert_not_called()
        assert len(result) == 1

    @patch('routers.conversations.conversations_db')
    def test_limit_2_uses_lite(self, mock_db):
        """limit=2 calls get_conversations_lite() (list optimization)."""
        mock_db.get_conversations_lite.return_value = [
            {'id': 'c1', 'is_locked': False},
            {'id': 'c2', 'is_locked': False},
        ]

        result = get_conversations(
            limit=2,
            offset=0,
            statuses="completed",
            include_discarded=False,
            start_date=None,
            end_date=None,
            folder_id=None,
            starred=None,
            uid='test_uid',
        )

        mock_db.get_conversations_lite.assert_called_once()
        mock_db.get_conversations.assert_not_called()
        assert len(result) == 2

    @patch('routers.conversations.conversations_db')
    def test_limit_100_uses_lite(self, mock_db):
        """limit=100 (default) uses lite path."""
        mock_db.get_conversations_lite.return_value = []

        get_conversations(
            limit=100,
            offset=0,
            statuses="completed",
            include_discarded=False,
            start_date=None,
            end_date=None,
            folder_id=None,
            starred=None,
            uid='test_uid',
        )

        mock_db.get_conversations_lite.assert_called_once()
        mock_db.get_conversations.assert_not_called()

    @patch('routers.conversations.conversations_db')
    def test_empty_statuses_defaults_to_processing_completed(self, mock_db):
        """Empty statuses string defaults to 'processing,completed'."""
        mock_db.get_conversations_lite.return_value = []

        get_conversations(
            limit=25,
            offset=0,
            statuses="",
            include_discarded=False,
            start_date=None,
            end_date=None,
            folder_id=None,
            starred=None,
            uid='test_uid',
        )

        call_kwargs = mock_db.get_conversations_lite.call_args
        assert call_kwargs[1]['statuses'] == ['processing', 'completed']

    @patch('routers.conversations.conversations_db')
    def test_locked_conversations_stripped(self, mock_db):
        """Locked conversations have sensitive fields stripped."""
        mock_db.get_conversations_lite.return_value = [
            {
                'id': 'c1',
                'is_locked': True,
                'structured': {'action_items': ['item1'], 'events': ['ev1']},
                'apps_results': ['app1'],
                'plugins_results': ['plug1'],
                'suggested_summarization_apps': ['sum1'],
            },
        ]

        result = get_conversations(
            limit=10,
            offset=0,
            statuses="completed",
            include_discarded=False,
            start_date=None,
            end_date=None,
            folder_id=None,
            starred=None,
            uid='test_uid',
        )

        assert result[0]['structured']['action_items'] == []
        assert result[0]['structured']['events'] == []
        assert result[0]['apps_results'] == []
        assert result[0]['plugins_results'] == []
        assert result[0]['suggested_summarization_apps'] == []
