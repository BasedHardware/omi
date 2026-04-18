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
        'source': 'friend',
    }


def _make_memory(locked=False, memory_id='mem-1'):
    """Create a minimal memory dict compatible with MemoryDB model."""
    return {
        'id': memory_id,
        'uid': 'test-uid',
        'is_locked': locked,
        'content': 'This is a secret memory that should not be visible when locked',
        'category': 'interesting',
        'created_at': '2024-01-01T00:00:00',
        'updated_at': '2024-01-01T00:00:00',
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
    """M1: Search results must exclude locked conversations entirely to prevent inference leaks."""

    def test_search_excludes_locked_results(self):
        """search_conversations must exclude locked hits entirely (not just redact)."""
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

        # Locked item must be excluded entirely (prevents inference leak)
        assert len(result['items']) == 1
        unlocked_item = result['items'][0]
        assert unlocked_item['structured']['title'] == 'Test Conversation'
        assert unlocked_item['structured']['overview'] == 'Test overview'
        assert len(unlocked_item['structured']['action_items']) == 1
        assert len(unlocked_item['transcript_segments']) == 1
        # total_pages uses page-level signal, not global found count
        assert result['total_pages'] == 1

    def test_search_total_pages_does_not_leak_locked_count(self):
        """total_pages must not inflate from locked docs on other pages."""
        mock_client = MagicMock()
        # Simulate: found=6 globally, per_page=5, 4 locked + 1 unlocked on this page
        hits = [
            {
                'document': {
                    **_make_conversation(locked=True, conversation_id=f'locked-{i}'),
                    'created_at': 1704067200,
                    'started_at': 1704067200,
                    'finished_at': 1704070800,
                }
            }
            for i in range(4)
        ] + [
            {
                'document': {
                    **_make_conversation(locked=False, conversation_id='unlocked-1'),
                    'created_at': 1704067200,
                    'started_at': 1704067200,
                    'finished_at': 1704070800,
                }
            }
        ]
        mock_client.collections.__getitem__.return_value.documents.search.return_value = {
            'hits': hits,
            'found': 6,
        }
        with patch('utils.conversations.search.client', mock_client):
            from utils.conversations.search import search_conversations

            result = search_conversations(uid='test-uid', query='test', per_page=5)

        assert len(result['items']) == 1
        # total_pages derived from visible items (1 < per_page=5), not raw hits or found count
        assert result['total_pages'] == 1

    def test_search_total_pages_last_page_no_leak(self):
        """When Typesense returns fewer than per_page hits, total_pages = current page."""
        mock_client = MagicMock()
        # Only 2 hits (< per_page=5), all locked → 0 items, total_pages=1
        hits = [
            {
                'document': {
                    **_make_conversation(locked=True, conversation_id=f'locked-{i}'),
                    'created_at': 1704067200,
                    'started_at': 1704067200,
                    'finished_at': 1704070800,
                }
            }
            for i in range(2)
        ]
        mock_client.collections.__getitem__.return_value.documents.search.return_value = {
            'hits': hits,
            'found': 2,
        }
        with patch('utils.conversations.search.client', mock_client):
            from utils.conversations.search import search_conversations

            result = search_conversations(uid='test-uid', query='test', per_page=5)

        assert len(result['items']) == 0
        # Not a full page → total_pages = current page (1), not found/per_page
        assert result['total_pages'] == 1


# =============================================================================
# Test conversation_tools.py — verify filtering logic in real module
# =============================================================================


class TestConversationToolFiltering:
    """H5: Chat/RAG conversation tools must filter out locked conversations."""

    def test_get_conversations_tool_filters_locked(self):
        """get_conversations_tool must exclude locked conversations from results."""
        import database.conversations as conversations_db
        import database.users as users_db

        data = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
            _make_conversation(locked=True, conversation_id='conv-3'),
        ]
        conversations_db.get_conversations = MagicMock(return_value=data)
        users_db.get_people_by_ids = MagicMock(return_value=[])

        from utils.retrieval.tools.conversation_tools import get_conversations_tool

        config = {'configurable': {'user_id': 'test-uid', 'conversations_collected': []}}
        result = get_conversations_tool.invoke({'limit': 10, 'offset': 0}, config=config)
        # Result is a string with "Conversation #N" format; should have exactly 1 conversation
        assert 'Conversation #1' in result
        assert 'Conversation #2' not in result  # Only 1 unlocked conv should appear

    def test_search_tool_filters_locked(self):
        """search_conversations_tool must exclude locked results."""
        import database.conversations as conversations_db
        import database.vector_db as vector_db
        import database.users as users_db

        data = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
        ]
        conversations_db.get_conversations_by_id = MagicMock(return_value=data)
        vector_db.query_vectors = MagicMock(return_value=[{'id': 'conv-1'}, {'id': 'conv-2'}])
        users_db.get_people_by_ids = MagicMock(return_value=[])

        from utils.retrieval.tools.conversation_tools import search_conversations_tool

        config = {'configurable': {'user_id': 'test-uid', 'conversations_collected': []}}
        result = search_conversations_tool.invoke({'query': 'test'}, config=config)
        # Only 1 unlocked conv should appear
        assert 'Conversation #1' in result
        assert 'Conversation #2' not in result


# =============================================================================
# Test memory_tools.py — verify filtering logic in real module
# =============================================================================


class TestMemoryToolFiltering:
    """M6: Chat/RAG memory tools must filter out locked memories."""

    def test_get_memories_filters_locked(self):
        """get_memories_tool must exclude locked memories from results."""
        import database.memories as memory_db

        locked_mem = _make_memory(locked=True)
        locked_mem['content'] = 'LOCKED_SECRET_CONTENT'
        unlocked_mem = _make_memory(locked=False, memory_id='mem-2')
        unlocked_mem['content'] = 'UNLOCKED_VISIBLE_CONTENT'
        memory_db.get_memories = MagicMock(return_value=[locked_mem, unlocked_mem])

        from utils.retrieval.tools.memory_tools import get_memories_tool

        config = {'configurable': {'user_id': 'test-uid'}}
        result = get_memories_tool.invoke({'limit': 10, 'offset': 0}, config=config)
        # Only unlocked memory content should appear; locked must be filtered
        assert 'UNLOCKED_VISIBLE_CONTENT' in result
        assert 'LOCKED_SECRET_CONTENT' not in result
        assert '1 total' in result  # Only 1 memory should appear

    def test_search_memories_filters_locked(self):
        """search_memories_tool must exclude locked memories from results."""
        import database.memories as memory_db
        import database.vector_db as vector_db

        data = [_make_memory(locked=True), _make_memory(locked=True, memory_id='mem-2')]
        memory_db.get_memories_by_ids = MagicMock(return_value=data)
        vector_db.find_similar_memories = MagicMock(return_value=[{'id': 'mem-1'}, {'id': 'mem-2'}])

        from utils.retrieval.tools.memory_tools import search_memories_tool

        config = {'configurable': {'user_id': 'test-uid'}}
        result = search_memories_tool.invoke({'query': 'test'}, config=config)
        # All memories locked, so result should indicate nothing found
        assert 'no' in result.lower() or 'mem-1' not in result


# =============================================================================
# Test webhooks — call the real functions
# =============================================================================


class TestWebhookLockEnforcement:
    """M2-M3: Webhooks must skip locked conversations."""

    def test_external_integrations_skips_locked(self):
        """trigger_external_integrations must return [] for locked conversations."""
        import asyncio

        from models.conversation import Conversation

        conv_data = _make_conversation(locked=True)
        conv = Conversation(**conv_data)

        from utils.app_integrations import trigger_external_integrations

        result = asyncio.run(trigger_external_integrations('test-uid', conv))
        assert result == []

    def test_external_integrations_does_not_skip_unlocked(self):
        """trigger_external_integrations must call get_available_apps for unlocked."""
        import asyncio

        from models.conversation import Conversation

        conv_data = _make_conversation(locked=False)
        conv = Conversation(**conv_data)

        mock_get_apps = MagicMock(return_value=[])
        with patch('utils.app_integrations.get_available_apps', mock_get_apps):
            from utils.app_integrations import trigger_external_integrations

            result = asyncio.run(trigger_external_integrations('test-uid', conv))
        # Verify downstream work was attempted (not short-circuited by lock check)
        mock_get_apps.assert_called_once()
        assert result == []

    def test_developer_webhook_skips_locked(self):
        """conversation_created_webhook must return early for locked conversations."""
        import asyncio

        from models.conversation import Conversation

        conv_data = _make_conversation(locked=True)
        conv = Conversation(**conv_data)

        mock_status = MagicMock()
        with patch('utils.webhooks.user_webhook_status_db', mock_status):
            from utils.webhooks import conversation_created_webhook

            asyncio.run(conversation_created_webhook('test-uid', conv))
        # If lock check works, user_webhook_status_db is never called
        mock_status.assert_not_called()

    def test_developer_webhook_proceeds_for_unlocked(self):
        """conversation_created_webhook must proceed for unlocked conversations."""
        import asyncio

        from models.conversation import Conversation

        conv_data = _make_conversation(locked=False)
        conv = Conversation(**conv_data)

        mock_status = MagicMock(return_value=False)
        with patch('utils.webhooks.user_webhook_status_db', mock_status):
            from utils.webhooks import conversation_created_webhook

            asyncio.run(conversation_created_webhook('test-uid', conv))
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
        """MCP SSE execute_tool('get_conversations') must clear action_items/events for locked."""
        import database.conversations as conversations_db

        conversations_db.get_conversations = MagicMock(
            return_value=[_make_conversation(locked=True), _make_conversation(locked=False, conversation_id='conv-2')]
        )

        from routers.mcp_sse import execute_tool

        result = execute_tool('test-uid', 'get_conversations', {})
        convs = result['conversations']

        assert convs[0]['structured']['action_items'] == []
        assert convs[0]['structured']['events'] == []
        assert convs[0]['structured']['title'] == 'Test Conversation'
        assert len(convs[1]['structured']['action_items']) == 1


# =============================================================================
# Test users.py endpoints
# =============================================================================


class TestUsersLockEnforcement:
    """L2/L3: Users endpoints must enforce lock."""

    def test_followup_question_rejects_locked(self):
        """L2: delete_person_endpoint must raise 402 for locked conversations."""
        from routers.users import delete_person_endpoint
        from fastapi import HTTPException

        with patch('routers.users.get_conversation', return_value=_make_conversation(locked=True)):
            with pytest.raises(HTTPException) as exc_info:
                delete_person_endpoint(memory_id='conv-1', uid='test-uid')
            assert exc_info.value.status_code == 402

    def test_followup_question_allows_unlocked(self):
        """delete_person_endpoint should proceed for unlocked conversations."""
        from routers.users import delete_person_endpoint

        with patch('routers.users.get_conversation', return_value=_make_conversation(locked=False)):
            with patch('routers.users.followup_question_prompt', return_value='test result'):
                result = delete_person_endpoint(memory_id='conv-1', uid='test-uid')
        assert result['result'] == 'test result'

    def test_daily_summary_excludes_locked(self):
        """L3: test_daily_summary must filter locked conversations before processing."""
        import database.conversations as conversations_db
        import database.notifications as notification_db
        import database.daily_summaries as daily_summaries_db

        data = [
            _make_conversation(locked=True),
            _make_conversation(locked=False, conversation_id='conv-2'),
            _make_conversation(locked=True, conversation_id='conv-3'),
        ]
        conversations_db.get_conversations = MagicMock(return_value=data)
        notification_db.get_user_time_zone = MagicMock(return_value=None)
        notification_db.get_all_tokens = MagicMock(return_value=['token1'])
        daily_summaries_db.create_daily_summary = MagicMock(return_value='summary-1')

        from routers.users import test_daily_summary

        mock_gen = MagicMock(return_value={'headline': 'Test', 'overview': 'Overview'})
        with patch('routers.users.generate_comprehensive_daily_summary', mock_gen):
            with patch('routers.users.send_notification'):
                result = test_daily_summary(uid='test-uid')

        # Verify only unlocked conversations were passed to summary generation
        call_args = mock_gen.call_args
        conversations_passed = call_args[0][1]  # second positional arg
        assert len(conversations_passed) == 1
        assert conversations_passed[0].id == 'conv-2'

    @pytest.mark.asyncio
    async def test_gdpr_export_includes_locked(self):
        """H6: GDPR export must include locked conversations (Art. 15)."""
        import database.conversations as conversations_db
        import database.memories as memories_db
        import database.chat as chat_db

        locked_conv = _make_conversation(locked=True)
        unlocked_conv = _make_conversation(locked=False, conversation_id='conv-2')
        conversations_db.iter_all_conversations = MagicMock(return_value=iter([locked_conv, unlocked_conv]))
        memories_db.get_memories = MagicMock(return_value=[])
        chat_db.iter_all_messages = MagicMock(return_value=iter([]))

        # These functions are imported via 'from database.users import *' so they live
        # in the routers.users namespace. Use create=True since the wildcard import
        # may not have populated them in the stub environment.
        # Patches must stay active during body consumption since generate() is lazy.
        with patch('routers.users.get_user_profile', return_value={'name': 'Test'}, create=True):
            with patch('routers.users.get_people', return_value=[], create=True):
                with patch('routers.users.get_standalone_action_items', return_value=[], create=True):
                    from routers.users import export_all_user_data

                    response = await export_all_user_data(uid='test-uid')

                    # Consume body inside patches — generate() is a lazy generator
                    body_parts = []
                    async for chunk in response.body_iterator:
                        body_parts.append(chunk)
                    body = ''.join(body_parts)

        import json

        data = json.loads(body)
        # Both locked and unlocked conversations must be in the export
        assert len(data['conversations']) == 2
        assert data['conversations'][0]['is_locked'] is True
        assert data['conversations'][1]['id'] == 'conv-2'


# =============================================================================
# Test MCP REST locked redaction
# =============================================================================


class TestMcpRestLockRedaction:
    """MCP REST get_conversations must redact locked conversation content."""

    def test_mcp_rest_redacts_locked(self):
        """GET /v1/mcp/conversations calls real router and redacts locked fields."""
        import database.conversations as conversations_db

        conversations_db.get_conversations = MagicMock(
            return_value=[_make_conversation(locked=True), _make_conversation(locked=False, conversation_id='conv-2')]
        )

        from routers.mcp import get_conversations

        result = get_conversations(uid='test-uid')

        assert result[0]['structured']['action_items'] == []
        assert result[0]['structured']['events'] == []
        assert result[0]['transcript_segments'] == []
        assert len(result[1]['structured']['action_items']) == 1
        assert len(result[1]['transcript_segments']) == 1


# =============================================================================
# Test scheduled daily summary excludes locked conversations
# =============================================================================


class TestScheduledDailySummaryLockFilter:
    """Scheduled daily summary must exclude locked conversations from LLM context."""

    def test_scheduled_summary_excludes_locked(self):
        """_send_summary_notification filters locked conversations before generating summary."""
        import database.conversations as conversations_db
        import database.daily_summaries as daily_summaries_db

        locked_conv = _make_conversation(locked=True)
        unlocked_conv = _make_conversation(locked=False, conversation_id='conv-2')
        conversations_db.get_conversations = MagicMock(return_value=[locked_conv, unlocked_conv])

        with patch('utils.other.notifications.try_acquire_daily_summary_lock', return_value=True):
            with patch(
                'utils.other.notifications.generate_comprehensive_daily_summary',
                return_value={'headline': 'Test', 'day_emoji': '📅', 'overview': 'ok'},
            ) as mock_gen:
                daily_summaries_db.create_daily_summary = MagicMock(return_value='summary-1')
                with patch('utils.other.notifications.send_notification'):
                    from utils.other.notifications import _send_summary_notification

                    _send_summary_notification(('test-uid', 'token', 'UTC'))

        # generate_comprehensive_daily_summary must be called only with unlocked conversations
        mock_gen.assert_called_once()
        conversations_passed = mock_gen.call_args[0][1]
        assert len(conversations_passed) == 1
        assert conversations_passed[0].id == 'conv-2'

    def test_scheduled_summary_skips_when_all_locked(self):
        """_send_summary_notification returns early when all conversations are locked."""
        import database.conversations as conversations_db

        conversations_db.get_conversations = MagicMock(return_value=[_make_conversation(locked=True)])

        with patch('utils.other.notifications.try_acquire_daily_summary_lock', return_value=True):
            with patch('utils.other.notifications.generate_comprehensive_daily_summary') as mock_gen:
                from utils.other.notifications import _send_summary_notification

                _send_summary_notification(('test-uid', 'token', 'UTC'))

        # Should not call LLM when no unlocked conversations remain
        mock_gen.assert_not_called()


# =============================================================================
# Test goal context excludes locked conversations and memories
# =============================================================================


class TestGoalContextLockFilter:
    """Goal suggestion/advice must exclude locked conversations and memories."""

    def test_get_goal_context_filters_locked_conversations(self):
        """_get_goal_context excludes locked conversations from vector and recent results."""
        import database.conversations as conversations_db
        import database.memories as memories_db
        import database.chat as chat_db

        locked_conv = _make_conversation(locked=True)
        locked_conv['structured']['overview'] = 'SECRET_LOCKED_OVERVIEW'
        unlocked_conv = _make_conversation(locked=False, conversation_id='conv-2')
        unlocked_conv['structured']['overview'] = 'VISIBLE_UNLOCKED_OVERVIEW'

        # Mock vector search to return both conv IDs
        with patch('utils.llm.goals.vector_search', return_value=['conv-1', 'conv-2']):
            conversations_db.get_conversations_by_id = MagicMock(return_value=[locked_conv, unlocked_conv])
            conversations_db.get_conversations = MagicMock(return_value=[])
            chat_db.get_messages = MagicMock(return_value=[])
            memories_db.get_memories = MagicMock(return_value=[])

            from utils.llm.goals import _get_goal_context

            result = _get_goal_context('test-uid', 'Exercise more')

        # Locked overview must not appear in context
        assert 'SECRET_LOCKED_OVERVIEW' not in result['conversation_context']
        assert 'VISIBLE_UNLOCKED_OVERVIEW' in result['conversation_context']

    def test_get_goal_context_filters_locked_memories(self):
        """_get_goal_context excludes locked memories from context."""
        import database.conversations as conversations_db
        import database.memories as memories_db
        import database.chat as chat_db

        locked_mem = {'content': 'LOCKED_SECRET_MEMORY', 'is_locked': True}
        unlocked_mem = {'content': 'VISIBLE_UNLOCKED_MEMORY', 'is_locked': False}

        with patch('utils.llm.goals.vector_search', return_value=[]):
            conversations_db.get_conversations_by_id = MagicMock(return_value=[])
            conversations_db.get_conversations = MagicMock(return_value=[])
            chat_db.get_messages = MagicMock(return_value=[])
            memories_db.get_memories = MagicMock(return_value=[locked_mem, unlocked_mem])

            from utils.llm.goals import _get_goal_context

            result = _get_goal_context('test-uid', 'Read more')

        assert 'LOCKED_SECRET_MEMORY' not in result['memory_context']
        assert 'VISIBLE_UNLOCKED_MEMORY' in result['memory_context']


# =============================================================================
# Test notification LLM excludes locked memories
# =============================================================================


class TestNotificationLlmLockFilter:
    """Credit-limit and subscription notifications must exclude locked memories."""

    @pytest.mark.asyncio
    async def test_get_relevant_memories_filters_locked(self):
        """get_relevant_memories must exclude locked memories from LLM context."""
        import database.memories as memories_db

        locked_mem = {'content': 'LOCKED_SECRET', 'is_locked': True}
        unlocked_mem = {'content': 'VISIBLE_CONTENT', 'is_locked': False}
        memories_db.get_memories = MagicMock(return_value=[locked_mem, unlocked_mem])

        from utils.llm.notifications import get_relevant_memories

        result = await get_relevant_memories('test-uid')

        assert len(result) == 1
        assert result[0]['content'] == 'VISIBLE_CONTENT'


# =============================================================================
# Test mentor proactive notifications exclude locked conversations
# =============================================================================


class TestMentorProactiveLockFilter:
    """Mentor proactive notifications must exclude locked conversations from context."""

    def test_mentor_proactive_filters_locked_conversations(self):
        """_process_mentor_proactive_notification must not feed locked conversations to LLM."""
        import database.conversations as conversations_db
        import database.mem_db as mem_db
        import database.redis_db as redis_db

        locked_conv = _make_conversation(locked=True)
        locked_conv['structured']['overview'] = 'SECRET_LOCKED_DATA'
        unlocked_conv = _make_conversation(locked=False, conversation_id='conv-2')
        unlocked_conv['structured']['overview'] = 'VISIBLE_DATA'

        # Disable rate limiting by returning None (no previous send)
        mem_db.get_proactive_noti_sent_at = MagicMock(return_value=None)
        redis_db.get_proactive_noti_sent_at = MagicMock(return_value=None)

        # Mock gate to pass
        gate_result = MagicMock()
        gate_result.is_relevant = True
        gate_result.relevance_score = 0.9
        gate_result.context_summary = 'test'
        gate_result.reasoning = 'test'

        with patch('utils.app_integrations.get_mentor_notification_frequency', return_value=5):
            with patch('utils.app_integrations.get_daily_notification_count', return_value=0):
                with patch('utils.app_integrations.get_prompt_memories', return_value=('Test', '')):
                    with patch('utils.app_integrations.get_user_goals', return_value=[]):
                        with patch('utils.app_integrations.get_app_messages', return_value=[]):
                            with patch('utils.app_integrations.track_usage'):
                                with patch('utils.app_integrations.evaluate_relevance', return_value=gate_result):
                                    with patch('utils.app_integrations.generate_embedding', return_value=[0.1] * 1536):
                                        with patch(
                                            'utils.app_integrations.query_vectors_by_metadata',
                                            return_value=['conv-1', 'conv-2'],
                                        ):
                                            conversations_db.get_conversations_by_id = MagicMock(
                                                return_value=[locked_conv, unlocked_conv]
                                            )
                                            conversations_db.get_conversations = MagicMock(return_value=[])

                                            with patch('utils.app_integrations.conversations_to_string') as mock_render:
                                                mock_render.return_value = ''

                                                draft = MagicMock()
                                                draft.notification_text = ''
                                                with patch(
                                                    'utils.app_integrations.generate_notification', return_value=draft
                                                ):
                                                    from utils.app_integrations import (
                                                        _process_mentor_proactive_notification,
                                                    )

                                                    _process_mentor_proactive_notification(
                                                        uid='test-uid',
                                                        conversation_messages=[{'text': 'hello', 'sender': 'human'}],
                                                    )

                                            # conversations_to_string called with only unlocked
                                            mock_render.assert_called_once()
                                            convos_passed = mock_render.call_args[0][0]
                                            assert len(convos_passed) == 1
                                            conv = convos_passed[0]
                                            is_locked = (
                                                conv.get('is_locked') if isinstance(conv, dict) else conv.is_locked
                                            )
                                            assert is_locked is not True


# =============================================================================
# Test integration search redacts locked conversation title/overview
# =============================================================================


class TestIntegrationSearchLockRedaction:
    """Integration search/list endpoints must redact title/overview for locked conversations."""

    @pytest.mark.asyncio
    async def test_integration_search_redacts_locked_title_overview(self):
        """Integration search re-fetches full convos — must also blank title/overview."""
        import database.conversations as conversations_db
        import database.apps as apps_db
        import database.redis_db as redis_db

        locked_conv = _make_conversation(locked=True)
        locked_conv['structured']['title'] = 'SECRET_TITLE'
        locked_conv['structured']['overview'] = 'SECRET_OVERVIEW'
        unlocked_conv = _make_conversation(locked=False, conversation_id='conv-2')

        # Mock search + db + auth
        with patch(
            'routers.integration.search_conversations',
            return_value={'items': [locked_conv, unlocked_conv], 'total_pages': 1, 'current_page': 1, 'per_page': 10},
        ):
            import copy

            conversations_db.get_conversations_by_id = MagicMock(
                return_value=[copy.deepcopy(locked_conv), copy.deepcopy(unlocked_conv)]
            )
            apps_db.get_app_by_id_db = MagicMock(return_value={'id': 'app-1', 'name': 'test'})
            redis_db.get_enabled_apps = MagicMock(return_value=['app-1'])

            with patch('routers.integration.verify_api_key', return_value=True):
                with patch('routers.integration.apps_utils') as mock_apps_utils:
                    mock_apps_utils.app_can_read_conversations.return_value = True

                    from routers.integration import search_conversations_via_integration

                    result = await search_conversations_via_integration(
                        request=MagicMock(),
                        app_id='app-1',
                        uid='test-uid',
                        search_request=MagicMock(
                            query='test',
                            page=1,
                            per_page=10,
                            include_discarded=False,
                            start_date=None,
                            end_date=None,
                        ),
                        max_transcript_segments=100,
                        authorization='Bearer test-key',
                    )

        # result is a dict (from .dict(exclude_none=True)), conversations are dicts
        convs = result['conversations']
        assert len(convs) == 2
        # The locked conversation must have redacted title/overview
        locked_items = [c for c in convs if c['structured']['title'] == '']
        assert len(locked_items) == 1
        assert locked_items[0]['structured']['overview'] == ''
        # Unlocked should preserve content
        unlocked_items = [c for c in convs if c['structured']['title'] != '']
        assert len(unlocked_items) == 1
        assert unlocked_items[0]['structured']['title'] == 'Test Conversation'


# =============================================================================
# Test get_prompt_data excludes locked memories
# =============================================================================


class TestPromptDataLockFilter:
    """get_prompt_data (shared utility) must exclude locked memories."""

    def test_get_prompt_data_filters_locked_memories(self):
        """get_prompt_data must not include locked memories in prompt context."""
        import database.memories as memories_db

        locked_mem = {
            'id': 'mem-1',
            'content': 'LOCKED_SECRET',
            'is_locked': True,
            'manually_added': False,
            'category': 'interesting',
        }
        unlocked_mem = {
            'id': 'mem-2',
            'content': 'VISIBLE_CONTENT',
            'is_locked': False,
            'manually_added': False,
            'category': 'interesting',
        }
        memories_db.get_memories = MagicMock(return_value=[locked_mem, unlocked_mem])

        with patch('utils.llms.memory.get_user_name', return_value='Test'):
            from utils.llms.memory import get_prompt_data

            _, user_made, generated = get_prompt_data('test-uid')

        # Only unlocked memory should appear
        all_mems = user_made + generated
        assert len(all_mems) == 1
        assert all_mems[0].content == 'VISIBLE_CONTENT'


# =============================================================================
# Test _retrieve_contextual_memories excludes locked conversations
# =============================================================================


class TestRetrieveContextualMemoriesLockFilter:
    """_retrieve_contextual_memories must exclude locked conversations."""

    def test_retrieve_contextual_memories_filters_locked(self):
        """_retrieve_contextual_memories must not return locked conversations."""
        import database.conversations as conversations_db

        locked_conv = _make_conversation(locked=True)
        unlocked_conv = _make_conversation(locked=False, conversation_id='conv-2')

        with patch('utils.app_integrations.generate_embedding', return_value=[0.1] * 3072):
            with patch('utils.app_integrations.query_vectors_by_metadata', return_value=['conv-1', 'conv-2']):
                conversations_db.get_conversations_by_id = MagicMock(return_value=[locked_conv, unlocked_conv])

                from utils.app_integrations import _retrieve_contextual_memories

                result = _retrieve_contextual_memories('test-uid', {'question': 'test'})

        assert len(result) == 1
        assert result[0]['id'] == 'conv-2'


# =============================================================================
# Test generate_persona_prompt excludes locked content
# =============================================================================


class TestPersonaGenerationLockFilter:
    """generate_persona_prompt must exclude locked memories and conversations."""

    @pytest.mark.asyncio
    async def test_generate_persona_prompt_filters_locked(self):
        """generate_persona_prompt lock filter must exclude locked memories/conversations.

        utils.apps is fully stubbed due to deep import chains, so we reload it
        inside the test to get the real function with all deps pre-stubbed.
        """
        import importlib

        # Temporarily remove the stub so we can load the real module
        old_mod = sys.modules.pop('utils.apps', None)
        # Add missing transitive stubs
        for dep in ['database.cache', 'database.llm_usage', 'utils.stripe', 'utils.social', 'utils.llm.persona']:
            if dep not in sys.modules:
                sys.modules[dep] = _AutoMockModule(dep)

        import database.memories as memories_db
        import database.conversations as conversations_db
        import database.auth as auth_db

        locked_mem = _make_memory(locked=True)
        locked_mem['content'] = 'LOCKED_SECRET'
        unlocked_mem = _make_memory(locked=False, memory_id='mem-2')
        unlocked_mem['content'] = 'visible memory'

        locked_conv = _make_conversation(locked=True)
        unlocked_conv = _make_conversation(locked=False, conversation_id='conv-2')

        memories_db.get_memories = MagicMock(return_value=[locked_mem, unlocked_mem])
        conversations_db.get_conversations = MagicMock(return_value=[locked_conv, unlocked_conv])
        auth_db.get_user_name = MagicMock(return_value='TestUser')

        persona = {'connected_accounts': [], 'twitter': None}

        try:
            import utils.apps as real_apps

            mock_track = MagicMock()
            mock_track.__enter__ = MagicMock(return_value=None)
            mock_track.__exit__ = MagicMock(return_value=False)
            real_apps.track_usage = MagicMock(return_value=mock_track)
            real_apps.condense_conversations = MagicMock(return_value='condensed convos')
            real_apps.condense_memories = MagicMock(return_value='condensed mems')

            result = await real_apps.generate_persona_prompt('test-uid', persona)

            # condense_memories should only receive unlocked memory content
            call_args = real_apps.condense_memories.call_args[0]
            memory_contents = call_args[0]
            assert 'LOCKED_SECRET' not in memory_contents
            assert 'visible memory' in memory_contents
        finally:
            # Restore the stub
            if old_mod is not None:
                sys.modules['utils.apps'] = old_mod


# =============================================================================
# Test integration list endpoint redacts locked conversations
# =============================================================================


class TestIntegrationListLockRedaction:
    """get_conversations_via_integration must redact locked conversation content."""

    @pytest.mark.asyncio
    async def test_integration_list_redacts_locked_title_overview(self):
        """Integration list must blank title/overview/action_items/events/transcript for locked."""
        import copy
        import database.conversations as conversations_db
        import database.apps as apps_db
        import database.redis_db as redis_db

        locked_conv = _make_conversation(locked=True)
        locked_conv['structured']['title'] = 'SECRET_TITLE'
        locked_conv['structured']['overview'] = 'SECRET_OVERVIEW'
        unlocked_conv = _make_conversation(locked=False, conversation_id='conv-2')

        conversations_db.get_conversations = MagicMock(
            return_value=[copy.deepcopy(locked_conv), copy.deepcopy(unlocked_conv)]
        )
        apps_db.get_app_by_id_db = MagicMock(return_value={'id': 'app-1', 'name': 'test'})
        redis_db.get_enabled_apps = MagicMock(return_value=['app-1'])

        with patch('routers.integration.verify_api_key', return_value=True):
            with patch('routers.integration.apps_utils') as mock_apps_utils:
                mock_apps_utils.app_can_read_conversations.return_value = True

                from routers.integration import get_conversations_via_integration

                result = await get_conversations_via_integration(
                    request=MagicMock(),
                    app_id='app-1',
                    uid='test-uid',
                    limit=100,
                    offset=0,
                    include_discarded=False,
                    statuses=[],
                    start_date=None,
                    end_date=None,
                    max_transcript_segments=100,
                    authorization='Bearer test-key',
                )

        convs = result['conversations']
        assert len(convs) == 2
        locked_items = [c for c in convs if c['structured']['title'] == '']
        assert len(locked_items) == 1
        assert locked_items[0]['structured']['overview'] == ''
        unlocked_items = [c for c in convs if c['structured']['title'] != '']
        assert len(unlocked_items) == 1
        assert unlocked_items[0]['structured']['title'] == 'Test Conversation'


# =============================================================================
# Test conversations list endpoint redacts locked conversations
# =============================================================================


class TestConversationListRedaction:
    """get_conversations router endpoint must redact locked conversation content."""

    def test_conversation_list_redacts_locked(self):
        """Main conversation list must clear action_items/events/transcript for locked."""
        import database.conversations as conversations_db

        locked_conv = _make_conversation(locked=True)
        unlocked_conv = _make_conversation(locked=False, conversation_id='conv-2')

        conversations_db.get_conversations_without_photos = MagicMock(return_value=[locked_conv, unlocked_conv])

        with patch('routers.conversations.auth') as mock_auth:
            mock_auth.get_current_user_uid = MagicMock(return_value='test-uid')

            from routers.conversations import get_conversations

            result = get_conversations(
                limit=100,
                offset=0,
                statuses='completed',
                include_discarded=False,
                start_date=None,
                end_date=None,
                folder_id=None,
                starred=None,
                uid='test-uid',
            )

        assert len(result) == 2
        locked = [c for c in result if c.get('is_locked')]
        assert len(locked) == 1
        assert locked[0]['structured']['action_items'] == []
        assert locked[0]['structured']['events'] == []
        assert locked[0]['transcript_segments'] == []

        unlocked = [c for c in result if not c.get('is_locked')]
        assert len(unlocked) == 1
        assert len(unlocked[0]['structured']['action_items']) == 1
        assert len(unlocked[0]['transcript_segments']) == 1


# =============================================================================
# Test suggest_goal excludes locked memories
# =============================================================================


class TestSuggestGoalLockFilter:
    """suggest_goal must exclude locked memories from context."""

    def test_suggest_goal_filters_locked_memories(self):
        """suggest_goal must not include locked memories in AI prompt context."""
        import database.memories as memories_db

        locked_mem = _make_memory(locked=True)
        locked_mem['content'] = 'LOCKED_SECRET'
        unlocked_mem = _make_memory(locked=False, memory_id='mem-2')
        unlocked_mem['content'] = 'visible goal-related memory'

        memories_db.get_memories = MagicMock(return_value=[locked_mem, unlocked_mem])

        mock_llm_response = MagicMock()
        mock_llm_response.content = '{"suggested_title": "Test Goal", "suggested_type": "scale", "suggested_target": 10, "suggested_min": 0, "suggested_max": 10, "reasoning": "test"}'

        mock_track = MagicMock()
        mock_track.__enter__ = MagicMock(return_value=None)
        mock_track.__exit__ = MagicMock(return_value=False)

        with patch('utils.llm.goals.track_usage', return_value=mock_track):
            with patch('utils.llm.goals.llm_mini') as mock_llm:
                mock_llm.invoke.return_value = mock_llm_response

                from utils.llm.goals import suggest_goal

                result = suggest_goal('test-uid')

        # Verify the prompt sent to the LLM did not contain locked content
        call_args = mock_llm.invoke.call_args[0][0]
        prompt_text = str(call_args)
        assert 'LOCKED_SECRET' not in prompt_text
        assert 'visible goal-related memory' in prompt_text


# =============================================================================
# Test MCP memory delete/edit — is_locked enforcement (#6511)
# =============================================================================


class TestMcpMemoryLockEnforcement:
    """Gaps 6-7: MCP REST delete/edit must reject locked memories."""

    def test_mcp_delete_memory_rejects_locked(self):
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=True))

        from routers.mcp import delete_memory

        try:
            delete_memory(memory_id='mem-1', uid='test-uid')
            assert False, "Should have raised HTTPException"
        except Exception as e:
            assert e.status_code == 402

    def test_mcp_delete_memory_allows_unlocked(self):
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=False))
        memories_db.delete_memory = MagicMock()

        from routers.mcp import delete_memory

        result = delete_memory(memory_id='mem-1', uid='test-uid')
        assert result == {"status": "ok"}
        memories_db.delete_memory.assert_called_once_with('test-uid', 'mem-1')

    def test_mcp_delete_memory_404_missing(self):
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=None)

        from routers.mcp import delete_memory

        try:
            delete_memory(memory_id='nonexistent', uid='test-uid')
            assert False, "Should have raised HTTPException"
        except Exception as e:
            assert e.status_code == 404

    def test_mcp_edit_memory_rejects_locked(self):
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=True))

        from routers.mcp import edit_memory

        try:
            edit_memory(memory_id='mem-1', value='new content', uid='test-uid')
            assert False, "Should have raised HTTPException"
        except Exception as e:
            assert e.status_code == 402

    def test_mcp_edit_memory_allows_unlocked(self):
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=False))
        memories_db.edit_memory = MagicMock()

        from routers.mcp import edit_memory

        result = edit_memory(memory_id='mem-1', value='new content', uid='test-uid')
        assert result == {"status": "ok"}
        memories_db.edit_memory.assert_called_once_with('test-uid', 'mem-1', 'new content')


# =============================================================================
# Test MCP SSE memory delete/edit — is_locked enforcement (#6511)
# =============================================================================


class TestMcpSseMemoryLockEnforcement:
    """Gaps 8-9: MCP SSE delete/edit must reject locked memories."""

    def test_mcp_sse_delete_memory_rejects_locked(self):
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=True))

        from routers.mcp_sse import execute_tool, ToolExecutionError

        try:
            execute_tool('test-uid', 'delete_memory', {'memory_id': 'mem-1'})
            assert False, "Should have raised ToolExecutionError"
        except ToolExecutionError as e:
            assert e.code == -32002
            assert 'paid plan' in e.message.lower()

    def test_mcp_sse_delete_memory_allows_unlocked(self):
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=False))
        memories_db.delete_memory = MagicMock()

        from routers.mcp_sse import execute_tool

        result = execute_tool('test-uid', 'delete_memory', {'memory_id': 'mem-1'})
        assert result == {"success": True}
        memories_db.delete_memory.assert_called_once_with('test-uid', 'mem-1')

    def test_mcp_sse_delete_memory_404_missing(self):
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=None)

        from routers.mcp_sse import execute_tool, ToolExecutionError

        try:
            execute_tool('test-uid', 'delete_memory', {'memory_id': 'nonexistent'})
            assert False, "Should have raised ToolExecutionError"
        except ToolExecutionError as e:
            assert e.code == -32001

    def test_mcp_sse_edit_memory_rejects_locked(self):
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=True))

        from routers.mcp_sse import execute_tool, ToolExecutionError

        try:
            execute_tool('test-uid', 'edit_memory', {'memory_id': 'mem-1', 'content': 'new'})
            assert False, "Should have raised ToolExecutionError"
        except ToolExecutionError as e:
            assert e.code == -32002

    def test_mcp_sse_edit_memory_allows_unlocked(self):
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=False))
        memories_db.edit_memory = MagicMock()

        from routers.mcp_sse import execute_tool

        result = execute_tool('test-uid', 'edit_memory', {'memory_id': 'mem-1', 'content': 'new'})
        assert result == {"success": True}
        memories_db.edit_memory.assert_called_once_with('test-uid', 'mem-1', 'new')


# =============================================================================
# Test folder move — is_locked enforcement (#6511)
# =============================================================================


class TestFolderMoveLockEnforcement:
    """Gap 10 + bonus: Folder move must reject locked conversations."""

    def test_move_conversation_rejects_locked(self):
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=True))

        from routers.folders import move_conversation_to_folder, MoveConversationRequest

        request = MoveConversationRequest(folder_id='folder-1')
        try:
            move_conversation_to_folder('conv-1', request, uid='test-uid')
            assert False, "Should have raised HTTPException"
        except Exception as e:
            assert e.status_code == 402

    def test_move_conversation_allows_unlocked(self):
        import database.conversations as conversations_db
        import database.folders as folders_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=False))
        folders_db.get_folder = MagicMock(return_value={'id': 'folder-1', 'name': 'Test'})
        folders_db.move_conversation_to_folder = MagicMock()

        from routers.folders import move_conversation_to_folder, MoveConversationRequest

        request = MoveConversationRequest(folder_id='folder-1')
        result = move_conversation_to_folder('conv-1', request, uid='test-uid')
        assert result == {"status": "ok"}

    def test_bulk_move_rejects_if_any_locked(self):
        import database.conversations as conversations_db
        import database.folders as folders_db

        conversations_db.get_conversation = MagicMock(
            side_effect=[
                _make_conversation(locked=False, conversation_id='conv-1'),
                _make_conversation(locked=True, conversation_id='conv-2'),
            ]
        )
        folders_db.get_folder = MagicMock(return_value={'id': 'folder-1', 'name': 'Test'})

        from routers.folders import bulk_move_conversations, BulkMoveConversationsRequest

        request = BulkMoveConversationsRequest(conversation_ids=['conv-1', 'conv-2'])
        try:
            bulk_move_conversations('folder-1', request, uid='test-uid')
            assert False, "Should have raised HTTPException"
        except Exception as e:
            assert e.status_code == 402

    def test_bulk_move_allows_all_unlocked(self):
        import database.conversations as conversations_db
        import database.folders as folders_db

        conversations_db.get_conversation = MagicMock(
            side_effect=[
                _make_conversation(locked=False, conversation_id='conv-1'),
                _make_conversation(locked=False, conversation_id='conv-2'),
            ]
        )
        folders_db.get_folder = MagicMock(return_value={'id': 'folder-1', 'name': 'Test'})
        folders_db.bulk_move_conversations_to_folder = MagicMock(return_value=2)

        from routers.folders import bulk_move_conversations, BulkMoveConversationsRequest

        request = BulkMoveConversationsRequest(conversation_ids=['conv-1', 'conv-2'])
        result = bulk_move_conversations('folder-1', request, uid='test-uid')
        assert result == {"status": "ok", "moved_count": 2}
