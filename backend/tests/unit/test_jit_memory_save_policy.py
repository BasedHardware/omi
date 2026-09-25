from __future__ import annotations

from testing.jit_processing import evaluate_fixture_case, evaluate_save_candidate, load_fixture_cases


def test_fixture_oracle_is_exactly_100_percent_and_preserves_metadata() -> None:
    cases = load_fixture_cases()
    decisions = [evaluate_fixture_case(case) for case in cases]

    assert len(decisions) == len(cases) > 0
    for case, decision in zip(cases, decisions, strict=True):
        expected = case["expected"]
        assert decision.accepted is expected["accepted"], case["case_id"]
        assert decision.reason == expected["reason"], case["case_id"]
        assert decision.kind == expected["kind"], case["case_id"]
        assert decision.slot == expected["slot"], case["case_id"]
        assert decision.provenance == case["candidate"]["provenance"], case["case_id"]


def test_fixture_oracle_is_deterministic_under_a_double_run() -> None:
    cases = load_fixture_cases()
    first = [evaluate_fixture_case(case).as_dict() for case in cases]
    second = [evaluate_fixture_case(case).as_dict() for case in cases]

    assert first == second


def test_secrets_and_third_party_subjects_never_enter_user_profile() -> None:
    cases = load_fixture_cases()
    decisions = [evaluate_fixture_case(case) for case in cases]

    for case, decision in zip(cases, decisions, strict=True):
        candidate = case["candidate"]
        if candidate["subject"] != "user":
            assert decision.accepted is False, case["case_id"]

    secret = next(case["candidate"] for case in cases if case["case_id"] == "secret-rejected")
    assert evaluate_save_candidate(secret).accepted is False

    third_party = next(case["candidate"] for case in cases if case["case_id"] == "third-party-rejected")
    assert evaluate_save_candidate(third_party).accepted is False
