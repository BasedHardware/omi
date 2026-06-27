"""Model registry: maps task name → list of candidate ModelSpec.

A `ModelRegistry` is built from either:
1. A JSON file (production: `benchmarks.json`), or
2. An empty registry (development: no candidates for any task).

Models in the registry are scored against their task using the scoring
function (T-001). The endpoint (T-004) picks the highest-scoring model
per task.

A missing task entry in the JSON returns an empty candidate list (not
an error) — useful when a task is defined but no models are benchmarked
yet; the endpoint can still respond with `{"model": null}`.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from utils.auto_router.scoring import ModelSpec

logger = logging.getLogger(__name__)


class ModelValidationError(ValueError):
    """Raised when the JSON file has structurally invalid model definitions."""


class ModelRegistry:
    """Maps task name → list of candidate ModelSpec for that task.

    Tasks with no entries simply return an empty list from `candidates_for`.
    This makes the registry robust to incomplete benchmark data — a missing
    task entry is not an error.
    """

    def __init__(self, models_by_task: Dict[str, List[ModelSpec]]):
        # Defensive copy: freeze values too so callers can't mutate ModelSpec lists.
        self._models: Dict[str, List[ModelSpec]] = {task: list(models) for task, models in models_by_task.items()}

    # ---- Factories ---------------------------------------------------------

    @classmethod
    def empty(cls) -> "ModelRegistry":
        """Return an empty registry — no candidates for any task."""
        return cls({})

    @classmethod
    def from_model_dicts(cls, models_by_task: Dict[str, List[dict]]) -> "ModelRegistry":
        """Build from a dict mapping task_name → list of model dicts."""
        result: Dict[str, List[ModelSpec]] = {}
        for task_name, model_dicts in models_by_task.items():
            result[task_name] = [_model_spec_from_dict(md) for md in model_dicts]
        return cls(result)

    @classmethod
    def from_json(cls, path: str | Path) -> "ModelRegistry":
        """Load models from a JSON file. The file must have a top-level "models" key
        with a dict mapping task_name → list of model dicts.

        Missing file → returns an empty registry (logs a warning).
        Malformed JSON → raises ModelValidationError.
        Top-level shape wrong → raises ModelValidationError.
        """
        path = Path(path)
        if not path.exists():
            logger.warning(f"ModelRegistry: file {path} not found, using empty registry")
            return cls.empty()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ModelValidationError(f"ModelRegistry: malformed JSON in {path}: {e}") from e
        if not isinstance(data, dict):
            raise ModelValidationError(
                f"ModelRegistry: {path} must be a JSON object at the top level, got {type(data).__name__}"
            )
        if "models" not in data:
            raise ModelValidationError(
                f"ModelRegistry: {path} must contain a top-level 'models' key "
                f"with a dict mapping task_name → list of model dicts"
            )
        if not isinstance(data["models"], dict):
            raise ModelValidationError(
                f"ModelRegistry: {path} 'models' must be a dict (task_name → list), got {type(data['models']).__name__}"
            )
        return cls.from_model_dicts(data["models"])

    # ---- Lookups -----------------------------------------------------------

    def candidates_for(self, task_name: str) -> List[ModelSpec]:
        """Return the list of candidate models for `task_name`.

        Returns an empty list if the task has no models registered (not an error).
        """
        return list(self._models.get(task_name, []))

    def all_tasks(self) -> List[str]:
        """Return all task names that have at least one model."""
        return list(self._models.keys())

    def total_candidate_count(self) -> int:
        """Return the total number of (task, model) pairs across all tasks."""
        return sum(len(models) for models in self._models.values())

    def __contains__(self, task_name: str) -> bool:
        return task_name in self._models


# ---- Internal helpers ------------------------------------------------------


def _model_spec_from_dict(md: dict) -> ModelSpec:
    """Build a ModelSpec from a dict.

    Required keys: id, quality_score, latency_score, cost_score.
    Optional keys: provider.

    Scores outside [0.0, 1.0] are allowed here (the scoring function clamps them),
    but we log a warning so bad benchmark data is visible.
    """
    required = ("id", "quality_score", "latency_score", "cost_score")
    missing = [k for k in required if k not in md]
    if missing:
        raise ModelValidationError(f"model dict missing required keys: {missing}; got: {md}")

    return ModelSpec(
        id=str(md["id"]),
        quality_score=_optional_float(md.get("quality_score")),
        latency_score=_optional_float(md.get("latency_score")),
        cost_score=_optional_float(md.get("cost_score")),
        provider=str(md.get("provider", "")),
    )


def _optional_float(value) -> Optional[float]:
    """Convert to float, or return None if the value is None or 'null'."""
    if value is None:
        return None
    return float(value)
