"""Per-user weight overrides for the LLM gateway.

Each user can override the per-lane objective weights (e.g., "for
``omi:auto:ptt-response`` I always want quality over latency"). The
overrides are stored once per uid and applied server-side at pick
time — clients don't pass them on every request.

A lane opts into accepting overrides via ``lane.objective_overridable``;
when that flag is false the override is rejected with 400 at the
endpoint layer. This file only knows about the data shape and merge
rules; whether a given lane accepts overrides is the route layer's
concern.

Validation matches the gateway's ``Objective`` schema (see
``llm_gateway.gateway.schemas``):
    - Each weight must be a finite number in ``[0.0, 1.0]``
    - The three weights must sum to 1.0 (tolerance 1e-3)
    - bool weights are rejected first (``bool`` is a subclass of
      ``int`` in Python, so ``float(True) == 1.0`` would silently
      accept booleans as weights)

A ``UserPrefs`` is a mapping from lane id (``omi:auto:<lane>``) to
``ObjectiveOverrides``. Lanes not in the mapping use the lane's default
weights (no behavior change for users who haven't set overrides).

Side-effect-free. No I/O, no async, no shared state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

# Tolerance matches `Objective.validate_weights` in schemas.py.
WEIGHT_SUM_TOLERANCE = 1e-3

# Lane ids are gated by the regex `^omi:auto:[a-z0-9][a-z0-9-]*$` in
# schemas.py. We re-validate at the prefs layer so a corrupted store
# cannot pass through a malicious / malformed lane id that the gateway
# would later reject mid-request.
import re as _re

_LANE_ID_PATTERN = _re.compile(r'^omi:auto:[a-z0-9][a-z0-9-]*$')


def _safe_to_float(value: Any, field_name: str, lane_id: str) -> float:
    """Convert a weight value to float, rejecting booleans explicitly.

    In Python, ``bool`` is a subclass of ``int``, so ``float(True) == 1.0``
    would silently accept booleans as weights. We reject them here before
    coercion with a clear error message.
    """
    if isinstance(value, bool):
        raise ValueError(f"UserPrefs weight '{field_name}' for lane '{lane_id}' must be a number, got bool")
    if not isinstance(value, (int, float)):
        raise ValueError(
            f"UserPrefs weight '{field_name}' for lane '{lane_id}' " f"must be a number, got {type(value).__name__}"
        )
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"UserPrefs weight '{field_name}' for lane '{lane_id}' must be finite, got {value!r}")
    return float(value)


@dataclass(frozen=True)
class ObjectiveOverrides:
    """Per-lane weight overrides.

    Same validation contract as ``Objective`` in ``schemas.py`` so a
    constructed instance can be used as an ``Objective`` directly. The
    gateway uses this as the input to ``merged_with`` and as the
    output of the prefs endpoint.
    """

    quality: float
    latency: float
    cost: float

    def __post_init__(self) -> None:
        for label, w in (
            ('quality', self.quality),
            ('latency', self.latency),
            ('cost', self.cost),
        ):
            if isinstance(w, bool):
                raise TypeError(f"ObjectiveOverrides.{label} must be a number, got bool")
            if not isinstance(w, (int, float)):
                raise TypeError(f"ObjectiveOverrides.{label} must be a number, got {type(w).__name__}")
            if not math.isfinite(w):
                raise ValueError(f"ObjectiveOverrides.{label} must be a finite number, got {w!r}")
            if w < 0.0 or w > 1.0:
                raise ValueError(f"ObjectiveOverrides.{label} must be in [0.0, 1.0], got {w}")
        total = self.quality + self.latency + self.cost
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(
                f"ObjectiveOverrides sum to {total:.4f}, expected 1.0 "
                f"(tolerance {WEIGHT_SUM_TOLERANCE}); "
                f"quality={self.quality}, latency={self.latency}, cost={self.cost}"
            )

    def as_dict(self) -> dict[str, float]:
        return {'quality': self.quality, 'latency': self.latency, 'cost': self.cost}


@dataclass(frozen=True)
class UserPrefs:
    """Per-user weight overrides for one or more lanes.

    Empty ``overrides`` means "use lane defaults for everything" — no
    behavior change. Adding an entry for a lane overrides that lane's
    default objective in the pick path.

    Frozen: mutating after construction is not allowed (callers should
    construct a new ``UserPrefs`` with updated values). The internal
    mapping is constructed via the factory, never from a raw dict
    reference, so callers can't mutate stored prefs by reference.
    """

    overrides: Mapping[str, ObjectiveOverrides] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for lane_id, overrides in self.overrides.items():
            if not isinstance(lane_id, str) or not lane_id:
                raise ValueError(f"UserPrefs override key must be a non-empty string, got {lane_id!r}")
            if not _LANE_ID_PATTERN.match(lane_id):
                raise ValueError(
                    f"UserPrefs override key {lane_id!r} is not a valid lane id "
                    f"(expected pattern ^omi:auto:[a-z0-9][a-z0-9-]*$)"
                )
            if not isinstance(overrides, ObjectiveOverrides):
                raise TypeError(
                    f"UserPrefs override for {lane_id!r} must be an ObjectiveOverrides, "
                    f"got {type(overrides).__name__}"
                )

    @classmethod
    def empty(cls) -> 'UserPrefs':
        """An empty UserPrefs (no overrides — use lane defaults)."""
        return cls(overrides={})

    def has_override_for(self, lane_id: str) -> bool:
        return lane_id in self.overrides

    def get_override(self, lane_id: str) -> Optional[ObjectiveOverrides]:
        return self.overrides.get(lane_id)

    def to_dict(self) -> dict[str, dict[str, float]]:
        """Serialize to a JSON-friendly nested dict.

        Returns: ``{lane_id: {quality, latency, cost}, ...}``.
        Empty overrides serialize as an empty dict.
        """
        return {lane_id: overrides.as_dict() for lane_id, overrides in self.overrides.items()}

    @classmethod
    def from_dict(cls, data: Optional[dict[str, dict[str, float]]]) -> 'UserPrefs':
        """Parse a JSON-friendly nested dict into a UserPrefs.

        Returns an empty UserPrefs if ``data`` is None or empty.

        Bool check FIRST: in Python, ``bool`` is a subclass of ``int``,
        so ``float(True) == 1.0`` would silently accept booleans as
        weights. We reject booleans explicitly with a clear error
        message.
        """
        if not data:
            return cls.empty()
        overrides: dict[str, ObjectiveOverrides] = {}
        for lane_id, weights_dict in data.items():
            if not isinstance(lane_id, str) or not lane_id:
                raise ValueError(f"UserPrefs key must be a non-empty string, got {lane_id!r}")
            if not _LANE_ID_PATTERN.match(lane_id):
                raise ValueError(
                    f"UserPrefs key {lane_id!r} is not a valid lane id "
                    f"(expected pattern ^omi:auto:[a-z0-9][a-z0-9-]*$)"
                )
            if not isinstance(weights_dict, dict):
                raise ValueError(
                    f"UserPrefs entry for {lane_id!r} must be a dict, " f"got {type(weights_dict).__name__}"
                )
            overrides[lane_id] = ObjectiveOverrides(
                quality=_safe_to_float(weights_dict['quality'], 'quality', lane_id),
                latency=_safe_to_float(weights_dict['latency'], 'latency', lane_id),
                cost=_safe_to_float(weights_dict['cost'], 'cost', lane_id),
            )
        return cls(overrides=overrides)


__all__ = [
    'ObjectiveOverrides',
    'UserPrefs',
    'WEIGHT_SUM_TOLERANCE',
]
