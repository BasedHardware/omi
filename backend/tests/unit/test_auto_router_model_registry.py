"""Unit tests for ModelRegistry."""

import json
import pytest
from pathlib import Path

from utils.auto_router.model_registry import (
    ModelRegistry,
    ModelValidationError,
)
from utils.auto_router.scoring import ModelSpec


# ---------------------------------------------------------------------------
# Empty registry
# ---------------------------------------------------------------------------


class TestEmpty:
    """ModelRegistry.empty() has no candidates for any task."""

    def test_empty_has_no_tasks(self):
        reg = ModelRegistry.empty()
        assert reg.all_tasks() == []
        assert reg.total_candidate_count() == 0

    def test_empty_candidates_for_any_task_is_empty_list(self):
        reg = ModelRegistry.empty()
        assert reg.candidates_for("anything") == []


# ---------------------------------------------------------------------------
# from_model_dicts
# ---------------------------------------------------------------------------


class TestFromModelDicts:
    """from_model_dicts builds the registry from raw dicts."""

    def test_valid_models_build_registry(self):
        models = {
            "ptt_response": [
                {"id": "m1", "quality_score": 0.5, "latency_score": 0.5, "cost_score": 0.5},
                {"id": "m2", "quality_score": 0.7, "latency_score": 0.3, "cost_score": 0.7},
            ],
        }
        reg = ModelRegistry.from_model_dicts(models)
        assert len(reg.candidates_for("ptt_response")) == 2

    def test_provider_field_optional(self):
        models = {
            "t": [{"id": "m1", "quality_score": 0.5, "latency_score": 0.5, "cost_score": 0.5}],
        }
        reg = ModelRegistry.from_model_dicts(models)
        spec = reg.candidates_for("t")[0]
        assert spec.provider == ""

    def test_provider_field_preserved(self):
        models = {
            "t": [{"id": "m1", "provider": "anthropic", "quality_score": 0.5, "latency_score": 0.5, "cost_score": 0.5}],
        }
        reg = ModelRegistry.from_model_dicts(models)
        spec = reg.candidates_for("t")[0]
        assert spec.provider == "anthropic"

    def test_none_score_allowed(self):
        models = {
            "t": [{"id": "m1", "quality_score": None, "latency_score": 0.5, "cost_score": 0.5}],
        }
        reg = ModelRegistry.from_model_dicts(models)
        spec = reg.candidates_for("t")[0]
        assert spec.quality_score is None

    def test_missing_required_key_raises(self):
        models = {
            "t": [{"id": "m1", "quality_score": 0.5, "latency_score": 0.5}],  # no cost_score
        }
        with pytest.raises(ModelValidationError, match="missing required keys"):
            ModelRegistry.from_model_dicts(models)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


class TestLookups:
    """candidates_for returns a list (possibly empty); total count is correct."""

    def test_candidates_for_unknown_task_is_empty_list_not_error(self):
        reg = ModelRegistry.empty()
        assert reg.candidates_for("no-such-task") == []

    def test_candidates_for_returns_a_copy(self):
        # Mutating the returned list must NOT affect the registry.
        models = {"t": [{"id": "m1", "quality_score": 0.5, "latency_score": 0.5, "cost_score": 0.5}]}
        reg = ModelRegistry.from_model_dicts(models)
        first = reg.candidates_for("t")
        first.clear()
        second = reg.candidates_for("t")
        assert len(second) == 1  # still has the model

    def test_total_candidate_count_sums_across_tasks(self):
        models = {
            "t1": [
                {"id": "a", "quality_score": 0.5, "latency_score": 0.5, "cost_score": 0.5},
                {"id": "b", "quality_score": 0.5, "latency_score": 0.5, "cost_score": 0.5},
            ],
            "t2": [
                {"id": "c", "quality_score": 0.5, "latency_score": 0.5, "cost_score": 0.5},
            ],
        }
        reg = ModelRegistry.from_model_dicts(models)
        assert reg.total_candidate_count() == 3

    def test_all_tasks_lists_only_tasks_with_models(self):
        models = {
            "t1": [{"id": "a", "quality_score": 0.5, "latency_score": 0.5, "cost_score": 0.5}],
        }
        reg = ModelRegistry.from_model_dicts(models)
        assert reg.all_tasks() == ["t1"]
        assert "t2" not in reg


# ---------------------------------------------------------------------------
# from_json
# ---------------------------------------------------------------------------


class TestFromJson:
    """from_json handles missing files, malformed JSON, and missing keys."""

    def test_missing_file_returns_empty_registry(self, tmp_path: Path):
        reg = ModelRegistry.from_json(tmp_path / "nonexistent.json")
        assert reg.total_candidate_count() == 0

    def test_valid_json_loads(self, tmp_path: Path):
        path = tmp_path / "models.json"
        path.write_text(
            json.dumps(
                {
                    "models": {
                        "ptt_response": [
                            {"id": "m1", "quality_score": 0.5, "latency_score": 0.5, "cost_score": 0.5},
                        ],
                    },
                }
            )
        )
        reg = ModelRegistry.from_json(path)
        assert len(reg.candidates_for("ptt_response")) == 1

    def test_malformed_json_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json at all")
        with pytest.raises(ModelValidationError, match="malformed JSON"):
            ModelRegistry.from_json(path)

    def test_missing_models_key_raises(self, tmp_path: Path):
        path = tmp_path / "wrong-shape.json"
        path.write_text(json.dumps({"not_models": {}}))
        with pytest.raises(ModelValidationError, match="top-level 'models' key"):
            ModelRegistry.from_json(path)

    def test_loads_benchmarks_example_json(self):
        # The committed example file must load without errors and have models for all 5 tasks.
        example = Path(__file__).parent.parent.parent / "utils" / "auto_router" / "benchmarks.example.json"
        if not example.exists():
            pytest.skip("benchmarks.example.json not present")
        reg = ModelRegistry.from_json(example)
        # Per spec AC: at least 3 models per task
        for task in (
            "ptt_response",
            "screenshot_understanding",
            "screenshot_embedding",
            "general_assistant",
            "transcription",
        ):
            assert (
                len(reg.candidates_for(task)) >= 3
            ), f"task {task!r} has only {len(reg.candidates_for(task))} models (need >= 3)"
