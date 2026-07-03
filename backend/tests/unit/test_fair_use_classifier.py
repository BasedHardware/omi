"""Tests for the LLM fair-use classifier (utils/llm/fair_use_classifier.py)."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

import utils.llm.fair_use_classifier as classifier_mod


@pytest.fixture
def conversations_db(monkeypatch):
    """Fake database.conversations patched onto the module under test."""
    fake = MagicMock()
    fake.get_conversations = MagicMock(return_value=[])
    monkeypatch.setattr(classifier_mod, 'conversations_db', fake)
    return fake


@pytest.fixture
def classifier_llm(monkeypatch):
    """Fake classifier LLM patched onto the module under test."""
    fake = MagicMock()
    monkeypatch.setattr(classifier_mod, '_classifier_llm', fake)
    return fake


class TestSelectRecipes:
    """Test dynamic recipe selection based on conversation patterns."""

    def test_empty_conversations_returns_empty(self):
        result = classifier_mod._select_recipes([])
        assert result == ""

    def test_long_sessions_trigger_audiobook_recipe(self):
        summaries = [{'title': f'Session {i}', 'duration_minutes': 90, 'category': 'other'} for i in range(5)]
        result = classifier_mod._select_recipes(summaries)
        assert 'Audiobook Detection' in result

    def test_uniform_durations_trigger_prerecorded_recipe(self):
        # All sessions ~30 min (low coefficient of variation)
        summaries = [
            {'title': f'Session {i}', 'duration_minutes': 30 + (i % 3), 'category': 'other'} for i in range(10)
        ]
        result = classifier_mod._select_recipes(summaries)
        assert 'Pre-recorded Content Detection' in result

    def test_medium_sessions_trigger_podcast_recipe(self):
        summaries = [{'title': f'Episode {i}', 'duration_minutes': 45, 'category': 'media'} for i in range(6)]
        result = classifier_mod._select_recipes(summaries)
        assert 'Podcast Detection' in result

    def test_high_count_few_categories_trigger_commercial_recipe(self):
        summaries = [{'title': f'Call {i}', 'duration_minutes': 10, 'category': 'business'} for i in range(25)]
        result = classifier_mod._select_recipes(summaries)
        assert 'Commercial Use Detection' in result

    def test_varied_normal_usage_triggers_no_special_recipe(self):
        summaries = [
            {'title': 'Team standup', 'duration_minutes': 15, 'category': 'meeting'},
            {'title': 'Lunch chat', 'duration_minutes': 45, 'category': 'personal'},
            {'title': 'Project review', 'duration_minutes': 60, 'category': 'work'},
        ]
        result = classifier_mod._select_recipes(summaries)
        assert result == ""


class TestPrepareConversationSummaries:
    """Test conversation metadata extraction."""

    def test_empty_conversations(self, conversations_db):
        conversations_db.get_conversations.return_value = []
        result = classifier_mod._prepare_conversation_summaries('user1')
        assert result == []

    def test_extracts_metadata_correctly(self, conversations_db):
        now = datetime.utcnow()
        conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-1',
                'structured': {'title': 'My Meeting', 'overview': 'We discussed plans', 'category': 'work'},
                'started_at': now - timedelta(hours=1),
                'finished_at': now,
                'source': 'omi',
                'created_at': now,
            }
        ]
        result = classifier_mod._prepare_conversation_summaries('user1')
        assert len(result) == 1
        assert result[0]['title'] == 'My Meeting'
        assert result[0]['category'] == 'work'
        assert result[0]['duration_minutes'] == pytest.approx(60.0, abs=0.5)

    def test_handles_missing_structured_fields(self, conversations_db):
        conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-2',
                'structured': None,
                'started_at': None,
                'finished_at': None,
                'source': 'omi',
                'created_at': datetime.utcnow(),
            }
        ]
        result = classifier_mod._prepare_conversation_summaries('user1')
        assert len(result) == 1
        assert result[0]['title'] == ''
        assert result[0]['duration_minutes'] == 0

    def test_truncates_long_overviews(self, conversations_db):
        long_overview = 'x' * 500
        conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-3',
                'structured': {'title': 'Test', 'overview': long_overview, 'category': 'other'},
                'started_at': datetime.utcnow(),
                'finished_at': datetime.utcnow(),
                'source': 'omi',
                'created_at': datetime.utcnow(),
            }
        ]
        result = classifier_mod._prepare_conversation_summaries('user1')
        assert len(result[0]['overview']) == 200


class TestClassifyUserPurpose:
    """Test the async LLM classification function."""

    @pytest.mark.asyncio
    async def test_returns_default_when_no_conversations(self, conversations_db, classifier_llm):
        conversations_db.get_conversations.return_value = []
        result = await classifier_mod.classify_user_purpose('user1')
        assert result['misuse_score'] == 0.0
        assert result['usage_type'] == 'none'

    @pytest.mark.asyncio
    async def test_parses_llm_response_correctly(self, conversations_db, classifier_llm):
        now = datetime.utcnow()
        conversations_db.get_conversations.return_value = [
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
                'misuse_score': 0.92,
                'usage_type': 'audiobook',
                'confidence': 0.95,
                'evidence': [{'conversation_id': 'conv-1', 'title': 'Harry Potter Chapter 12', 'reason': 'Book title'}],
                'reasoning': 'Clear audiobook pattern',
            }
        )
        classifier_llm.ainvoke = AsyncMock(return_value=llm_response)

        result = await classifier_mod.classify_user_purpose('user1')

        assert result['misuse_score'] == pytest.approx(0.92)
        assert result['usage_type'] == 'audiobook'
        assert result['confidence'] == pytest.approx(0.95)
        assert len(result['evidence']) == 1

    @pytest.mark.asyncio
    async def test_handles_markdown_code_block_response(self, conversations_db, classifier_llm):
        now = datetime.utcnow()
        conversations_db.get_conversations.return_value = [
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
        llm_response.content = '```json\n{"misuse_score": 0.1, "usage_type": "none", "confidence": 0.9, "evidence": [], "reasoning": "Normal"}\n```'
        classifier_llm.ainvoke = AsyncMock(return_value=llm_response)

        result = await classifier_mod.classify_user_purpose('user1')
        assert result['misuse_score'] == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_clamps_score_to_valid_range(self, conversations_db, classifier_llm):
        now = datetime.utcnow()
        conversations_db.get_conversations.return_value = [
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
            {'misuse_score': 1.5, 'usage_type': 'none', 'confidence': -0.2, 'evidence': [], 'reasoning': ''}
        )
        classifier_llm.ainvoke = AsyncMock(return_value=llm_response)

        result = await classifier_mod.classify_user_purpose('user1')
        assert result['misuse_score'] == 1.0
        assert result['confidence'] == 0.0

    @pytest.mark.asyncio
    async def test_returns_default_on_json_parse_error(self, conversations_db, classifier_llm):
        now = datetime.utcnow()
        conversations_db.get_conversations.return_value = [
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
        classifier_llm.ainvoke = AsyncMock(return_value=llm_response)

        result = await classifier_mod.classify_user_purpose('user1')
        assert result['misuse_score'] == 0.0
        assert result['usage_type'] == 'none'

    @pytest.mark.asyncio
    async def test_returns_default_on_llm_error(self, conversations_db, classifier_llm):
        now = datetime.utcnow()
        conversations_db.get_conversations.return_value = [
            {
                'id': 'conv-1',
                'structured': {'title': 'T', 'overview': '', 'category': ''},
                'started_at': now,
                'finished_at': now,
                'source': 'omi',
                'created_at': now,
            }
        ]
        classifier_llm.ainvoke = AsyncMock(side_effect=Exception('LLM timeout'))

        result = await classifier_mod.classify_user_purpose('user1')
        assert result['misuse_score'] == 0.0
