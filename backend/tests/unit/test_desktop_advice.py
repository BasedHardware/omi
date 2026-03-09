"""Tests for desktop advice handler (Phase 2 — #5396)."""

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

from utils.desktop.advice import (
    AdviceResult,
    ADVICE_SYSTEM_PROMPT,
    _build_advice_context,
    generate_advice,
)
from models.message_event import AdviceExtractedEvent


class TestAdviceResultModel:
    def test_advice_with_content(self):
        r = AdviceResult(has_advice=True, content="Take a break", category="health", confidence=0.8)
        assert r.has_advice is True
        assert r.content == "Take a break"
        assert r.category == "health"

    def test_no_advice(self):
        r = AdviceResult(has_advice=False, confidence=0.1)
        assert r.has_advice is False
        assert r.content is None
        assert r.category is None

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            AdviceResult(has_advice=True, confidence=2.0)


class TestAdviceExtractedEvent:
    def test_event_with_advice(self):
        event = AdviceExtractedEvent(
            frame_id="frame789",
            advice={"content": "Try dark mode", "category": "productivity", "confidence": 0.7},
        )
        data = event.to_json()
        assert data["type"] == "advice_extracted"
        assert data["frame_id"] == "frame789"
        assert data["advice"]["content"] == "Try dark mode"

    def test_event_no_advice(self):
        event = AdviceExtractedEvent(frame_id="frame789", advice=None)
        data = event.to_json()
        assert data["advice"] is None


class TestBuildAdviceContext:
    @patch('utils.desktop.advice.get_action_items')
    @patch('utils.desktop.advice.get_user_goals')
    def test_goals_and_tasks_in_context(self, mock_goals, mock_tasks):
        mock_goals.return_value = [{'title': 'Ship v2'}]
        mock_tasks.return_value = [{'description': 'Write tests'}]
        ctx = _build_advice_context("uid1")
        assert "Ship v2" in ctx
        assert "Write tests" in ctx

    @patch('utils.desktop.advice.get_action_items')
    @patch('utils.desktop.advice.get_user_goals')
    def test_empty_context(self, mock_goals, mock_tasks):
        mock_goals.return_value = []
        mock_tasks.return_value = []
        ctx = _build_advice_context("uid1")
        assert ctx == ""

    @patch('utils.desktop.advice.get_action_items')
    @patch('utils.desktop.advice.get_user_goals')
    def test_graceful_on_errors(self, mock_goals, mock_tasks):
        mock_goals.side_effect = Exception("DB error")
        mock_tasks.side_effect = Exception("DB error")
        ctx = _build_advice_context("uid1")
        assert ctx == ""

    @patch('utils.desktop.advice.get_action_items')
    @patch('utils.desktop.advice.get_user_goals')
    def test_goals_fallback_to_description(self, mock_goals, mock_tasks):
        mock_goals.return_value = [{'description': 'Fallback goal'}]
        mock_tasks.return_value = []
        ctx = _build_advice_context("uid1")
        assert "Fallback goal" in ctx


class TestGenerateAdvice:
    @patch('utils.desktop.advice._build_advice_context')
    @patch('utils.desktop.advice.llm_gemini_flash')
    def test_returns_advice(self, mock_llm, mock_ctx):
        mock_ctx.return_value = ""
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(
            return_value=AdviceResult(
                has_advice=True,
                content="Consider using a linter",
                category="productivity",
                confidence=0.75,
            )
        )
        result = asyncio.get_event_loop().run_until_complete(generate_advice("uid1", "base64img", "VS Code", "main.py"))
        assert result["has_advice"] is True
        assert result["advice"]["content"] == "Consider using a linter"
        assert result["advice"]["category"] == "productivity"

    @patch('utils.desktop.advice._build_advice_context')
    @patch('utils.desktop.advice.llm_gemini_flash')
    def test_no_advice(self, mock_llm, mock_ctx):
        mock_ctx.return_value = ""
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(return_value=AdviceResult(has_advice=False, confidence=0.1))
        result = asyncio.get_event_loop().run_until_complete(generate_advice("uid1", "base64img"))
        assert result["has_advice"] is False
        assert result["advice"] is None

    @patch('utils.desktop.advice._build_advice_context')
    @patch('utils.desktop.advice.llm_gemini_flash')
    def test_includes_app_info(self, mock_llm, mock_ctx):
        mock_ctx.return_value = ""
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(return_value=AdviceResult(has_advice=False, confidence=0.1))
        asyncio.get_event_loop().run_until_complete(generate_advice("uid1", "base64img", "Chrome", "Stack Overflow"))
        call_args = mock_parser.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        text_content = human_msg.content[0]["text"]
        assert "Chrome" in text_content
        assert "Stack Overflow" in text_content


class TestAdviceSystemPrompt:
    def test_includes_categories(self):
        assert "productivity" in ADVICE_SYSTEM_PROMPT
        assert "mistake_prevention" in ADVICE_SYSTEM_PROMPT
        assert "health" in ADVICE_SYSTEM_PROMPT
        assert "goal_alignment" in ADVICE_SYSTEM_PROMPT

    def test_includes_tone_guidance(self):
        assert "TONE" in ADVICE_SYSTEM_PROMPT
