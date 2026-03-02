"""
Tests for MCP and developer router lite/full conversation routing.
Imports the REAL router functions via module stubbing to avoid Firestore init.
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
    "dev_api_key",
    "goals",
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
    "utils.scopes",
    "dependencies",
]:
    _ensure_mock_module(name)

# Force reimport
for mod_name in list(sys.modules.keys()):
    if mod_name.startswith("routers.mcp") or mod_name.startswith("routers.developer"):
        del sys.modules[mod_name]

from routers.mcp import get_conversations as mcp_get_conversations  # noqa: E402
from routers.developer import get_conversations as dev_get_conversations  # noqa: E402


class TestMcpConversationsLite:
    @patch('routers.mcp.conversations_db')
    def test_mcp_list_uses_lite(self, mock_db):
        """MCP list endpoint always uses get_conversations_lite."""
        mock_db.get_conversations_lite.return_value = []

        mcp_get_conversations(uid='test_uid')

        mock_db.get_conversations_lite.assert_called_once()
        mock_db.get_conversations.assert_not_called()


class TestDeveloperConversationsLite:
    @patch('routers.developer.users_db')
    @patch('routers.developer.conversations_db')
    def test_include_transcript_false_uses_lite(self, mock_db, mock_users):
        """Developer endpoint with include_transcript=False uses lite."""
        mock_db.get_conversations_lite.return_value = []

        dev_get_conversations(
            uid='test_uid',
            limit=25,
            offset=0,
            include_transcript=False,
            start_date=None,
            end_date=None,
            categories='',
        )

        mock_db.get_conversations_lite.assert_called_once()
        mock_db.get_conversations.assert_not_called()

    @patch('routers.developer.users_db')
    @patch('routers.developer.conversations_db')
    def test_include_transcript_true_uses_full(self, mock_db, mock_users):
        """Developer endpoint with include_transcript=True uses full get_conversations."""
        mock_db.get_conversations.return_value = [{'id': 'c1', 'is_locked': False, 'transcript_segments': []}]
        mock_users.get_user_profile.return_value = {'name': 'Test'}
        mock_users.get_people_by_ids.return_value = []

        dev_get_conversations(
            uid='test_uid',
            limit=25,
            offset=0,
            include_transcript=True,
            start_date=None,
            end_date=None,
            categories='',
        )

        mock_db.get_conversations.assert_called_once()
        mock_db.get_conversations_lite.assert_not_called()

    @patch('routers.developer.users_db')
    @patch('routers.developer.conversations_db')
    def test_include_transcript_false_no_speaker_enrichment(self, mock_db, mock_users):
        """Developer endpoint with include_transcript=False skips speaker enrichment."""
        mock_db.get_conversations_lite.return_value = [{'id': 'c1', 'is_locked': False}]

        dev_get_conversations(
            uid='test_uid',
            limit=25,
            offset=0,
            include_transcript=False,
            start_date=None,
            end_date=None,
            categories='',
        )

        # _add_speaker_names_to_segments calls users_db.get_user_profile
        mock_users.get_user_profile.assert_not_called()
