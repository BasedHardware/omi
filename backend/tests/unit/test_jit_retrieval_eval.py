from dataclasses import replace

import pytest

from testing.jit_processing.retrieval_eval import (
    CandidateThresholdConfig,
    RetrievalBounds,
    evaluate_retrieval_case,
    evaluate_retrieval_golden_set,
    hydrate_bounded_windows,
    load_retrieval_expected_refs,
    load_retrieval_golden_set,
)


def _bundle():
    cases = load_retrieval_golden_set()
    expected = load_retrieval_expected_refs()
    return cases, expected


def test_versioned_golden_set_covers_required_retrieval_shapes_and_keeps_refs_external():
    cases, expected = _bundle()

    assert {case.category for case in cases} == {
        "literal",
        "paraphrased",
        "entity",
        "temporal",
        "multi-conversation",
        "ambiguous-person",
        "not-found",
    }
    assert {case.case_id for case in cases} == set(expected)
    assert all(ref.startswith("ev:") for refs in expected.values() for ref in refs)
    assert all("expected" not in case.query.casefold() for case in cases)


def test_golden_evaluation_is_deterministic_and_reports_all_metrics():
    cases, expected = _bundle()
    latencies = {case.case_id: float(index + 1) * 10 for index, case in enumerate(cases)}

    first = evaluate_retrieval_golden_set(cases, expected, supplied_latency_ms=latencies)
    second = evaluate_retrieval_golden_set(cases, expected, supplied_latency_ms=latencies)

    assert [evaluation.as_dict() for evaluation in first] == [evaluation.as_dict() for evaluation in second]
    for evaluation in first:
        metrics = evaluation.metrics
        assert set(metrics.as_dict()) >= {
            "source_hit",
            "false_positive",
            "false_positive_rate",
            "evidence_grounding",
            "tool_call_count",
            "character_proxy",
            "token_proxy",
            "supplied_latency_ms",
        }
        assert metrics.character_proxy > 0
        assert metrics.token_proxy == (metrics.character_proxy + 3) // 4


def test_literal_paraphrase_entity_temporal_and_multi_conversation_hits_are_grounded():
    cases, expected = _bundle()
    evaluations = evaluate_retrieval_golden_set(cases, expected, supplied_latency_ms={})
    by_id = {evaluation.case_id: evaluation for evaluation in evaluations}

    for case_id in (
        "literal-editor",
        "paraphrased-morning-drink",
        "entity-project-atlas",
        "temporal-dentist",
    ):
        metrics = by_id[case_id].metrics
        assert metrics.source_hit == 1.0
        assert metrics.false_positive == 0.0
        assert metrics.evidence_grounding == 1.0
        assert metrics.tool_call_count == 2

    multi = by_id["multi-conversation-accessibility"]
    assert multi.metrics.source_hit == 1.0
    assert multi.metrics.matched_expected_ref_count == 2
    assert multi.metrics.hydrated_ref_count == 2
    assert len(multi.hydrated_windows) == 2


def test_ambiguous_person_surfaces_false_positive_candidates_without_asserting_an_answer():
    cases, expected = _bundle()
    ambiguous = next(case for case in cases if case.case_id == "ambiguous-person-alex")

    evaluation = evaluate_retrieval_case(ambiguous, expected[ambiguous.case_id], supplied_latency_ms=42)

    assert [match.card_id for match in evaluation.selected_cards] == [
        "card-ambiguous-alex-chen",
        "card-ambiguous-alex-rivera",
    ]
    assert evaluation.metrics.source_hit == 0.0
    assert evaluation.metrics.false_positive == 1.0
    assert evaluation.metrics.false_positive_rate == 1.0
    assert evaluation.metrics.evidence_grounding == 0.0
    assert evaluation.metrics.supplied_latency_ms == 42.0


def test_not_found_is_a_bounded_no_source_result():
    cases, expected = _bundle()
    not_found = next(case for case in cases if case.case_id == "not-found-constellation")

    evaluation = evaluate_retrieval_case(not_found, expected[not_found.case_id], supplied_latency_ms=7.5)

    assert evaluation.selected_cards == ()
    assert evaluation.hydrated_windows == ()
    assert evaluation.metrics.source_hit == 1.0
    assert evaluation.metrics.false_positive == 0.0
    assert evaluation.metrics.evidence_grounding == 1.0
    assert evaluation.metrics.tool_call_count == 1
    assert evaluation.metrics.supplied_latency_ms == 7.5


def test_window_hydration_is_card_linked_bounded_and_deterministic():
    cases, _ = _bundle()
    multi = next(case for case in cases if case.case_id == "multi-conversation-accessibility")
    tight = replace(
        multi,
        bounds=RetrievalBounds(
            max_summary_cards=2,
            max_summary_card_chars=80,
            max_window_chars=80,
            max_window_turns=1,
        ),
    )

    first = evaluate_retrieval_case(tight, ["ev:conv-multi-1:turn-4", "ev:conv-multi-2:turn-6"], supplied_latency_ms=0)
    second = evaluate_retrieval_case(tight, ["ev:conv-multi-1:turn-4", "ev:conv-multi-2:turn-6"], supplied_latency_ms=0)

    assert first.hydrated_windows == second.hydrated_windows
    assert sum(window.character_count for window in first.hydrated_windows) <= 80
    assert all(window.character_count <= 80 for window in first.hydrated_windows)
    assert all(window.window_id.startswith("window-multi-") for window in first.hydrated_windows)


def test_candidate_threshold_configuration_is_exposed_without_a_pass_fail_label():
    cases, expected = _bundle()
    thresholds = CandidateThresholdConfig(
        source_hit_min=0.9,
        false_positive_rate_max=0.1,
        evidence_grounding_min=0.9,
        max_tool_call_count=2,
        max_token_proxy=300,
        max_latency_ms=250,
    )

    evaluation = evaluate_retrieval_golden_set(
        cases,
        expected,
        supplied_latency_ms={},
        candidate_thresholds=thresholds,
    )[0]
    payload = evaluation.as_dict()

    assert payload["candidate_thresholds"] == thresholds.as_dict()
    assert "passed" not in payload
    assert "ratified" not in payload


@pytest.mark.parametrize("latency", [-1, float("inf"), "slow", True])
def test_supplied_latency_is_validated_without_measuring_a_live_call(latency):
    cases, expected = _bundle()
    with pytest.raises(ValueError, match="supplied_latency_ms"):
        evaluate_retrieval_case(cases[0], expected[cases[0].case_id], supplied_latency_ms=latency)


def test_hydrator_never_accepts_a_window_not_referenced_by_selected_card():
    cases, _ = _bundle()
    case = cases[0]
    selected = ()

    hydrated = hydrate_bounded_windows(
        selected,
        case.summary_cards,
        case.windows,
        bounds=case.bounds,
    )

    assert hydrated == ()
