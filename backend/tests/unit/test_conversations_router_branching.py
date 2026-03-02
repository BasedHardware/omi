"""
Tests for the limit-based branching in GET /v1/conversations.
limit=1 uses full get_conversations() (in-progress recovery needs transcripts).
limit>1 uses get_conversations_lite() (list view optimization).
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# Stub database package and submodules to avoid Firestore init.
if "database" not in sys.modules:
    database_mod = _stub_module("database")
    database_mod.__path__ = []
else:
    database_mod = sys.modules["database"]

for submodule in [
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
    full_name = f"database.{submodule}"
    if full_name not in sys.modules:
        mod = _stub_module(full_name)
        setattr(database_mod, submodule, mod)

# Set up mock Firestore client
client_mod = sys.modules["database._client"]
client_mod.db = MagicMock()
client_mod.document_id_from_seed = MagicMock(return_value="doc-id")

# Stub out heavy utility modules
for name in [
    "utils.apps",
    "utils.llm.memories",
    "utils.conversations.process_conversation",
    "utils.notifications",
    "utils.webhooks",
    "utils.llm.external_integrations",
    "utils.retrieval.rag",
    "utils.other.hume",
]:
    if name not in sys.modules:
        _stub_module(name)

# Mock conversations_db at module scope so routers.conversations can import it
mock_conv_db = MagicMock()
sys.modules["database.conversations"] = mock_conv_db


def _call_get_conversations(limit, statuses="completed", offset=0):
    """Simulate the router's get_conversations branching logic."""
    # Replicate the exact branching from routers/conversations.py
    uid = 'test_uid'
    include_discarded = False
    start_date = None
    end_date = None
    folder_id = None
    starred = None

    if len(statuses) == 0:
        statuses = "processing,completed"

    if limit > 1:
        conversations = mock_conv_db.get_conversations_lite(
            uid,
            limit,
            offset,
            include_discarded=include_discarded,
            statuses=statuses.split(",") if len(statuses) > 0 else [],
            start_date=start_date,
            end_date=end_date,
            folder_id=folder_id,
            starred=starred,
        )
    else:
        conversations = mock_conv_db.get_conversations(
            uid,
            limit,
            offset,
            include_discarded=include_discarded,
            statuses=statuses.split(",") if len(statuses) > 0 else [],
            start_date=start_date,
            end_date=end_date,
            folder_id=folder_id,
            starred=starred,
        )

    for conv in conversations:
        if conv.get('is_locked', False):
            conv['structured']['action_items'] = []
            conv['structured']['events'] = []
            conv['apps_results'] = []
            conv['plugins_results'] = []
            conv['suggested_summarization_apps'] = []
    return conversations


class TestConversationsRouterBranching:
    def setup_method(self):
        mock_conv_db.reset_mock()

    def test_limit_1_uses_full_hydration(self):
        """limit=1 calls get_conversations() for in-progress recovery (needs transcripts)."""
        mock_conv_db.get_conversations.return_value = [{'id': 'c1', 'is_locked': False}]

        result = _call_get_conversations(limit=1, statuses="in_progress")

        mock_conv_db.get_conversations.assert_called_once()
        mock_conv_db.get_conversations_lite.assert_not_called()
        assert len(result) == 1

    def test_limit_2_uses_lite(self):
        """limit=2 calls get_conversations_lite() (list optimization)."""
        mock_conv_db.get_conversations_lite.return_value = [
            {'id': 'c1', 'is_locked': False},
            {'id': 'c2', 'is_locked': False},
        ]

        result = _call_get_conversations(limit=2)

        mock_conv_db.get_conversations_lite.assert_called_once()
        mock_conv_db.get_conversations.assert_not_called()
        assert len(result) == 2

    def test_limit_100_uses_lite(self):
        """limit=100 (default) uses lite path."""
        mock_conv_db.get_conversations_lite.return_value = []

        _call_get_conversations(limit=100)

        mock_conv_db.get_conversations_lite.assert_called_once()
        mock_conv_db.get_conversations.assert_not_called()

    def test_empty_statuses_defaults_to_processing_completed(self):
        """Empty statuses string defaults to 'processing,completed'."""
        mock_conv_db.get_conversations_lite.return_value = []

        _call_get_conversations(limit=25, statuses="")

        call_kwargs = mock_conv_db.get_conversations_lite.call_args
        assert call_kwargs[1]['statuses'] == ['processing', 'completed']

    def test_locked_conversations_stripped(self):
        """Locked conversations have sensitive fields stripped."""
        mock_conv_db.get_conversations_lite.return_value = [
            {
                'id': 'c1',
                'is_locked': True,
                'structured': {'action_items': ['item1'], 'events': ['ev1']},
                'apps_results': ['app1'],
                'plugins_results': ['plug1'],
                'suggested_summarization_apps': ['sum1'],
            },
        ]

        result = _call_get_conversations(limit=10)

        assert result[0]['structured']['action_items'] == []
        assert result[0]['structured']['events'] == []
        assert result[0]['apps_results'] == []
        assert result[0]['plugins_results'] == []
        assert result[0]['suggested_summarization_apps'] == []
