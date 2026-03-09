"""Tests for desktop live notes handler (Phase 2 — #5396)."""

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

from utils.desktop.live_notes import (
    LiveNoteResult,
    LIVE_NOTES_SYSTEM_PROMPT,
    generate_live_note,
)
from models.message_event import LiveNoteEvent


class TestLiveNoteResultModel:
    def test_note_with_text(self):
        r = LiveNoteResult(text="Key decision: ship by Friday")
        assert r.text == "Key decision: ship by Friday"

    def test_empty_note(self):
        r = LiveNoteResult(text="")
        assert r.text == ""


class TestLiveNoteEvent:
    def test_event_structure(self):
        event = LiveNoteEvent(text="Meeting note content")
        data = event.to_json()
        assert data["type"] == "live_note"
        assert data["text"] == "Meeting note content"


class TestGenerateLiveNote:
    @patch('utils.desktop.live_notes.llm_mini')
    def test_returns_note(self, mock_llm):
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(return_value=LiveNoteResult(text="- Decision: use Redis for caching"))
        result = asyncio.get_event_loop().run_until_complete(
            generate_live_note("We decided to use Redis for caching the API responses")
        )
        assert result["text"] == "- Decision: use Redis for caching"

    @patch('utils.desktop.live_notes.llm_mini')
    def test_empty_result(self, mock_llm):
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(return_value=LiveNoteResult(text=""))
        result = asyncio.get_event_loop().run_until_complete(generate_live_note("um yeah so like um"))
        assert result["text"] == ""

    @patch('utils.desktop.live_notes.llm_mini')
    def test_includes_session_context(self, mock_llm):
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(return_value=LiveNoteResult(text="note"))
        asyncio.get_event_loop().run_until_complete(
            generate_live_note("transcript text", session_context="Sprint planning")
        )
        call_args = mock_parser.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        assert "Sprint planning" in human_msg.content

    @patch('utils.desktop.live_notes.llm_mini')
    def test_sends_system_prompt(self, mock_llm):
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(return_value=LiveNoteResult(text=""))
        asyncio.get_event_loop().run_until_complete(generate_live_note("test text"))
        call_args = mock_parser.ainvoke.call_args[0][0]
        sys_msg = call_args[0]
        assert LIVE_NOTES_SYSTEM_PROMPT in sys_msg.content


class TestLiveNotesSystemPrompt:
    def test_includes_condensation_rules(self):
        assert "Condense" in LIVE_NOTES_SYSTEM_PROMPT

    def test_includes_word_limit(self):
        assert "200 words" in LIVE_NOTES_SYSTEM_PROMPT

    def test_includes_preservation_rules(self):
        assert "names" in LIVE_NOTES_SYSTEM_PROMPT
        assert "decisions" in LIVE_NOTES_SYSTEM_PROMPT
