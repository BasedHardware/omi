"""Unit tests for the auto-router scoring engine.

The scoring function is the heart of the framework — these tests pin the
formula and its defensive behaviors (clamping, None handling, determinism).
"""

import pytest

from utils.auto_router.scoring import ModelSpec, TaskSpec, score, _clamp_0_1


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _model(id: str = "test-model", q=0.5, l=0.5, c=0.5, provider="test") -> ModelSpec:
    """Build a ModelSpec with default mid-range scores."""
    return ModelSpec(id=id, quality_score=q, latency_score=l, cost_score=c, provider=provider)


def _task(name="test-task", qw=0.4, lw=0.4, cw=0.2) -> TaskSpec:
    """Build a TaskSpec with default balanced weights."""
    return TaskSpec(name=name, quality_weight=qw, latency_weight=lw, cost_weight=cw)


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestConstructorValidation:
    """Empty id fields should be rejected at construction time."""

    def test_model_rejects_empty_id(self):
        with pytest.raises(ValueError, match="id must be non-empty"):
            ModelSpec(id="", quality_score=0.5, latency_score=0.5, cost_score=0.5)

    def test_task_rejects_empty_name(self):
        with pytest.raises(ValueError, match="name must be non-empty"):
            TaskSpec(name="", quality_weight=0.4, latency_weight=0.4, cost_weight=0.2)

    def test_model_default_provider_is_empty_string(self):
        m = ModelSpec(id="x", quality_score=0.5, latency_score=0.5, cost_score=0.5)
        assert m.provider == ""

    def test_task_default_description_is_empty_string(self):
        t = TaskSpec(name="x", quality_weight=0.4, latency_weight=0.4, cost_weight=0.2)
        assert t.description == ""


# ---------------------------------------------------------------------------
# AC1: Formula returns weighted sum exactly
# ---------------------------------------------------------------------------


class TestScoringFormula:
    """The formula is total = qw*q + lw*l + cw*c. Pin it."""

    def test_balanced_weights_mid_scores(self):
        # 0.4 * 0.5 + 0.4 * 0.5 + 0.2 * 0.5 = 0.5
        assert score(_model(), _task()) == pytest.approx(0.5)

    def test_perfect_scores_equal_to_weight_sum(self):
        # All 1.0 scores → returns sum of weights
        m = _model(q=1.0, l=1.0, c=1.0)
        t = _task(qw=0.4, lw=0.4, cw=0.2)
        assert score(m, t) == pytest.approx(1.0)  # weights sum to 1.0

    def test_zero_scores_return_zero(self):
        assert score(_model(q=0.0, l=0.0, c=0.0), _task()) == pytest.approx(0.0)

    def test_quality_only_task_picks_quality_dominant(self):
        # Quality-only weights: ignore latency + cost
        m = _model(q=1.0, l=0.0, c=0.0)
        t = _task(qw=1.0, lw=0.0, cw=0.0)
        assert score(m, t) == pytest.approx(1.0)

    def test_latency_only_task_picks_latency_dominant(self):
        m = _model(q=0.0, l=1.0, c=0.0)
        t = _task(qw=0.0, lw=1.0, cw=0.0)
        assert score(m, t) == pytest.approx(1.0)

    def test_cost_only_task_picks_cost_dominant(self):
        m = _model(q=0.0, l=0.0, c=1.0)
        t = _task(qw=0.0, lw=0.0, cw=1.0)
        assert score(m, t) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# AC2: Component scores are clamped to [0.0, 1.0]
# ---------------------------------------------------------------------------


class TestClamping:
    """Out-of-range component scores silently clamp — don't crash, don't propagate."""

    def test_quality_above_one_clamps_to_one(self):
        m = _model(q=1.5, l=0.0, c=0.0)
        t = _task(qw=1.0, lw=0.0, cw=0.0)
        assert score(m, t) == pytest.approx(1.0)

    def test_quality_below_zero_clamps_to_zero(self):
        m = _model(q=-0.3, l=0.0, c=0.0)
        t = _task(qw=1.0, lw=0.0, cw=0.0)
        assert score(m, t) == pytest.approx(0.0)

    def test_latency_above_one_clamps(self):
        m = _model(q=0.0, l=10.0, c=0.0)
        t = _task(qw=0.0, lw=1.0, cw=0.0)
        assert score(m, t) == pytest.approx(1.0)

    def test_latency_below_zero_clamps(self):
        m = _model(q=0.0, l=-5.0, c=0.0)
        t = _task(qw=0.0, lw=1.0, cw=0.0)
        assert score(m, t) == pytest.approx(0.0)

    def test_cost_above_one_clamps(self):
        m = _model(q=0.0, l=0.0, c=99.0)
        t = _task(qw=0.0, lw=0.0, cw=1.0)
        assert score(m, t) == pytest.approx(1.0)

    def test_clamp_helper_handles_none(self):
        assert _clamp_0_1(None) == 0.0

    def test_clamp_helper_handles_negative(self):
        assert _clamp_0_1(-0.5) == 0.0

    def test_clamp_helper_handles_above_one(self):
        assert _clamp_0_1(2.5) == 1.0

    def test_clamp_helper_preserves_in_range(self):
        assert _clamp_0_1(0.7) == 0.7


# ---------------------------------------------------------------------------
# AC3: Weights not summing to 1.0 are NOT renormalized
# ---------------------------------------------------------------------------


class TestWeightHandling:
    """Explicit weights are the contract. The function does not silently renormalize."""

    def test_weights_summing_to_less_than_one_preserved(self):
        # Weights 0.3 + 0.3 + 0.1 = 0.7 (not 1.0). Score reflects this exactly.
        m = _model(q=1.0, l=1.0, c=1.0)
        t = _task(qw=0.3, lw=0.3, cw=0.1)
        # 0.3*1 + 0.3*1 + 0.1*1 = 0.7 (NOT renormalized to 1.0)
        assert score(m, t) == pytest.approx(0.7)

    def test_weights_summing_to_more_than_one_preserved(self):
        # Weights 0.5 + 0.5 + 0.5 = 1.5 (not 1.0). Score exceeds 1.0.
        m = _model(q=1.0, l=1.0, c=1.0)
        t = _task(qw=0.5, lw=0.5, cw=0.5)
        # 0.5 + 0.5 + 0.5 = 1.5 (explicitly preserved, NOT renormalized)
        assert score(m, t) == pytest.approx(1.5)

    def test_zero_weights_produce_zero(self):
        m = _model(q=1.0, l=1.0, c=1.0)
        t = _task(qw=0.0, lw=0.0, cw=0.0)
        assert score(m, t) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# AC4: None component scores are treated as 0
# ---------------------------------------------------------------------------


class TestNoneHandling:
    """A model not benchmarked for a dimension gets 0 for that dimension."""

    def test_none_quality_treated_as_zero(self):
        m = ModelSpec(id="x", quality_score=None, latency_score=1.0, cost_score=1.0)
        t = _task(qw=1.0, lw=0.0, cw=0.0)
        assert score(m, t) == pytest.approx(0.0)

    def test_none_latency_treated_as_zero(self):
        m = ModelSpec(id="x", quality_score=1.0, latency_score=None, cost_score=1.0)
        t = _task(qw=0.0, lw=1.0, cw=0.0)
        assert score(m, t) == pytest.approx(0.0)

    def test_none_cost_treated_as_zero(self):
        m = ModelSpec(id="x", quality_score=1.0, latency_score=1.0, cost_score=None)
        t = _task(qw=0.0, lw=0.0, cw=1.0)
        assert score(m, t) == pytest.approx(0.0)

    def test_all_none_returns_zero(self):
        m = ModelSpec(id="x", quality_score=None, latency_score=None, cost_score=None)
        t = _task()
        assert score(m, t) == pytest.approx(0.0)

    def test_partial_none_still_uses_other_dimensions(self):
        # Only quality known: should still pick up the quality component
        m = ModelSpec(id="x", quality_score=1.0, latency_score=None, cost_score=None)
        t = _task(qw=0.4, lw=0.4, cw=0.2)
        # 0.4*1.0 + 0.4*0.0 + 0.2*0.0 = 0.4
        assert score(m, t) == pytest.approx(0.4)

    def test_score_returns_float_not_optional(self):
        # Even with all-None input, the return type is float (never None).
        m = ModelSpec(id="x", quality_score=None, latency_score=None, cost_score=None)
        result = score(m, _task())
        assert isinstance(result, float)
        assert result == 0.0


# ---------------------------------------------------------------------------
# AC5: Pure function — deterministic, no side effects
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Same inputs always produce the same output."""

    def test_same_inputs_same_output_called_twice(self):
        m = _model(q=0.7, l=0.3, c=0.9)
        t = _task(qw=0.5, lw=0.3, cw=0.2)
        first = score(m, t)
        second = score(m, t)
        assert first == second

    def test_different_models_with_same_scores_produce_same_score(self):
        # Two distinct models with identical scores should yield the same number.
        # (Tie-breaking on which one is PICKED is a registry/endpoint concern, not scoring.)
        m1 = _model(id="model-a", q=0.5, l=0.5, c=0.5)
        m2 = _model(id="model-b", q=0.5, l=0.5, c=0.5)
        t = _task()
        assert score(m1, t) == score(m2, t)

    def test_score_does_not_mutate_inputs(self):
        # Frozen dataclasses can't be mutated, but verify the scoring function
        # doesn't write to anything via a side channel either.
        m = _model()
        t = _task()
        score(m, t)
        score(m, t)
        score(m, t)
        # If the function had side effects (caching, logging), the state would
        # diverge between calls. Just verify the inputs are still usable.
        assert m.quality_score == 0.5
        assert t.quality_weight == 0.4
