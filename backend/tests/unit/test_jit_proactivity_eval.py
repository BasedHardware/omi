"""Hermetic Phase 0 contract tests for local JIT proactivity evaluation."""

from __future__ import annotations

from pathlib import Path

from testing.jit_processing.proactivity_eval import evaluate_fixture, load_fixture

FIXTURE = Path(__file__).parents[2] / "testing" / "jit_processing" / "fixtures" / "proactivity_cases.json"


def test_fixture_covers_the_required_local_trigger_surfaces_and_expected_decisions() -> None:
    fixture = load_fixture(FIXTURE)
    report = evaluate_fixture(FIXTURE)
    expected_by_id = {case["case_id"]: case["expected"] for case in fixture["cases"]}
    actual_by_id = {case.case_id: case for case in report.cases}

    assert set(actual_by_id) == set(expected_by_id)
    for case_id, expected in expected_by_id.items():
        actual = actual_by_id[case_id]
        assert actual.actual_status == expected["status"], case_id
        assert actual.actual_reason == expected["reason"], case_id
        assert list(actual.matched_conditions) == expected["matched_conditions"], case_id
        assert list(actual.missing_conditions) == expected["missing_conditions"], case_id
        assert actual.matched_fraction == expected["matched_fraction"], case_id

    categories = {case.category for case in report.cases}
    assert {
        "entity",
        "keyword",
        "app_window",
        "time_calendar",
        "embedding",
        "embedding_ambiguous_hit",
        "negative",
        "unavailable_device",
    } <= categories


def test_fixture_metrics_are_descriptive_and_use_the_ratified_threshold_contract() -> None:
    report = evaluate_fixture(FIXTURE)

    assert report.metrics.case_count == 16
    assert report.metrics.expected_match_count == 6
    assert report.metrics.predicted_match_count == 6
    assert report.metrics.true_positives == 6
    assert report.metrics.false_positives == 0
    assert report.metrics.false_negatives == 0
    assert report.metrics.true_negatives == 8
    assert report.metrics.triage_count == 2
    assert report.metrics.precision == 1.0
    assert report.metrics.recall == 1.0
    assert report.candidate_config["ratified"] is True
    assert report.candidate_config["ratified_thresholds"] == {
        "embedding_match": 0.82,
        "embedding_triage": 0.74,
    }


def test_exposure_rates_and_supplied_cost_fields_are_reported_without_inference() -> None:
    report = evaluate_fixture(FIXTURE)
    exposure = report.exposure

    assert exposure.active_hours == 8.0
    assert exposure.active_days == 2.0
    assert exposure.full_agent_wakeups == 2
    assert exposure.full_agent_wakeups_per_active_hour == 0.25
    assert exposure.full_agent_wakeups_per_active_day == 1.0
    assert exposure.supplied_cost == {
        "currency": "USD",
        "local_evaluation_count": 16,
        "full_agent_wakeup_count": 2,
        "local_evaluation_unit_cost_usd": 0.0,
        "full_agent_wakeup_unit_cost_usd": 0.12,
        "total_cost_usd": 0.24,
    }


def test_double_run_is_byte_stable_and_ambiguous_embedding_limit_is_explicit() -> None:
    first = evaluate_fixture(FIXTURE).as_dict()
    second = evaluate_fixture(FIXTURE).as_dict()
    assert first == second

    ambiguous = next(case for case in load_fixture(FIXTURE)["cases"] if case["category"] == "embedding_ambiguous_hit")
    assert "0.74 through 0.82 ambiguity band" in ambiguous["limitation"]
    result = next(case for case in evaluate_fixture(FIXTURE).cases if case.category == "embedding_ambiguous_hit")
    assert result.actual_status == "triage"


def test_unavailable_device_cases_never_match() -> None:
    report = evaluate_fixture(FIXTURE)
    unavailable = [case for case in report.cases if case.category == "unavailable_device"]

    assert unavailable
    assert all(case.actual_status in {"triage", "no_match"} for case in unavailable)
    assert all(case.actual_status != "match" for case in unavailable)
