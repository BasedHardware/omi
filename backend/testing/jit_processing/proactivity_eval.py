"""Offline, fixture-backed evaluation for the local JIT watchlist.

This harness evaluates the existing pure trigger compiler/evaluator only.  It
does not call a model, inspect a live device, or infer a wakeup/cost from a
case.  Fixture expectations are the human-authored oracle; the evaluator never
reads them while deciding a trigger result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from utils.memory.jit_trigger_contract import (
    TriggerDecision,
    TriggerDecisionStatus,
    TriggerObservation,
    TriggerRuntimePolicy,
    compile_trigger_condition,
    evaluate_trigger,
)

PROACTIVITY_EVAL_SCHEMA_VERSION = "jit_proactivity_eval.v1"
DEFAULT_FIXTURE_PATH = Path(__file__).with_name("fixtures") / "proactivity_cases.json"


@dataclass(frozen=True)
class ProactivityCaseResult:
    case_id: str
    category: str
    expected_status: str
    actual_status: str
    actual_reason: str
    matched_conditions: tuple[str, ...]
    missing_conditions: tuple[str, ...]
    matched_fraction: float
    observation_fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProactivityMetrics:
    case_count: int
    expected_match_count: int
    predicted_match_count: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    triage_count: int
    precision: float | None
    recall: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProactivityExposureRates:
    active_hours: float
    active_days: float
    full_agent_wakeups: int
    full_agent_wakeups_per_active_hour: float
    full_agent_wakeups_per_active_day: float
    supplied_cost: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProactivityEvalReport:
    schema_version: str
    candidate_config: dict[str, Any]
    cases: tuple[ProactivityCaseResult, ...]
    metrics: ProactivityMetrics
    exposure: ProactivityExposureRates

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_config": dict(self.candidate_config),
            "cases": [case.as_dict() for case in self.cases],
            "metrics": self.metrics.as_dict(),
            "exposure": self.exposure.as_dict(),
        }


def load_fixture(path: Path | None = None) -> dict[str, Any]:
    """Load one versioned synthetic fixture without contacting any provider."""

    fixture_path = path or DEFAULT_FIXTURE_PATH
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("proactivity fixture must be an object")
    if raw.get("schema_version") != PROACTIVITY_EVAL_SCHEMA_VERSION:
        raise ValueError(f"unsupported proactivity fixture schema: {raw.get('schema_version')!r}")
    if not isinstance(raw.get("cases"), list) or not raw["cases"]:
        raise ValueError("proactivity fixture must contain non-empty cases")
    if not isinstance(raw.get("exposure"), dict):
        raise ValueError("proactivity fixture must contain supplied exposure data")
    return raw


def _required_string(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"fixture field {key!r} must be a non-empty string")
    return value.strip()


def _expected_status(case: Mapping[str, Any]) -> str:
    expected = case.get("expected")
    if not isinstance(expected, Mapping):
        raise ValueError(f"case {_required_string(case, 'case_id')!r} has no expected decision")
    status = _required_string(expected, "status")
    if status not in {status.value for status in TriggerDecisionStatus}:
        raise ValueError(f"unsupported expected decision status: {status!r}")
    return status


def _observation(case: Mapping[str, Any]) -> TriggerObservation:
    raw = case.get("observation", {})
    if not isinstance(raw, Mapping):
        raise ValueError(f"case {_required_string(case, 'case_id')!r} observation must be an object")
    return TriggerObservation.model_validate(dict(raw))


def _assert_expected_shape(case: Mapping[str, Any], decision: TriggerDecision) -> None:
    """Compare optional exact fields from the fixture oracle, never drive evaluation."""

    expected = case["expected"]
    expected_reason = expected.get("reason")
    if expected_reason is not None and decision.reason != expected_reason:
        raise AssertionError(f"{case['case_id']}: expected reason {expected_reason!r}, got {decision.reason!r}")
    for field, actual in (
        ("matched_conditions", decision.matched_conditions),
        ("missing_conditions", decision.missing_conditions),
    ):
        expected_values = expected.get(field)
        if expected_values is not None and tuple(expected_values) != actual:
            raise AssertionError(f"{case['case_id']}: expected {field} {expected_values!r}, got {actual!r}")
    expected_fraction = expected.get("matched_fraction")
    if expected_fraction is not None and float(expected_fraction) != decision.matched_fraction:
        raise AssertionError(
            f"{case['case_id']}: expected matched_fraction {expected_fraction!r}, " f"got {decision.matched_fraction!r}"
        )


def _evaluate_case(case: Mapping[str, Any], *, policy: TriggerRuntimePolicy) -> ProactivityCaseResult:
    case_id = _required_string(case, "case_id")
    category = _required_string(case, "category")
    condition = case.get("condition")
    if not isinstance(condition, Mapping):
        raise ValueError(f"case {case_id!r} condition must be an object")

    # The expected decision is deliberately read only after this pure evaluation
    # has produced its result. It cannot influence compilation or matching.
    compiled = compile_trigger_condition(condition)
    decision = evaluate_trigger(compiled, _observation(case), policy=policy)
    _assert_expected_shape(case, decision)
    return ProactivityCaseResult(
        case_id=case_id,
        category=category,
        expected_status=_expected_status(case),
        actual_status=decision.status.value,
        actual_reason=decision.reason,
        matched_conditions=decision.matched_conditions,
        missing_conditions=decision.missing_conditions,
        matched_fraction=decision.matched_fraction,
        observation_fingerprint=decision.observation_fingerprint,
    )


def _positive_metrics(results: tuple[ProactivityCaseResult, ...]) -> ProactivityMetrics:
    expected_positive = {result.case_id for result in results if result.expected_status == "match"}
    predicted_positive = {result.case_id for result in results if result.actual_status == "match"}
    expected_negative = {result.case_id for result in results if result.expected_status == "no_match"}
    predicted_negative = {result.case_id for result in results if result.actual_status == "no_match"}
    true_positives = len(expected_positive & predicted_positive)
    false_positives = len(predicted_positive - expected_positive)
    false_negatives = len(expected_positive - predicted_positive)
    # Triage is an abstention, not a negative prediction. Keep true negatives
    # restricted to explicit no_match/no_match pairs so this report cannot hide
    # unavailable-context behavior inside a binary confusion matrix.
    true_negatives = len(expected_negative & predicted_negative)
    predicted_count = len(predicted_positive)
    expected_count = len(expected_positive)
    return ProactivityMetrics(
        case_count=len(results),
        expected_match_count=expected_count,
        predicted_match_count=predicted_count,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        true_negatives=true_negatives,
        triage_count=sum(result.actual_status == "triage" for result in results),
        precision=(true_positives / predicted_count) if predicted_count else None,
        recall=(true_positives / expected_count) if expected_count else None,
    )


def _exposure_rates(exposure: Mapping[str, Any]) -> ProactivityExposureRates:
    def positive_number(key: str) -> float:
        value = exposure.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"exposure.{key} must be a positive number")
        return float(value)

    wakeups = exposure.get("full_agent_wakeups")
    if isinstance(wakeups, bool) or not isinstance(wakeups, int) or wakeups < 0:
        raise ValueError("exposure.full_agent_wakeups must be a non-negative integer")
    supplied_cost = exposure.get("cost")
    if not isinstance(supplied_cost, Mapping):
        raise ValueError("exposure.cost must contain supplied cost fields")
    return ProactivityExposureRates(
        active_hours=positive_number("active_hours"),
        active_days=positive_number("active_days"),
        full_agent_wakeups=wakeups,
        full_agent_wakeups_per_active_hour=wakeups / positive_number("active_hours"),
        full_agent_wakeups_per_active_day=wakeups / positive_number("active_days"),
        supplied_cost=dict(supplied_cost),
    )


def evaluate_fixture(path: Path | None = None) -> ProactivityEvalReport:
    """Evaluate all fixture cases and calculate descriptive offline metrics."""

    fixture = load_fixture(path)
    candidate_config = fixture.get("candidate_config", {})
    if not isinstance(candidate_config, Mapping):
        raise ValueError("candidate_config must be an object")
    runtime_policy = candidate_config.get("runtime_policy", {})
    if not isinstance(runtime_policy, Mapping):
        raise ValueError("candidate_config.runtime_policy must be an object")
    policy = TriggerRuntimePolicy.model_validate(dict(runtime_policy))
    raw_cases = fixture["cases"]
    cases = tuple(_evaluate_case(case, policy=policy) for case in raw_cases if isinstance(case, Mapping))
    if len(cases) != len(raw_cases):
        raise ValueError("proactivity fixture cases must be objects")
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("proactivity fixture case_id values must be unique")
    return ProactivityEvalReport(
        schema_version=fixture["schema_version"],
        candidate_config=dict(candidate_config),
        cases=cases,
        metrics=_positive_metrics(cases),
        exposure=_exposure_rates(fixture["exposure"]),
    )


__all__ = [
    "DEFAULT_FIXTURE_PATH",
    "PROACTIVITY_EVAL_SCHEMA_VERSION",
    "ProactivityCaseResult",
    "ProactivityEvalReport",
    "ProactivityExposureRates",
    "ProactivityMetrics",
    "evaluate_fixture",
    "load_fixture",
]
