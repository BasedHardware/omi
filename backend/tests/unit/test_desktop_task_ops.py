"""Tests for desktop task operations (rerank + dedup) handlers (Phase 2 — #5396)."""

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

from utils.desktop.task_ops import (
    RankedTask,
    RerankResult,
    DedupGroup,
    DedupResult,
    RERANK_SYSTEM_PROMPT,
    DEDUP_SYSTEM_PROMPT,
    rerank_tasks,
    dedup_tasks,
)
from models.message_event import RerankCompleteEvent, DedupCompleteEvent

# --- Rerank tests ---


class TestRankedTaskModel:
    def test_ranked_task(self):
        t = RankedTask(id="task1", new_position=1)
        assert t.id == "task1"
        assert t.new_position == 1


class TestRerankResult:
    def test_rerank_result(self):
        r = RerankResult(updated_tasks=[RankedTask(id="t1", new_position=1)])
        assert len(r.updated_tasks) == 1


class TestRerankCompleteEvent:
    def test_event_structure(self):
        event = RerankCompleteEvent(updated_tasks=[{"id": "t1", "new_position": 1}])
        data = event.to_json()
        assert data["type"] == "rerank_complete"
        assert len(data["updated_tasks"]) == 1


class TestRerankTasks:
    @patch('utils.desktop.task_ops.get_action_items')
    @patch('utils.desktop.task_ops.llm_mini')
    def test_rerank_returns_order(self, mock_llm, mock_get):
        mock_get.return_value = [
            {'id': 't1', 'description': 'Low priority', 'priority': 'low'},
            {'id': 't2', 'description': 'Urgent fix', 'priority': 'high', 'due_at': '2026-03-08'},
        ]
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(
            return_value=RerankResult(
                updated_tasks=[
                    RankedTask(id="t2", new_position=1),
                    RankedTask(id="t1", new_position=2),
                ]
            )
        )
        result = asyncio.get_event_loop().run_until_complete(rerank_tasks("uid1"))
        assert result["updated_tasks"][0]["id"] == "t2"
        assert result["updated_tasks"][0]["new_position"] == 1

    @patch('utils.desktop.task_ops.get_action_items')
    def test_rerank_empty_tasks(self, mock_get):
        mock_get.return_value = []
        result = asyncio.get_event_loop().run_until_complete(rerank_tasks("uid1"))
        assert result["updated_tasks"] == []

    @patch('utils.desktop.task_ops.get_action_items')
    def test_rerank_db_error(self, mock_get):
        mock_get.side_effect = Exception("DB error")
        result = asyncio.get_event_loop().run_until_complete(rerank_tasks("uid1"))
        assert result["updated_tasks"] == []


# --- Dedup tests ---


class TestDedupGroupModel:
    def test_dedup_group(self):
        g = DedupGroup(keep_id="t1", delete_ids=["t2", "t3"], reason="Same task")
        assert g.keep_id == "t1"
        assert len(g.delete_ids) == 2


class TestDedupResult:
    def test_dedup_with_groups(self):
        r = DedupResult(groups=[DedupGroup(keep_id="t1", delete_ids=["t2"], reason="Duplicate")])
        assert len(r.groups) == 1

    def test_dedup_no_groups(self):
        r = DedupResult()
        assert r.groups == []


class TestDedupCompleteEvent:
    def test_event_structure(self):
        event = DedupCompleteEvent(deleted_ids=["t2", "t3"], reason="Duplicate tasks")
        data = event.to_json()
        assert data["type"] == "dedup_complete"
        assert data["deleted_ids"] == ["t2", "t3"]
        assert data["reason"] == "Duplicate tasks"


class TestDedupTasks:
    @patch('utils.desktop.task_ops.get_action_items')
    @patch('utils.desktop.task_ops.llm_mini')
    def test_dedup_finds_duplicates(self, mock_llm, mock_get):
        mock_get.return_value = [
            {'id': 't1', 'description': 'Call John'},
            {'id': 't2', 'description': 'Phone John'},
            {'id': 't3', 'description': 'Write report'},
        ]
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(
            return_value=DedupResult(
                groups=[DedupGroup(keep_id="t1", delete_ids=["t2"], reason="Same action: contact John")]
            )
        )
        result = asyncio.get_event_loop().run_until_complete(dedup_tasks("uid1"))
        assert result["deleted_ids"] == ["t2"]
        assert "contact John" in result["reason"]

    @patch('utils.desktop.task_ops.get_action_items')
    @patch('utils.desktop.task_ops.llm_mini')
    def test_dedup_no_duplicates(self, mock_llm, mock_get):
        mock_get.return_value = [
            {'id': 't1', 'description': 'Task A'},
            {'id': 't2', 'description': 'Task B'},
        ]
        mock_parser = MagicMock()
        mock_llm.with_structured_output.return_value = mock_parser
        mock_parser.ainvoke = AsyncMock(return_value=DedupResult())
        result = asyncio.get_event_loop().run_until_complete(dedup_tasks("uid1"))
        assert result["deleted_ids"] == []
        assert result["reason"] == "No duplicates found"

    @patch('utils.desktop.task_ops.get_action_items')
    def test_dedup_too_few_tasks(self, mock_get):
        mock_get.return_value = [{'id': 't1', 'description': 'Only one'}]
        result = asyncio.get_event_loop().run_until_complete(dedup_tasks("uid1"))
        assert result["deleted_ids"] == []
        assert "Not enough" in result["reason"]

    @patch('utils.desktop.task_ops.get_action_items')
    def test_dedup_db_error(self, mock_get):
        mock_get.side_effect = Exception("DB error")
        result = asyncio.get_event_loop().run_until_complete(dedup_tasks("uid1"))
        assert result["deleted_ids"] == []
        assert "Failed" in result["reason"]


class TestRerankSystemPrompt:
    def test_includes_rules(self):
        assert "RULES" in RERANK_SYSTEM_PROMPT
        assert "deadlines" in RERANK_SYSTEM_PROMPT


class TestDedupSystemPrompt:
    def test_includes_rules(self):
        assert "RULES" in DEDUP_SYSTEM_PROMPT
        assert "duplicates" in DEDUP_SYSTEM_PROMPT.lower()
