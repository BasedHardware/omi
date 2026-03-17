"""Tests for the LLM abuse detection classifier (utils/llm/abuse_detection.py)."""

import json
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing the module under test
# ---------------------------------------------------------------------------
_db_client = types.ModuleType('database._client')
_db_client.db = MagicMock()
sys.modules.setdefault('database._client', _db_client)

_redis_mod = types.ModuleType('database.redis_db')
_redis_mod.r = MagicMock()
sys.modules.setdefault('database.redis_db', _redis_mod)

sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.firestore_v1', MagicMock())

# Stub database.conversations
_conversations_db = types.ModuleType('database.conversations')
_conversations_db.get_conversations = MagicMock(return_value=[])
sys.modules.setdefault('database.conversations', _conversations_db)

# Stub llm clients
_llm_clients = types.ModuleType('utils.llm.clients')
_llm_clients.llm_mini = MagicMock()
sys.modules.setdefault('utils.llm.clients', _llm_clients)

import utils.llm.abuse_detection as abuse_mod


class TestSelectRecipes:
    """Test dynamic recipe selection based on conversation patterns."""

    def test_empty_conversations_returns_empty(self):
        result = abuse_mod._select_recipes([])
        assert result == ""

    def test_long_sessions_trigger_audiobook_recipe(self):
        summaries = [{'title': f'Session {i}', 'duration_minutes': 90, 'category': 'other'} for i in range(5)]
        result = abuse_mod._select_recipes(summaries)
        assert 'Audiobook Detection' in result

    def test_uniform_durations_trigger_prerecorded_recipe(self):
        # All sessions ~30 min (low coefficient of variation)
        summaries = [
            {'title': f'Session {i}', 'duration_minutes': 30 + (i % 3), 'category': 'other'} for i in range(10)
        ]
        result = abuse_mod._select_recipes(summaries)
        assert 'Pre-recorded Content Detection' in result

    def test_medium_sessions_trigger_podcast_recipe(self):
        summaries = [{'title': f'Episode {i}', 'duration_minutes': 45, 'category': 'media'} for i in range(6)]
        result = abuse_mod._select_recipes(summaries)
        assert 'Podcast Detection' in result

    def test_high_count_few_categories_trigger_commercial_recipe(self):
        summaries = [{'title': f'Call {i}', 'duration_minutes': 10, 'category': 'business'} for i in range(25)]
        result = abuse_mod._select_recipes(summaries)
        assert 'Commercial Use Detection' in result

    def test_varied_normal_usage_triggers_no_special_recipe(self):
        summaries = [
            {'title': 'Team standup', 'duration_minutes': 15, 'category': 'meeting'},
            {'title': 'Lunch chat', 'duration_minutes': 45, 'category': 'personal'},
            {'title': 'Project review', 'duration_minutes': 60, 'category': 'work'},
        ]
        result = abuse_mod._select_recipes(summaries)
        assert result == ""


class TestPrepareConversationSummaries:
    """Test conversation metadata extraction."""

    def test_empty_conversations(self):
        _conversations_db.get_conversations.return_value = []
        result = abuse_mod._prepare_conversation_summaries('user1')
        assert result == []

    def test_extracts_metadata_correctly(self):
        now = datetime.utcnow()
        _conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-1',
                'structured': {'title': 'My Meeting', 'overview': 'We discussed plans', 'category': 'work'},
                'started_at': now - timedelta(hours=1),
                'finished_at': now,
                'source': 'omi',
                'created_at': now,
            }
        ]
        result = abuse_mod._prepare_conversation_summaries('user1')
        assert len(result) == 1
        assert result[0]['title'] == 'My Meeting'
        assert result[0]['category'] == 'work'
        assert result[0]['duration_minutes'] == pytest.approx(60.0, abs=0.5)

    def test_handles_missing_structured_fields(self):
        _conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-2',
                'structured': None,
                'started_at': None,
                'finished_at': None,
                'source': 'omi',
                'created_at': datetime.utcnow(),
            }
        ]
        result = abuse_mod._prepare_conversation_summaries('user1')
        assert len(result) == 1
        assert result[0]['title'] == ''
        assert result[0]['duration_minutes'] == 0

    def test_truncates_long_overviews(self):
        long_overview = 'x' * 500
        _conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-3',
                'structured': {'title': 'Test', 'overview': long_overview, 'category': 'other'},
                'started_at': datetime.utcnow(),
                'finished_at': datetime.utcnow(),
                'source': 'omi',
                'created_at': datetime.utcnow(),
            }
        ]
        result = abuse_mod._prepare_conversation_summaries('user1')
        assert len(result[0]['overview']) == 200


class TestClassifyUserPurpose:
    """Test the async LLM classification function."""

    @pytest.mark.asyncio
    async def test_returns_default_when_no_conversations(self):
        _conversations_db.get_conversations.return_value = []
        result = await abuse_mod.classify_user_purpose('user1')
        assert result['abuse_score'] == 0.0
        assert result['abuse_type'] == 'none'

    @pytest.mark.asyncio
    async def test_parses_llm_response_correctly(self):
        now = datetime.utcnow()
        _conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-1',
                'structured': {'title': 'Harry Potter Chapter 12', 'overview': 'Book reading', 'category': 'other'},
                'started_at': now - timedelta(hours=2),
                'finished_at': now,
                'source': 'omi',
                'created_at': now,
            }
        ]

        llm_response = MagicMock()
        llm_response.content = json.dumps(
            {
                'abuse_score': 0.92,
                'abuse_type': 'audiobook',
                'confidence': 0.95,
                'evidence': [{'conversation_id': 'conv-1', 'title': 'Harry Potter Chapter 12', 'reason': 'Book title'}],
                'reasoning': 'Clear audiobook pattern',
            }
        )
        _llm_clients.llm_mini.ainvoke = AsyncMock(return_value=llm_response)

        result = await abuse_mod.classify_user_purpose('user1')

        assert result['abuse_score'] == pytest.approx(0.92)
        assert result['abuse_type'] == 'audiobook'
        assert result['confidence'] == pytest.approx(0.95)
        assert len(result['evidence']) == 1

    @pytest.mark.asyncio
    async def test_handles_markdown_code_block_response(self):
        now = datetime.utcnow()
        _conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-1',
                'structured': {'title': 'Test', 'overview': 'Test', 'category': 'other'},
                'started_at': now,
                'finished_at': now,
                'source': 'omi',
                'created_at': now,
            }
        ]

        llm_response = MagicMock()
        llm_response.content = '```json\n{"abuse_score": 0.1, "abuse_type": "none", "confidence": 0.9, "evidence": [], "reasoning": "Normal"}\n```'
        _llm_clients.llm_mini.ainvoke = AsyncMock(return_value=llm_response)

        result = await abuse_mod.classify_user_purpose('user1')
        assert result['abuse_score'] == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_clamps_score_to_valid_range(self):
        now = datetime.utcnow()
        _conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-1',
                'structured': {'title': 'T', 'overview': '', 'category': ''},
                'started_at': now,
                'finished_at': now,
                'source': 'omi',
                'created_at': now,
            }
        ]

        llm_response = MagicMock()
        llm_response.content = json.dumps(
            {'abuse_score': 1.5, 'abuse_type': 'none', 'confidence': -0.2, 'evidence': [], 'reasoning': ''}
        )
        _llm_clients.llm_mini.ainvoke = AsyncMock(return_value=llm_response)

        result = await abuse_mod.classify_user_purpose('user1')
        assert result['abuse_score'] == 1.0
        assert result['confidence'] == 0.0

    @pytest.mark.asyncio
    async def test_returns_default_on_json_parse_error(self):
        now = datetime.utcnow()
        _conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-1',
                'structured': {'title': 'T', 'overview': '', 'category': ''},
                'started_at': now,
                'finished_at': now,
                'source': 'omi',
                'created_at': now,
            }
        ]

        llm_response = MagicMock()
        llm_response.content = 'This is not JSON at all'
        _llm_clients.llm_mini.ainvoke = AsyncMock(return_value=llm_response)

        result = await abuse_mod.classify_user_purpose('user1')
        assert result['abuse_score'] == 0.0
        assert result['abuse_type'] == 'none'

    @pytest.mark.asyncio
    async def test_returns_default_on_llm_error(self):
        now = datetime.utcnow()
        _conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-1',
                'structured': {'title': 'T', 'overview': '', 'category': ''},
                'started_at': now,
                'finished_at': now,
                'source': 'omi',
                'created_at': now,
            }
        ]
        _llm_clients.llm_mini.ainvoke = AsyncMock(side_effect=Exception('LLM timeout'))

        result = await abuse_mod.classify_user_purpose('user1')
        assert result['abuse_score'] == 0.0
