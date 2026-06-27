"""Task registry: maps task names to TaskSpec definitions.

A `TaskRegistry` is built from either:
1. A JSON file (production: `benchmarks.json` loaded at startup), or
2. The built-in defaults below (development: zero-config).

All task names referenced anywhere in the system MUST be defined in the
TaskRegistry — the endpoint (T-004) raises HTTP 400 for unknown tasks.

Built-in defaults for the 5 task types from the spec (auto-router v1 brief):
- ptt_response:           q=0.4, l=0.5, c=0.1  (latency-critical — real-time voice)
- screenshot_understanding: q=0.6, l=0.2, c=0.2  (quality-critical — vision)
- screenshot_embedding:    q=0.2, l=0.3, c=0.5  (cost-critical — bulk processing)
- general_assistant:       q=0.5, l=0.3, c=0.2  (balanced)
- transcription:           q=0.3, l=0.6, c=0.1  (latency-critical — STT is real-time)

These weights are the v1 starting point. The weights are NOT renormalized
in `score()` — they're applied exactly as specified. To bias a task toward
quality, raise `quality_weight`; the others drop accordingly.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from utils.auto_router.scoring import TaskSpec

logger = logging.getLogger(__name__)


# Tolerance for "weights sum to 1.0" validation. Allows tiny floating-point drift.
WEIGHT_SUM_TOLERANCE = 1e-3


class UnknownTaskError(KeyError):
    """Raised when looking up a task name that isn't in the registry."""

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"unknown task: {self.name!r} (not in TaskRegistry)"


class TaskValidationError(ValueError):
    """Raised when the JSON file has structurally invalid task definitions."""


# Built-in defaults — used when no JSON file is provided.
# Each tuple is (name, quality_weight, latency_weight, cost_weight, description).
_BUILTIN_TASKS: List[dict] = [
    {
        "name": "ptt_response",
        "quality_weight": 0.4,
        "latency_weight": 0.5,
        "cost_weight": 0.1,
        "description": "Real-time voice responses via the realtime hub. Latency-critical.",
    },
    {
        "name": "screenshot_understanding",
        "quality_weight": 0.6,
        "latency_weight": 0.2,
        "cost_weight": 0.2,
        "description": "Vision-language analysis of screen captures. Quality-critical.",
    },
    {
        "name": "screenshot_embedding",
        "quality_weight": 0.2,
        "latency_weight": 0.3,
        "cost_weight": 0.5,
        "description": "Embedding pipeline for screen captures and retrieval. Cost-critical.",
    },
    {
        "name": "general_assistant",
        "quality_weight": 0.5,
        "latency_weight": 0.3,
        "cost_weight": 0.2,
        "description": "General chat assistant replies. Balanced quality/latency/cost.",
    },
    {
        "name": "transcription",
        "quality_weight": 0.3,
        "latency_weight": 0.6,
        "cost_weight": 0.1,
        "description": "Speech-to-text transcription (STT). Latency-critical.",
    },
]


class TaskRegistry:
    """Maps task name → TaskSpec.

    Use `TaskRegistry.defaults()` to get the 5 built-in tasks (no file needed),
    or `TaskRegistry.from_json(path)` to load from a JSON file. The endpoint
    layer combines a TaskRegistry with a ModelRegistry.
    """

    def __init__(self, tasks: Dict[str, TaskSpec]):
        # Defensive copy: callers shouldn't be able to mutate the internal dict.
        self._tasks: Dict[str, TaskSpec] = dict(tasks)

    # ---- Factories ---------------------------------------------------------

    @classmethod
    def defaults(cls) -> "TaskRegistry":
        """Return a registry with the 5 built-in task types."""
        return cls.from_task_dicts(_BUILTIN_TASKS)

    @classmethod
    def from_task_dicts(cls, task_dicts: List[dict]) -> "TaskRegistry":
        """Build from a list of dicts (each has keys: name, quality_weight,
        latency_weight, cost_weight, description). Validates weights sum to 1.0.
        """
        tasks: Dict[str, TaskSpec] = {}
        for td in task_dicts:
            spec = _task_spec_from_dict(td)
            if spec.name in tasks:
                raise TaskValidationError(f"duplicate task name in registry: {spec.name!r}")
            tasks[spec.name] = spec
        return cls(tasks)

    @classmethod
    def from_json(cls, path: str | Path) -> "TaskRegistry":
        """Load tasks from a JSON file. The file must have a top-level "tasks" key
        with a list of task dicts.

        Missing file → returns the built-in defaults (logs a warning, doesn't raise).
        Malformed JSON → raises TaskValidationError.
        Top-level shape wrong (not a dict, or 'tasks' missing/not a list) → raises TaskValidationError.
        """
        path = Path(path)
        if not path.exists():
            logger.warning(f"TaskRegistry: file {path} not found, using built-in defaults")
            return cls.defaults()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise TaskValidationError(f"TaskRegistry: malformed JSON in {path}: {e}") from e
        if not isinstance(data, dict):
            raise TaskValidationError(
                f"TaskRegistry: {path} must be a JSON object at the top level, got {type(data).__name__}"
            )
        if "tasks" not in data:
            raise TaskValidationError(f"TaskRegistry: {path} must contain a top-level 'tasks' key")
        if not isinstance(data["tasks"], list):
            raise TaskValidationError(
                f"TaskRegistry: {path} 'tasks' must be a list, got {type(data['tasks']).__name__}"
            )
        return cls.from_task_dicts(data["tasks"])

    # ---- Lookups -----------------------------------------------------------

    def get(self, name: str) -> TaskSpec:
        """Return the TaskSpec for `name`. Raises UnknownTaskError if not found."""
        if name not in self._tasks:
            raise UnknownTaskError(name)
        return self._tasks[name]

    def try_get(self, name: str) -> Optional[TaskSpec]:
        """Return the TaskSpec for `name`, or None if not found."""
        return self._tasks.get(name)

    def names(self) -> List[str]:
        """Return all registered task names (unsorted; do not rely on order)."""
        return list(self._tasks.keys())

    def all(self) -> List[TaskSpec]:
        """Return all registered TaskSpecs (unsorted)."""
        return list(self._tasks.values())

    def __contains__(self, name: str) -> bool:
        return name in self._tasks

    def __len__(self) -> int:
        return len(self._tasks)


# ---- Internal helpers ------------------------------------------------------


def _task_spec_from_dict(td: dict) -> TaskSpec:
    """Build a TaskSpec from a dict, with weight-sum validation.

    Raises TaskValidationError on missing keys or weights that don't sum to 1.0.
    """
    required = ("name", "quality_weight", "latency_weight", "cost_weight")
    missing = [k for k in required if k not in td]
    if missing:
        raise TaskValidationError(f"task dict missing required keys: {missing}; got: {td}")

    qw = float(td["quality_weight"])
    lw = float(td["latency_weight"])
    cw = float(td["cost_weight"])

    total = qw + lw + cw
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise TaskValidationError(
            f"task {td['name']!r} weights sum to {total:.4f}, expected 1.0 "
            f"(tolerance {WEIGHT_SUM_TOLERANCE}); quality={qw}, latency={lw}, cost={cw}"
        )

    return TaskSpec(
        name=str(td["name"]),
        quality_weight=qw,
        latency_weight=lw,
        cost_weight=cw,
        description=str(td.get("description", "")),
    )
