"""Tests for desktop profile generation handler (Phase 2 — #5396)."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault('firebase_admin', MagicMock())
sys.modules.setdefault('firebase_admin.auth', MagicMock())
sys.modules.setdefault('firebase_admin.firestore', MagicMock())
sys.modules.setdefault('database._client', MagicMock())
_mock_clients = MagicMock()
sys.modules.setdefault('utils.llm.clients', _mock_clients)

from utils.desktop.profile import (
    ProfileResult,
    PROFILE_SYSTEM_PROMPT,
    generate_profile,
)
from models.message_event import ProfileUpdatedEvent


class TestProfileResultModel:
    def test_profile_text(self):
        r = ProfileResult(profile_text="The user is a backend engineer focused on Python.")
        assert "backend engineer" in r.profile_text


class TestProfileUpdatedEvent:
    def test_event_structure(self):
        event = ProfileUpdatedEvent(profile_text="User profile text")
        data = event.to_json()
        assert data["type"] == "profile_updated"
        assert data["profile_text"] == "User profile text"


class TestGenerateProfile:
    @patch('utils.desktop.profile.get_memories')
    @patch('utils.desktop.profile.get_action_items')
    @patch('utils.desktop.profile.get_user_goals')
    @patch('utils.desktop.profile.llm_mini')
    def test_generates_profile(self, mock_llm, mock_goals, mock_tasks, mock_memories):
        mock_goals.return_value = [{'title': 'Ship v2'}]
        mock_tasks.return_value = [{'description': 'Fix auth bug'}]
        mock_memories.return_value = [{'structured': {'content': 'User prefers Python'}}]
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(
            return_value=ProfileResult(profile_text="The user is a developer focused on shipping v2.")
        )
        result = asyncio.get_event_loop().run_until_complete(generate_profile("uid1"))
        assert "developer" in result["profile_text"]

    @patch('utils.desktop.profile.get_memories')
    @patch('utils.desktop.profile.get_action_items')
    @patch('utils.desktop.profile.get_user_goals')
    def test_no_data_returns_default(self, mock_goals, mock_tasks, mock_memories):
        mock_goals.return_value = []
        mock_tasks.return_value = []
        mock_memories.return_value = []
        result = asyncio.get_event_loop().run_until_complete(generate_profile("uid1"))
        assert "No data available" in result["profile_text"]

    @patch('utils.desktop.profile.get_memories')
    @patch('utils.desktop.profile.get_action_items')
    @patch('utils.desktop.profile.get_user_goals')
    @patch('utils.desktop.profile.llm_mini')
    def test_graceful_on_db_errors(self, mock_llm, mock_goals, mock_tasks, mock_memories):
        mock_goals.side_effect = Exception("DB error")
        mock_tasks.side_effect = Exception("DB error")
        mock_memories.side_effect = Exception("DB error")
        result = asyncio.get_event_loop().run_until_complete(generate_profile("uid1"))
        assert "No data available" in result["profile_text"]

    @patch('utils.desktop.profile.get_memories')
    @patch('utils.desktop.profile.get_action_items')
    @patch('utils.desktop.profile.get_user_goals')
    @patch('utils.desktop.profile.llm_mini')
    def test_includes_goals_in_prompt(self, mock_llm, mock_goals, mock_tasks, mock_memories):
        mock_goals.return_value = [{'title': 'Learn Rust'}]
        mock_tasks.return_value = []
        mock_memories.return_value = []
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(
            return_value=ProfileResult(profile_text="Profile text")
        )
        asyncio.get_event_loop().run_until_complete(generate_profile("uid1"))
        call_args = mock_parser.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        assert "Learn Rust" in human_msg.content


class TestProfileSystemPrompt:
    def test_third_person_format(self):
        assert "third person" in PROFILE_SYSTEM_PROMPT

    def test_word_limit(self):
        assert "300 words" in PROFILE_SYSTEM_PROMPT

    def test_factual_requirement(self):
        assert "factual" in PROFILE_SYSTEM_PROMPT
