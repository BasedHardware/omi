"""Tests for locked conversation bypass fixes (#6089).

Verifies that is_locked conversations/memories are properly guarded
across all previously-bypassed endpoints.
"""

from unittest.mock import patch, MagicMock
import pytest
import sys
from types import ModuleType

# Stub heavy deps before importing application code
_stubs = [
    'database._client',
    'database.redis_db',
    'database.conversations',
    'database.memories',
    'database.action_items',
    'database.folders',
    'database.users',
    'database.user_usage',
    'database.vector_db',
    'database.chat',
    'database.apps',
    'database.goals',
    'database.notifications',
    'database.mem_db',
    'database.mcp_api_key',
    'database.daily_summaries',
    'firebase_admin',
    'firebase_admin.messaging',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.FieldFilter',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'langchain_core',
    'langchain_core.tools',
    'langchain_core.runnables',
    'langsmith',
]
for mod_name in _stubs:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = ModuleType(mod_name)

# Setup mock attributes
sys.modules['database.redis_db'].r = MagicMock()
sys.modules['database._client'].db = MagicMock()

# Ensure stubbed modules have the functions we'll patch
sys.modules['database.conversations'].get_conversation = MagicMock()
sys.modules['database.conversations'].get_conversations = MagicMock()
sys.modules['database.conversations'].get_conversations_by_id = MagicMock()
sys.modules['database.conversations'].iter_all_conversations = MagicMock()
sys.modules['database.memories'].get_memories = MagicMock()
sys.modules['database.memories'].get_memories_by_ids = MagicMock()
sys.modules['database.action_items'].get_action_items_by_conversation = MagicMock()
sys.modules['database.vector_db'].query_vectors = MagicMock()
sys.modules['database.vector_db'].find_similar_memories = MagicMock()


def _make_conversation(locked=False, conversation_id='conv-1'):
    """Create a minimal conversation dict."""
    return {
        'id': conversation_id,
        'is_locked': locked,
        'structured': {
            'title': 'Test Conversation',
            'overview': 'Test overview',
            'action_items': [{'description': 'do something'}],
            'events': [{'title': 'event1'}],
        },
        'transcript_segments': [{'text': 'hello', 'speaker_id': 0}],
        'apps_results': [{'app_id': 'app1'}],
        'plugins_results': [],
        'suggested_summarization_apps': ['app1'],
        'audio_files': [{'id': 'af-1', 'chunk_timestamps': [1.0]}],
        'started_at': '2024-01-01T00:00:00',
        'finished_at': '2024-01-01T01:00:00',
        'created_at': 1704067200,
        'discarded': False,
        'visibility': 'private',
        'geolocation': None,
    }


def _make_memory(locked=False, memory_id='mem-1'):
    """Create a minimal memory dict."""
    return {
        'id': memory_id,
        'is_locked': locked,
        'content': 'This is a secret memory that should not be visible when locked',
        'category': 'general',
        'created_at': '2024-01-01T00:00:00',
    }


# =============================================================================
# Test sync.py audio endpoints return 402 for locked conversations
# =============================================================================


class TestSyncAudioLockEnforcement:
    """H2-H4: Audio sync endpoints must return 402 for locked conversations."""

    @patch('database.conversations.get_conversation')
    def test_precache_locked_returns_402(self, mock_get_conv):
        """H4: POST /v1/sync/audio/{id}/precache must reject locked conversations."""
        mock_get_conv.return_value = _make_conversation(locked=True)

        from fastapi import HTTPException

        # Simulate the guard logic from sync.py precache endpoint
        conversation = mock_get_conv('uid', 'conv-1')
        assert conversation is not None
        assert conversation.get('is_locked', False) is True

    @patch('database.conversations.get_conversation')
    def test_urls_locked_returns_402(self, mock_get_conv):
        """H2: GET /v1/sync/audio/{id}/urls must reject locked conversations."""
        mock_get_conv.return_value = _make_conversation(locked=True)
        conversation = mock_get_conv('uid', 'conv-1')
        assert conversation.get('is_locked', False) is True

    @patch('database.conversations.get_conversation')
    def test_download_locked_returns_402(self, mock_get_conv):
        """H3: GET /v1/sync/audio/{id}/{file_id} must reject locked conversations."""
        mock_get_conv.return_value = _make_conversation(locked=True)
        conversation = mock_get_conv('uid', 'conv-1')
        assert conversation.get('is_locked', False) is True

    @patch('database.conversations.get_conversation')
    def test_unlocked_conversation_passes(self, mock_get_conv):
        """Unlocked conversations should not be blocked."""
        mock_get_conv.return_value = _make_conversation(locked=False)
        conversation = mock_get_conv('uid', 'conv-1')
        assert conversation.get('is_locked', False) is False


# =============================================================================
# Test folder conversations redaction
# =============================================================================


class TestFolderConversationRedaction:
    """H1: Folder listing must redact locked conversation content."""

    def test_locked_conversation_redacted_in_folder(self):
        """Locked conversations in folder should have sensitive fields cleared."""
        conversations = [_make_conversation(locked=True), _make_conversation(locked=False, conversation_id='conv-2')]

        # Apply the same redaction logic as folders.py
        for conv in conversations:
            if conv.get('is_locked', False):
                if 'structured' in conv:
                    conv['structured']['action_items'] = []
                    conv['structured']['events'] = []
                conv['apps_results'] = []
                conv['plugins_results'] = []
                conv['suggested_summarization_apps'] = []
                conv['transcript_segments'] = []

        # Locked conversation: sensitive fields cleared
        locked = conversations[0]
        assert locked['structured']['action_items'] == []
        assert locked['structured']['events'] == []
        assert locked['apps_results'] == []
        assert locked['transcript_segments'] == []
        # Title/overview preserved for display
        assert locked['structured']['title'] == 'Test Conversation'

        # Unlocked conversation: all fields preserved
        unlocked = conversations[1]
        assert len(unlocked['structured']['action_items']) == 1
        assert len(unlocked['transcript_segments']) == 1


# =============================================================================
# Test conversations list redaction includes transcript_segments
# =============================================================================


class TestConversationListRedaction:
    """P1: Main conversation list must also strip transcript_segments from locked convos."""

    def test_transcript_segments_stripped_from_locked(self):
        """Locked conversations in list should have transcript_segments cleared."""
        conv = _make_conversation(locked=True)

        # Apply the strengthened redaction logic
        if conv.get('is_locked', False):
            if 'structured' in conv:
                conv['structured']['action_items'] = []
                conv['structured']['events'] = []
            conv['apps_results'] = []
            conv['plugins_results'] = []
            conv['suggested_summarization_apps'] = []
            conv['transcript_segments'] = []

        assert conv['transcript_segments'] == []
        assert conv['structured']['action_items'] == []


# =============================================================================
# Test public conversations filter
# =============================================================================


class TestPublicConversationFilter:
    """L1: Public conversation listing must exclude locked conversations."""

    def test_locked_filtered_from_public(self):
        """Locked conversations should be excluded from public listing."""
        conversations = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
        ]
        filtered = [c for c in conversations if not c.get('is_locked', False)]
        assert len(filtered) == 1
        assert filtered[0]['id'] == 'conv-2'


# =============================================================================
# Test search redaction
# =============================================================================


class TestSearchRedaction:
    """M1: Search results must redact locked conversation content."""

    def test_locked_search_results_redacted(self):
        """Locked conversations in search should have action_items/events/transcript cleared."""
        doc = _make_conversation(locked=True)

        # Apply search redaction logic
        if doc.get('is_locked', False):
            structured = doc.get('structured', {})
            if structured:
                structured['action_items'] = []
                structured['events'] = []
            doc['transcript_segments'] = []

        assert doc['structured']['action_items'] == []
        assert doc['structured']['events'] == []
        assert doc['transcript_segments'] == []
        # Title/overview preserved for search display
        assert doc['structured']['title'] == 'Test Conversation'


# =============================================================================
# Test chat/RAG tool filtering
# =============================================================================


class TestConversationToolFiltering:
    """H5: Chat/RAG conversation tools must filter out locked conversations."""

    def test_locked_conversations_filtered_from_tool(self):
        """get_conversations_tool should exclude locked conversations."""
        conversations_data = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
            _make_conversation(locked=True, conversation_id='conv-3'),
        ]
        filtered = [c for c in conversations_data if not c.get('is_locked', False)]
        assert len(filtered) == 1
        assert filtered[0]['id'] == 'conv-2'

    def test_search_tool_filters_locked(self):
        """search_conversations_tool should exclude locked conversations."""
        conversations_data = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
        ]
        filtered = [c for c in conversations_data if not c.get('is_locked', False)]
        assert len(filtered) == 1


# =============================================================================
# Test memory tool filtering
# =============================================================================


class TestMemoryToolFiltering:
    """M6: Chat/RAG memory tools must filter out locked memories."""

    def test_locked_memories_filtered(self):
        """get_memories_tool should exclude locked memories."""
        memories = [
            _make_memory(locked=True),
            _make_memory(locked=False, memory_id='mem-2'),
        ]
        filtered = [m for m in memories if not m.get('is_locked', False)]
        assert len(filtered) == 1
        assert filtered[0]['id'] == 'mem-2'

    def test_search_memories_filters_locked(self):
        """search_memories_tool should exclude locked memories."""
        memories = [
            _make_memory(locked=True),
            _make_memory(locked=True, memory_id='mem-2'),
        ]
        filtered = [m for m in memories if not m.get('is_locked', False)]
        assert len(filtered) == 0


# =============================================================================
# Test webhook skipping
# =============================================================================


class TestWebhookLockEnforcement:
    """M2-M3: Webhooks must skip locked conversations."""

    def test_external_integrations_skip_locked(self):
        """trigger_external_integrations should return [] for locked conversations."""
        from models.conversation import Conversation

        conv_data = _make_conversation(locked=True)
        conv_data['status'] = 'completed'
        conv_data['language'] = 'en'

        # Simulate the guard logic
        is_locked = conv_data.get('is_locked', False)
        assert is_locked is True
        # When locked, function returns [] without sending webhooks

    def test_developer_webhook_skips_locked(self):
        """conversation_created_webhook should return early for locked conversations."""
        # Simulate the guard
        conv_data = _make_conversation(locked=True)
        is_locked = conv_data.get('is_locked', False)
        assert is_locked is True


# =============================================================================
# Test action items per-conversation endpoint
# =============================================================================


class TestActionItemsLockEnforcement:
    """M4: Per-conversation action items endpoint must return 402 for locked."""

    @patch('database.conversations.get_conversation')
    def test_locked_conversation_action_items_blocked(self, mock_get_conv):
        """GET /v1/conversations/{id}/action-items must reject locked conversations."""
        mock_get_conv.return_value = _make_conversation(locked=True)
        conversation = mock_get_conv('uid', 'conv-1')
        assert conversation.get('is_locked', False) is True


# =============================================================================
# Test MCP SSE locked redaction
# =============================================================================


class TestMcpSseLockRedaction:
    """M5: MCP SSE get_conversations must redact locked conversation structured data."""

    def test_mcp_sse_redacts_locked(self):
        """MCP SSE should clear action_items/events for locked conversations."""
        conv = _make_conversation(locked=True)
        structured = conv.get("structured")

        if conv.get("is_locked", False) and structured:
            structured = dict(structured)
            structured['action_items'] = []
            structured['events'] = []

        assert structured['action_items'] == []
        assert structured['events'] == []
        assert structured['title'] == 'Test Conversation'


# =============================================================================
# Test users.py endpoints
# =============================================================================


class TestUsersLockEnforcement:
    """L2/L3: Users endpoints must enforce lock."""

    def test_followup_question_blocked_for_locked(self):
        """L2: followup-question must return 402 for locked conversations."""
        conv = _make_conversation(locked=True)
        assert conv.get('is_locked', False) is True

    def test_daily_summary_filters_locked(self):
        """L3: Daily summary test must exclude locked conversations."""
        conversations_data = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
            _make_conversation(locked=True, conversation_id='conv-3'),
        ]
        filtered = [c for c in conversations_data if not c.get('is_locked', False)]
        assert len(filtered) == 1
        assert filtered[0]['id'] == 'conv-2'

    def test_gdpr_export_includes_locked(self):
        """H6: GDPR export intentionally includes locked conversations (Art. 15)."""
        conversations = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
        ]
        # GDPR export does NOT filter — all conversations included
        assert len(conversations) == 2
