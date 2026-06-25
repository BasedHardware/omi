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


# ---------------------------------------------------------------------------
# Edge cases: Unicode, empty fields, model used across multiple tasks
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """JSON loader should handle non-ASCII, empty fields, and shared model IDs."""

    def test_unicode_model_id_loads(self, tmp_path: Path):
        path = tmp_path / "models.json"
        path.write_text(
            json.dumps(
                {
                    "models": {
                        "translation": [
                            {
                                "id": "gpt-4o-模型-\u4e2d\u6587",
                                "provider": "openai",
                                "quality_score": 0.9,
                                "latency_score": 0.7,
                                "cost_score": 0.5,
                            }
                        ],
                    },
                },
                ensure_ascii=False,
            )
        )
        reg = ModelRegistry.from_json(path)
        candidates = reg.candidates_for("translation")
        assert candidates[0].id == "gpt-4o-模型-\u4e2d\u6587"

    def test_empty_provider_string_accepted(self, tmp_path: Path):
        path = tmp_path / "models.json"
        path.write_text(
            json.dumps(
                {
                    "models": {
                        "t": [
                            {
                                "id": "m1",
                                "quality_score": 0.5,
                                "latency_score": 0.5,
                                "cost_score": 0.5,
                            }
                        ],
                    },
                }
            )
        )
        reg = ModelRegistry.from_json(path)
        assert reg.candidates_for("t")[0].provider == ""

    def test_same_model_id_in_multiple_tasks_allowed(self, tmp_path: Path):
        # A model can be a candidate for multiple tasks (e.g., claude-sonnet-4-6
        # is in both ptt_response and screenshot_understanding).
        path = tmp_path / "models.json"
        path.write_text(
            json.dumps(
                {
                    "models": {
                        "task_a": [
                            {
                                "id": "shared-model",
                                "quality_score": 0.5,
                                "latency_score": 0.5,
                                "cost_score": 0.5,
                            }
                        ],
                        "task_b": [
                            {
                                "id": "shared-model",
                                "quality_score": 0.7,
                                "latency_score": 0.3,
                                "cost_score": 0.7,
                            }
                        ],
                    },
                }
            )
        )
        reg = ModelRegistry.from_json(path)
        # Same ID, different task — each task gets its own copy of the ModelSpec.
        assert reg.candidates_for("task_a")[0].quality_score == 0.5
        assert reg.candidates_for("task_b")[0].quality_score == 0.7

    def test_very_long_model_id_accepted(self, tmp_path: Path):
        long_id = "a" * 500
        path = tmp_path / "models.json"
        path.write_text(
            json.dumps(
                {
                    "models": {
                        "t": [
                            {
                                "id": long_id,
                                "quality_score": 0.5,
                                "latency_score": 0.5,
                                "cost_score": 0.5,
                            }
                        ],
                    },
                }
            )
        )
        reg = ModelRegistry.from_json(path)
        assert reg.candidates_for("t")[0].id == long_id

    def test_models_array_can_be_empty_per_task(self, tmp_path: Path):
        # Empty candidate list is valid (no models registered yet for a new task).
        path = tmp_path / "models.json"
        path.write_text(
            json.dumps(
                {
                    "models": {
                        "task_with_models": [
                            {
                                "id": "m1",
                                "quality_score": 0.5,
                                "latency_score": 0.5,
                                "cost_score": 0.5,
                            }
                        ],
                        "task_without_models": [],
                    },
                }
            )
        )
        reg = ModelRegistry.from_json(path)
        assert len(reg.candidates_for("task_with_models")) == 1
        assert len(reg.candidates_for("task_without_models")) == 0

    def test_top_level_must_be_object(self, tmp_path: Path):
        # Top-level array → clean error, not AttributeError.
        path = tmp_path / "wrong.json"
        path.write_text(json.dumps([{"task": []}]))
        with pytest.raises(ModelValidationError, match="JSON object at the top level"):
            ModelRegistry.from_json(path)

    def test_models_must_be_dict(self, tmp_path: Path):
        # `models` as a list → clean error, not AttributeError on .values().
        path = tmp_path / "wrong.json"
        path.write_text(json.dumps({"models": []}))
        with pytest.raises(ModelValidationError, match="'models' must be a dict"):
            ModelRegistry.from_json(path)

    def test_models_key_missing(self, tmp_path: Path):
        path = tmp_path / "wrong.json"
        path.write_text(json.dumps({"other_key": {}}))
        with pytest.raises(ModelValidationError, match="must contain a top-level 'models' key"):
            ModelRegistry.from_json(path)


# ---------------------------------------------------------------------------
# AC: v5 benchmarks expansion — new STT + OpenAI embedding models
# ---------------------------------------------------------------------------


class TestV5BenchmarksExpansion:
    """v5 added 1 STT model (assemblyai-universal) and updated/expanded
    OpenAI embedding models (text-embedding-3-small updated to MTEB-based
    scores; text-embedding-3-large + text-embedding-ada-002 added)."""

    @pytest.fixture
    def example(self) -> Path:
        path = Path(__file__).parent.parent.parent / "utils" / "auto_router" / "benchmarks.example.json"
        if not path.exists():
            pytest.skip("benchmarks.example.json not present")
        return path

    def test_assemblyai_universal_present_in_transcription(self, example):
        """v5 added assemblyai-universal as a STT option (WER ~8.4%)."""
        reg = ModelRegistry.from_json(example)
        ids = [m.id for m in reg.candidates_for("transcription")]
        assert "assemblyai-universal" in ids
        # Verify it has valid scores (the spec's MTEB-based defaults)
        aai = next(m for m in reg.candidates_for("transcription") if m.id == "assemblyai-universal")
        assert 0.0 <= aai.quality_score <= 1.0
        assert 0.0 <= aai.latency_score <= 1.0
        assert 0.0 <= aai.cost_score <= 1.0
        # Quality should be the highest in the set (it's the most accurate)
        assert aai.quality_score >= 0.85, f"AssemblyAI quality should be high: {aai.quality_score}"

    def test_transcription_has_4_candidates(self, example):
        """After v5: parakeet + deepgram + whisper + assemblyai = 4 candidates."""
        reg = ModelRegistry.from_json(example)
        assert len(reg.candidates_for("transcription")) == 4

    def test_openai_embedding_models_present(self, example):
        """v5 has all 3 OpenAI embedding models."""
        reg = ModelRegistry.from_json(example)
        ids = [m.id for m in reg.candidates_for("screenshot_embedding")]
        assert "text-embedding-3-small" in ids
        assert "text-embedding-3-large" in ids
        assert "text-embedding-ada-002" in ids

    def test_text_embedding_3_large_has_highest_quality_among_openai(self, example):
        """text-embedding-3-large should have higher quality than the other two."""
        reg = ModelRegistry.from_json(example)
        models = {m.id: m for m in reg.candidates_for("screenshot_embedding")}
        large = models["text-embedding-3-large"]
        small = models["text-embedding-3-small"]
        ada = models["text-embedding-ada-002"]
        assert large.quality_score > small.quality_score
        assert large.quality_score > ada.quality_score

    def test_screenshot_embedding_has_5_candidates(self, example):
        """After v5: 3 OpenAI + voyage + cohere = 5 candidates."""
        reg = ModelRegistry.from_json(example)
        assert len(reg.candidates_for("screenshot_embedding")) == 5
