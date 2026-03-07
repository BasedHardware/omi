"""Tests for desktop memory extraction handler (Phase 2 — #5396)."""

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

from utils.desktop.memories import (
    ExtractedMemory,
    MemoryExtractionResult,
    MEMORY_SYSTEM_PROMPT,
    _build_memory_context,
    extract_memories,
)
from models.message_event import MemoriesExtractedEvent


class TestExtractedMemoryModel:
    def test_memory_all_fields(self):
        m = ExtractedMemory(content="User prefers dark mode", category="system", confidence=0.95)
        assert m.content == "User prefers dark mode"
        assert m.category == "system"
        assert m.confidence == 0.95

    def test_memory_interesting_category(self):
        m = ExtractedMemory(content="AI tip from article", category="interesting", confidence=0.7)
        assert m.category == "interesting"

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            ExtractedMemory(content="test", category="system", confidence=1.5)


class TestMemoryExtractionResult:
    def test_result_with_memories(self):
        result = MemoryExtractionResult(
            memories=[ExtractedMemory(content="Fact 1", category="system", confidence=0.8)]
        )
        assert len(result.memories) == 1

    def test_result_empty(self):
        result = MemoryExtractionResult()
        assert result.memories == []


class TestMemoriesExtractedEvent:
    def test_event_structure(self):
        event = MemoriesExtractedEvent(
            frame_id="frame456",
            memories=[{"content": "Test fact", "category": "system", "confidence": 0.9}],
        )
        data = event.to_json()
        assert data["type"] == "memories_extracted"
        assert data["frame_id"] == "frame456"
        assert len(data["memories"]) == 1


class TestBuildMemoryContext:
    @patch('utils.desktop.memories.get_memories')
    def test_existing_memories_in_context(self, mock_get):
        mock_get.return_value = [
            {'structured': {'content': 'User likes Python'}},
            {'content': 'Fallback content'},
        ]
        ctx = _build_memory_context("uid1")
        assert "User likes Python" in ctx
        assert "Fallback content" in ctx
        assert "DO NOT extract duplicates" in ctx

    @patch('utils.desktop.memories.get_memories')
    def test_empty_context(self, mock_get):
        mock_get.return_value = []
        ctx = _build_memory_context("uid1")
        assert ctx == ""

    @patch('utils.desktop.memories.get_memories')
    def test_graceful_on_errors(self, mock_get):
        mock_get.side_effect = Exception("DB error")
        ctx = _build_memory_context("uid1")
        assert ctx == ""


class TestExtractMemories:
    @patch('utils.desktop.memories._build_memory_context')
    @patch('utils.desktop.memories.llm_gemini_flash')
    def test_extract_returns_memories(self, mock_llm, mock_ctx):
        mock_ctx.return_value = ""
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(
            return_value=MemoryExtractionResult(
                memories=[
                    ExtractedMemory(content="User works on Omi project", category="system", confidence=0.85),
                ]
            )
        )
        result = asyncio.get_event_loop().run_until_complete(
            extract_memories("uid1", "base64img", "VS Code", "omi/main.py")
        )
        assert len(result["memories"]) == 1
        assert result["memories"][0]["content"] == "User works on Omi project"
        assert result["memories"][0]["category"] == "system"

    @patch('utils.desktop.memories._build_memory_context')
    @patch('utils.desktop.memories.llm_gemini_flash')
    def test_extract_empty_result(self, mock_llm, mock_ctx):
        mock_ctx.return_value = ""
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(return_value=MemoryExtractionResult())
        result = asyncio.get_event_loop().run_until_complete(
            extract_memories("uid1", "base64img")
        )
        assert result["memories"] == []

    @patch('utils.desktop.memories._build_memory_context')
    @patch('utils.desktop.memories.llm_gemini_flash')
    def test_sends_image_and_system_prompt(self, mock_llm, mock_ctx):
        mock_ctx.return_value = ""
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(return_value=MemoryExtractionResult())
        asyncio.get_event_loop().run_until_complete(
            extract_memories("uid1", "testimg64")
        )
        call_args = mock_parser.ainvoke.call_args[0][0]
        sys_msg = call_args[0]
        human_msg = call_args[1]
        assert MEMORY_SYSTEM_PROMPT in sys_msg.content
        assert human_msg.content[1]["image_url"]["url"] == "data:image/jpeg;base64,testimg64"


class TestMemorySystemPrompt:
    def test_includes_extraction_rules(self):
        assert "EXTRACTION RULES" in MEMORY_SYSTEM_PROMPT

    def test_includes_dedup(self):
        assert "DEDUPLICATION" in MEMORY_SYSTEM_PROMPT

    def test_includes_categories(self):
        assert "system" in MEMORY_SYSTEM_PROMPT
        assert "interesting" in MEMORY_SYSTEM_PROMPT
