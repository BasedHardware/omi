# Failure-Class: FC-empty-ladder-gate-drift-misroutes-recovery-units-between-hold-retry-and-terminal-rungs
"""The empty ladder's handoff disposition is one closed predicate, pinned cell-by-cell.

``empty_ladder_handoff`` answers, for one worker reason, whether the unit
rides the recovery handoff. The GPU worker asks it at two boundaries (the
terminal ``RecoveryWork`` selection and the post-retry hold gate), so this
suite pins the full flag×reason truth table, the name and call contracts,
and equivalence with the inline expression both boundaries carried before
the extraction. A drift between the predicate and any boundary now fails
here before it can misroute a production unit between ladder rungs.

Truth table under test (rec = recovery flag, dis = disposition flag,
saf = safety net):

- ``empty_asr``: True iff ``saf or rec or dis`` (the reason sits in both
  arms of the historical expression).
- ``no_owned_words``: True iff ``saf or dis``.
- every other reason: False at every combination.
"""

import inspect

import pytest

from config.batch_pipeline_empty_asr import empty_ladder_handoff
from utils.batch_pipeline.contracts import EMPTY_WORKER_REASONS, WorkerValidationReason

FAMILY = ('empty_asr', 'no_owned_words')
COMBOS = (
    (True, True, True),
    (True, False, True),
    (False, True, True),
    (False, False, True),
    (True, True, False),
    (True, False, False),
    (False, True, False),
    (False, False, False),
)


def handoff(reason, recovery, disposition, safety):
    return empty_ladder_handoff(
        reason, recovery_enabled=recovery, disposition_enabled=disposition, safety_enabled=safety
    )


# --- empty_asr cells: safety dominates, recovery alone carries the kill-switched arm ------


def test_empty_asr_safety_on_recovers_even_with_both_flags_off():
    assert handoff('empty_asr', False, False, True) is True


def test_empty_asr_safety_on_with_recovery_on_still_hands_off():
    assert handoff('empty_asr', True, False, True) is True


def test_empty_asr_safety_on_with_disposition_on_still_hands_off():
    assert handoff('empty_asr', False, True, True) is True


def test_empty_asr_safety_on_with_every_flag_on_still_hands_off():
    assert handoff('empty_asr', True, True, True) is True


def test_empty_asr_recovery_flag_alone_carries_the_kill_switched_arm():
    assert handoff('empty_asr', True, False, False) is True


def test_empty_asr_recovery_with_disposition_without_safety_still_hands_off():
    assert handoff('empty_asr', True, True, False) is True


def test_empty_asr_disposition_flag_alone_carries_the_kill_switched_arm():
    assert handoff('empty_asr', False, True, False) is True


def test_empty_asr_recovery_and_disposition_each_carry_the_arm_without_safety():
    assert handoff('empty_asr', True, False, False) is True
    assert handoff('empty_asr', False, True, False) is True


def test_empty_asr_every_switch_off_keeps_the_unit_off_the_handoff():
    assert handoff('empty_asr', False, False, False) is False


# --- no_owned_words cells: safety dominates, disposition alone carries the kill-switched arm


def test_no_owned_words_safety_on_recovers_even_with_both_flags_off():
    assert handoff('no_owned_words', False, False, True) is True


def test_no_owned_words_safety_on_with_disposition_on_still_hands_off():
    assert handoff('no_owned_words', False, True, True) is True


def test_no_owned_words_safety_on_with_recovery_on_still_hands_off():
    assert handoff('no_owned_words', True, False, True) is True


def test_no_owned_words_safety_on_with_every_flag_on_still_hands_off():
    assert handoff('no_owned_words', True, True, True) is True


def test_no_owned_words_disposition_flag_alone_carries_the_kill_switched_arm():
    assert handoff('no_owned_words', False, True, False) is True


def test_no_owned_words_disposition_with_recovery_without_safety_still_hands_off():
    assert handoff('no_owned_words', True, True, False) is True


def test_no_owned_words_without_safety_or_disposition_stays_off_despite_recovery():
    assert handoff('no_owned_words', True, False, False) is False


def test_no_owned_words_every_switch_off_keeps_the_unit_off_the_handoff():
    assert handoff('no_owned_words', False, False, False) is False


# --- non-family reasons never hand off at any combination ---------------------------------


def test_word_clock_never_hands_off_on_any_flag_combination():
    for recovery, disposition, safety in COMBOS:
        assert handoff('word_clock', recovery, disposition, safety) is False


def test_unsupported_language_never_hands_off_on_any_flag_combination():
    for recovery, disposition, safety in COMBOS:
        assert handoff('unsupported_language', recovery, disposition, safety) is False


def test_word_shape_never_hands_off_on_any_flag_combination():
    for recovery, disposition, safety in COMBOS:
        assert handoff('word_shape', recovery, disposition, safety) is False


def test_vad_bounds_never_hands_off_on_any_flag_combination():
    for recovery, disposition, safety in COMBOS:
        assert handoff('vad_bounds', recovery, disposition, safety) is False


def test_empty_reason_token_never_hands_off_on_any_flag_combination():
    for recovery, disposition, safety in COMBOS:
        assert handoff('', recovery, disposition, safety) is False


def test_word_sequence_never_hands_off_on_any_flag_combination():
    for recovery, disposition, safety in COMBOS:
        assert handoff('word_sequence', recovery, disposition, safety) is False


def test_unclassified_never_hands_off_on_any_flag_combination():
    for recovery, disposition, safety in COMBOS:
        assert handoff('unclassified', recovery, disposition, safety) is False


def test_staged_audio_invalid_never_hands_off_on_any_flag_combination():
    for recovery, disposition, safety in COMBOS:
        assert handoff('staged_audio_invalid', recovery, disposition, safety) is False


# --- the family arm is exactly the closed empty vocabulary --------------------------------


def test_every_empty_worker_reason_rides_the_family_arm_under_safety():
    for reason in sorted(EMPTY_WORKER_REASONS):
        assert handoff(reason, False, False, True) is True


def test_no_empty_worker_reason_rides_the_family_arm_with_every_switch_off():
    for reason in sorted(EMPTY_WORKER_REASONS):
        assert handoff(reason, False, False, False) is False


def test_non_family_closed_reasons_stay_off_even_under_safety():
    closed = {reason.value for reason in WorkerValidationReason} - EMPTY_WORKER_REASONS
    for reason in sorted(closed):
        assert handoff(reason, False, False, True) is False


def test_reason_vocabulary_member_outside_the_family_matches_word_clock_cells():
    closed = {reason.value for reason in WorkerValidationReason} - EMPTY_WORKER_REASONS
    for reason in sorted(closed):
        for recovery, disposition, safety in COMBOS:
            assert handoff(reason, recovery, disposition, safety) is False


# --- safety dominance boundaries -----------------------------------------------------------


def test_safety_never_turns_a_handoff_answer_false_for_empty_asr():
    for recovery, disposition in ((True, True), (True, False), (False, True), (False, False)):
        without = handoff('empty_asr', recovery, disposition, False)
        with_safety = handoff('empty_asr', recovery, disposition, True)
        assert (without, with_safety) in {(False, True), (True, True)}


def test_safety_never_turns_a_handoff_answer_false_for_no_owned_words():
    for recovery, disposition in ((True, True), (True, False), (False, True), (False, False)):
        without = handoff('no_owned_words', recovery, disposition, False)
        with_safety = handoff('no_owned_words', recovery, disposition, True)
        assert (without, with_safety) in {(False, True), (True, True)}


def test_safety_alone_is_enough_for_both_family_reasons():
    assert handoff('empty_asr', False, False, True) is True
    assert handoff('no_owned_words', False, False, True) is True


def test_safety_off_leaves_each_family_reason_to_its_own_arms():
    assert handoff('empty_asr', True, False, False) is True
    assert handoff('empty_asr', False, True, False) is True
    assert handoff('no_owned_words', False, True, False) is True
    assert handoff('no_owned_words', True, False, False) is False


def test_under_safety_the_two_family_reasons_answer_identically():
    for recovery, disposition, safety in COMBOS:
        if safety:
            assert handoff('empty_asr', recovery, disposition, safety) is True
            assert handoff('no_owned_words', recovery, disposition, safety) is True


def test_recovery_and_disposition_flags_are_interchangeable_only_under_safety():
    assert handoff('empty_asr', True, False, False) == handoff('empty_asr', False, True, False)
    assert handoff('no_owned_words', True, False, False) != handoff('no_owned_words', False, True, False)
    assert handoff('no_owned_words', True, False, True) == handoff('no_owned_words', False, True, True)


# --- reason name boundaries -----------------------------------------------------------------


def test_reason_with_trailing_space_is_not_the_family_token():
    assert handoff('empty_asr ', True, True, False) is False


def test_reason_with_leading_space_is_not_the_family_token():
    assert handoff(' empty_asr', True, True, False) is False


def test_uppercase_reason_is_not_the_family_token():
    assert handoff('EMPTY_ASR', True, True, False) is False


def test_hyphenated_reason_is_not_the_family_token():
    assert handoff('empty-asr', True, True, False) is False


def test_no_owned_words_with_trailing_space_is_not_the_family_token():
    assert handoff('no_owned_words ', False, False, True) is False


def test_none_reason_is_not_the_family_token():
    assert handoff(None, True, True, False) is False


def test_bytes_reason_is_not_the_family_token():
    assert handoff(b'empty_asr', True, True, False) is False


def test_tab_padded_reason_is_not_the_family_token():
    assert handoff('empty_asr\t', True, True, False) is False


def test_nul_suffixed_reason_is_not_the_family_token():
    assert handoff('empty_asr\x00', True, True, False) is False


def test_pluralized_reason_is_not_the_family_token():
    assert handoff('empty_asrs', True, True, False) is False


def test_truncated_reason_is_not_the_family_token():
    assert handoff('empty_as', True, True, False) is False


def test_extended_reason_is_not_the_family_token():
    assert handoff('empty_asr_error', True, True, False) is False


def test_newline_padded_reason_is_not_the_family_token():
    assert handoff('empty_asr\n', True, True, False) is False


def test_unicode_lookalike_reason_is_not_the_family_token():
    assert handoff('еmpty_asr', True, True, False) is False  # first glyph is Cyrillic


def test_snake_cased_variant_is_not_the_family_token():
    assert handoff('EMPTY_asr', True, True, False) is False


def test_no_owned_hyphenated_variant_is_not_the_family_token():
    assert handoff('no-owned-words', False, True, False) is False


# --- call contract ---------------------------------------------------------------------------


def test_flags_are_keyword_only():
    with pytest.raises(TypeError):
        empty_ladder_handoff('empty_asr', True, False, True)


def test_missing_recovery_flag_is_rejected():
    with pytest.raises(TypeError):
        empty_ladder_handoff('empty_asr', disposition_enabled=True, safety_enabled=True)


def test_missing_disposition_flag_is_rejected():
    with pytest.raises(TypeError):
        empty_ladder_handoff('empty_asr', recovery_enabled=True, safety_enabled=True)


def test_missing_safety_flag_is_rejected():
    with pytest.raises(TypeError):
        empty_ladder_handoff('empty_asr', recovery_enabled=True, disposition_enabled=True)


def test_unknown_keyword_is_rejected():
    with pytest.raises(TypeError):
        empty_ladder_handoff(
            'empty_asr', recovery_enabled=True, disposition_enabled=True, safety_enabled=True, safety=True
        )


def test_true_answers_are_real_bools():
    assert handoff('empty_asr', False, False, True) is True


def test_false_answers_are_real_bools():
    assert handoff('word_clock', True, True, True) is False


def test_flags_carry_no_defaults_in_the_signature():
    signature = inspect.signature(empty_ladder_handoff)
    for name in ('recovery_enabled', 'disposition_enabled', 'safety_enabled'):
        assert signature.parameters[name].default is inspect.Parameter.empty
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_str_subclass_reason_matches_the_family_token():
    class Reason(str):
        pass

    assert handoff(Reason('empty_asr'), False, False, True) is True
    assert handoff(Reason('no_owned_words'), False, True, False) is True


# --- equivalence with the historical inline expressions -------------------------------------


def _historical_terminal_gate(reason, recovery, disposition, safety):
    # The exact inline expression the assemble_words RecoveryWork selection
    # carried before the extraction, including its operator precedence.
    return (reason == 'empty_asr' and (recovery or safety)) or (
        reason in {'empty_asr', 'no_owned_words'} and (disposition or safety)
    )


def _historical_hold_gate(reason, recovery, disposition, safety):
    # The post-retry hold gate negated the same expression.
    return not (
        (reason == 'empty_asr' and (recovery or safety))
        or (reason in {'empty_asr', 'no_owned_words'} and (disposition or safety))
    )


def test_predicate_equals_the_historical_terminal_gate_on_every_family_cell():
    for reason in FAMILY:
        for recovery, disposition, safety in COMBOS:
            assert handoff(reason, recovery, disposition, safety) == _historical_terminal_gate(
                reason, recovery, disposition, safety
            )


def test_predicate_equals_the_historical_terminal_gate_on_every_non_family_cell():
    for reason in ('word_clock', 'unclassified', ''):
        for recovery, disposition, safety in COMBOS:
            assert handoff(reason, recovery, disposition, safety) == _historical_terminal_gate(
                reason, recovery, disposition, safety
            )


def test_negated_predicate_equals_the_historical_hold_gate_on_every_family_cell():
    for reason in FAMILY:
        for recovery, disposition, safety in COMBOS:
            assert handoff(reason, recovery, disposition, safety) is not _historical_hold_gate(
                reason, recovery, disposition, safety
            )


def test_negated_predicate_equals_the_historical_hold_gate_on_every_non_family_cell():
    for reason in ('word_clock', 'unclassified', ''):
        for recovery, disposition, safety in COMBOS:
            assert handoff(reason, recovery, disposition, safety) is not _historical_hold_gate(
                reason, recovery, disposition, safety
            )


def test_historical_precedence_trap_stays_fixed_parenthesization_is_mandatory():
    # The historical expression relied on ``and`` binding tighter than ``or``;
    # a naive left-to-right reading answers differently for no_owned_words.
    reason, recovery, disposition, safety = 'no_owned_words', True, False, False
    assert handoff(reason, recovery, disposition, safety) is False
    assert _historical_terminal_gate(reason, recovery, disposition, safety) is False


# --- purity and determinism ------------------------------------------------------------------


def test_repeated_calls_are_deterministic():
    first = handoff('empty_asr', True, False, True)
    for _ in range(5):
        assert handoff('empty_asr', True, False, True) is first


def test_environment_changes_never_alter_fixed_arguments(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    assert handoff('no_owned_words', False, False, False) is False


def test_environment_kill_switches_never_alter_fixed_arguments(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'false')
    assert handoff('empty_asr', True, False, True) is True


def test_predicate_reads_no_module_state_between_calls():
    answers = {(combo): handoff('empty_asr', *combo) for combo in COMBOS}
    again = {(combo): handoff('empty_asr', *combo) for combo in COMBOS}
    assert answers == again


# --- the second closed reason rides the same cells ---------------------------------------------


def test_decoded_duration_mismatch_never_hands_off_on_any_flag_combination():
    for recovery, disposition, safety in COMBOS:
        assert handoff('decoded_duration_mismatch', recovery, disposition, safety) is False


def test_retained_audio_invalid_never_hands_off_on_any_flag_combination():
    for recovery, disposition, safety in COMBOS:
        assert handoff('retained_audio_invalid', recovery, disposition, safety) is False


def test_no_owned_cells_answer_true_whenever_any_admitting_flag_is_on():
    for recovery, disposition, safety in COMBOS:
        expected = safety or disposition
        assert handoff('no_owned_words', recovery, disposition, safety) is expected


def test_empty_asr_cells_answer_true_whenever_any_admitting_flag_is_on():
    for recovery, disposition, safety in COMBOS:
        expected = safety or recovery or disposition
        assert handoff('empty_asr', recovery, disposition, safety) is expected


def test_safety_off_disposition_on_is_the_only_no_owned_kill_switch_arm():
    assert handoff('no_owned_words', False, True, False) is True
    assert handoff('no_owned_words', False, False, False) is False


def test_safety_off_recovery_on_is_one_of_two_empty_asr_kill_switch_arms():
    assert handoff('empty_asr', True, False, False) is True
    assert handoff('empty_asr', False, True, False) is True


def test_safety_domination_holds_cell_by_cell_for_empty_asr():
    for recovery, disposition in ((True, True), (True, False), (False, True), (False, False)):
        assert handoff('empty_asr', recovery, disposition, True) is True


def test_safety_domination_holds_cell_by_cell_for_no_owned_words():
    for recovery, disposition in ((True, True), (True, False), (False, True), (False, False)):
        assert handoff('no_owned_words', recovery, disposition, True) is True


def test_flag_triples_exhaust_the_whole_matrix_for_the_family():
    seen = set()
    for recovery, disposition, safety in COMBOS:
        seen.add((handoff('empty_asr', recovery, disposition, safety),))
    assert seen == {(True,), (False,)}


def test_the_predicate_answers_for_every_closed_reason_token(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', raising=False)
    closed = {reason.value for reason in WorkerValidationReason}
    for reason in sorted(closed):
        answer = handoff(reason, False, False, True)
        assert answer is (reason in EMPTY_WORKER_REASONS)


# --- precedence documentation cells -------------------------------------------------------------


def test_precedence_cell_no_owned_recovery_only_without_safety_is_false():
    # ``(True and (True)) or (True and (False))`` under a left-to-right
    # misreading would answer True; the parenthesized contract answers False.
    assert handoff('no_owned_words', True, False, False) is False


def test_precedence_cell_no_owned_disposition_only_without_safety_is_true():
    assert handoff('no_owned_words', False, True, False) is True


def test_precedence_cell_empty_asr_every_single_flag_alone_is_true():
    for flags in ((True, False, False), (False, True, False), (False, False, True)):
        assert handoff('empty_asr', *flags) is True


def test_precedence_cell_no_owned_safety_or_disposition_never_recovery():
    assert handoff('no_owned_words', True, False, False) is False
    assert handoff('no_owned_words', False, True, False) is True
    assert handoff('no_owned_words', False, False, True) is True


# --- derived contract cells ----------------------------------------------------------------------


def test_the_predicate_and_its_negation_partition_the_matrix():
    for reason in FAMILY:
        for recovery, disposition, safety in COMBOS:
            gate = handoff(reason, recovery, disposition, safety)
            assert (gate, not gate) in {(True, False), (False, True)}


def test_both_boundary_answers_agree_for_the_family_at_safety_on():
    for recovery, disposition in ((True, True), (True, False), (False, True), (False, False)):
        assert handoff('empty_asr', recovery, disposition, True) == handoff(
            'no_owned_words', recovery, disposition, True
        )


def test_unknown_reason_tokens_answer_false_under_every_single_flag():
    for reason in ('', 'unclassified', 'unknown', 'word_clocks'):
        assert handoff(reason, True, False, False) is False
        assert handoff(reason, False, True, False) is False
        assert handoff(reason, False, False, True) is False


def test_the_word_clocks_stage_token_is_distinct_from_the_word_clock_reason():
    assert handoff('word_clocks', True, True, True) is False
    assert handoff('word_clock', True, True, True) is False


def test_asr_recovery_stage_token_never_hands_off():
    assert handoff('asr_recovery', True, True, True) is False


def test_fetch_decode_stage_token_never_hands_off():
    assert handoff('fetch_decode', True, True, True) is False
