"""Scoring engine for the auto-router.

Pure-function scoring for a single (model, task) pair:

    total = quality_weight * quality_score
          + latency_weight * latency_score
          + cost_weight    * cost_score

Each component score is clamped to [0.0, 1.0] before weighting to defend
against malformed benchmark data. A `None` component is treated as 0 (not
propagated as `None`, so the caller always gets a `float`).

Weights are NOT renormalized — they're applied as the caller specified.
This is the explicit contract: weights sum to 1.0 by convention (validated
at task load time in the registry) but the scoring function itself is
honest about what it computed.

This module is intentionally side-effect-free: no I/O, no async, no shared
state. The daily-refresh cache wraps this function for the endpoint layer.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ModelSpec:
    """A candidate model with quality/latency/cost scores on the [0.0, 1.0] scale.

    Scores are NORMALIZED — 1.0 means "best in class for this dimension",
    0.0 means "worst". Benchmark source is responsible for normalization
    (see `benchmarks.example.json` for the format).

    `None` for any score is allowed and treated as 0 by the scoring function
    — useful when a model hasn't been benchmarked for a particular dimension.
    """

    id: str
    quality_score: Optional[float]
    latency_score: Optional[float]
    cost_score: Optional[float]
    provider: str = ""  # e.g. "anthropic", "openai", "google". Not used in scoring.

    def __post_init__(self):
        # Defensive: id must be non-empty (callers depend on it for tie-breaking + lookup).
        if not self.id:
            raise ValueError("ModelSpec.id must be non-empty")


@dataclass(frozen=True)
class TaskSpec:
    """A task type with per-dimension weights.

    Weights are expected to sum to 1.0 (validated at registry load time).
    They are NOT renormalized by the scoring function — explicit weights
    are the contract. To bias a task toward quality, set
    quality_weight higher; the other weights drop accordingly.
    """

    name: str
    quality_weight: float
    latency_weight: float
    cost_weight: float
    description: str = ""

    def __post_init__(self):
        if not self.name:
            raise ValueError("TaskSpec.name must be non-empty")
        # Weights are validated at the registry layer (sum to 1.0); the scoring
        # function itself accepts any non-negative values without renormalizing.


def _clamp_0_1(value: Optional[float]) -> float:
    """Clamp a score to [0.0, 1.0]. None → 0.0."""
    if value is None:
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def score(model: ModelSpec, task: TaskSpec) -> float:
    """Compute the weighted score of `model` for `task`.

    Formula: `total = quality_weight * quality_score + latency_weight * latency_score + cost_weight * cost_score`

    Each component score is clamped to [0.0, 1.0] before weighting (defensive
    against malformed benchmark data — out-of-range values silently clamp rather
    than throwing, because the scoring path runs on every request and a malformed
    benchmark file should not 500 the entire endpoint).

    `None` for any component score is treated as 0 (a model not benchmarked for
    that dimension does not get a free pass on it — it gets a zero for that
    dimension, which usually drops it out of the top picks).

    Returns a float in [0.0, 1.0] assuming weights are in [0.0, 1.0]; if weights
    are unconstrained (sum > 1.0), the return may exceed 1.0 — that's fine for
    ranking, the registry enforces weight-sum=1.0 by convention.

    Pure function. No I/O, no async, deterministic.
    """
    q = _clamp_0_1(model.quality_score)
    l = _clamp_0_1(model.latency_score)
    c = _clamp_0_1(model.cost_score)
    return task.quality_weight * q + task.latency_weight * l + task.cost_weight * c
