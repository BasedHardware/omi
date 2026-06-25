"""Unit tests for TaskRegistry."""

import json
import pytest
from pathlib import Path

from utils.auto_router.task_registry import (
    TaskRegistry,
    UnknownTaskError,
    TaskValidationError,
)


# ---------------------------------------------------------------------------
# Built-in defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    """TaskRegistry.defaults() returns the 5 v1 task types."""

    def test_defaults_has_five_tasks(self):
        reg = TaskRegistry.defaults()
        assert len(reg) == 5

    def test_defaults_contains_all_expected_tasks(self):
        reg = TaskRegistry.defaults()
        assert "ptt_response" in reg
        assert "screenshot_understanding" in reg
        assert "screenshot_embedding" in reg
        assert "general_assistant" in reg
        assert "transcription" in reg

    def test_defaults_weights_sum_to_one(self):
        reg = TaskRegistry.defaults()
        for spec in reg.all():
            total = spec.quality_weight + spec.latency_weight + spec.cost_weight
            assert abs(total - 1.0) < 1e-3, f"{spec.name} weights sum to {total}"


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


class TestLookups:
    """get/try_get/names/all behave correctly."""

    def test_get_known_task_returns_spec(self):
        reg = TaskRegistry.defaults()
        spec = reg.get("ptt_response")
        assert spec.name == "ptt_response"
        assert spec.latency_weight > spec.cost_weight  # latency-critical

    def test_get_unknown_task_raises(self):
        reg = TaskRegistry.defaults()
        with pytest.raises(UnknownTaskError) as excinfo:
            reg.get("nonexistent_task")
        assert excinfo.value.name == "nonexistent_task"
        assert "nonexistent_task" in str(excinfo.value)

    def test_try_get_returns_none_for_unknown(self):
        reg = TaskRegistry.defaults()
        assert reg.try_get("nope") is None

    def test_try_get_returns_spec_for_known(self):
        reg = TaskRegistry.defaults()
        spec = reg.try_get("ptt_response")
        assert spec is not None
        assert spec.name == "ptt_response"

    def test_names_returns_all_registered(self):
        reg = TaskRegistry.defaults()
        assert set(reg.names()) == {
            "ptt_response",
            "screenshot_understanding",
            "screenshot_embedding",
            "general_assistant",
            "transcription",
        }

    def test_contains_operator(self):
        reg = TaskRegistry.defaults()
        assert "ptt_response" in reg
        assert "nonexistent" not in reg


# ---------------------------------------------------------------------------
# from_task_dicts
# ---------------------------------------------------------------------------


class TestFromTaskDicts:
    """from_task_dicts validates weight sums and rejects malformed input."""

    def test_valid_tasks_build_registry(self):
        tasks = [
            {"name": "a", "quality_weight": 0.5, "latency_weight": 0.3, "cost_weight": 0.2},
            {"name": "b", "quality_weight": 0.3, "latency_weight": 0.3, "cost_weight": 0.4},
        ]
        reg = TaskRegistry.from_task_dicts(tasks)
        assert len(reg) == 2

    def test_weights_not_summing_to_one_raises(self):
        tasks = [
            {"name": "bad", "quality_weight": 0.5, "latency_weight": 0.3, "cost_weight": 0.1},
        ]
        with pytest.raises(TaskValidationError, match="weights sum to"):
            TaskRegistry.from_task_dicts(tasks)

    def test_weights_summing_to_one_within_tolerance_accepted(self):
        # Weights 0.5 + 0.3 + 0.2 = 1.0 exactly (within tolerance).
        tasks = [
            {"name": "exact", "quality_weight": 0.5, "latency_weight": 0.3, "cost_weight": 0.2},
        ]
        reg = TaskRegistry.from_task_dicts(tasks)
        assert "exact" in reg

    def test_weights_within_tolerance_but_not_exact_accepted(self):
        # Weights sum to 1.0005 — within tolerance 1e-3 (0.001).
        tasks = [
            {"name": "close", "quality_weight": 0.5, "latency_weight": 0.3, "cost_weight": 0.2005},
        ]
        reg = TaskRegistry.from_task_dicts(tasks)
        assert "close" in reg

    def test_missing_required_key_raises(self):
        tasks = [{"name": "incomplete", "quality_weight": 0.5, "latency_weight": 0.5}]
        with pytest.raises(TaskValidationError, match="missing required keys"):
            TaskRegistry.from_task_dicts(tasks)

    def test_duplicate_task_name_raises(self):
        tasks = [
            {"name": "dup", "quality_weight": 0.5, "latency_weight": 0.3, "cost_weight": 0.2},
            {"name": "dup", "quality_weight": 0.3, "latency_weight": 0.3, "cost_weight": 0.4},
        ]
        with pytest.raises(TaskValidationError, match="duplicate task name"):
            TaskRegistry.from_task_dicts(tasks)

    def test_description_is_optional(self):
        tasks = [{"name": "no-desc", "quality_weight": 0.5, "latency_weight": 0.3, "cost_weight": 0.2}]
        reg = TaskRegistry.from_task_dicts(tasks)
        assert reg.get("no-desc").description == ""


# ---------------------------------------------------------------------------
# from_json
# ---------------------------------------------------------------------------


class TestFromJson:
    """from_json handles missing files, malformed JSON, and missing keys."""

    def test_missing_file_returns_defaults(self, tmp_path: Path):
        reg = TaskRegistry.from_json(tmp_path / "nonexistent.json")
        assert len(reg) == 5  # built-in defaults

    def test_valid_json_loads(self, tmp_path: Path):
        path = tmp_path / "tasks.json"
        path.write_text(
            json.dumps(
                {
                    "tasks": [
                        {"name": "t1", "quality_weight": 0.5, "latency_weight": 0.3, "cost_weight": 0.2},
                    ]
                }
            )
        )
        reg = TaskRegistry.from_json(path)
        assert "t1" in reg

    def test_malformed_json_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{ this is not json")
        with pytest.raises(TaskValidationError, match="malformed JSON"):
            TaskRegistry.from_json(path)

    def test_missing_tasks_key_raises(self, tmp_path: Path):
        path = tmp_path / "wrong-shape.json"
        path.write_text(json.dumps({"not_tasks": []}))
        with pytest.raises(TaskValidationError, match="top-level 'tasks' key"):
            TaskRegistry.from_json(path)

    def test_loads_benchmarks_example_json(self):
        # The committed example file must load without errors and contain all 5 tasks.
        from utils.auto_router.task_registry import TaskRegistry as TR

        example = Path(__file__).parent.parent.parent / "utils" / "auto_router" / "benchmarks.example.json"
        if not example.exists():
            pytest.skip("benchmarks.example.json not present (test runs from a different cwd)")
        reg = TR.from_json(example)
        assert len(reg) == 5

    def test_top_level_must_be_object(self, tmp_path: Path):
        # If someone writes `"tasks": [...]` (a top-level list), we should
        # raise a clean TaskValidationError, not crash with AttributeError.
        path = tmp_path / "wrong-shape.json"
        path.write_text(json.dumps([{"name": "x", "quality_weight": 0.5, "latency_weight": 0.5, "cost_weight": 0}]))
        with pytest.raises(TaskValidationError, match="JSON object at the top level"):
            TaskRegistry.from_json(path)

    def test_tasks_must_be_list(self, tmp_path: Path):
        # If `tasks` is a dict instead of a list, raise a clean error.
        path = tmp_path / "wrong-shape.json"
        path.write_text(
            json.dumps({"tasks": {"name": "x", "quality_weight": 0.5, "latency_weight": 0.5, "cost_weight": 0}})
        )
        with pytest.raises(TaskValidationError, match="'tasks' must be a list"):
            TaskRegistry.from_json(path)

    def test_tasks_key_missing(self, tmp_path: Path):
        path = tmp_path / "wrong-shape.json"
        path.write_text(json.dumps({"other_key": []}))
        with pytest.raises(TaskValidationError, match="must contain a top-level 'tasks' key"):
            TaskRegistry.from_json(path)
