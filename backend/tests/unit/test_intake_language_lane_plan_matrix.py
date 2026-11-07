"""Intake unit language plan matrix: lane, reason and frozen language per evidence cell.

The GPU worker's language barrier raises ``unsupported_language`` for any speech
whose frozen language is not Parakeet-supported, so every admitted cell here
names its lane up front. A non-affirmative decision plus strict speech proof
takes the provider lane; silence and unavailable evidence keep the compute lane
with the worker's own strict inspector as authority.
"""

import pytest

from config.batch_pipeline_language import (
    INTAKE_UNIT_LANES,
    INTAKE_UNIT_PLAN_REASONS,
    IntakeUnitLanguagePlan,
    intake_unit_language_plan,
)
from config.prerecorded_language import language_class

GUARD = True
NO_GUARD = False


def plan(decision='und', safe=False, speech=None, input_language='multi', guard=GUARD):
    return intake_unit_language_plan(
        decision_language=decision,
        parakeet_safe=safe,
        strict_speech=speech,
        input_language=input_language,
        language_guard=guard,
    )


def test_detected_unsupported_speech_takes_provider_lane():
    assert plan('ja', False, True).lane == 'multilingual'


def test_detected_unsupported_speech_names_the_closed_reason():
    assert plan('ja', False, True).reason == 'detected_unsupported_speech'


def test_detected_unsupported_speech_freezes_the_detected_code():
    assert plan('ja', False, True).frozen_language == 'ja'


def test_unknown_speech_takes_provider_lane():
    assert plan('und', False, True).lane == 'multilingual'


def test_unknown_speech_names_the_closed_reason():
    assert plan('und', False, True).reason == 'unknown_speech'


def test_unknown_speech_freezes_und():
    assert plan('und', False, True).frozen_language == 'und'


def test_low_confidence_supported_code_with_speech_takes_provider_lane():
    assert plan('en', False, True).lane == 'multilingual'


def test_low_confidence_supported_code_with_speech_names_unknown_speech():
    assert plan('en', False, True).reason == 'unknown_speech'


def test_low_confidence_supported_code_with_speech_freezes_und():
    assert plan('en', False, True).frozen_language == 'und'


def test_unavailable_detection_with_speech_still_proves_speech_through_strict_vad():
    assert plan(None, False, True).lane == 'multilingual'


def test_unavailable_detection_with_speech_names_unknown_speech():
    assert plan(None, False, True).reason == 'unknown_speech'


def test_unavailable_detection_with_speech_freezes_und():
    assert plan(None, False, True).frozen_language == 'und'


def test_blank_detection_with_speech_takes_provider_lane():
    assert plan('', False, True).lane == 'multilingual'


def test_multi_detection_with_speech_takes_provider_lane():
    assert plan('multi', False, True).lane == 'multilingual'


def test_silent_unknown_unit_keeps_compute_lane():
    assert plan('und', False, False).lane == 'parakeet'


def test_silent_unknown_unit_names_the_barrier_reason():
    assert plan('und', False, False).reason == 'silent_or_unresolved_barrier'


def test_silent_unknown_unit_freezes_und():
    assert plan('und', False, False).frozen_language == 'und'


def test_unmeasured_unknown_unit_keeps_compute_lane():
    assert plan('und', False, None).lane == 'parakeet'


def test_unmeasured_unknown_unit_names_the_barrier_reason():
    assert plan('und', False, None).reason == 'silent_or_unresolved_barrier'


def test_unmeasured_unknown_unit_freezes_und():
    assert plan('und', False, None).frozen_language == 'und'


def test_silent_detected_unsupported_unit_keeps_compute_lane():
    assert plan('ja', False, False).lane == 'parakeet'


def test_silent_detected_unsupported_unit_names_the_barrier_reason():
    assert plan('ja', False, False).reason == 'silent_or_unresolved_barrier'


def test_silent_detected_unsupported_unit_freezes_the_detected_code():
    assert plan('ja', False, False).frozen_language == 'ja'


def test_unmeasured_detected_unsupported_unit_keeps_compute_lane():
    assert plan('ja', False, None).lane == 'parakeet'


def test_unmeasured_detected_unsupported_unit_freezes_the_detected_code():
    assert plan('ja', False, None).frozen_language == 'ja'


def test_silent_low_confidence_supported_code_keeps_compute_lane():
    assert plan('en', False, False).lane == 'parakeet'


def test_silent_low_confidence_supported_code_freezes_und():
    assert plan('en', False, False).frozen_language == 'und'


def test_unmeasured_low_confidence_supported_code_keeps_compute_lane():
    assert plan('en', False, None).lane == 'parakeet'


def test_unmeasured_low_confidence_supported_code_freezes_und():
    assert plan('en', False, None).frozen_language == 'und'


def test_silent_blank_detection_keeps_compute_lane():
    assert plan('', False, False).lane == 'parakeet'


def test_silent_blank_detection_freezes_und():
    assert plan('', False, False).frozen_language == 'und'


def test_unmeasured_blank_detection_keeps_compute_lane():
    assert plan('', False, None).lane == 'parakeet'


def test_unmeasured_blank_detection_freezes_und():
    assert plan('', False, None).frozen_language == 'und'


def test_silent_multi_detection_keeps_compute_lane():
    assert plan('multi', False, False).lane == 'parakeet'


def test_unmeasured_multi_detection_keeps_compute_lane():
    assert plan('multi', False, None).lane == 'parakeet'


def test_safe_decision_wins_over_strict_speech():
    assert plan('en', True, True).lane == 'parakeet'


def test_safe_decision_names_its_reason_despite_speech():
    assert plan('en', True, True).reason == 'decision_parakeet_safe'


def test_safe_decision_freezes_the_decided_code_despite_speech():
    assert plan('en', True, True).frozen_language == 'en'


def test_safe_decision_wins_over_silence():
    assert plan('en', True, False).lane == 'parakeet'


def test_safe_decision_wins_over_unmeasured_evidence():
    assert plan('en', True, None).lane == 'parakeet'


def test_safe_unsupported_class_decision_is_impossible_but_still_safe():
    assert plan('ja', True, True).lane == 'parakeet'


def test_guard_off_restores_input_language_freeze():
    assert plan('und', False, True, guard=NO_GUARD).frozen_language == 'multi'


def test_guard_off_freeze_is_never_normalized():
    assert plan('und', False, True, input_language='', guard=NO_GUARD).frozen_language == ''


def test_empty_frozen_language_is_a_valid_parent_parity_value():
    from config.batch_pipeline_language import IntakeUnitLanguagePlan

    assert IntakeUnitLanguagePlan('parakeet', 'guard_disabled', '').frozen_language == ''


def test_oversized_frozen_language_is_still_rejected():
    from config.batch_pipeline_language import IntakeUnitLanguagePlan

    with pytest.raises(ValueError):
        IntakeUnitLanguagePlan('parakeet', 'guard_disabled', 'x' * 17)


def test_guard_off_keeps_compute_lane_for_unresolved_speech():
    assert plan('und', False, True, guard=NO_GUARD).lane == 'parakeet'


def test_guard_off_names_the_guard_reason():
    assert plan('und', False, True, guard=NO_GUARD).reason == 'guard_disabled'


def test_guard_off_still_freezes_a_confident_unsupported_code():
    assert plan('ja', False, True, guard=NO_GUARD).frozen_language == 'ja'


def test_guard_off_still_flips_proven_unsupported_speech():
    assert plan('ja', False, True, guard=NO_GUARD).lane == 'multilingual'


def test_guard_off_never_flips_unresolved_speech():
    assert plan('en', False, True, guard=NO_GUARD).lane == 'parakeet'


def test_guard_off_with_safe_decision_freezes_the_decided_code():
    assert plan('en', True, None, guard=NO_GUARD).frozen_language == 'en'


def test_guard_off_with_blank_input_freezes_the_raw_input():
    assert plan('und', False, None, input_language='', guard=NO_GUARD).frozen_language == ''


def test_blank_input_language_freezes_verbatim_for_parent_parity():
    assert plan(None, False, None, input_language='', guard=NO_GUARD).frozen_language == ''


def test_multi_input_language_freezes_verbatim_for_parent_parity():
    assert plan(None, False, None, input_language='multi', guard=NO_GUARD).frozen_language == 'multi'


def test_guard_off_ignores_strict_speech_proof():
    assert plan('und', False, True, guard=NO_GUARD).reason == 'guard_disabled'


def test_declared_supported_language_classifies_supported():
    assert language_class('en') == 'supported'


def test_declared_unsupported_language_classifies_unsupported():
    assert language_class('ja') == 'unsupported'


def test_und_classifies_unknown():
    assert language_class('und') == 'unknown'


def test_multi_classifies_unknown():
    assert language_class('multi') == 'unknown'


def test_blank_classifies_unknown():
    assert language_class('') == 'unknown'


def test_none_classifies_unknown():
    assert language_class(None) == 'unknown'


def test_plan_lanes_are_the_closed_pair():
    assert INTAKE_UNIT_LANES == frozenset({'parakeet', 'multilingual'})


def test_plan_reasons_are_closed():
    assert INTAKE_UNIT_PLAN_REASONS == frozenset(
        {
            'guard_disabled',
            'decision_parakeet_safe',
            'unknown_speech',
            'detected_unsupported_speech',
            'silent_or_unresolved_barrier',
        }
    )


def test_plan_rejects_an_off_vocabulary_lane():
    with pytest.raises(ValueError):
        IntakeUnitLanguagePlan('gpu', 'unknown_speech', 'und')


def test_plan_rejects_a_free_form_reason():
    with pytest.raises(ValueError):
        IntakeUnitLanguagePlan('multilingual', 'because', 'und')


def test_plan_still_requires_a_bounded_string():
    assert len(IntakeUnitLanguagePlan('multilingual', 'unknown_speech', 'und').frozen_language) == 3


def test_plan_rejects_an_oversized_frozen_language():
    with pytest.raises(ValueError):
        IntakeUnitLanguagePlan('multilingual', 'unknown_speech', 'x' * 17)


def test_plan_accepts_a_bounded_frozen_language():
    assert IntakeUnitLanguagePlan('multilingual', 'unknown_speech', 'und').frozen_language == 'und'


def test_plan_is_frozen_data():
    value = plan('ja', False, True)
    with pytest.raises(Exception):
        value.lane = 'parakeet'


@pytest.mark.parametrize('code', ['en', 'es', 'fr', 'de', 'it', 'pt'])
def test_supported_european_codes_with_speech_and_low_confidence_take_provider_lane(code):
    assert plan(code, False, True).lane == 'multilingual'


@pytest.mark.parametrize('code', ['en', 'es', 'fr', 'de', 'it', 'pt'])
def test_supported_european_codes_with_speech_and_low_confidence_name_unknown_speech(code):
    assert plan(code, False, True).reason == 'unknown_speech'


@pytest.mark.parametrize('code', ['en', 'es', 'fr', 'de', 'it', 'pt'])
def test_supported_european_codes_with_speech_and_low_confidence_freeze_und(code):
    assert plan(code, False, True).frozen_language == 'und'


@pytest.mark.parametrize('code', ['en', 'es', 'fr', 'de', 'it', 'pt'])
def test_supported_european_codes_silent_and_low_confidence_keep_compute_lane(code):
    assert plan(code, False, False).lane == 'parakeet'


@pytest.mark.parametrize('code', ['en', 'es', 'fr', 'de', 'it', 'pt'])
def test_supported_european_codes_silent_and_low_confidence_freeze_und(code):
    assert plan(code, False, False).frozen_language == 'und'


@pytest.mark.parametrize('code', ['ja', 'zh', 'ko', 'ar', 'hi', 'th', 'vi'])
def test_documented_wrong_script_codes_with_speech_take_provider_lane(code):
    assert language_class(code) == 'unsupported'
    assert plan(code, False, True).lane == 'multilingual'


@pytest.mark.parametrize('code', ['ja', 'zh', 'ko', 'ar', 'hi', 'th', 'vi'])
def test_documented_wrong_script_codes_with_speech_freeze_the_detected_code(code):
    assert plan(code, False, True).frozen_language == code


@pytest.mark.parametrize('code', ['ja', 'zh', 'ko', 'ar', 'hi', 'th', 'vi'])
def test_documented_wrong_script_codes_silent_keep_compute_lane(code):
    assert plan(code, False, False).lane == 'parakeet'


@pytest.mark.parametrize('code', ['ja', 'zh', 'ko', 'ar', 'hi', 'th', 'vi'])
def test_documented_wrong_script_codes_silent_freeze_the_detected_code(code):
    assert plan(code, False, False).frozen_language == code


@pytest.mark.parametrize('code', ['ja', 'zh', 'ko', 'ar', 'hi', 'th', 'vi'])
def test_documented_wrong_script_codes_unmeasured_keep_compute_lane(code):
    assert plan(code, False, None).lane == 'parakeet'


@pytest.mark.parametrize('speech', [True])
def test_speech_is_the_only_evidence_that_flips_the_lane(speech):
    assert plan('und', False, speech).lane == 'multilingual'


@pytest.mark.parametrize('speech', [False, None])
def test_absent_speech_evidence_never_flips_the_lane(speech):
    assert plan('und', False, speech).lane == 'parakeet'


@pytest.mark.parametrize('speech', [False, None])
def test_absent_speech_evidence_names_the_barrier_reason(speech):
    assert plan('und', False, speech).reason == 'silent_or_unresolved_barrier'


@pytest.mark.parametrize('decision', ['und', '', 'multi', None])
def test_unknown_class_decisions_with_speech_flip_to_multilingual(decision):
    assert plan(decision, False, True).lane == 'multilingual'


@pytest.mark.parametrize('decision', ['und', '', 'multi', None])
def test_unknown_class_decisions_with_speech_freeze_und(decision):
    assert plan(decision, False, True).frozen_language == 'und'


@pytest.mark.parametrize('decision', ['und', '', 'multi', None])
def test_unknown_class_decisions_silent_keep_compute_lane(decision):
    assert plan(decision, False, False).lane == 'parakeet'


@pytest.mark.parametrize('decision', ['und', '', 'multi', None])
def test_unknown_class_decisions_silent_freeze_und(decision):
    assert plan(decision, False, False).frozen_language == 'und'


@pytest.mark.parametrize('decision', ['und', '', 'multi', None])
def test_unknown_class_decisions_unmeasured_keep_compute_lane(decision):
    assert plan(decision, False, None).lane == 'parakeet'


@pytest.mark.parametrize('guard', [True, False])
def test_guard_value_always_returns_a_closed_lane(guard):
    assert plan('ja', False, True, guard=guard).lane in INTAKE_UNIT_LANES


@pytest.mark.parametrize('guard', [True, False])
def test_guard_value_always_names_a_closed_reason(guard):
    assert plan('ja', False, True, guard=guard).reason in INTAKE_UNIT_PLAN_REASONS


@pytest.mark.parametrize('safe', [True, False])
def test_safety_flag_always_returns_a_closed_lane(safe):
    assert plan('en', safe, True).lane in INTAKE_UNIT_LANES


@pytest.mark.parametrize('safe', [True, False])
def test_safety_flag_always_names_a_closed_reason(safe):
    assert plan('en', safe, True).reason in INTAKE_UNIT_PLAN_REASONS


def test_provider_lane_requires_speech_not_safety():
    assert plan('ja', False, True).lane == 'multilingual' and plan('ja', True, True).lane == 'parakeet'


def test_compute_lane_is_the_default_for_every_unproven_cell():
    for speech in (False, None):
        for decision in ('und', '', 'multi', None, 'en', 'ja'):
            assert plan(decision, False, speech).lane == 'parakeet'


def test_provider_lane_cells_all_carry_speech_proof():
    for decision in ('und', '', 'multi', None, 'en', 'ja'):
        assert plan(decision, False, True).lane == 'multilingual'


def test_frozen_language_is_never_empty_in_any_cell():
    for decision in ('und', '', 'multi', None, 'en', 'ja'):
        for speech in (True, False, None):
            assert plan(decision, False, speech).frozen_language


def test_frozen_language_is_bounded_in_any_cell():
    for decision in ('und', '', 'multi', None, 'en', 'ja'):
        for speech in (True, False, None):
            assert len(plan(decision, False, speech).frozen_language) <= 16


def test_guard_off_cell_never_reads_strict_evidence():
    for speech in (True, False, None):
        assert plan('und', False, speech, guard=NO_GUARD).reason == 'guard_disabled'


def test_safe_cell_never_reads_strict_evidence():
    for speech in (True, False, None):
        assert plan('en', True, speech).reason == 'decision_parakeet_safe'


def test_multilingual_cells_require_the_guard():
    for decision in ('und', 'ja', 'en'):
        value = plan(decision, False, True)
        assert value.lane == 'multilingual' and value.frozen_language in {decision, 'und'}


def test_barrier_reason_cells_never_flip_to_multilingual():
    for decision in ('und', '', 'multi', None, 'en', 'ja'):
        for speech in (False, None):
            assert plan(decision, False, speech).reason == 'silent_or_unresolved_barrier'


def test_und_stays_the_freeze_for_unresolved_speech_cells():
    for decision in ('und', '', 'multi', None, 'en'):
        assert plan(decision, False, False).frozen_language == 'und'


def test_detected_code_stays_the_freeze_for_unresolved_unsupported_cells():
    for code in ('ja', 'zh', 'ar'):
        assert plan(code, False, False).frozen_language == code
