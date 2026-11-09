# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The empty-ladder channel predicate, pinned cell-by-cell over the closed vocabulary.

``empty_ladder_recovery_failure`` accepts exactly the two-key closed shapes the
scheduler stores on a job, with the stage the empty ladder owns
(``assemble_words``) and the family reasons (``empty_asr``/``no_owned_words``).
Every (stage, reason) pair of the closed worker vocabularies is pinned against
a literal oracle written into the test, plus the hostile-input surface, the
family constants' membership, and the boundary against the language-guard set.

The predicate is the scheduler side of the demotion; the worker side reads the
same constants directly (``EMPTY_LADDER_RECOVERY_REASONS`` +
``EMPTY_LADDER_RECOVERY_STAGE``), so these cells bound both sites.
"""

from utils.batch_pipeline.errors import (
    EMPTY_LADDER_RECOVERY_REASONS,
    EMPTY_LADDER_RECOVERY_STAGE,
    LANGUAGE_GUARD_REDRIVE_REASONS,
    empty_ladder_recovery_failure,
)
from config.batch_pipeline_empty_asr import empty_ladder_handoff
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage, reason_values

FAMILY = ("empty_asr", "no_owned_words")
STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery', 'unknown')
REASONS = (
    'staged_audio_invalid',
    'retained_audio_invalid',
    'decoded_duration_mismatch',
    'word_shape',
    'word_clock',
    'word_sequence',
    'vad_nonfinite',
    'vad_order',
    'vad_bounds',
    'empty_asr',
    'no_owned_words',
    'unsupported_language',
    'outside_admitted_source',
    'unknown',
)


def test_predicate_stage_fetch_decode_reason_staged_audio_invalid_is_false():
    """(fetch_decode, staged_audio_invalid) -> False."""
    shape = {"stage": "fetch_decode", "reason": "staged_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_retained_audio_invalid_is_false():
    """(fetch_decode, retained_audio_invalid) -> False."""
    shape = {"stage": "fetch_decode", "reason": "retained_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_decoded_duration_mismatch_is_false():
    """(fetch_decode, decoded_duration_mismatch) -> False."""
    shape = {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_word_shape_is_false():
    """(fetch_decode, word_shape) -> False."""
    shape = {"stage": "fetch_decode", "reason": "word_shape"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_word_clock_is_false():
    """(fetch_decode, word_clock) -> False."""
    shape = {"stage": "fetch_decode", "reason": "word_clock"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_word_sequence_is_false():
    """(fetch_decode, word_sequence) -> False."""
    shape = {"stage": "fetch_decode", "reason": "word_sequence"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_vad_nonfinite_is_false():
    """(fetch_decode, vad_nonfinite) -> False."""
    shape = {"stage": "fetch_decode", "reason": "vad_nonfinite"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_vad_order_is_false():
    """(fetch_decode, vad_order) -> False."""
    shape = {"stage": "fetch_decode", "reason": "vad_order"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_vad_bounds_is_false():
    """(fetch_decode, vad_bounds) -> False."""
    shape = {"stage": "fetch_decode", "reason": "vad_bounds"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_empty_asr_is_false():
    """(fetch_decode, empty_asr) -> False."""
    shape = {"stage": "fetch_decode", "reason": "empty_asr"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_no_owned_words_is_false():
    """(fetch_decode, no_owned_words) -> False."""
    shape = {"stage": "fetch_decode", "reason": "no_owned_words"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_unsupported_language_is_false():
    """(fetch_decode, unsupported_language) -> False."""
    shape = {"stage": "fetch_decode", "reason": "unsupported_language"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_outside_admitted_source_is_false():
    """(fetch_decode, outside_admitted_source) -> False."""
    shape = {"stage": "fetch_decode", "reason": "outside_admitted_source"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_fetch_decode_reason_unknown_is_false():
    """(fetch_decode, unknown) -> False."""
    shape = {"stage": "fetch_decode", "reason": "unknown"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_staged_audio_invalid_is_false():
    """(vad_windows, staged_audio_invalid) -> False."""
    shape = {"stage": "vad_windows", "reason": "staged_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_retained_audio_invalid_is_false():
    """(vad_windows, retained_audio_invalid) -> False."""
    shape = {"stage": "vad_windows", "reason": "retained_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_decoded_duration_mismatch_is_false():
    """(vad_windows, decoded_duration_mismatch) -> False."""
    shape = {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_word_shape_is_false():
    """(vad_windows, word_shape) -> False."""
    shape = {"stage": "vad_windows", "reason": "word_shape"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_word_clock_is_false():
    """(vad_windows, word_clock) -> False."""
    shape = {"stage": "vad_windows", "reason": "word_clock"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_word_sequence_is_false():
    """(vad_windows, word_sequence) -> False."""
    shape = {"stage": "vad_windows", "reason": "word_sequence"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_vad_nonfinite_is_false():
    """(vad_windows, vad_nonfinite) -> False."""
    shape = {"stage": "vad_windows", "reason": "vad_nonfinite"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_vad_order_is_false():
    """(vad_windows, vad_order) -> False."""
    shape = {"stage": "vad_windows", "reason": "vad_order"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_vad_bounds_is_false():
    """(vad_windows, vad_bounds) -> False."""
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_empty_asr_is_false():
    """(vad_windows, empty_asr) -> False."""
    shape = {"stage": "vad_windows", "reason": "empty_asr"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_no_owned_words_is_false():
    """(vad_windows, no_owned_words) -> False."""
    shape = {"stage": "vad_windows", "reason": "no_owned_words"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_unsupported_language_is_false():
    """(vad_windows, unsupported_language) -> False."""
    shape = {"stage": "vad_windows", "reason": "unsupported_language"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_outside_admitted_source_is_false():
    """(vad_windows, outside_admitted_source) -> False."""
    shape = {"stage": "vad_windows", "reason": "outside_admitted_source"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_vad_windows_reason_unknown_is_false():
    """(vad_windows, unknown) -> False."""
    shape = {"stage": "vad_windows", "reason": "unknown"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_staged_audio_invalid_is_false():
    """(word_clocks, staged_audio_invalid) -> False."""
    shape = {"stage": "word_clocks", "reason": "staged_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_retained_audio_invalid_is_false():
    """(word_clocks, retained_audio_invalid) -> False."""
    shape = {"stage": "word_clocks", "reason": "retained_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_decoded_duration_mismatch_is_false():
    """(word_clocks, decoded_duration_mismatch) -> False."""
    shape = {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_word_shape_is_false():
    """(word_clocks, word_shape) -> False."""
    shape = {"stage": "word_clocks", "reason": "word_shape"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_word_clock_is_false():
    """(word_clocks, word_clock) -> False."""
    shape = {"stage": "word_clocks", "reason": "word_clock"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_word_sequence_is_false():
    """(word_clocks, word_sequence) -> False."""
    shape = {"stage": "word_clocks", "reason": "word_sequence"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_vad_nonfinite_is_false():
    """(word_clocks, vad_nonfinite) -> False."""
    shape = {"stage": "word_clocks", "reason": "vad_nonfinite"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_vad_order_is_false():
    """(word_clocks, vad_order) -> False."""
    shape = {"stage": "word_clocks", "reason": "vad_order"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_vad_bounds_is_false():
    """(word_clocks, vad_bounds) -> False."""
    shape = {"stage": "word_clocks", "reason": "vad_bounds"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_empty_asr_is_false():
    """(word_clocks, empty_asr) -> False."""
    shape = {"stage": "word_clocks", "reason": "empty_asr"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_no_owned_words_is_false():
    """(word_clocks, no_owned_words) -> False."""
    shape = {"stage": "word_clocks", "reason": "no_owned_words"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_unsupported_language_is_false():
    """(word_clocks, unsupported_language) -> False."""
    shape = {"stage": "word_clocks", "reason": "unsupported_language"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_outside_admitted_source_is_false():
    """(word_clocks, outside_admitted_source) -> False."""
    shape = {"stage": "word_clocks", "reason": "outside_admitted_source"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_word_clocks_reason_unknown_is_false():
    """(word_clocks, unknown) -> False."""
    shape = {"stage": "word_clocks", "reason": "unknown"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_staged_audio_invalid_is_false():
    """(assemble_words, staged_audio_invalid) -> False."""
    shape = {"stage": "assemble_words", "reason": "staged_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_retained_audio_invalid_is_false():
    """(assemble_words, retained_audio_invalid) -> False."""
    shape = {"stage": "assemble_words", "reason": "retained_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_decoded_duration_mismatch_is_false():
    """(assemble_words, decoded_duration_mismatch) -> False."""
    shape = {"stage": "assemble_words", "reason": "decoded_duration_mismatch"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_word_shape_is_false():
    """(assemble_words, word_shape) -> False."""
    shape = {"stage": "assemble_words", "reason": "word_shape"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_word_clock_is_false():
    """(assemble_words, word_clock) -> False."""
    shape = {"stage": "assemble_words", "reason": "word_clock"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_word_sequence_is_false():
    """(assemble_words, word_sequence) -> False."""
    shape = {"stage": "assemble_words", "reason": "word_sequence"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_vad_nonfinite_is_false():
    """(assemble_words, vad_nonfinite) -> False."""
    shape = {"stage": "assemble_words", "reason": "vad_nonfinite"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_vad_order_is_false():
    """(assemble_words, vad_order) -> False."""
    shape = {"stage": "assemble_words", "reason": "vad_order"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_vad_bounds_is_false():
    """(assemble_words, vad_bounds) -> False."""
    shape = {"stage": "assemble_words", "reason": "vad_bounds"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_empty_asr_is_true():
    """(assemble_words, empty_asr) -> True."""
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    assert empty_ladder_recovery_failure(shape) is True


def test_predicate_stage_assemble_words_reason_no_owned_words_is_true():
    """(assemble_words, no_owned_words) -> True."""
    shape = {"stage": "assemble_words", "reason": "no_owned_words"}
    assert empty_ladder_recovery_failure(shape) is True


def test_predicate_stage_assemble_words_reason_unsupported_language_is_false():
    """(assemble_words, unsupported_language) -> False."""
    shape = {"stage": "assemble_words", "reason": "unsupported_language"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_outside_admitted_source_is_false():
    """(assemble_words, outside_admitted_source) -> False."""
    shape = {"stage": "assemble_words", "reason": "outside_admitted_source"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_assemble_words_reason_unknown_is_false():
    """(assemble_words, unknown) -> False."""
    shape = {"stage": "assemble_words", "reason": "unknown"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_staged_audio_invalid_is_false():
    """(asr_recovery, staged_audio_invalid) -> False."""
    shape = {"stage": "asr_recovery", "reason": "staged_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_retained_audio_invalid_is_false():
    """(asr_recovery, retained_audio_invalid) -> False."""
    shape = {"stage": "asr_recovery", "reason": "retained_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_decoded_duration_mismatch_is_false():
    """(asr_recovery, decoded_duration_mismatch) -> False."""
    shape = {"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_word_shape_is_false():
    """(asr_recovery, word_shape) -> False."""
    shape = {"stage": "asr_recovery", "reason": "word_shape"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_word_clock_is_false():
    """(asr_recovery, word_clock) -> False."""
    shape = {"stage": "asr_recovery", "reason": "word_clock"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_word_sequence_is_false():
    """(asr_recovery, word_sequence) -> False."""
    shape = {"stage": "asr_recovery", "reason": "word_sequence"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_vad_nonfinite_is_false():
    """(asr_recovery, vad_nonfinite) -> False."""
    shape = {"stage": "asr_recovery", "reason": "vad_nonfinite"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_vad_order_is_false():
    """(asr_recovery, vad_order) -> False."""
    shape = {"stage": "asr_recovery", "reason": "vad_order"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_vad_bounds_is_false():
    """(asr_recovery, vad_bounds) -> False."""
    shape = {"stage": "asr_recovery", "reason": "vad_bounds"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_empty_asr_is_false():
    """(asr_recovery, empty_asr) -> False."""
    shape = {"stage": "asr_recovery", "reason": "empty_asr"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_no_owned_words_is_false():
    """(asr_recovery, no_owned_words) -> False."""
    shape = {"stage": "asr_recovery", "reason": "no_owned_words"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_unsupported_language_is_false():
    """(asr_recovery, unsupported_language) -> False."""
    shape = {"stage": "asr_recovery", "reason": "unsupported_language"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_outside_admitted_source_is_false():
    """(asr_recovery, outside_admitted_source) -> False."""
    shape = {"stage": "asr_recovery", "reason": "outside_admitted_source"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_asr_recovery_reason_unknown_is_false():
    """(asr_recovery, unknown) -> False."""
    shape = {"stage": "asr_recovery", "reason": "unknown"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_staged_audio_invalid_is_false():
    """(unknown, staged_audio_invalid) -> False."""
    shape = {"stage": "unknown", "reason": "staged_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_retained_audio_invalid_is_false():
    """(unknown, retained_audio_invalid) -> False."""
    shape = {"stage": "unknown", "reason": "retained_audio_invalid"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_decoded_duration_mismatch_is_false():
    """(unknown, decoded_duration_mismatch) -> False."""
    shape = {"stage": "unknown", "reason": "decoded_duration_mismatch"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_word_shape_is_false():
    """(unknown, word_shape) -> False."""
    shape = {"stage": "unknown", "reason": "word_shape"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_word_clock_is_false():
    """(unknown, word_clock) -> False."""
    shape = {"stage": "unknown", "reason": "word_clock"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_word_sequence_is_false():
    """(unknown, word_sequence) -> False."""
    shape = {"stage": "unknown", "reason": "word_sequence"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_vad_nonfinite_is_false():
    """(unknown, vad_nonfinite) -> False."""
    shape = {"stage": "unknown", "reason": "vad_nonfinite"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_vad_order_is_false():
    """(unknown, vad_order) -> False."""
    shape = {"stage": "unknown", "reason": "vad_order"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_vad_bounds_is_false():
    """(unknown, vad_bounds) -> False."""
    shape = {"stage": "unknown", "reason": "vad_bounds"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_empty_asr_is_false():
    """(unknown, empty_asr) -> False."""
    shape = {"stage": "unknown", "reason": "empty_asr"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_no_owned_words_is_false():
    """(unknown, no_owned_words) -> False."""
    shape = {"stage": "unknown", "reason": "no_owned_words"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_unsupported_language_is_false():
    """(unknown, unsupported_language) -> False."""
    shape = {"stage": "unknown", "reason": "unsupported_language"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_outside_admitted_source_is_false():
    """(unknown, outside_admitted_source) -> False."""
    shape = {"stage": "unknown", "reason": "outside_admitted_source"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_stage_unknown_reason_unknown_is_false():
    """(unknown, unknown) -> False."""
    shape = {"stage": "unknown", "reason": "unknown"}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_none_input_is_false():
    assert empty_ladder_recovery_failure(None) is False


def test_predicate_plain_string_is_false():
    assert empty_ladder_recovery_failure("assemble_words") is False


def test_predicate_integer_is_false():
    assert empty_ladder_recovery_failure(42) is False


def test_predicate_empty_list_is_false():
    assert empty_ladder_recovery_failure([]) is False


def test_predicate_key_list_is_false():
    assert empty_ladder_recovery_failure(["stage", "reason"]) is False


def test_predicate_empty_dict_is_false():
    assert empty_ladder_recovery_failure({}) is False


def test_predicate_stage_only_dict_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words"}) is False


def test_predicate_reason_only_dict_is_false():
    assert empty_ladder_recovery_failure({"reason": "empty_asr"}) is False


def test_predicate_extra_field_dict_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words", "reason": "empty_asr", "extra": 1}) is False


def test_predicate_non_string_stage_is_false():
    assert empty_ladder_recovery_failure({"stage": 123, "reason": "empty_asr"}) is False


def test_predicate_non_string_reason_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words", "reason": 123}) is False


def test_predicate_none_stage_is_false():
    assert empty_ladder_recovery_failure({"stage": None, "reason": "empty_asr"}) is False


def test_predicate_none_reason_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words", "reason": None}) is False


def test_predicate_bytes_reason_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words", "reason": b"empty_asr"}) is False


def test_predicate_bytes_stage_is_false():
    assert empty_ladder_recovery_failure({"stage": b"assemble_words", "reason": "empty_asr"}) is False


def test_family_member_empty_asr_is_closed_vocabulary():
    assert "empty_asr" in reason_values(WorkerValidationReason)


def test_family_member_no_owned_words_is_closed_vocabulary():
    assert "no_owned_words" in reason_values(WorkerValidationReason)


def test_family_stage_is_the_ladder_stage_member():
    assert EMPTY_LADDER_RECOVERY_STAGE == WorkerValidationStage.ASSEMBLE_WORDS.value


def test_family_is_disjoint_from_the_guard_set():
    assert EMPTY_LADDER_RECOVERY_REASONS & LANGUAGE_GUARD_REDRIVE_REASONS == frozenset()


def test_family_is_a_frozenset():
    assert isinstance(EMPTY_LADDER_RECOVERY_REASONS, frozenset)


def test_family_frozenset_refuses_growth():
    try:
        EMPTY_LADDER_RECOVERY_REASONS.add("word_shape")
    except AttributeError:
        return
    raise AssertionError("family set must not grow")


def test_empty_asr_rides_the_handoff_with_defaults():
    assert empty_ladder_handoff("empty_asr", recovery_enabled=False, disposition_enabled=False, safety_enabled=True)


def test_no_owned_words_rides_the_handoff_with_defaults():
    assert empty_ladder_handoff(
        "no_owned_words", recovery_enabled=False, disposition_enabled=False, safety_enabled=True
    )


def test_kept_reason_word_shape_never_rides_the_handoff():
    assert not empty_ladder_handoff("word_shape", recovery_enabled=True, disposition_enabled=True, safety_enabled=True)


def test_guard_reason_never_rides_the_empty_handoff():
    assert not empty_ladder_handoff(
        "unsupported_language", recovery_enabled=True, disposition_enabled=True, safety_enabled=True
    )
