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
    """Per-user preferences for one or more tasks.

    Two kinds of overrides per task:

    1. **Weight overrides** (`overrides`): per-task weights (quality/latency/cost)
       used by the `/pick` endpoint when computing the score. Empty means
       "use the task's default weights from TaskRegistry".

    2. **Model overrides** (`model_overrides`): explicit model pin per task
       (added in v6). When set, `/pick` returns this model directly with
       `attribution: "user_override"` instead of computing a pick. Empty
       means "let the auto-router choose".

    Both default to empty. Construction is additive — old callers passing
    only `overrides={...}` continue to work (backward compatible).

    Frozen: mutating after construction is not allowed (caller should
    construct a new UserPrefs with updated values).
    """

    overrides: Mapping[str, TaskWeights] = field(default_factory=dict)
    model_overrides: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        # Validate weight overrides.
        for task_name, weights in self.overrides.items():
            if not isinstance(task_name, str) or not task_name:
                raise ValueError(f"UserPrefs override key must be a non-empty string, got {task_name!r}")
            if not isinstance(weights, TaskWeights):
                raise TypeError(
                    f"UserPrefs override for {task_name!r} must be a TaskWeights, " f"got {type(weights).__name__}"
                )
        # Validate model overrides (v6). Each task name must be a non-empty
        # string; each model ID must be a non-empty string. We don't
        # validate the model exists in the candidate set here — that's
        # done at /pick time so users can pin models before they're
        # registered (forward-compat).
        for task_name, model_id in self.model_overrides.items():
            if not isinstance(task_name, str) or not task_name:
                raise ValueError(f"UserPrefs model_override key must be a non-empty string, got {task_name!r}")
            if not isinstance(model_id, str) or not model_id:
                raise ValueError(
                    f"UserPrefs model_override for {task_name!r} must be a non-empty string, got {model_id!r}"
                )

    @classmethod
    def empty(cls) -> "UserPrefs":
        """An empty UserPrefs (no overrides — use task defaults + auto-router picks)."""
        return cls(overrides={}, model_overrides={})

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

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly nested dict.

        Returns a dict with two keys:
            - "overrides": {task_name: {quality, latency, cost}, ...}
            - "model_overrides": {task_name: model_id, ...}  (v6)

        Both serialize as empty dicts when empty. Always includes both
        keys for forward-compat (clients that only know about "overrides"
        can ignore the new key; clients that know about model_overrides
        can use them).
        """
        return {
            "overrides": {task_name: weights.as_dict() for task_name, weights in self.overrides.items()},
            "model_overrides": dict(self.model_overrides),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "UserPrefs":
        """Parse a JSON-friendly nested dict into a UserPrefs.

        Returns an empty UserPrefs if `data` is None or empty.

        Backward-compat: if `data` is a flat dict (legacy v3 format with
        only weight overrides, no "overrides" / "model_overrides" keys),
        we treat it as the `overrides` field. If `data` is the new format
        with both keys, we use them.

        Format detection:
        - Legacy: `{"ptt_response": {"quality": 0.4, ...}}` (no wrapper key)
        - New:    `{"overrides": {...}, "model_overrides": {...}}` (wrapped)
        """
        if not data:
            return cls.empty()

        # New format detection: top-level has the wrapper keys.
        if "overrides" in data or "model_overrides" in data:
            raw_overrides = data.get("overrides") or {}
            raw_model_overrides = data.get("model_overrides") or {}
            if not isinstance(raw_overrides, dict):
                raise ValueError(f"UserPrefs 'overrides' must be a dict, got {type(raw_overrides).__name__}")
            if not isinstance(raw_model_overrides, dict):
                raise ValueError(
                    f"UserPrefs 'model_overrides' must be a dict, got {type(raw_model_overrides).__name__}"
                )
            return cls(
                overrides=_parse_legacy_overrides(raw_overrides),
                model_overrides=dict(raw_model_overrides),
            )

        # Legacy format: top-level IS the overrides dict.
        return cls(overrides=_parse_legacy_overrides(data), model_overrides={})


def _parse_legacy_overrides(data: Dict[str, Any]) -> Dict[str, TaskWeights]:
    """Parse the v3-format `{task: {quality, latency, cost}}` dict.

    Used both for legacy top-level input and the new `overrides` field.
    """
    overrides: Dict[str, TaskWeights] = {}
    for task_name, weights_dict in data.items():
        if not isinstance(weights_dict, dict):
            raise ValueError(f"UserPrefs entry for {task_name!r} must be a dict, " f"got {type(weights_dict).__name__}")
        overrides[task_name] = TaskWeights(
            quality=_safe_to_float(weights_dict["quality"], "quality", task_name),
            latency=_safe_to_float(weights_dict["latency"], "latency", task_name),
            cost=_safe_to_float(weights_dict["cost"], "cost", task_name),
        )
    return overrides
