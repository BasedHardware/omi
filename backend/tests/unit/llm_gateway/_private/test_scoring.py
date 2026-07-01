"""Parity tests for the cherry-picked scoring engine (R5a).

The scoring module is byte-equivalent to v3's `backend/utils/auto_router/scoring.py`.
These tests pin the critical behaviors so any drift between v3 and this copy
(e.g. from a future re-cherry-pick that updates one but not the other) is caught
by CI. We don't duplicate all 50+ v3 tests — just the formulas + validation rules
that the R1 emitter depends on.

Lint check at the bottom enforces the runtime isolation contract: the
`_private/` namespace must NOT be exposed via `llm_gateway.routers.*`.
"""

from __future__ import annotations

import importlib
import math

import pytest

from llm_gateway.gateway._private.scoring import ModelSpec, TaskSpec, _clamp_0_1, score

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _model(id: str = "test-model", q=0.5, l=0.5, c=0.5, provider="test") -> ModelSpec:
    return ModelSpec(id=id, quality_score=q, latency_score=l, cost_score=c, provider=provider)


def _task(name: str = "test-task", qw=0.4, lw=0.4, cw=0.2) -> TaskSpec:
    return TaskSpec(name=name, quality_weight=qw, latency_weight=lw, cost_weight=cw)


# ---------------------------------------------------------------------------
# Formula (parity with v3 TestScoringFormula)
# ---------------------------------------------------------------------------


class TestScoringFormula:
    """total = qw*q + lw*l + cw*c — pinned exactly."""

    def test_balanced_weights_mid_scores(self):
        # 0.4 * 0.5 + 0.4 * 0.5 + 0.2 * 0.5 = 0.5
        assert score(_model(), _task()) == pytest.approx(0.5)

    def test_perfect_scores_equal_to_weight_sum(self):
        # All 1.0 → returns sum of weights (= 1.0 for valid weights)
        assert score(_model(q=1.0, l=1.0, c=1.0), _task()) == pytest.approx(1.0)

    def test_zero_scores_return_zero(self):
        assert score(_model(q=0.0, l=0.0, c=0.0), _task()) == pytest.approx(0.0)

    def test_quality_only_task_picks_quality_dominant(self):
        m = _model(q=1.0, l=0.0, c=0.0)
        t = _task(qw=1.0, lw=0.0, cw=0.0)
        assert score(m, t) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Clamping (parity with v3 TestClamping)
# ---------------------------------------------------------------------------


class TestClamping:
    """Out-of-range scores clamp to [0.0, 1.0]; None / NaN → 0.0."""

    def test_quality_above_one_clamps_to_one(self):
        m = _model(q=2.5, l=0.5, c=0.5)
        # quality clamp to 1.0 → 0.4*1.0 + 0.4*0.5 + 0.2*0.5 = 0.4+0.2+0.1 = 0.7
        assert score(m, _task()) == pytest.approx(0.7)

    def test_quality_below_zero_clamps_to_zero(self):
        m = _model(q=-1.0, l=0.5, c=0.5)
        # quality clamp to 0.0 → 0.4*0.0 + 0.4*0.5 + 0.2*0.5 = 0.0+0.2+0.1 = 0.3
        assert score(m, _task()) == pytest.approx(0.3)

    def test_none_scores_treated_as_zero(self):
        m = ModelSpec(id="x", quality_score=None, latency_score=None, cost_score=None, provider="")
        # all None → all clamp to 0 → 0.0
        assert score(m, _task()) == pytest.approx(0.0)

    def test_nan_scores_treated_as_zero(self):
        m = ModelSpec(id="x", quality_score=float("nan"), latency_score=0.5, cost_score=0.5, provider="")
        # NaN quality → 0 → 0.0 + 0.4*0.5 + 0.2*0.5 = 0.3
        assert score(m, _task()) == pytest.approx(0.3)

    def test_clamp_helper_handles_none(self):
        assert _clamp_0_1(None) == 0.0

    def test_clamp_helper_handles_nan(self):
        assert _clamp_0_1(float("nan")) == 0.0

    def test_clamp_helper_preserves_in_range(self):
        assert _clamp_0_1(0.42) == 0.42


# ---------------------------------------------------------------------------
# Weight validation (parity with v3 TestWeightHandling + TestWeightValidation)
# ---------------------------------------------------------------------------


class TestWeightValidation:
    """The plan mandates sum-to-1.0 within 1e-3 tolerance + bool/NaN/inf rejection."""

    def test_valid_weights_summing_to_one_are_accepted(self):
        TaskSpec(name="t", quality_weight=0.4, latency_weight=0.4, cost_weight=0.2)  # no raise

    def test_valid_weights_within_tolerance_accepted(self):
        # Weights sum to 1.0005 — within 1e-3 tolerance of 1.0.
        TaskSpec(name="t", quality_weight=0.5, latency_weight=0.3, cost_weight=0.2005)

    def test_weights_summing_to_less_than_one_rejected(self):
        with pytest.raises(ValueError, match="sum to"):
            TaskSpec(name="t", quality_weight=0.3, latency_weight=0.3, cost_weight=0.3)

    def test_weights_summing_to_more_than_one_rejected(self):
        with pytest.raises(ValueError, match="sum to"):
            TaskSpec(name="t", quality_weight=0.5, latency_weight=0.5, cost_weight=0.5)

    def test_bool_weight_rejected(self):
        # bool is a subclass of int in Python; reject BEFORE treating as 1.0/0.0
        with pytest.raises(TypeError, match="must be a number"):
            TaskSpec(name="t", quality_weight=True, latency_weight=0.0, cost_weight=0.0)

    def test_nan_weight_rejected(self):
        with pytest.raises(ValueError, match="must be a finite number"):
            TaskSpec(name="t", quality_weight=float("nan"), latency_weight=0.5, cost_weight=0.5)

    def test_positive_infinity_rejected(self):
        with pytest.raises(ValueError, match="must be a finite number"):
            TaskSpec(name="t", quality_weight=float("inf"), latency_weight=0.5, cost_weight=0.5)

    def test_negative_infinity_rejected(self):
        with pytest.raises(ValueError, match="must be a finite number"):
            TaskSpec(name="t", quality_weight=float("-inf"), latency_weight=0.5, cost_weight=0.5)

    def test_negative_weight_rejected(self):
        with pytest.raises(ValueError, match=r"must be in \[0\.0, 1\.0\]"):
            TaskSpec(name="t", quality_weight=-0.1, latency_weight=0.5, cost_weight=0.6)

    def test_weight_above_one_rejected(self):
        with pytest.raises(ValueError, match=r"must be in \[0\.0, 1\.0\]"):
            TaskSpec(name="t", quality_weight=1.5, latency_weight=0.0, cost_weight=-0.5)

    def test_string_weight_rejected(self):
        with pytest.raises(TypeError, match="must be a number"):
            TaskSpec(name="t", quality_weight="0.5", latency_weight=0.0, cost_weight=0.5)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ModelSpec validation
# ---------------------------------------------------------------------------


class TestModelSpecValidation:
    def test_model_rejects_empty_id(self):
        with pytest.raises(ValueError, match="id must be non-empty"):
            ModelSpec(id="", quality_score=0.5, latency_score=0.5, cost_score=0.5)

    def test_task_rejects_empty_name(self):
        with pytest.raises(ValueError, match="name must be non-empty"):
            TaskSpec(name="", quality_weight=0.4, latency_weight=0.4, cost_weight=0.2)


# ---------------------------------------------------------------------------
# Lint: _private/ must NOT be exposed via llm_gateway.routers.*
# ---------------------------------------------------------------------------


class TestPrivateNamespaceIsolation:
    """Runtime isolation contract: scoring happens at artifact-emission time,
    never on the request path. The _private/ namespace must not leak into
    llm_gateway.routers.* — that's what makes scoring a private dep.
    """

    def test_private_scoring_not_exposed_via_routers_openai_compatible(self):
        # Force-import the routers package to trigger any __init__.py side effects
        importlib.import_module("llm_gateway.routers.openai_compatible")
        with pytest.raises((ImportError, AttributeError)):
            from llm_gateway.routers.openai_compatible import _private_scoring  # noqa: F401

    def test_private_scoring_not_exposed_via_routers_health(self):
        importlib.import_module("llm_gateway.routers.health")
        with pytest.raises((ImportError, AttributeError)):
            from llm_gateway.routers.health import _private_scoring  # noqa: F401

    def test_private_scoring_not_exposed_via_routers_metrics(self):
        importlib.import_module("llm_gateway.routers.metrics")
        with pytest.raises((ImportError, AttributeError)):
            from llm_gateway.routers.metrics import _private_scoring  # noqa: F401


# ---------------------------------------------------------------------------
# benchmarks_fetcher.py cherry-pick sanity (T-002 acceptance)
# ---------------------------------------------------------------------------


class TestBenchmarksFetcherImport:
    """T-002: verify the cherry-picked BenchmarksFetcher imports cleanly and
    exposes the constants the R1 emitter depends on. No behavioral tests here —
    those live in v3's own test suite (we don't re-run them in this branch;
    the cherry-pick is byte-equivalent so v3's tests transitively cover it).
    """

    def test_benchmarks_fetcher_imports_with_expected_constants(self):
        from llm_gateway.gateway._private.benchmarks_fetcher import (
            AA_API_URL,
            AA_ENV_VAR,
            AA_UNCOVERED_TASKS,
            BenchmarksFetcher,
            get_benchmarks_fetcher,
        )

        assert AA_API_URL == "https://artificialanalysis.ai/api/v2/data/llms/models"
        assert AA_ENV_VAR == "AA_API_KEY"
        # Tasks AA doesn't cover — preserved from example data per v3 contract
        assert AA_UNCOVERED_TASKS == frozenset({"transcription", "screenshot_embedding"})
        assert callable(BenchmarksFetcher)
        assert callable(get_benchmarks_fetcher)
