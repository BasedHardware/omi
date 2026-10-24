"""
Defensive regression tests for goals LLM utilities and endpoints.
Verifies null safety for qualitative goals, cleared metrics, null LLM suggestions,
non-finite numeric coercion, and FastAPI response validation resilience.
"""

import os
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import database.goals as goals_db
import utils.llm.goals as llm_goals
from utils.llm.goals import safe_float, safe_optional_float
from models.goal import GoalSuggestionResponse
import routers.goals as goals_router


class _StubDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None

    def get(self):
        return self


class _StubGoalsCollection:
    def __init__(self, goals):
        self._goals = goals
        self._limit = None

    def where(self, **_kwargs):
        return self

    def limit(self, count):
        self._limit = count
        return self

    def stream(self):
        docs = [_StubDoc(doc_id, self._goals[doc_id]) for doc_id in sorted(self._goals)]
        return docs if self._limit is None else docs[: self._limit]

    def document(self, doc_id):
        return _StubDoc(doc_id, self._goals.get(doc_id))


class _StubFirestoreClient:
    def __init__(self, goals):
        self._goals = goals

    def collection(self, _name):
        return self

    def document(self, _doc_id):
        return SimpleNamespace(collection=lambda _name: _StubGoalsCollection(self._goals))


def _setup_stub_goals(monkeypatch, goals, llm_reply="Keep taking consistent action."):
    prompts = []
    monkeypatch.setattr(goals_db, "_get_db", lambda firestore_client=None: _StubFirestoreClient(goals))
    monkeypatch.setattr(
        llm_goals,
        "_get_goal_context",
        lambda *_a: {"conversation_context": "Discussion on goals", "chat_context": "Planning", "memory_context": "User notes"},
    )
    monkeypatch.setattr(llm_goals, "track_usage", lambda *_a, **_k: nullcontext())
    monkeypatch.setattr(
        llm_goals,
        "get_llm",
        lambda _name: SimpleNamespace(invoke=lambda prompt: prompts.append(prompt) or SimpleNamespace(content=llm_reply)),
    )
    return prompts


class TestGoalAdviceNullSafety:
    """Verifies get_goal_advice never crashes on null, missing, zero, or non-finite metrics."""

    def test_get_goal_advice_with_cleared_metric_qualitative(self, monkeypatch):
        """When clear_metric=True or qualitative goal, target_value and current_value are None."""
        goal_data = {
            "id": "goal_qual_1",
            "title": "Practice Mindfulness Daily",
            "is_active": True,
            "status": "focused",
            "metric": None,
            "current_value": None,
            "target_value": None,
        }
        prompts = _setup_stub_goals(monkeypatch, {"goal_qual_1": goal_data}, llm_reply="Meditate for 5 minutes each morning.")

        advice = llm_goals.get_goal_advice("u1", "goal_qual_1")

        assert advice == "Meditate for 5 minutes each morning."
        assert len(prompts) == 1
        assert "PROGRESS: Qualitative goal (no numeric metric set)" in prompts[0]
        assert 'GOAL: "Practice Mindfulness Daily"' in prompts[0]

    def test_get_goal_advice_with_target_zero(self, monkeypatch):
        """target_value = 0 must not cause ZeroDivisionError or compare crash."""
        goal_data = {
            "id": "goal_zero",
            "title": "Zero Target Goal",
            "is_active": True,
            "current_value": 0.0,
            "target_value": 0.0,
        }
        prompts = _setup_stub_goals(monkeypatch, {"goal_zero": goal_data})

        advice = llm_goals.get_goal_advice("u1", "goal_zero")
        assert advice == "Keep taking consistent action."
        assert "PROGRESS: 0 / 0" in prompts[0]

    def test_get_goal_advice_with_current_value_only(self, monkeypatch):
        """Only current_value set (no numeric target)."""
        goal_data = {
            "id": "goal_curr",
            "title": "Open-ended Savings",
            "is_active": True,
            "current_value": 500.0,
            "target_value": None,
        }
        prompts = _setup_stub_goals(monkeypatch, {"goal_curr": goal_data})

        advice = llm_goals.get_goal_advice("u1", "goal_curr")
        assert advice == "Keep taking consistent action."
        assert "PROGRESS: 500 (no numeric target set)" in prompts[0]

    def test_get_goal_advice_with_target_value_only(self, monkeypatch):
        """Only target_value set (no current progress recorded yet)."""
        goal_data = {
            "id": "goal_targ",
            "title": "Target Goal",
            "is_active": True,
            "current_value": None,
            "target_value": 100.0,
        }
        prompts = _setup_stub_goals(monkeypatch, {})
        monkeypatch.setattr(goals_db, "get_goal_by_id", lambda _uid, _gid: goal_data)

        advice = llm_goals.get_goal_advice("u1", "goal_targ")
        assert advice == "Keep taking consistent action."
        assert "PROGRESS: Target 100 (current progress not tracked numerically)" in prompts[0]

    def test_get_goal_advice_with_non_numeric_and_nan(self, monkeypatch):
        """Corrupt or non-finite values in storage fall back gracefully."""
        goal_data = {
            "id": "goal_corrupt",
            "title": "Corrupt Metric Goal",
            "is_active": True,
            "current_value": float("nan"),
            "target_value": "not-a-number",
        }
        prompts = _setup_stub_goals(monkeypatch, {"goal_corrupt": goal_data})

        advice = llm_goals.get_goal_advice("u1", "goal_corrupt")
        assert advice == "Keep taking consistent action."
        assert "PROGRESS: Qualitative goal (no numeric metric set)" in prompts[0]

    def test_get_goal_advice_missing_or_inactive_goal(self, monkeypatch):
        """Missing or inactive goal raises ValueError so the router can return HTTP 404."""
        _setup_stub_goals(monkeypatch, {"inactive": {"is_active": False, "title": "Done"}})

        with pytest.raises(ValueError, match="Goal not found"):
            llm_goals.get_goal_advice("u1", "missing_id")

        with pytest.raises(ValueError, match="Goal not found"):
            llm_goals.get_goal_advice("u1", "inactive")

    def test_get_goal_advice_llm_failure_returns_fallback_advice(self, monkeypatch):
        """Active goal where LLM invocation fails gracefully falls back to canned advice."""
        goal_data = {
            "id": "goal_err",
            "title": "Active Goal",
            "is_active": True,
            "current_value": 5.0,
            "target_value": 10.0,
        }
        _setup_stub_goals(monkeypatch, {"goal_err": goal_data})

        class FailingLLM:
            def invoke(self, *args, **kwargs):
                raise RuntimeError("LLM service unavailable")

        monkeypatch.setattr(llm_goals, "get_llm", lambda _name: FailingLLM())

        advice = llm_goals.get_goal_advice("u1", "goal_err")
        assert advice == "Focus on the next small step toward your goal."


class TestGoalSuggestionNullSafety:
    """Verifies suggest_goal produces strictly valid GoalSuggestionResponse payloads."""

    def test_suggest_goal_coerces_null_fields_to_valid_floats(self, monkeypatch):
        """When LLM returns null for numeric target/min/max, sanitize to valid floats."""
        llm_json = """
        {
            "suggested_title": "Drink more water",
            "suggested_type": "numeric",
            "suggested_target": null,
            "suggested_min": null,
            "suggested_max": null,
            "reasoning": "Hydration is essential for focus."
        }
        """
        monkeypatch.setattr(llm_goals, "track_usage", lambda *_a, **_k: nullcontext())
        monkeypatch.setattr(
            llm_goals,
            "get_llm",
            lambda _name: SimpleNamespace(invoke=lambda _p: SimpleNamespace(content=llm_json)),
        )
        with patch("utils.memory.memory_service.MemoryService.read", return_value=[SimpleNamespace(dict=lambda: {"content": "water"})]):
            res = llm_goals.suggest_goal("u1")

        assert res["suggested_title"] == "Drink more water"
        assert res["suggested_type"] == "numeric"
        assert isinstance(res["suggested_target"], float)
        assert res["suggested_target"] == 10.0
        assert isinstance(res["suggested_min"], float)
        assert res["suggested_min"] == 0.0
        assert isinstance(res["suggested_max"], float)
        assert res["suggested_max"] == 10.0
        assert res["reasoning"] == "Hydration is essential for focus."

        # Verify Pydantic schema validation passes without ResponseValidationError
        validated = GoalSuggestionResponse(**res)
        assert validated.suggested_target == 10.0

    def test_suggest_goal_handles_reversed_min_max(self, monkeypatch):
        """When suggested_min > suggested_max, swap bounds."""
        llm_json = """
        {
            "suggested_title": "Sleep 8 hours",
            "suggested_type": "scale",
            "suggested_target": 8.0,
            "suggested_min": 10.0,
            "suggested_max": 2.0,
            "reasoning": "Rest is key."
        }
        """
        monkeypatch.setattr(llm_goals, "track_usage", lambda *_a, **_k: nullcontext())
        monkeypatch.setattr(
            llm_goals,
            "get_llm",
            lambda _name: SimpleNamespace(invoke=lambda _p: SimpleNamespace(content=llm_json)),
        )
        with patch("utils.memory.memory_service.MemoryService.read", return_value=[SimpleNamespace(dict=lambda: {"content": "sleep"})]):
            res = llm_goals.suggest_goal("u1")

        assert res["suggested_min"] <= res["suggested_max"]
        validated = GoalSuggestionResponse(**res)
        assert validated.suggested_min == 2.0
        assert validated.suggested_max == 10.0

    def test_suggest_goal_handles_nan_and_inf(self, monkeypatch):
        """NaN and Inf strings are coerced to safe finite float defaults."""
        llm_json = """
        {
            "suggested_title": "Run often",
            "suggested_type": "numeric",
            "suggested_target": "NaN",
            "suggested_min": "-Infinity",
            "suggested_max": "Infinity",
            "reasoning": "Cardio health."
        }
        """
        monkeypatch.setattr(llm_goals, "track_usage", lambda *_a, **_k: nullcontext())
        monkeypatch.setattr(
            llm_goals,
            "get_llm",
            lambda _name: SimpleNamespace(invoke=lambda _p: SimpleNamespace(content=llm_json)),
        )
        with patch("utils.memory.memory_service.MemoryService.read", return_value=[SimpleNamespace(dict=lambda: {"content": "running"})]):
            res = llm_goals.suggest_goal("u1")

        assert res["suggested_target"] == 10.0
        assert res["suggested_min"] == 0.0
        assert res["suggested_max"] == 10.0
        validated = GoalSuggestionResponse(**res)
        assert validated.suggested_target == 10.0

    def test_suggest_goal_fallback_when_no_memories(self):
        """When user has no memories, fallback is valid GoalSuggestionResponse."""
        with patch("utils.memory.memory_service.MemoryService.read", return_value=[]):
            res = llm_goals.suggest_goal("u1")

        validated = GoalSuggestionResponse(**res)
        assert validated.suggested_title == "Learn something new every day"
        assert validated.suggested_target == 10.0

    def test_suggest_goal_fallback_on_json_parse_failure(self, monkeypatch):
        """When LLM returns malformed non-JSON, fallback is valid GoalSuggestionResponse."""
        monkeypatch.setattr(llm_goals, "track_usage", lambda *_a, **_k: nullcontext())
        monkeypatch.setattr(
            llm_goals,
            "get_llm",
            lambda _name: SimpleNamespace(invoke=lambda _p: SimpleNamespace(content="I suggest you run daily!")),
        )
        with patch("utils.memory.memory_service.MemoryService.read", return_value=[SimpleNamespace(dict=lambda: {"content": "run"})]):
            res = llm_goals.suggest_goal("u1")

        validated = GoalSuggestionResponse(**res)
        assert validated.suggested_target == 10.0

    def test_sanitize_suggestion_delegation_consistency(self):
        """Verify sanitize_goal_suggestion delegates to models.goal.sanitize_suggestion_dict with identical defaults."""
        from models.goal import sanitize_suggestion_dict

        raw = {"suggested_title": "  Test Goal  ", "suggested_type": "UNKNOWN", "suggested_target": "25.5"}
        res_models = sanitize_suggestion_dict(raw)
        res_llm = llm_goals.sanitize_goal_suggestion(raw)
        assert res_models == res_llm
        assert res_models["reasoning"] == "Start tracking your daily progress!"
        assert res_llm["suggested_type"] == "scale"
        assert res_llm["suggested_target"] == 25.5


class TestGoalRouterEndpointDefensive:
    """Verifies router-level defensive behaviors for advice and suggestions."""

    def test_get_goal_advice_router_raises_404_for_missing_goal(self):
        """GET /v1/goals/{goal_id}/advice raises HTTPException(404) when goal does not exist."""
        with patch.object(goals_router, "get_goal_advice_llm", side_effect=ValueError("Goal not found")):
            with patch.object(goals_router, "require_generated_compute"):
                with pytest.raises(HTTPException) as exc_info:
                    goals_router.get_goal_advice(goal_id="nonexistent", uid="u1")
                assert exc_info.value.status_code == 404
                assert exc_info.value.detail == "Goal not found"

    def test_get_current_goal_advice_with_missing_id_in_dict(self):
        """If user goal dict exists but lacks 'id', return setup message rather than raising KeyError."""
        with patch.object(goals_router.goals_db, "get_user_goal", return_value={"title": "Corrupt goal without id"}):
            res = goals_router.get_current_goal_advice(uid="u1")

        assert res == {"advice": "Set a goal to get personalized advice!"}

    def test_get_current_goal_advice_raises_404_on_inactive_goal_race(self):
        """GET /v1/goals/advice raises HTTPException(404) if goal becomes inactive before advice generation."""
        with patch.object(goals_router.goals_db, "get_user_goal", return_value={"id": "g1", "title": "Goal"}):
            with patch.object(goals_router, "get_goal_advice", side_effect=ValueError("Goal not found")):
                with pytest.raises(HTTPException) as exc_info:
                    goals_router.get_current_goal_advice(uid="u1")
                assert exc_info.value.status_code == 404
                assert exc_info.value.detail == "Goal not found"

    def test_suggest_goal_endpoint_returns_valid_response_dict(self):
        """GET /v1/goals/suggest handler returns a dict that validates under GoalSuggestionResponse."""
        valid_dict = {
            "suggested_title": "Read 10 books",
            "suggested_type": "numeric",
            "suggested_target": 10.0,
            "suggested_min": 0.0,
            "suggested_max": 20.0,
            "reasoning": "Books expand knowledge",
        }
        with patch.object(goals_router, "suggest_goal_llm", return_value=valid_dict):
            res = goals_router.suggest_goal(uid="u1")

        assert GoalSuggestionResponse(**res).suggested_target == 10.0


class TestBooleanTrapDefensive:
    """Verifies float parsing helpers explicitly guard against Python bool-is-int subclass trap."""

    def test_safe_float_and_optional_float_boolean_trap(self):
        assert safe_float(True, 10.0) == 10.0
        assert safe_float(False, 10.0) == 10.0
        assert safe_float("True", 10.0) == 10.0
        assert safe_float(None, 10.0) == 10.0
        assert safe_float("", 10.0) == 10.0
        assert safe_float(float("nan"), 10.0) == 10.0
        assert safe_float(float("inf"), 10.0) == 10.0
        assert safe_float(12.5, 10.0) == 12.5

        assert safe_optional_float(True) is None
        assert safe_optional_float(False) is None
        assert safe_optional_float(None) is None
        assert safe_optional_float("nan") is None
        assert safe_optional_float(42.0) == 42.0

    def test_suggest_goal_coerces_boolean_hallucinations_from_llm(self, monkeypatch):
        llm_json = """
        {
            "suggested_title": "Drink more water",
            "suggested_type": "numeric",
            "suggested_target": true,
            "suggested_min": false,
            "suggested_max": true,
            "reasoning": "Stay hydrated"
        }
        """
        monkeypatch.setattr(llm_goals, "track_usage", lambda *_a, **_k: nullcontext())
        monkeypatch.setattr(
            llm_goals,
            "get_llm",
            lambda _name: SimpleNamespace(invoke=lambda _p: SimpleNamespace(content=llm_json)),
        )
        with patch("utils.memory.memory_service.MemoryService.read", return_value=[SimpleNamespace(dict=lambda: {"content": "water"})]):
            res = llm_goals.suggest_goal("u1")

        assert res["suggested_target"] == 10.0
        assert res["suggested_min"] == 0.0
        assert res["suggested_max"] == 10.0

    def test_goal_suggestion_response_self_healing_validator(self):
        """GoalSuggestionResponse self-heals invalid inputs (nulls, booleans, reversed bounds)."""
        raw = {
            "suggested_title": None,
            "suggested_type": "invalid_type",
            "suggested_target": True,
            "suggested_min": 50.0,
            "suggested_max": 10.0,
            "reasoning": None,
        }
        model = GoalSuggestionResponse.model_validate(raw)
        assert model.suggested_title == "Make progress every day"
        assert model.suggested_type == "scale"
        assert model.suggested_target == 10.0
        assert model.suggested_min == 10.0
        assert model.suggested_max == 50.0
        assert model.reasoning == "Start tracking your daily progress!"


class TestExtractProgressNullSafety:
    """Verifies progress extraction works safely with null current_value and qualitative goals."""

    def test_extract_progress_skips_purely_qualitative_goals_saving_tokens(self, monkeypatch):
        """Purely qualitative goals (no target, metric, or current value) must be skipped to save tokens."""
        goals_data = {
            "goal_qual": {
                "id": "goal_qual",
                "title": "Read Literature",
                "goal_type": None,
                "current_value": None,
                "target_value": None,
                "metric": None,
            }
        }
        prompts = _setup_stub_goals(monkeypatch, goals_data)
        result = llm_goals.extract_and_update_goal_progress("u1", "I read 3 books this month")

        assert result is None
        # Assert LLM was never invoked — 0 tokens burned!
        assert len(prompts) == 0

    def test_extract_progress_with_none_current_value_on_numeric_goal(self, monkeypatch):
        """Numeric goals with current_value=None format safely and update on new values."""
        goals_data = {
            "goal_num": {
                "id": "goal_num",
                "title": "Read 10 Books",
                "goal_type": "numeric",
                "current_value": None,
                "target_value": 10.0,
            }
        }
        prompts = _setup_stub_goals(
            monkeypatch,
            goals_data,
            llm_reply='[{"goal_id": "goal_num", "found": true, "value": 3.0, "reasoning": "read 3 books"}]',
        )
        saved_updates = []
        monkeypatch.setattr(
            goals_db,
            "update_goal_progress",
            lambda _uid, goal_id, value, **_k: saved_updates.append((goal_id, value)),
        )

        result = llm_goals.extract_and_update_goal_progress("u1", "I read 3 books this month")

        assert result is not None
        assert result.get("status") == "updated"
        assert saved_updates == [("goal_num", 3.0)]
        assert len(prompts) == 1
        assert ('progress: 0.0/10.0' in prompts[0]) or ('progress: not set/10.0' in prompts[0])
