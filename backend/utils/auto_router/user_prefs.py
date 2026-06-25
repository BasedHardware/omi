"""Per-user weight overrides for the auto-router.

v3 lets each user override the per-task default weights (e.g., "for PTT
I always want quality over latency"). The overrides are stored on the
backend and applied server-side when the `/pick` endpoint runs — the
client doesn't need to pass them on every request.

Validation matches `TaskSpec`:
    - Each weight must be a finite number in [0.0, 1.0]
    - The three weights must sum to 1.0 (tolerance 1e-3)
    - bool weights are rejected first (silent True/False-as-1.0/0.0 would
      bypass the sum=1.0 check)

A `UserPrefs` is a mapping from task name to `TaskWeights`. Tasks not in
the mapping use the task's default weights (no behavior change for
users who haven't set any overrides).

Side-effect-free. No I/O, no async, no shared state.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, Mapping, Optional


def _safe_to_float(value: Any, field_name: str, task_name: str) -> float:
    """Convert a weight value to float, rejecting booleans explicitly.

    In Python, `bool` is a subclass of `int`, so `float(True) == 1.0` would
    silently accept booleans as weights. The TaskWeights constructor
    checks `isinstance(w, bool)` AFTER coercion, so the bool silently
    becomes 1.0 and passes through. We reject it here before coercion
    with a clear error message.
    """
    if isinstance(value, bool):
        raise ValueError(f"UserPrefs weight '{field_name}' for task '{task_name}' " f"must be a number, got bool")
    if not isinstance(value, (int, float)):
        raise ValueError(
            f"UserPrefs weight '{field_name}' for task '{task_name}' " f"must be a number, got {type(value).__name__}"
        )
    if math.isnan(value):
        raise ValueError(f"UserPrefs weight '{field_name}' for task '{task_name}' must be finite")
    return float(value)


@dataclass(frozen=True)
class TaskWeights:
    """Per-task weights with the same validation as `TaskSpec` weights.

    Used both as the input to `UserPrefs` overrides and (via
    `merged_with`) as the effective weights applied at scoring time.
    """

    quality: float
    latency: float
    cost: float

    def __post_init__(self):
        for label, w in (
            ("quality", self.quality),
            ("latency", self.latency),
            ("cost", self.cost),
        ):
            if isinstance(w, bool):
                raise TypeError(f"TaskWeights.{label} must be a number, got bool")
            if not isinstance(w, (int, float)):
                raise TypeError(f"TaskWeights.{label} must be a number, got {type(w).__name__}")
            if not math.isfinite(w):
                raise ValueError(f"TaskWeights.{label} must be a finite number, got {w!r}")
            if w < 0.0 or w > 1.0:
                raise ValueError(f"TaskWeights.{label} must be in [0.0, 1.0], got {w}")
        total = self.quality + self.latency + self.cost
        if abs(total - 1.0) > 1e-3:
            raise ValueError(
                f"TaskWeights sum to {total:.4f}, expected 1.0 (tolerance 1e-3); "
                f"quality={self.quality}, latency={self.latency}, cost={self.cost}"
            )

    def as_dict(self) -> Dict[str, float]:
        return {"quality": self.quality, "latency": self.latency, "cost": self.cost}


@dataclass(frozen=True)
class UserPrefs:
    """Per-user weight overrides for one or more tasks.

    Empty `overrides` means "use task defaults for everything" — no
    behavior change. Adding an entry for a task overrides that task's
    default weights in the scoring path.

    Frozen: mutating after construction is not allowed (caller should
    construct a new UserPrefs with updated values).
    """

    overrides: Mapping[str, TaskWeights] = field(default_factory=dict)

    def __post_init__(self):
        # Validate every entry's weights (TaskWeights.__post_init__ runs
        # on construction). Also ensure task names are non-empty strings.
        for task_name, weights in self.overrides.items():
            if not isinstance(task_name, str) or not task_name:
                raise ValueError(f"UserPrefs override key must be a non-empty string, got {task_name!r}")
            if not isinstance(weights, TaskWeights):
                raise TypeError(
                    f"UserPrefs override for {task_name!r} must be a TaskWeights, " f"got {type(weights).__name__}"
                )

    @classmethod
    def empty(cls) -> "UserPrefs":
        """An empty UserPrefs (no overrides — use task defaults)."""
        return cls(overrides={})

    def merged_with(self, defaults: Mapping[str, TaskWeights]) -> Dict[str, TaskWeights]:
        """Return the effective weights for each task: defaults + overrides.

        Tasks in `overrides` use the user's weights; tasks NOT in
        `overrides` use the task's default weights. If a task is in
        `overrides` but NOT in `defaults`, the override is preserved
        (the caller is expected to validate task names elsewhere).

        Returns a plain dict (not a UserPrefs) because the merged result
        is by definition per-task, not a stored user preference.
        """
        merged: Dict[str, TaskWeights] = dict(defaults)
        for task_name, user_weights in self.overrides.items():
            merged[task_name] = user_weights
        return merged

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        """Serialize to a JSON-friendly nested dict.

        Returns: {task_name: {quality, latency, cost}, ...}
        Empty overrides serialize as an empty dict.
        """
        return {task_name: weights.as_dict() for task_name, weights in self.overrides.items()}

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Dict[str, float]]]) -> "UserPrefs":
        """Parse a JSON-friendly nested dict into a UserPrefs.

        Returns an empty UserPrefs if `data` is None or empty.

        Bool check FIRST: in Python, `bool` is a subclass of `int`, so
        `float(True) == 1.0` would silently accept booleans as weights.
        We reject booleans explicitly with a clear error message.
        """
        if not data:
            return cls.empty()
        overrides: Dict[str, TaskWeights] = {}
        for task_name, weights_dict in data.items():
            if not isinstance(weights_dict, dict):
                raise ValueError(
                    f"UserPrefs entry for {task_name!r} must be a dict, " f"got {type(weights_dict).__name__}"
                )
            overrides[task_name] = TaskWeights(
                quality=_safe_to_float(weights_dict["quality"], "quality", task_name),
                latency=_safe_to_float(weights_dict["latency"], "latency", task_name),
                cost=_safe_to_float(weights_dict["cost"], "cost", task_name),
            )
        return cls(overrides=overrides)
