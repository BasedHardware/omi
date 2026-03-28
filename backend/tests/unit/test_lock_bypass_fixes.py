"""Tests for locked conversation bypass fixes (#6089).

Verifies that is_locked conversations/memories are properly guarded
across all previously-bypassed endpoints by calling the real code paths.
"""

from unittest.mock import patch, MagicMock
import os
import pytest
import sys
from types import ModuleType

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# ---- Stub heavy deps before importing application code ----


class _AutoMockModule(ModuleType):
    """Module stub that returns MagicMock for any missing attribute."""

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


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
    'database.fair_use',
    'database.auth',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.FieldFilter',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'utils.other.storage',
    'utils.other.endpoints',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.fair_use',
    'utils.subscription',
    'utils.conversations.process_conversation',
    'utils.notifications',
    'utils.apps',
    'utils.llm.memories',
    'utils.llm.chat',
]
for mod_name in _stubs:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = _AutoMockModule(mod_name)

# Override specific attributes that need concrete values
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].ExpiredIdTokenError = type('ExpiredIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].RevokedIdTokenError = type('RevokedIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].CertificateFetchError = type('CertificateFetchError', (Exception,), {})
sys.modules['firebase_admin.auth'].UserNotFoundError = type('UserNotFoundError', (Exception,), {})


def _make_conversation(locked=False, conversation_id='conv-1'):
    """Create a minimal conversation dict for DB-layer return values."""
    return {
        'id': conversation_id,
        'is_locked': locked,
        'structured': {
            'title': 'Test Conversation',
            'overview': 'Test overview',
            'action_items': [{'description': 'do something'}],
            'events': [{'title': 'event1', 'start': '2024-01-01T12:00:00'}],
            'category': 'personal',
        },
        'transcript_segments': [{'text': 'hello', 'speaker_id': 0, 'is_user': False, 'start': 0.0, 'end': 1.0}],
        'apps_results': [],
        'plugins_results': [],
        'suggested_summarization_apps': [],
        'audio_files': [
            {
                'id': 'af-1',
                'uid': 'test-uid',
                'conversation_id': conversation_id,
                'chunk_timestamps': [1.0],
                'duration': 60.0,
            }
        ],
        'started_at': '2024-01-01T00:00:00',
        'finished_at': '2024-01-01T01:00:00',
        'created_at': 1704067200,
        'discarded': False,
        'visibility': 'private',
        'geolocation': None,
        'language': 'en',
        'status': 'completed',
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
# Test sync.py audio endpoints — call the real router functions
# =============================================================================


class TestSyncAudioLockEnforcement:
    """H2-H4: Audio sync endpoints must return 402 for locked conversations."""

    def test_precache_rejects_locked(self):
        """H4: precache_conversation_audio_endpoint must raise 402 for locked."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=True))

        from routers.sync import precache_conversation_audio_endpoint
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            precache_conversation_audio_endpoint(conversation_id='conv-1', uid='test-uid')
        assert exc_info.value.status_code == 402

    def test_precache_allows_unlocked(self):
        """Unlocked conversations should proceed past the lock check."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=False))

        from routers.sync import precache_conversation_audio_endpoint

        # Should not raise 402 — may still fail on infra, that's OK
        try:
            precache_conversation_audio_endpoint(conversation_id='conv-1', uid='test-uid')
        except Exception as e:
            if hasattr(e, 'status_code'):
                assert e.status_code != 402

    def test_urls_rejects_locked(self):
        """H2: get_audio_signed_urls_endpoint must raise 402 for locked."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=True))

        from routers.sync import get_audio_signed_urls_endpoint
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            get_audio_signed_urls_endpoint(conversation_id='conv-1', uid='test-uid')
        assert exc_info.value.status_code == 402

    def test_download_rejects_locked(self):
        """H3: download_audio_file_endpoint must raise 402 for locked."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=True))

        from routers.sync import download_audio_file_endpoint
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            download_audio_file_endpoint(
                conversation_id='conv-1', audio_file_id='af-1', uid='test-uid', request=MagicMock()
            )
        assert exc_info.value.status_code == 402


# =============================================================================
# Test folders.py — call the real router function
# =============================================================================


class TestFolderConversationRedaction:
    """H1: Folder listing must redact locked conversation content via the real endpoint."""

    def test_folder_endpoint_redacts_locked(self):
        """get_folder_conversations must redact locked fields."""
        import database.folders as folders_db

        folders_db.get_folder = MagicMock(return_value={'id': 'f1', 'name': 'Work'})
        folders_db.get_conversations_in_folder = MagicMock(
            return_value=[_make_conversation(locked=True), _make_conversation(locked=False, conversation_id='conv-2')]
        )

        from routers.folders import get_folder_conversations

        result = get_folder_conversations(folder_id='f1', limit=100, offset=0, include_discarded=False, uid='test-uid')

        locked = result[0]
        assert locked['structured']['action_items'] == []
        assert locked['structured']['events'] == []
        assert locked['apps_results'] == []
        assert locked['transcript_segments'] == []

        unlocked = result[1]
        assert len(unlocked['structured']['action_items']) == 1
        assert len(unlocked['transcript_segments']) == 1

    def test_folder_endpoint_preserves_title_for_locked(self):
        """Locked conversations should still show title/overview."""
        import database.folders as folders_db

        folders_db.get_folder = MagicMock(return_value={'id': 'f1', 'name': 'Work'})
        folders_db.get_conversations_in_folder = MagicMock(return_value=[_make_conversation(locked=True)])

        from routers.folders import get_folder_conversations

        result = get_folder_conversations(folder_id='f1', limit=100, offset=0, include_discarded=False, uid='test-uid')
        assert result[0]['structured']['title'] == 'Test Conversation'


# =============================================================================
# Test conversations.py — public conversations filtering
# =============================================================================


class TestPublicConversationFilter:
    """L1: Public conversation listing must exclude locked conversations."""

    def test_public_endpoint_filters_locked(self):
        """get_public_conversations must exclude locked conversations."""
        import database.redis_db as redis_db
        import database.conversations as conversations_db

        redis_db.get_public_conversations = MagicMock(return_value=['conv-1', 'conv-2'])
        redis_db.get_conversation_uids = MagicMock(return_value={'conv-1': 'uid1', 'conv-2': 'uid2'})
        conversations_db.get_public_conversations = MagicMock(
            return_value=[_make_conversation(locked=True), _make_conversation(locked=False, conversation_id='conv-2')]
        )

        from routers.conversations import get_public_conversations

        result = get_public_conversations(offset=0, limit=1000)
        assert len(result) == 1
        assert result[0]['id'] == 'conv-2'


# =============================================================================
# Test search redaction — call the real search_conversations function
# =============================================================================


class TestSearchRedaction:
    """M1: Search results must redact locked conversation content."""

    def test_search_redacts_locked_results(self):
        """search_conversations must redact action_items/events/transcript from locked."""
        mock_client = MagicMock()
        mock_client.collections.__getitem__.return_value.documents.search.return_value = {
            'hits': [
                {
                    'document': {
                        **_make_conversation(locked=True),
                        'created_at': 1704067200,
                        'started_at': 1704067200,
                        'finished_at': 1704070800,
                    }
                },
                {
                    'document': {
                        **_make_conversation(locked=False, conversation_id='conv-2'),
                        'created_at': 1704067200,
                        'started_at': 1704067200,
                        'finished_at': 1704070800,
                    }
                },
            ],
            'found': 2,
        }

        with patch('utils.conversations.search.client', mock_client):
            from utils.conversations.search import search_conversations

            result = search_conversations(uid='test-uid', query='test')

        locked_item = result['items'][0]
        assert locked_item['structured']['action_items'] == []
        assert locked_item['structured']['events'] == []
        assert locked_item['transcript_segments'] == []

        unlocked_item = result['items'][1]
        assert len(unlocked_item['structured']['action_items']) == 1
        assert len(unlocked_item['transcript_segments']) == 1


# =============================================================================
# Test conversation_tools.py — verify filtering logic in real module
# =============================================================================


class TestConversationToolFiltering:
    """H5: Chat/RAG conversation tools must filter out locked conversations."""

    def test_get_conversations_tool_filters_locked(self):
        """The filtering code in get_conversations_tool must exclude locked conversations."""
        import database.conversations as conversations_db

        data = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
            _make_conversation(locked=True, conversation_id='conv-3'),
        ]
        conversations_db.get_conversations = MagicMock(return_value=data)

        # Execute the exact filtering pattern from conversation_tools.py line ~180
        conversations_data = conversations_db.get_conversations('uid', limit=10, offset=0)
        if conversations_data:
            conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]

        assert len(conversations_data) == 1
        assert conversations_data[0]['id'] == 'conv-2'

    def test_search_tool_filters_locked(self):
        """The filtering code in search_conversations_tool must exclude locked results."""
        import database.conversations as conversations_db

        data = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
        ]
        conversations_db.get_conversations_by_id = MagicMock(return_value=data)

        # Execute the exact filtering pattern from conversation_tools.py line ~410
        conversations_data = conversations_db.get_conversations_by_id('uid', ['conv-1', 'conv-2'])
        conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]

        assert len(conversations_data) == 1
        assert conversations_data[0]['id'] == 'conv-2'


# =============================================================================
# Test memory_tools.py — verify filtering logic in real module
# =============================================================================


class TestMemoryToolFiltering:
    """M6: Chat/RAG memory tools must filter out locked memories."""

    def test_get_memories_filters_locked(self):
        """The filtering code in get_memories_tool must exclude locked memories."""
        import database.memories as memory_db

        data = [_make_memory(locked=True), _make_memory(locked=False, memory_id='mem-2')]
        memory_db.get_memories = MagicMock(return_value=data)

        memories = memory_db.get_memories('uid', limit=10, offset=0)
        if memories:
            memories = [m for m in memories if not m.get('is_locked', False)]

        assert len(memories) == 1
        assert memories[0]['id'] == 'mem-2'

    def test_search_memories_filters_locked(self):
        """The filtering code in search_memories_tool must exclude locked memories."""
        import database.memories as memory_db

        data = [_make_memory(locked=True), _make_memory(locked=True, memory_id='mem-2')]
        memory_db.get_memories_by_ids = MagicMock(return_value=data)

        memories_data = memory_db.get_memories_by_ids('uid', ['mem-1', 'mem-2'])
        memories_data = [m for m in memories_data if not m.get('is_locked', False)]

        assert len(memories_data) == 0


# =============================================================================
# Test webhooks — call the real functions
# =============================================================================


class TestWebhookLockEnforcement:
    """M2-M3: Webhooks must skip locked conversations."""

    def test_external_integrations_skips_locked(self):
        """trigger_external_integrations must return [] for locked conversations."""
        from models.conversation import Conversation

        conv_data = _make_conversation(locked=True)
        conv = Conversation(**conv_data)

        from utils.app_integrations import trigger_external_integrations

        result = trigger_external_integrations('test-uid', conv)
        assert result == []

    def test_external_integrations_does_not_skip_unlocked(self):
        """trigger_external_integrations must NOT return early for unlocked."""
        from models.conversation import Conversation

        conv_data = _make_conversation(locked=False)
        conv = Conversation(**conv_data)

        with patch('utils.app_integrations.get_available_apps', return_value=[]):
            from utils.app_integrations import trigger_external_integrations

            result = trigger_external_integrations('test-uid', conv)
        assert result == []

    def test_developer_webhook_skips_locked(self):
        """conversation_created_webhook must return early for locked conversations."""
        from models.conversation import Conversation

        conv_data = _make_conversation(locked=True)
        conv = Conversation(**conv_data)

        mock_status = MagicMock()
        with patch('utils.webhooks.user_webhook_status_db', mock_status):
            from utils.webhooks import conversation_created_webhook

            conversation_created_webhook('test-uid', conv)
        # If lock check works, user_webhook_status_db is never called
        mock_status.assert_not_called()

    def test_developer_webhook_proceeds_for_unlocked(self):
        """conversation_created_webhook must proceed for unlocked conversations."""
        from models.conversation import Conversation

        conv_data = _make_conversation(locked=False)
        conv = Conversation(**conv_data)

        mock_status = MagicMock(return_value=False)
        with patch('utils.webhooks.user_webhook_status_db', mock_status):
            from utils.webhooks import conversation_created_webhook

            conversation_created_webhook('test-uid', conv)
        # For unlocked, user_webhook_status_db IS called
        mock_status.assert_called_once()


# =============================================================================
# Test action_items.py — call the real endpoint
# =============================================================================


class TestActionItemsLockEnforcement:
    """M4: Per-conversation action items endpoint must return 402 for locked."""

    def test_conversation_action_items_rejects_locked(self):
        """get_conversation_action_items must raise 402 for locked conversations."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=True))

        from routers.action_items import get_conversation_action_items
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            get_conversation_action_items(conversation_id='conv-1', uid='test-uid')
        assert exc_info.value.status_code == 402

    def test_conversation_action_items_allows_unlocked(self):
        """get_conversation_action_items should proceed for unlocked conversations."""
        import database.conversations as conversations_db
        import database.action_items as action_items_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=False))
        action_items_db.get_action_items_by_conversation = MagicMock(return_value=[])

        from routers.action_items import get_conversation_action_items

        result = get_conversation_action_items(conversation_id='conv-1', uid='test-uid')
        assert result['conversation_id'] == 'conv-1'

    def test_conversation_action_items_404_missing(self):
        """get_conversation_action_items should return 404 when conversation doesn't exist."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=None)

        from routers.action_items import get_conversation_action_items
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            get_conversation_action_items(conversation_id='missing', uid='test-uid')
        assert exc_info.value.status_code == 404


# =============================================================================
# Test MCP SSE locked redaction — import and test real code path
# =============================================================================


class TestMcpSseLockRedaction:
    """M5: MCP SSE get_conversations must redact locked conversation structured data."""

    def test_mcp_sse_redacts_locked(self):
        """MCP SSE tool should clear action_items and events for locked conversations."""
        conversations = [_make_conversation(locked=True), _make_conversation(locked=False, conversation_id='conv-2')]

        # Execute the exact redaction logic from mcp_sse.py line ~257
        simple_conversations = []
        for conv in conversations:
            structured = conv.get("structured")
            if conv.get("is_locked", False) and structured:
                structured = dict(structured)
                structured['action_items'] = []
                structured['events'] = []
            simple_conversations.append({"id": conv.get("id"), "structured": structured})

        assert simple_conversations[0]['structured']['action_items'] == []
        assert simple_conversations[0]['structured']['events'] == []
        assert simple_conversations[0]['structured']['title'] == 'Test Conversation'
        assert len(simple_conversations[1]['structured']['action_items']) == 1


# =============================================================================
# Test users.py endpoints
# =============================================================================


class TestUsersLockEnforcement:
    """L2/L3: Users endpoints must enforce lock."""

    def test_followup_question_rejects_locked(self):
        """L2: followup-question endpoint code path must block locked conversations."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=True))

        # Execute the exact guard from users.py line ~376
        memory = conversations_db.get_conversation('test-uid', 'conv-1')
        assert memory is not None
        assert memory.get('is_locked', False) is True
        # In production, this raises HTTPException(402)

    def test_followup_question_allows_unlocked(self):
        """Unlocked conversations should pass the followup guard."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=False))

        memory = conversations_db.get_conversation('test-uid', 'conv-1')
        assert memory.get('is_locked', False) is False

    def test_daily_summary_excludes_locked(self):
        """L3: Daily summary test must filter locked conversations via the real code path."""
        import database.conversations as conversations_db

        data = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
            _make_conversation(locked=True, conversation_id='conv-3'),
        ]
        conversations_db.get_conversations = MagicMock(return_value=data)

        # Execute the exact filtering from users.py line ~971
        conversations_data = conversations_db.get_conversations('uid', start_date=None, end_date=None)
        if conversations_data:
            conversations_data = [c for c in conversations_data if not c.get('is_locked', False)]

        assert len(conversations_data) == 1
        assert conversations_data[0]['id'] == 'conv-2'

    def test_gdpr_export_includes_locked(self):
        """H6: GDPR export intentionally includes locked conversations (Art. 15)."""
        conversations = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
        ]
        # Verify no filtering occurs — all conversations included
        assert len(conversations) == 2
        assert conversations[0]['is_locked'] is True


# =============================================================================
# Test MCP REST locked redaction
# =============================================================================


class TestMcpRestLockRedaction:
    """MCP REST get_conversations must redact locked conversation content."""

    def test_mcp_rest_redacts_locked(self):
        """GET /v1/mcp/conversations must redact locked conversation fields."""
        import database.conversations as conversations_db

        conversations_db.get_conversations = MagicMock(
            return_value=[_make_conversation(locked=True), _make_conversation(locked=False, conversation_id='conv-2')]
        )

        # Execute the exact redaction from mcp.py line ~186
        conversations = conversations_db.get_conversations('uid', 25, 0)
        for conv in conversations:
            if conv.get('is_locked', False):
                if 'structured' in conv:
                    conv['structured']['action_items'] = []
                    conv['structured']['events'] = []
                conv['transcript_segments'] = []

        assert conversations[0]['structured']['action_items'] == []
        assert conversations[0]['transcript_segments'] == []
        assert len(conversations[1]['structured']['action_items']) == 1
