"""Tests for desktop task extraction handler (Phase 2 — #5396)."""

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

from utils.desktop.tasks import (
    ExtractedTask,
    TaskExtractionResult,
    TASK_SYSTEM_PROMPT,
    _build_task_context,
    extract_tasks,
)
from models.message_event import TasksExtractedEvent


class TestExtractedTaskModel:
    def test_task_with_all_fields(self):
        task = ExtractedTask(
            title="Review pull request 42 for authentication changes",
            description="Check auth middleware",
            priority="high",
            tags=["code-review", "auth"],
            source_app="GitHub",
            inferred_deadline="2026-03-10",
            confidence=0.9,
            source_category="direct_request",
        )
        assert task.title == "Review pull request 42 for authentication changes"
        assert task.priority == "high"
        assert task.confidence == 0.9

    def test_task_defaults(self):
        task = ExtractedTask(
            title="Update the README with new API docs",
            priority="low",
            confidence=0.5,
        )
        assert task.description == ""
        assert task.tags == []
        assert task.source_app == ""
        assert task.inferred_deadline is None
        assert task.source_category == "reactive"

    def test_task_confidence_bounds(self):
        with pytest.raises(Exception):
            ExtractedTask(title="Test", priority="high", confidence=1.5)
        with pytest.raises(Exception):
            ExtractedTask(title="Test", priority="high", confidence=-0.1)


class TestTaskExtractionResult:
    def test_result_with_tasks(self):
        result = TaskExtractionResult(
            has_new_tasks=True,
            tasks=[
                ExtractedTask(title="Call John about the project deadline", priority="high", confidence=0.8),
            ],
            context_summary="Slack messages",
            current_activity="Reading messages",
        )
        assert result.has_new_tasks is True
        assert len(result.tasks) == 1

    def test_result_no_tasks(self):
        result = TaskExtractionResult(
            has_new_tasks=False,
            context_summary="IDE open",
            current_activity="Coding",
        )
        assert result.has_new_tasks is False
        assert result.tasks == []


class TestTasksExtractedEvent:
    def test_event_structure(self):
        event = TasksExtractedEvent(
            frame_id="frame123",
            tasks=[{"title": "Test task", "priority": "high"}],
        )
        data = event.to_json()
        assert data["type"] == "tasks_extracted"
        assert data["frame_id"] == "frame123"
        assert len(data["tasks"]) == 1


class TestBuildTaskContext:
    @patch('utils.desktop.tasks.get_action_items')
    def test_active_tasks_in_context(self, mock_get):
        mock_get.return_value = [
            {'description': 'Write tests', 'due_at': '2026-03-10'},
            {'description': 'Fix bug'},
        ]
        ctx = _build_task_context("uid1")
        assert "Write tests" in ctx
        assert "Due: 2026-03-10" in ctx
        assert "Fix bug" in ctx
        assert "Pending" in ctx

    @patch('utils.desktop.tasks.get_action_items')
    def test_completed_tasks_in_context(self, mock_get):
        mock_get.side_effect = [
            [],  # active tasks
            [{'description': 'Done task'}],  # completed tasks
        ]
        ctx = _build_task_context("uid1")
        assert "Done task" in ctx
        assert "Completed" in ctx

    @patch('utils.desktop.tasks.get_action_items')
    def test_empty_context(self, mock_get):
        mock_get.return_value = []
        ctx = _build_task_context("uid1")
        assert ctx == ""

    @patch('utils.desktop.tasks.get_action_items')
    def test_graceful_on_errors(self, mock_get):
        mock_get.side_effect = Exception("DB error")
        ctx = _build_task_context("uid1")
        assert ctx == ""


class TestExtractTasks:
    @patch('utils.desktop.tasks._build_task_context')
    @patch('utils.desktop.tasks.llm_gemini_flash')
    def test_extract_tasks_returns_result(self, mock_llm, mock_ctx):
        mock_ctx.return_value = ""
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(
            return_value=TaskExtractionResult(
                has_new_tasks=True,
                tasks=[
                    ExtractedTask(
                        title="Review pull request 42 for auth changes",
                        priority="high",
                        confidence=0.9,
                        source_app="GitHub",
                    )
                ],
                context_summary="GitHub PR page",
                current_activity="Reviewing code",
            )
        )
        result = asyncio.get_event_loop().run_until_complete(
            extract_tasks("uid1", "base64img", "Chrome", "GitHub PR")
        )
        assert result["has_new_tasks"] is True
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["title"] == "Review pull request 42 for auth changes"
        assert result["tasks"][0]["source_app"] == "GitHub"

    @patch('utils.desktop.tasks._build_task_context')
    @patch('utils.desktop.tasks.llm_gemini_flash')
    def test_extract_tasks_no_tasks(self, mock_llm, mock_ctx):
        mock_ctx.return_value = ""
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(
            return_value=TaskExtractionResult(
                has_new_tasks=False,
                context_summary="Desktop idle",
                current_activity="Nothing",
            )
        )
        result = asyncio.get_event_loop().run_until_complete(
            extract_tasks("uid1", "base64img")
        )
        assert result["has_new_tasks"] is False
        assert result["tasks"] == []

    @patch('utils.desktop.tasks._build_task_context')
    @patch('utils.desktop.tasks.llm_gemini_flash')
    def test_source_app_fallback(self, mock_llm, mock_ctx):
        mock_ctx.return_value = ""
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(
            return_value=TaskExtractionResult(
                has_new_tasks=True,
                tasks=[
                    ExtractedTask(
                        title="Send email to team about deadline update",
                        priority="medium",
                        confidence=0.7,
                        source_app="",  # empty
                    )
                ],
            )
        )
        result = asyncio.get_event_loop().run_until_complete(
            extract_tasks("uid1", "base64img", "Slack", "General")
        )
        # Falls back to app_name when source_app is empty
        assert result["tasks"][0]["source_app"] == "Slack"

    @patch('utils.desktop.tasks._build_task_context')
    @patch('utils.desktop.tasks.llm_gemini_flash')
    def test_includes_context_in_prompt(self, mock_llm, mock_ctx):
        mock_ctx.return_value = "Existing active tasks:\n- Write tests [Pending]"
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(
            return_value=TaskExtractionResult(has_new_tasks=False)
        )
        asyncio.get_event_loop().run_until_complete(
            extract_tasks("uid1", "base64img", "VS Code", "main.py")
        )
        call_args = mock_parser.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        text_content = human_msg.content[0]["text"]
        assert "Write tests" in text_content
        assert "VS Code" in text_content


class TestTaskSystemPrompt:
    def test_prompt_includes_dedup_rules(self):
        assert "DEDUPLICATION" in TASK_SYSTEM_PROMPT

    def test_prompt_includes_priority_guidelines(self):
        assert "high" in TASK_SYSTEM_PROMPT
        assert "medium" in TASK_SYSTEM_PROMPT
        assert "low" in TASK_SYSTEM_PROMPT

    def test_prompt_includes_source_categories(self):
        assert "direct_request" in TASK_SYSTEM_PROMPT
        assert "self_generated" in TASK_SYSTEM_PROMPT
        assert "calendar_driven" in TASK_SYSTEM_PROMPT
