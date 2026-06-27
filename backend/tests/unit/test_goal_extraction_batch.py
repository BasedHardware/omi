"""
Tests for batched goal extraction (issue #4789).
Verifies extract_and_update_goal_progress makes exactly 1 LLM call regardless of goal count.
"""

import importlib
import json
import os
import sys
import types
from contextlib import nullcontext
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
    if "." in name:
        parent_name, attr = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr, sys.modules[name])
    return sys.modules[name]


_DATABASE_SUBMODULES = (
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
)
_RESTORED_MODULES = tuple(
    ["database"]
    + [f"database.{submodule}" for submodule in _DATABASE_SUBMODULES]
    + [
        "utils",
        "utils.llm",
        "utils.llms",
        "utils.llms.memory",
        "utils.llm.clients",
        "utils.llm.usage_tracker",
        "utils.llm.goals",
    ]
)
_PARENT_ATTRS = tuple(
    [("database", submodule) for submodule in _DATABASE_SUBMODULES]
    + [
        ("utils", "llm"),
        ("utils", "llms"),
        ("utils.llms", "memory"),
        ("utils.llm", "clients"),
        ("utils.llm", "usage_tracker"),
        ("utils.llm", "goals"),
    ]
)
_MISSING = object()
_saved_modules = {name: sys.modules.get(name, _MISSING) for name in _RESTORED_MODULES}
_saved_parent_attrs = {
    (parent_name, attr): getattr(sys.modules.get(parent_name), attr, _MISSING) for parent_name, attr in _PARENT_ATTRS
}


def _restore_stub_modules():
    current_modules = {name: sys.modules.get(name, _MISSING) for name in _RESTORED_MODULES}
    for name in sorted(_RESTORED_MODULES, key=lambda module_name: module_name.count("."), reverse=True):
        original = _saved_modules[name]
        if original is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original

    for (parent_name, attr), original in _saved_parent_attrs.items():
        parent = sys.modules.get(parent_name)
        if parent is None:
            continue
        if original is _MISSING:
            child_name = f"{parent_name}.{attr}"
            current = current_modules.get(child_name, _MISSING)
            if current is not _MISSING and getattr(parent, attr, _MISSING) is current:
                delattr(parent, attr)
        else:
            setattr(parent, attr, original)


# --- Stub database package and submodules ---
database_mod = _stub_module("database")
if not hasattr(database_mod, '__path__'):
    database_mod.__path__ = []
for submodule in _DATABASE_SUBMODULES:
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
if not hasattr(clients_mod, 'get_llm'):
    clients_mod.get_llm = MagicMock()

# Stub usage tracking so importing utils.llm.goals does not pull optional usage deps.
usage_tracker_mod = _stub_module("utils.llm.usage_tracker")
usage_tracker_mod.track_usage = MagicMock(side_effect=lambda *args, **kwargs: nullcontext())
usage_tracker_mod.Features = types.SimpleNamespace(GOALS="goals")

# Shortcut references to mocked modules and functions
mock_llm_usage_db = sys.modules["database.llm_usage"]
mock_goals_db = sys.modules["database.goals"]
mock_memories_db = sys.modules["database.memories"]
mock_conversations_db = sys.modules["database.conversations"]
mock_chat_db = sys.modules["database.chat"]
mock_vector_db = sys.modules["database.vector_db"]
mock_memory_module = sys.modules["utils.llms.memory"]

try:
    _goals_module = importlib.import_module("utils.llm.goals")
finally:
    _restore_stub_modules()


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


def _import_goals_module():
    """Return the isolated module imported while heavy dependencies were stubbed."""
    return _goals_module


def _run_with_llm(mock_llm, uid: str, text: str):
    goals_module = _import_goals_module()
    with patch.object(goals_module, "get_llm", MagicMock(return_value=mock_llm)):
        return goals_module.extract_and_update_goal_progress(uid, text)


def _reset_mock(mock, *, return_value=_MISSING, side_effect=_MISSING):
    mock.reset_mock(return_value=True, side_effect=True)
    if return_value is not _MISSING:
        mock.return_value = return_value
    if side_effect is not _MISSING:
        mock.side_effect = side_effect


@pytest.fixture(autouse=True)
def reset_mocks():
    _reset_mock(mock_llm_usage_db.record_llm_usage)
    _reset_mock(mock_goals_db.get_user_goal, return_value=None)
    _reset_mock(mock_goals_db.get_user_goals, return_value=[])
    _reset_mock(mock_goals_db.update_goal_progress)
    _reset_mock(mock_memories_db.get_memories, return_value=[])
    _reset_mock(mock_conversations_db.get_conversations, return_value=[])
    _reset_mock(mock_conversations_db.get_conversations_by_id, return_value=[])
    _reset_mock(mock_chat_db.get_messages, return_value=[])
    _reset_mock(mock_vector_db.query_vectors, return_value=[])
    _reset_mock(mock_memory_module.get_prompt_memories, return_value=("TestUser", "some memories"))

    goals_module = _import_goals_module()
    _reset_mock(goals_module.track_usage, side_effect=lambda *args, **kwargs: nullcontext())
    _reset_mock(goals_module.get_llm)
    yield


class TestBatchedGoalExtraction:
    """Core test: exactly 1 LLM call regardless of goal count."""

    def test_single_goal_one_llm_call(self):
        """1 goal -> 1 LLM call."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='[]')

        _run_with_llm(mock_llm, "uid-1", "I went for a walk today")
        assert mock_llm.invoke.call_count == 1

    def test_three_goals_one_llm_call(self):
        """3 goals -> still exactly 1 LLM call (was 3 before fix)."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A, GOAL_B, GOAL_C]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='[]')

        _run_with_llm(mock_llm, "uid-1", "Just had lunch")
        assert mock_llm.invoke.call_count == 1

    def test_prompt_contains_all_goals(self):
        """Prompt must mention all goal titles for the LLM to evaluate."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A, GOAL_B, GOAL_C]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='[]')

        _run_with_llm(mock_llm, "uid-1", "Some message")

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

        result = _run_with_llm(mock_llm, "uid-1", "I saved another $500 today")

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

        result = _run_with_llm(mock_llm, "uid-1", "Saved $1000 and finished reading a book")

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

        result = _run_with_llm(mock_llm, "uid-1", "Weather is nice today")

        assert result["status"] == "no_update"
        mock_goals_db.update_goal_progress.assert_not_called()

    def test_same_value_not_updated(self):
        """If extracted value equals current, skip the update."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps([{"goal_id": "goal-a", "found": True, "value": 2000, "reasoning": "same value"}])
        )

        result = _run_with_llm(mock_llm, "uid-1", "I have $2000 saved")

        assert result["status"] == "no_update"
        mock_goals_db.update_goal_progress.assert_not_called()

    def test_unknown_goal_id_ignored(self):
        """If LLM returns a goal_id not in user's goals, ignore it."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps([{"goal_id": "nonexistent", "found": True, "value": 999, "reasoning": "wrong id"}])
        )

        result = _run_with_llm(mock_llm, "uid-1", "Some message")

        assert result["status"] == "no_update"
        mock_goals_db.update_goal_progress.assert_not_called()


class TestEdgeCases:
    """Edge cases and guard rails."""

    def test_no_goals_returns_none(self):
        """No active goals -> return None, no LLM call."""
        mock_goals_db.get_user_goals.return_value = []
        mock_llm = MagicMock()

        result = _run_with_llm(mock_llm, "uid-1", "I saved $500")

        assert result is None
        mock_llm.invoke.assert_not_called()

    def test_short_text_returns_none(self):
        """Text shorter than 5 chars -> return None, no LLM call."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()

        result = _run_with_llm(mock_llm, "uid-1", "hi")

        assert result is None
        mock_llm.invoke.assert_not_called()

    def test_empty_text_returns_none(self):
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()

        result = _run_with_llm(mock_llm, "uid-1", "")

        assert result is None
        mock_llm.invoke.assert_not_called()

    def test_malformed_llm_response_no_crash(self):
        """If LLM returns garbage, don't crash."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Sorry, I cannot help with that.")

        result = _run_with_llm(mock_llm, "uid-1", "I saved $500 today")

        assert result["status"] == "no_update"
        mock_goals_db.update_goal_progress.assert_not_called()

    def test_llm_exception_returns_error(self):
        """If LLM call throws, return error status."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API timeout")

        result = _run_with_llm(mock_llm, "uid-1", "I saved $500 today")

        assert result["status"] == "error"

    def test_negative_value_rejected(self):
        """Negative values from LLM should be ignored."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps([{"goal_id": "goal-a", "found": True, "value": -500, "reasoning": "negative"}])
        )

        result = _run_with_llm(mock_llm, "uid-1", "I lost $500")

        assert result["status"] == "no_update"
        mock_goals_db.update_goal_progress.assert_not_called()

    def test_nan_value_rejected(self):
        """NaN values should be ignored."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content='[{"goal_id": "goal-a", "found": true, "value": NaN, "reasoning": "bad"}]'
        )

        result = _run_with_llm(mock_llm, "uid-1", "Something happened")

        # NaN in JSON is invalid, so parsing fails gracefully
        assert result["status"] == "no_update"
        mock_goals_db.update_goal_progress.assert_not_called()

    def test_duplicate_goal_id_deduped(self):
        """If LLM returns same goal_id twice, only process first occurrence."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps(
                [
                    {"goal_id": "goal-a", "found": True, "value": 3000, "reasoning": "first"},
                    {"goal_id": "goal-a", "found": True, "value": 5000, "reasoning": "duplicate"},
                ]
            )
        )

        result = _run_with_llm(mock_llm, "uid-1", "I saved $3000 or maybe $5000")

        assert result["status"] == "updated"
        assert len(result["updates"]) == 1
        assert result["updates"][0]["new_value"] == 3000
        mock_goals_db.update_goal_progress.assert_called_once()

    def test_llm_returns_array_with_extra_text(self):
        """LLM wraps JSON in prose — parser should still extract the array."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content='Here is the analysis:\n[{"goal_id": "goal-a", "found": true, "value": 4000, "reasoning": "saved more"}]\nHope this helps!'
        )

        result = _run_with_llm(mock_llm, "uid-1", "I now have $4000 saved")

        assert result["status"] == "updated"
        assert result["updates"][0]["new_value"] == 4000

    def test_one_bad_result_doesnt_block_others(self):
        """A malformed result shouldn't prevent processing valid ones."""
        mock_goals_db.get_user_goals.return_value = [GOAL_A, GOAL_B]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps(
                [
                    {"goal_id": "goal-a", "found": True, "value": "not_a_number", "reasoning": "bad"},
                    {"goal_id": "goal-b", "found": True, "value": 50, "reasoning": "ran 50 miles"},
                ]
            )
        )

        result = _run_with_llm(mock_llm, "uid-1", "I ran 50 miles and saved some money")

        assert result["status"] == "updated"
        assert len(result["updates"]) == 1
        assert result["updates"][0]["goal_id"] == "goal-b"
