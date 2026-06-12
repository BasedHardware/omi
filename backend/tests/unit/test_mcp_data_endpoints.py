"""Unit tests for the new MCP data endpoints/tools: action items, goals, chat,
people, screen activity, and daily summaries.

Tests both the REST handlers (routers/mcp.py) and the MCP tool dispatch
(routers/mcp_sse.py) with mocked database calls, following the heavy-dep
stubbing pattern in test_mcp_search_memories.py.
"""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import os
import sys
from types import ModuleType

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')


class _AutoMockModule(ModuleType):
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
    'database.screen_activity',
    'database.x_posts',
    'database.fair_use',
    'database.auth',
    'database.dev_api_key',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.FieldFilter',
    'google',
    'google.cloud',
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
    'utils.conversations.render',
    'utils.notifications',
    'utils.apps',
    'utils.llm.memories',
    'utils.llm.chat',
    'utils.log_sanitizer',
    'utils.executors',
    'dependencies',
]
for mod_name in _stubs:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = _AutoMockModule(mod_name)

sys.modules['dependencies'].get_uid_from_mcp_api_key = MagicMock(return_value='user-1')
sys.modules['dependencies'].get_current_user_id = MagicMock(return_value='user-1')
sys.modules['utils.other.endpoints'].with_rate_limit = MagicMock(side_effect=lambda dependency, _policy: dependency)
sys.modules['utils.other.endpoints'].check_rate_limit_inline = MagicMock()
sys.modules['utils.apps'].update_personas_async = MagicMock()
sys.modules['utils.executors'].db_executor = MagicMock()
sys.modules['utils.executors'].postprocess_executor = MagicMock()
sys.modules['utils.llm.memories'].identify_category_for_memory = MagicMock(return_value='other')
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].ExpiredIdTokenError = type('ExpiredIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].RevokedIdTokenError = type('RevokedIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].CertificateFetchError = type('CertificateFetchError', (Exception,), {})
sys.modules['firebase_admin.auth'].UserNotFoundError = type('UserNotFoundError', (Exception,), {})

from routers import mcp as rest  # noqa: E402
from routers import mcp_sse as sse  # noqa: E402

NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)
UID = "user-1"


def _action_item(item_id='a1', desc='Email Bob', completed=False, deleted=False, locked=False):
    return {
        'id': item_id,
        'description': desc,
        'completed': completed,
        'created_at': NOW,
        'due_at': NOW,
        'completed_at': None,
        'conversation_id': 'conv-1',
        'deleted': deleted,
        'is_locked': locked,
    }


class TestActionItems:
    @patch('routers.mcp.action_items_db')
    def test_rest_returns_items_and_drops_deleted(self, mock_db):
        mock_db.get_action_items.return_value = [_action_item('a1'), _action_item('a2', deleted=True)]
        result = rest.get_action_items(uid=UID)
        assert [i['id'] for i in result] == ['a1']
        assert result[0]['description'] == 'Email Bob'

    @patch('routers.mcp.action_items_db')
    def test_rest_limit_clamped(self, mock_db):
        mock_db.get_action_items.return_value = []
        rest.get_action_items(limit=99999, uid=UID)
        _, kwargs = mock_db.get_action_items.call_args
        assert kwargs['limit'] == 500

    @patch('routers.mcp_sse.action_items_db')
    def test_tool_dispatch(self, mock_db):
        mock_db.get_action_items.return_value = [_action_item('a1'), _action_item('a2', deleted=True)]
        result = sse.execute_tool(UID, 'get_action_items', {'completed': False})
        assert [i['id'] for i in result['action_items']] == ['a1']

    @patch('routers.mcp_sse.action_items_db')
    def test_tool_rejects_bad_date(self, mock_db):
        with pytest.raises(sse.ToolExecutionError):
            sse.execute_tool(UID, 'get_action_items', {'due_start_date': 'not-a-date'})

    @patch('routers.mcp_sse.action_items_db')
    def test_locked_description_truncated(self, mock_db):
        long_desc = 'x' * 200
        mock_db.get_action_items.return_value = [_action_item('a1', desc=long_desc, locked=True)]
        result = sse.execute_tool(UID, 'get_action_items', {})
        assert result['action_items'][0]['description'].endswith('...')
        assert len(result['action_items'][0]['description']) == 73


class TestGoals:
    @patch('routers.mcp.goals_db')
    def test_rest(self, mock_db):
        mock_db.get_all_goals.return_value = [{'id': 'g1', 'title': 'Ship MCP', 'is_active': True}]
        result = rest.get_goals(uid=UID)
        assert result[0]['title'] == 'Ship MCP'
        mock_db.get_all_goals.assert_called_once_with(UID, include_inactive=False)

    @patch('routers.mcp_sse.goals_db')
    def test_tool(self, mock_db):
        mock_db.get_all_goals.return_value = [{'id': 'g1', 'title': 'Ship MCP'}]
        result = sse.execute_tool(UID, 'get_goals', {'include_inactive': True})
        assert result['goals'][0]['id'] == 'g1'
        mock_db.get_all_goals.assert_called_once_with(UID, include_inactive=True)


class TestChat:
    @patch('routers.mcp.chat_db')
    def test_rest_shapes_message(self, mock_db):
        mock_db.get_messages.return_value = [
            {'id': 'm1', 'text': 'hi', 'sender': 'human', 'type': 'text', 'created_at': NOW, 'files_id': []}
        ]
        result = rest.get_chat_messages(uid=UID)
        assert result == [{'id': 'm1', 'text': 'hi', 'sender': 'human', 'type': 'text', 'created_at': NOW}]

    @patch('routers.mcp_sse.chat_db')
    def test_tool(self, mock_db):
        mock_db.get_messages.return_value = [{'id': 'm1', 'text': 'hi', 'sender': 'ai', 'type': 'text'}]
        result = sse.execute_tool(UID, 'get_chat_messages', {'limit': 10})
        assert result['messages'][0]['sender'] == 'ai'


class TestPeople:
    def _person(self):
        return {
            'id': 'p1',
            'name': 'Bob',
            'created_at': NOW,
            'speech_sample_transcripts': ['hello there', 'how are you'],
            'speech_samples': ['gs://bucket/secret.wav'],
            'speaker_embedding': [0.1, 0.2, 0.3],
        }

    @patch('routers.mcp.users_db')
    def test_rest_drops_audio_and_embeddings(self, mock_db):
        mock_db.get_people.return_value = [self._person()]
        result = rest.get_people(uid=UID)
        assert result[0]['name'] == 'Bob'
        assert 'speech_samples' not in result[0]
        assert 'speaker_embedding' not in result[0]
        assert result[0]['speech_sample_transcripts'] == ['hello there', 'how are you']

    @patch('routers.mcp_sse.users_db')
    def test_tool(self, mock_db):
        mock_db.get_people.return_value = [self._person()]
        result = sse.execute_tool(UID, 'get_people', {})
        assert result['people'][0]['id'] == 'p1'
        assert 'speech_samples' not in result['people'][0]


class TestScreenActivity:
    def _row(self):
        return {
            'id': 's1',
            'timestamp': '2026-06-11 10:00:00.000',
            'appName': 'Cursor',
            'windowTitle': 'mcp.py',
            'ocrText': 'def foo',
        }

    @patch('routers.mcp.screen_activity_db')
    def test_rest_rows(self, mock_db):
        mock_db.get_screen_activity.return_value = [self._row()]
        result = rest.get_screen_activity(uid=UID)
        assert result == [
            {
                'id': 's1',
                'timestamp': '2026-06-11 10:00:00.000',
                'app_name': 'Cursor',
                'window_title': 'mcp.py',
                'ocr_text': 'def foo',
            }
        ]

    @patch('routers.mcp.screen_activity_db')
    def test_rest_summary_mode(self, mock_db):
        mock_db.get_screen_activity_summary.return_value = {'apps': {'Cursor': {'count': 1}}, 'total_screenshots': 1}
        result = rest.get_screen_activity(summary=True, uid=UID)
        assert result['total_screenshots'] == 1
        mock_db.get_screen_activity.assert_not_called()

    @patch('routers.mcp_sse.screen_activity_db')
    def test_tool_rows(self, mock_db):
        mock_db.get_screen_activity.return_value = [self._row()]
        result = sse.execute_tool(UID, 'get_screen_activity', {'limit': 5})
        assert result['screen_activity'][0]['app_name'] == 'Cursor'

    @patch('routers.mcp_sse.screen_activity_db')
    def test_tool_summary(self, mock_db):
        mock_db.get_screen_activity_summary.return_value = {'apps': {}, 'total_screenshots': 0}
        result = sse.execute_tool(UID, 'get_screen_activity', {'summary': True})
        assert result['total_screenshots'] == 0


class TestDailySummaries:
    @patch('routers.mcp.daily_summaries_db')
    def test_rest(self, mock_db):
        mock_db.get_daily_summaries.return_value = [{'date': '2026-06-11', 'content': 'Worked on MCP'}]
        result = rest.get_daily_summaries(uid=UID)
        assert result[0]['date'] == '2026-06-11'

    @patch('routers.mcp_sse.daily_summaries_db')
    def test_tool(self, mock_db):
        mock_db.get_daily_summaries.return_value = [{'date': '2026-06-11', 'content': 'x'}]
        result = sse.execute_tool(UID, 'get_daily_summaries', {'limit': 5})
        assert result['daily_summaries'][0]['date'] == '2026-06-11'


class TestToolRegistry:
    def test_new_tools_registered(self):
        names = {t['name'] for t in sse.MCP_TOOLS}
        for expected in [
            'get_action_items',
            'get_goals',
            'get_chat_messages',
            'get_people',
            'get_screen_activity',
            'get_daily_summaries',
        ]:
            assert expected in names, f"{expected} missing from MCP_TOOLS"

    def test_every_tool_has_a_dispatch_branch(self):
        # Each declared read-only data tool must dispatch (not fall through to "Unknown tool").
        for name in ['get_action_items', 'get_goals', 'get_chat_messages', 'get_people', 'get_daily_summaries']:
            with patch.object(sse, 'action_items_db'), patch.object(sse, 'goals_db'), patch.object(
                sse, 'chat_db'
            ), patch.object(sse, 'users_db'), patch.object(sse, 'daily_summaries_db'):
                try:
                    sse.execute_tool(UID, name, {})
                except sse.ToolExecutionError as e:
                    assert 'Unknown tool' not in e.message
