"""
Tests for batched goal extraction (issue #4789).
Verifies extract_and_update_goal_progress makes exactly 1 LLM call regardless of goal count.
"""

import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# --- Stub database package and submodules ---
database_mod = _stub_module("database")
if not hasattr(database_mod, '__path__'):
    database_mod.__path__ = []
for submodule in [
    "redis_db",
    "memories",
    "conversations",
    "users",
    "tasks",
    "trends",
    "action_items",
    "folders",
    "calendar_meetings",
    "vector_db",
    "apps",
    "llm_usage",
    "_client",
    "chat",
    "goals",
    "knowledge_graph",
    "daily_summaries",
    "mem_db",
    "notifications",
]:
    mod = _stub_module(f"database.{submodule}")
    setattr(database_mod, submodule, mod)

# Set needed attributes on db stubs
sys.modules["database.llm_usage"].record_llm_usage = MagicMock()
sys.modules["database.goals"].get_user_goal = MagicMock(return_value=None)
sys.modules["database.goals"].get_user_goals = MagicMock(return_value=[])
sys.modules["database.goals"].update_goal_progress = MagicMock()
sys.modules["database.memories"].get_memories = MagicMock(return_value=[])
sys.modules["database.conversations"].get_conversations = MagicMock(return_value=[])
sys.modules["database.conversations"].get_conversations_by_id = MagicMock(return_value=[])
sys.modules["database.chat"].get_messages = MagicMock(return_value=[])
sys.modules["database.vector_db"].query_vectors = MagicMock(return_value=[])

# Stub utils.llms.memory
llms_mod = _stub_module("utils.llms")
if not hasattr(llms_mod, '__path__'):
    llms_mod.__path__ = []
_stub_module("utils.llms.memory")
sys.modules["utils.llms.memory"].get_prompt_memories = MagicMock(return_value=("TestUser", "some memories"))

# Ensure clients module has mocks (but don't create new ones if already set)
clients_mod = _stub_module("utils.llm.clients")
if not hasattr(clients_mod, 'llm_mini'):
    clients_mod.llm_mini = MagicMock()
if not hasattr(clients_mod, 'llm_medium'):
    clients_mod.llm_medium = MagicMock()

# Shortcut references to mocked db functions
mock_goals_db = sys.modules["database.goals"]


# --- Test data ---

GOAL_A = {
    "id": "goal-a",
    "title": "Save $10,000",
    "current_value": 2000,
    "target_value": 10000,
    "goal_type": "numeric",
}

GOAL_B = {
    "id": "goal-b",
    "title": "Run 100 miles",
    "current_value": 30,
    "target_value": 100,
    "goal_type": "numeric",
}

GOAL_C = {
    "id": "goal-c",
    "title": "Read 20 books",
    "current_value": 5,
    "target_value": 20,
    "goal_type": "numeric",
}


def _import_fn():
    """Lazy import to avoid capturing mock references at module load time."""
    from utils.llm.goals import extract_and_update_goal_progress

    return extract_and_update_goal_progress


@pytest.fixture(autouse=True)
def reset_mocks():
    mock_goals_db.get_user_goals.reset_mock()
    mock_goals_db.update_goal_progress.reset_mock()
    yield


class TestBatchedGoalExtraction:
    """Core test: exactly 1 LLM call regardless of goal count."""

    def test_single_goal_one_llm_call(self):
        """1 goal -> 1 LLM call."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='[]')

        with patch("utils.llm.goals.llm_mini", mock_llm):
            _import_fn()("uid-1", "I went for a walk today")
        assert mock_llm.invoke.call_count == 1

    def test_three_goals_one_llm_call(self):
        """3 goals -> still exactly 1 LLM call (was 3 before fix)."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A, GOAL_B, GOAL_C]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='[]')

        with patch("utils.llm.goals.llm_mini", mock_llm):
            _import_fn()("uid-1", "Just had lunch")
        assert mock_llm.invoke.call_count == 1

    def test_prompt_contains_all_goals(self):
        """Prompt must mention all goal titles for the LLM to evaluate."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A, GOAL_B, GOAL_C]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='[]')

        with patch("utils.llm.goals.llm_mini", mock_llm):
            _import_fn()("uid-1", "Some message")

        prompt = mock_llm.invoke.call_args[0][0]
        assert "Save $10,000" in prompt
        assert "Run 100 miles" in prompt
        assert "Read 20 books" in prompt


class TestGoalProgressUpdate:
    """Test that matched goals get updated correctly."""

    def test_single_match_updates_db(self):
        """When LLM finds progress for one goal, update it."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A, GOAL_B]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps([{"goal_id": "goal-a", "found": True, "value": 2500, "reasoning": "saved $500 more"}])
        )

        with patch("utils.llm.goals.llm_mini", mock_llm):
            result = _import_fn()("uid-1", "I saved another $500 today")

        assert result["status"] == "updated"
        assert len(result["updates"]) == 1
        assert result["updates"][0]["goal_id"] == "goal-a"
        assert result["updates"][0]["new_value"] == 2500
        mock_goals_db.update_goal_progress.assert_called_once_with("uid-1", "goal-a", 2500)

    def test_multiple_matches_update_all(self):
        """When LLM finds progress for multiple goals, update all."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A, GOAL_B, GOAL_C]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps(
                [
                    {"goal_id": "goal-a", "found": True, "value": 3000, "reasoning": "mentioned savings"},
                    {"goal_id": "goal-c", "found": True, "value": 6, "reasoning": "finished a book"},
                ]
            )
        )

        with patch("utils.llm.goals.llm_mini", mock_llm):
            result = _import_fn()("uid-1", "Saved $1000 and finished reading a book")

        assert result["status"] == "updated"
        assert len(result["updates"]) == 2
        goal_ids = [u["goal_id"] for u in result["updates"]]
        assert "goal-a" in goal_ids
        assert "goal-c" in goal_ids
        assert mock_goals_db.update_goal_progress.call_count == 2

    def test_no_match_returns_no_update(self):
        """When no goals match, return no_update."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A, GOAL_B]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='[]')

        with patch("utils.llm.goals.llm_mini", mock_llm):
            result = _import_fn()("uid-1", "Weather is nice today")

        assert result["status"] == "no_update"
        mock_goals_db.update_goal_progress.assert_not_called()

    def test_same_value_not_updated(self):
        """If extracted value equals current, skip the update."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps([{"goal_id": "goal-a", "found": True, "value": 2000, "reasoning": "same value"}])
        )

        with patch("utils.llm.goals.llm_mini", mock_llm):
            result = _import_fn()("uid-1", "I have $2000 saved")

        assert result["status"] == "no_update"
        mock_goals_db.update_goal_progress.assert_not_called()

    def test_unknown_goal_id_ignored(self):
        """If LLM returns a goal_id not in user's goals, ignore it."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps([{"goal_id": "nonexistent", "found": True, "value": 999, "reasoning": "wrong id"}])
        )

        with patch("utils.llm.goals.llm_mini", mock_llm):
            result = _import_fn()("uid-1", "Some message")

        assert result["status"] == "no_update"
        mock_goals_db.update_goal_progress.assert_not_called()


class TestEdgeCases:
    """Edge cases and guard rails."""

    def test_no_goals_returns_none(self):
        """No active goals -> return None, no LLM call."""
        mock_goals_db.get_user_goals.return_value = []
        mock_llm = MagicMock()

        with patch("utils.llm.goals.llm_mini", mock_llm):
            result = _import_fn()("uid-1", "I saved $500")

        assert result is None
        mock_llm.invoke.assert_not_called()

    def test_short_text_returns_none(self):
        """Text shorter than 5 chars -> return None, no LLM call."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()

        with patch("utils.llm.goals.llm_mini", mock_llm):
            result = _import_fn()("uid-1", "hi")

        assert result is None
        mock_llm.invoke.assert_not_called()

    def test_empty_text_returns_none(self):
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()

        with patch("utils.llm.goals.llm_mini", mock_llm):
            result = _import_fn()("uid-1", "")

        assert result is None
        mock_llm.invoke.assert_not_called()

    def test_malformed_llm_response_no_crash(self):
        """If LLM returns garbage, don't crash."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Sorry, I cannot help with that.")

        with patch("utils.llm.goals.llm_mini", mock_llm):
            result = _import_fn()("uid-1", "I saved $500 today")

        assert result["status"] == "no_update"
        mock_goals_db.update_goal_progress.assert_not_called()

    def test_llm_exception_returns_error(self):
        """If LLM call throws, return error status."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API timeout")

        with patch("utils.llm.goals.llm_mini", mock_llm):
            result = _import_fn()("uid-1", "I saved $500 today")

        assert result["status"] == "error"
