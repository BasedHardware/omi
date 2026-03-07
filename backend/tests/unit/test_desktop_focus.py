"""Tests for desktop focus analysis (Phase 2 — #5396)."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock heavy dependencies before any project imports
sys.modules.setdefault('firebase_admin', MagicMock())
sys.modules.setdefault('firebase_admin.auth', MagicMock())
sys.modules.setdefault('firebase_admin.firestore', MagicMock())
sys.modules.setdefault('database._client', MagicMock())
_mock_clients = MagicMock()
sys.modules.setdefault('utils.llm.clients', _mock_clients)

# Now safe to import
from utils.desktop.focus import FocusResult, FOCUS_SYSTEM_PROMPT, _build_context
from models.message_event import FocusResultEvent

# --- FocusResult model tests ---


class TestFocusResultModel:
    def test_focus_result_focused(self):
        result = FocusResult(
            status="focused",
            app_or_site="VS Code",
            description="Writing Python code",
            message="Great focus!",
        )
        assert result.status == "focused"
        assert result.app_or_site == "VS Code"
        assert result.description == "Writing Python code"
        assert result.message == "Great focus!"

    def test_focus_result_distracted(self):
        result = FocusResult(
            status="distracted",
            app_or_site="YouTube",
            description="Watching videos",
            message="Time to refocus!",
        )
        assert result.status == "distracted"
        assert result.app_or_site == "YouTube"

    def test_focus_result_message_optional(self):
        result = FocusResult(
            status="focused",
            app_or_site="Terminal",
            description="Running tests",
        )
        assert result.message is None

    def test_focus_result_message_none_explicit(self):
        result = FocusResult(
            status="focused",
            app_or_site="Terminal",
            description="Running tests",
            message=None,
        )
        assert result.message is None


# --- FocusResultEvent tests ---


class TestFocusResultEvent:
    def test_focus_result_event_to_json(self):
        event = FocusResultEvent(
            frame_id="abc-123",
            status="focused",
            app_or_site="VS Code",
            description="Writing code",
            message="Keep it up!",
        )
        j = event.to_json()
        assert j["type"] == "focus_result"
        assert j["frame_id"] == "abc-123"
        assert j["status"] == "focused"
        assert j["app_or_site"] == "VS Code"
        assert j["description"] == "Writing code"
        assert j["message"] == "Keep it up!"
        assert "event_type" not in j

    def test_focus_result_event_null_message(self):
        event = FocusResultEvent(
            frame_id="def-456",
            status="distracted",
            app_or_site="Twitter",
            description="Browsing feed",
        )
        j = event.to_json()
        assert j["type"] == "focus_result"
        assert j["message"] is None

    def test_focus_result_event_default_type(self):
        event = FocusResultEvent(
            frame_id="x",
            status="focused",
            app_or_site="Code",
            description="Working",
        )
        assert event.event_type == "focus_result"


# --- Context building tests ---


class TestBuildContext:
    @patch('utils.desktop.focus.get_memories', return_value=[])
    @patch('utils.desktop.focus.get_action_items', return_value=[])
    @patch('utils.desktop.focus.get_user_goals', return_value=[])
    def test_empty_context(self, mock_goals, mock_tasks, mock_memories):
        result = _build_context("test-uid")
        assert result == ""

    @patch('utils.desktop.focus.get_memories', return_value=[])
    @patch('utils.desktop.focus.get_action_items', return_value=[])
    @patch(
        'utils.desktop.focus.get_user_goals',
        return_value=[
            {"title": "Ship Phase 2"},
            {"title": "Learn Rust"},
        ],
    )
    def test_goals_in_context(self, mock_goals, mock_tasks, mock_memories):
        result = _build_context("test-uid")
        assert "Active Goals:" in result
        assert "Ship Phase 2" in result
        assert "Learn Rust" in result

    @patch('utils.desktop.focus.get_memories', return_value=[])
    @patch(
        'utils.desktop.focus.get_action_items',
        return_value=[
            {"description": "Fix login bug"},
            {"description": "Review PR #42"},
        ],
    )
    @patch('utils.desktop.focus.get_user_goals', return_value=[])
    def test_tasks_in_context(self, mock_goals, mock_tasks, mock_memories):
        result = _build_context("test-uid")
        assert "Current Tasks:" in result
        assert "Fix login bug" in result
        assert "Review PR #42" in result

    @patch(
        'utils.desktop.focus.get_memories',
        return_value=[
            {"structured": {"title": "Learned about WebSockets"}},
        ],
    )
    @patch('utils.desktop.focus.get_action_items', return_value=[])
    @patch('utils.desktop.focus.get_user_goals', return_value=[])
    def test_memories_in_context(self, mock_goals, mock_tasks, mock_memories):
        result = _build_context("test-uid")
        assert "Recent Memories:" in result
        assert "Learned about WebSockets" in result

    @patch('utils.desktop.focus.get_memories', side_effect=Exception("DB error"))
    @patch('utils.desktop.focus.get_action_items', side_effect=Exception("DB error"))
    @patch('utils.desktop.focus.get_user_goals', side_effect=Exception("DB error"))
    def test_context_graceful_on_errors(self, mock_goals, mock_tasks, mock_memories):
        result = _build_context("test-uid")
        assert result == ""

    @patch('utils.desktop.focus.get_memories', return_value=[])
    @patch('utils.desktop.focus.get_action_items', return_value=[])
    @patch(
        'utils.desktop.focus.get_user_goals',
        return_value=[
            {"description": "Goal without title"},
        ],
    )
    def test_goals_fallback_to_description(self, mock_goals, mock_tasks, mock_memories):
        result = _build_context("test-uid")
        assert "Goal without title" in result

    @patch(
        'utils.desktop.focus.get_memories',
        return_value=[
            {"content": "Memory without structured field"},
        ],
    )
    @patch('utils.desktop.focus.get_action_items', return_value=[])
    @patch('utils.desktop.focus.get_user_goals', return_value=[])
    def test_memories_fallback_to_content(self, mock_goals, mock_tasks, mock_memories):
        result = _build_context("test-uid")
        assert "Memory without structured field" in result


# --- analyze_focus integration tests ---


class TestAnalyzeFocus:
    @patch('utils.desktop.focus._build_context', return_value="")
    @patch('utils.desktop.focus.llm_gemini_flash')
    def test_analyze_focus_returns_result(self, mock_llm, mock_ctx):
        from utils.desktop.focus import analyze_focus

        mock_parser = MagicMock()
        mock_parser.ainvoke = AsyncMock(
            return_value=FocusResult(
                status="focused",
                app_or_site="VS Code",
                description="Editing Python",
                message="Nice work!",
            )
        )
        mock_llm.with_structured_output.return_value = mock_parser

        result = asyncio.get_event_loop().run_until_complete(
            analyze_focus(uid="test", image_b64="base64data", app_name="VS Code", window_title="main.py")
        )

        assert result["status"] == "focused"
        assert result["app_or_site"] == "VS Code"
        assert result["description"] == "Editing Python"
        assert result["message"] == "Nice work!"

    @patch('utils.desktop.focus._build_context', return_value="Active Goals:\n- Ship code")
    @patch('utils.desktop.focus.llm_gemini_flash')
    def test_analyze_focus_includes_context_in_prompt(self, mock_llm, mock_ctx):
        from utils.desktop.focus import analyze_focus

        mock_parser = MagicMock()
        mock_parser.ainvoke = AsyncMock(
            return_value=FocusResult(
                status="distracted",
                app_or_site="Twitter",
                description="Browsing",
            )
        )
        mock_llm.with_structured_output.return_value = mock_parser

        asyncio.get_event_loop().run_until_complete(analyze_focus(uid="test", image_b64="data"))

        call_args = mock_parser.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        prompt_text = human_msg.content[0]["text"]
        assert "Active Goals:" in prompt_text

    @patch('utils.desktop.focus._build_context', return_value="")
    @patch('utils.desktop.focus.llm_gemini_flash')
    def test_analyze_focus_includes_history(self, mock_llm, mock_ctx):
        from utils.desktop.focus import analyze_focus

        mock_parser = MagicMock()
        mock_parser.ainvoke = AsyncMock(
            return_value=FocusResult(
                status="focused",
                app_or_site="Terminal",
                description="Running tests",
            )
        )
        mock_llm.with_structured_output.return_value = mock_parser

        asyncio.get_event_loop().run_until_complete(
            analyze_focus(
                uid="test",
                image_b64="data",
                history="1. [focused] VS Code: Writing code",
            )
        )

        call_args = mock_parser.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        prompt_text = human_msg.content[0]["text"]
        assert "Recent activity" in prompt_text

    @patch('utils.desktop.focus._build_context', return_value="")
    @patch('utils.desktop.focus.llm_gemini_flash')
    def test_analyze_focus_includes_app_and_window(self, mock_llm, mock_ctx):
        from utils.desktop.focus import analyze_focus

        mock_parser = MagicMock()
        mock_parser.ainvoke = AsyncMock(
            return_value=FocusResult(
                status="focused",
                app_or_site="Safari",
                description="Reading docs",
            )
        )
        mock_llm.with_structured_output.return_value = mock_parser

        asyncio.get_event_loop().run_until_complete(
            analyze_focus(uid="test", image_b64="data", app_name="Safari", window_title="MDN Web Docs")
        )

        call_args = mock_parser.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        prompt_text = human_msg.content[0]["text"]
        assert "Safari" in prompt_text
        assert "MDN Web Docs" in prompt_text

    @patch('utils.desktop.focus._build_context', return_value="")
    @patch('utils.desktop.focus.llm_gemini_flash')
    def test_analyze_focus_sends_image_as_base64(self, mock_llm, mock_ctx):
        from utils.desktop.focus import analyze_focus

        mock_parser = MagicMock()
        mock_parser.ainvoke = AsyncMock(
            return_value=FocusResult(
                status="focused",
                app_or_site="Code",
                description="Coding",
            )
        )
        mock_llm.with_structured_output.return_value = mock_parser

        asyncio.get_event_loop().run_until_complete(analyze_focus(uid="test", image_b64="FAKE_BASE64_IMAGE"))

        call_args = mock_parser.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        image_part = human_msg.content[1]
        assert image_part["type"] == "image_url"
        assert "FAKE_BASE64_IMAGE" in image_part["image_url"]["url"]

    @patch('utils.desktop.focus._build_context', return_value="")
    @patch('utils.desktop.focus.llm_gemini_flash')
    def test_analyze_focus_sends_system_prompt(self, mock_llm, mock_ctx):
        from utils.desktop.focus import analyze_focus

        mock_parser = MagicMock()
        mock_parser.ainvoke = AsyncMock(
            return_value=FocusResult(
                status="focused",
                app_or_site="Code",
                description="Coding",
            )
        )
        mock_llm.with_structured_output.return_value = mock_parser

        asyncio.get_event_loop().run_until_complete(analyze_focus(uid="test", image_b64="data"))

        call_args = mock_parser.ainvoke.call_args[0][0]
        system_msg = call_args[0]
        assert FOCUS_SYSTEM_PROMPT in system_msg.content

    @patch('utils.desktop.focus._build_context', return_value="")
    @patch('utils.desktop.focus.llm_gemini_flash')
    def test_analyze_focus_distracted_result(self, mock_llm, mock_ctx):
        from utils.desktop.focus import analyze_focus

        mock_parser = MagicMock()
        mock_parser.ainvoke = AsyncMock(
            return_value=FocusResult(
                status="distracted",
                app_or_site="Reddit",
                description="Scrolling r/programming",
                message="Back to work!",
            )
        )
        mock_llm.with_structured_output.return_value = mock_parser

        result = asyncio.get_event_loop().run_until_complete(analyze_focus(uid="test", image_b64="data"))

        assert result["status"] == "distracted"
        assert result["app_or_site"] == "Reddit"
        assert result["message"] == "Back to work!"


# --- System prompt content tests ---


class TestFocusSystemPrompt:
    def test_prompt_includes_focused_criteria(self):
        assert "Code editors" in FOCUS_SYSTEM_PROMPT

    def test_prompt_includes_distracted_criteria(self):
        assert "YouTube" in FOCUS_SYSTEM_PROMPT
        assert "Twitter" in FOCUS_SYSTEM_PROMPT

    def test_prompt_warns_about_log_text(self):
        assert "log text" in FOCUS_SYSTEM_PROMPT

    def test_prompt_mentions_context_aware(self):
        assert "CONTEXT-AWARE" in FOCUS_SYSTEM_PROMPT

    def test_prompt_coaching_message_guidance(self):
        assert "100 characters max" in FOCUS_SYSTEM_PROMPT
