# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""The disposition predicate's closed shape, cell-by-cell.

Every (stage, reason) diagnosis the store validators admit is driven through
``validation_disposition_failure`` under both positions of the disposition
switch: the fetch_decode trio answers unconditionally at the stage the typed
classes raise nowhere else, the vad/word verdicts answer under the switch at
any closed stage, and everything else — the deliberately-retryable
admitted-source refusal, the anonymous bucket, the sibling empty-ladder and
language-guard families — keeps its fault classification. Hostile input never
raises and never demotes.
"""

from utils.batch_pipeline.errors import (
    validation_disposition_failure,
)

STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery')
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
TRIO = ('staged_audio_invalid', 'retained_audio_invalid', 'decoded_duration_mismatch')
FLAGGED = ('word_shape', 'word_clock', 'word_sequence', 'vad_nonfinite', 'vad_order', 'vad_bounds')


def test_predicate_fetch_decode_staged_audio_invalid_switch_on():
    """(fetch_decode, staged_audio_invalid) under switch on expects True."""
    assert (
        validation_disposition_failure(
            {"stage": "fetch_decode", "reason": "staged_audio_invalid"}, disposition_enabled=True
        )
        is True
    )


def test_predicate_fetch_decode_staged_audio_invalid_switch_off():
    """(fetch_decode, staged_audio_invalid) under switch off expects True."""
    assert (
        validation_disposition_failure(
            {"stage": "fetch_decode", "reason": "staged_audio_invalid"}, disposition_enabled=False
        )
        is True
    )


def test_predicate_fetch_decode_retained_audio_invalid_switch_on():
    """(fetch_decode, retained_audio_invalid) under switch on expects True."""
    assert (
        validation_disposition_failure(
            {"stage": "fetch_decode", "reason": "retained_audio_invalid"}, disposition_enabled=True
        )
        is True
    )


def test_predicate_fetch_decode_retained_audio_invalid_switch_off():
    """(fetch_decode, retained_audio_invalid) under switch off expects True."""
    assert (
        validation_disposition_failure(
            {"stage": "fetch_decode", "reason": "retained_audio_invalid"}, disposition_enabled=False
        )
        is True
    )


def test_predicate_fetch_decode_decoded_duration_mismatch_switch_on():
    """(fetch_decode, decoded_duration_mismatch) under switch on expects True."""
    assert (
        validation_disposition_failure(
            {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}, disposition_enabled=True
        )
        is True
    )


def test_predicate_fetch_decode_decoded_duration_mismatch_switch_off():
    """(fetch_decode, decoded_duration_mismatch) under switch off expects True."""
    assert (
        validation_disposition_failure(
            {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}, disposition_enabled=False
        )
        is True
    )


def test_predicate_fetch_decode_word_shape_switch_on():
    """(fetch_decode, word_shape) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "word_shape"}, disposition_enabled=True)
        is True
    )


def test_predicate_fetch_decode_word_shape_switch_off():
    """(fetch_decode, word_shape) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "word_shape"}, disposition_enabled=False)
        is False
    )


def test_predicate_fetch_decode_word_clock_switch_on():
    """(fetch_decode, word_clock) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "word_clock"}, disposition_enabled=True)
        is True
    )


def test_predicate_fetch_decode_word_clock_switch_off():
    """(fetch_decode, word_clock) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "word_clock"}, disposition_enabled=False)
        is False
    )


def test_predicate_fetch_decode_word_sequence_switch_on():
    """(fetch_decode, word_sequence) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "word_sequence"}, disposition_enabled=True)
        is True
    )


def test_predicate_fetch_decode_word_sequence_switch_off():
    """(fetch_decode, word_sequence) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "word_sequence"}, disposition_enabled=False)
        is False
    )


def test_predicate_fetch_decode_vad_nonfinite_switch_on():
    """(fetch_decode, vad_nonfinite) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "vad_nonfinite"}, disposition_enabled=True)
        is True
    )


def test_predicate_fetch_decode_vad_nonfinite_switch_off():
    """(fetch_decode, vad_nonfinite) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "vad_nonfinite"}, disposition_enabled=False)
        is False
    )


def test_predicate_fetch_decode_vad_order_switch_on():
    """(fetch_decode, vad_order) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "vad_order"}, disposition_enabled=True)
        is True
    )


def test_predicate_fetch_decode_vad_order_switch_off():
    """(fetch_decode, vad_order) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "vad_order"}, disposition_enabled=False)
        is False
    )


def test_predicate_fetch_decode_vad_bounds_switch_on():
    """(fetch_decode, vad_bounds) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "vad_bounds"}, disposition_enabled=True)
        is True
    )


def test_predicate_fetch_decode_vad_bounds_switch_off():
    """(fetch_decode, vad_bounds) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "vad_bounds"}, disposition_enabled=False)
        is False
    )


def test_predicate_fetch_decode_empty_asr_switch_on():
    """(fetch_decode, empty_asr) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "empty_asr"}, disposition_enabled=True)
        is False
    )


def test_predicate_fetch_decode_empty_asr_switch_off():
    """(fetch_decode, empty_asr) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "empty_asr"}, disposition_enabled=False)
        is False
    )


def test_predicate_fetch_decode_no_owned_words_switch_on():
    """(fetch_decode, no_owned_words) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "no_owned_words"}, disposition_enabled=True)
        is False
    )


def test_predicate_fetch_decode_no_owned_words_switch_off():
    """(fetch_decode, no_owned_words) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "no_owned_words"}, disposition_enabled=False)
        is False
    )


def test_predicate_fetch_decode_unsupported_language_switch_on():
    """(fetch_decode, unsupported_language) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "fetch_decode", "reason": "unsupported_language"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_fetch_decode_unsupported_language_switch_off():
    """(fetch_decode, unsupported_language) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "fetch_decode", "reason": "unsupported_language"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_fetch_decode_outside_admitted_source_switch_on():
    """(fetch_decode, outside_admitted_source) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "fetch_decode", "reason": "outside_admitted_source"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_fetch_decode_outside_admitted_source_switch_off():
    """(fetch_decode, outside_admitted_source) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "fetch_decode", "reason": "outside_admitted_source"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_fetch_decode_unknown_switch_on():
    """(fetch_decode, unknown) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "unknown"}, disposition_enabled=True)
        is False
    )


def test_predicate_fetch_decode_unknown_switch_off():
    """(fetch_decode, unknown) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "fetch_decode", "reason": "unknown"}, disposition_enabled=False)
        is False
    )


def test_predicate_vad_windows_staged_audio_invalid_switch_on():
    """(vad_windows, staged_audio_invalid) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "staged_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_vad_windows_staged_audio_invalid_switch_off():
    """(vad_windows, staged_audio_invalid) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "staged_audio_invalid"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_vad_windows_retained_audio_invalid_switch_on():
    """(vad_windows, retained_audio_invalid) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "retained_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_vad_windows_retained_audio_invalid_switch_off():
    """(vad_windows, retained_audio_invalid) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "retained_audio_invalid"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_vad_windows_decoded_duration_mismatch_switch_on():
    """(vad_windows, decoded_duration_mismatch) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_vad_windows_decoded_duration_mismatch_switch_off():
    """(vad_windows, decoded_duration_mismatch) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_vad_windows_word_shape_switch_on():
    """(vad_windows, word_shape) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "word_shape"}, disposition_enabled=True)
        is True
    )


def test_predicate_vad_windows_word_shape_switch_off():
    """(vad_windows, word_shape) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "word_shape"}, disposition_enabled=False)
        is False
    )


def test_predicate_vad_windows_word_clock_switch_on():
    """(vad_windows, word_clock) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "word_clock"}, disposition_enabled=True)
        is True
    )


def test_predicate_vad_windows_word_clock_switch_off():
    """(vad_windows, word_clock) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "word_clock"}, disposition_enabled=False)
        is False
    )


def test_predicate_vad_windows_word_sequence_switch_on():
    """(vad_windows, word_sequence) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "word_sequence"}, disposition_enabled=True)
        is True
    )


def test_predicate_vad_windows_word_sequence_switch_off():
    """(vad_windows, word_sequence) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "word_sequence"}, disposition_enabled=False)
        is False
    )


def test_predicate_vad_windows_vad_nonfinite_switch_on():
    """(vad_windows, vad_nonfinite) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "vad_nonfinite"}, disposition_enabled=True)
        is True
    )


def test_predicate_vad_windows_vad_nonfinite_switch_off():
    """(vad_windows, vad_nonfinite) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "vad_nonfinite"}, disposition_enabled=False)
        is False
    )


def test_predicate_vad_windows_vad_order_switch_on():
    """(vad_windows, vad_order) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "vad_order"}, disposition_enabled=True)
        is True
    )


def test_predicate_vad_windows_vad_order_switch_off():
    """(vad_windows, vad_order) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "vad_order"}, disposition_enabled=False)
        is False
    )


def test_predicate_vad_windows_vad_bounds_switch_on():
    """(vad_windows, vad_bounds) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "vad_bounds"}, disposition_enabled=True)
        is True
    )


def test_predicate_vad_windows_vad_bounds_switch_off():
    """(vad_windows, vad_bounds) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "vad_bounds"}, disposition_enabled=False)
        is False
    )


def test_predicate_vad_windows_empty_asr_switch_on():
    """(vad_windows, empty_asr) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "empty_asr"}, disposition_enabled=True)
        is False
    )


def test_predicate_vad_windows_empty_asr_switch_off():
    """(vad_windows, empty_asr) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "empty_asr"}, disposition_enabled=False)
        is False
    )


def test_predicate_vad_windows_no_owned_words_switch_on():
    """(vad_windows, no_owned_words) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "no_owned_words"}, disposition_enabled=True)
        is False
    )


def test_predicate_vad_windows_no_owned_words_switch_off():
    """(vad_windows, no_owned_words) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "no_owned_words"}, disposition_enabled=False)
        is False
    )


def test_predicate_vad_windows_unsupported_language_switch_on():
    """(vad_windows, unsupported_language) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "unsupported_language"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_vad_windows_unsupported_language_switch_off():
    """(vad_windows, unsupported_language) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "unsupported_language"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_vad_windows_outside_admitted_source_switch_on():
    """(vad_windows, outside_admitted_source) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "outside_admitted_source"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_vad_windows_outside_admitted_source_switch_off():
    """(vad_windows, outside_admitted_source) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "vad_windows", "reason": "outside_admitted_source"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_vad_windows_unknown_switch_on():
    """(vad_windows, unknown) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "unknown"}, disposition_enabled=True) is False
    )


def test_predicate_vad_windows_unknown_switch_off():
    """(vad_windows, unknown) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "vad_windows", "reason": "unknown"}, disposition_enabled=False)
        is False
    )


def test_predicate_word_clocks_staged_audio_invalid_switch_on():
    """(word_clocks, staged_audio_invalid) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "staged_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_word_clocks_staged_audio_invalid_switch_off():
    """(word_clocks, staged_audio_invalid) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "staged_audio_invalid"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_word_clocks_retained_audio_invalid_switch_on():
    """(word_clocks, retained_audio_invalid) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "retained_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_word_clocks_retained_audio_invalid_switch_off():
    """(word_clocks, retained_audio_invalid) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "retained_audio_invalid"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_word_clocks_decoded_duration_mismatch_switch_on():
    """(word_clocks, decoded_duration_mismatch) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_word_clocks_decoded_duration_mismatch_switch_off():
    """(word_clocks, decoded_duration_mismatch) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_word_clocks_word_shape_switch_on():
    """(word_clocks, word_shape) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "word_shape"}, disposition_enabled=True)
        is True
    )


def test_predicate_word_clocks_word_shape_switch_off():
    """(word_clocks, word_shape) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "word_shape"}, disposition_enabled=False)
        is False
    )


def test_predicate_word_clocks_word_clock_switch_on():
    """(word_clocks, word_clock) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "word_clock"}, disposition_enabled=True)
        is True
    )


def test_predicate_word_clocks_word_clock_switch_off():
    """(word_clocks, word_clock) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "word_clock"}, disposition_enabled=False)
        is False
    )


def test_predicate_word_clocks_word_sequence_switch_on():
    """(word_clocks, word_sequence) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "word_sequence"}, disposition_enabled=True)
        is True
    )


def test_predicate_word_clocks_word_sequence_switch_off():
    """(word_clocks, word_sequence) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "word_sequence"}, disposition_enabled=False)
        is False
    )


def test_predicate_word_clocks_vad_nonfinite_switch_on():
    """(word_clocks, vad_nonfinite) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "vad_nonfinite"}, disposition_enabled=True)
        is True
    )


def test_predicate_word_clocks_vad_nonfinite_switch_off():
    """(word_clocks, vad_nonfinite) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "vad_nonfinite"}, disposition_enabled=False)
        is False
    )


def test_predicate_word_clocks_vad_order_switch_on():
    """(word_clocks, vad_order) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "vad_order"}, disposition_enabled=True)
        is True
    )


def test_predicate_word_clocks_vad_order_switch_off():
    """(word_clocks, vad_order) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "vad_order"}, disposition_enabled=False)
        is False
    )


def test_predicate_word_clocks_vad_bounds_switch_on():
    """(word_clocks, vad_bounds) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "vad_bounds"}, disposition_enabled=True)
        is True
    )


def test_predicate_word_clocks_vad_bounds_switch_off():
    """(word_clocks, vad_bounds) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "vad_bounds"}, disposition_enabled=False)
        is False
    )


def test_predicate_word_clocks_empty_asr_switch_on():
    """(word_clocks, empty_asr) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "empty_asr"}, disposition_enabled=True)
        is False
    )


def test_predicate_word_clocks_empty_asr_switch_off():
    """(word_clocks, empty_asr) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "empty_asr"}, disposition_enabled=False)
        is False
    )


def test_predicate_word_clocks_no_owned_words_switch_on():
    """(word_clocks, no_owned_words) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "no_owned_words"}, disposition_enabled=True)
        is False
    )


def test_predicate_word_clocks_no_owned_words_switch_off():
    """(word_clocks, no_owned_words) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "no_owned_words"}, disposition_enabled=False)
        is False
    )


def test_predicate_word_clocks_unsupported_language_switch_on():
    """(word_clocks, unsupported_language) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "unsupported_language"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_word_clocks_unsupported_language_switch_off():
    """(word_clocks, unsupported_language) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "unsupported_language"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_word_clocks_outside_admitted_source_switch_on():
    """(word_clocks, outside_admitted_source) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "outside_admitted_source"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_word_clocks_outside_admitted_source_switch_off():
    """(word_clocks, outside_admitted_source) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "word_clocks", "reason": "outside_admitted_source"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_word_clocks_unknown_switch_on():
    """(word_clocks, unknown) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "unknown"}, disposition_enabled=True) is False
    )


def test_predicate_word_clocks_unknown_switch_off():
    """(word_clocks, unknown) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "word_clocks", "reason": "unknown"}, disposition_enabled=False)
        is False
    )


def test_predicate_assemble_words_staged_audio_invalid_switch_on():
    """(assemble_words, staged_audio_invalid) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "staged_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_assemble_words_staged_audio_invalid_switch_off():
    """(assemble_words, staged_audio_invalid) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "staged_audio_invalid"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_assemble_words_retained_audio_invalid_switch_on():
    """(assemble_words, retained_audio_invalid) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "retained_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_assemble_words_retained_audio_invalid_switch_off():
    """(assemble_words, retained_audio_invalid) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "retained_audio_invalid"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_assemble_words_decoded_duration_mismatch_switch_on():
    """(assemble_words, decoded_duration_mismatch) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "decoded_duration_mismatch"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_assemble_words_decoded_duration_mismatch_switch_off():
    """(assemble_words, decoded_duration_mismatch) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "decoded_duration_mismatch"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_assemble_words_word_shape_switch_on():
    """(assemble_words, word_shape) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "word_shape"}, disposition_enabled=True)
        is True
    )


def test_predicate_assemble_words_word_shape_switch_off():
    """(assemble_words, word_shape) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "word_shape"}, disposition_enabled=False)
        is False
    )


def test_predicate_assemble_words_word_clock_switch_on():
    """(assemble_words, word_clock) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "word_clock"}, disposition_enabled=True)
        is True
    )


def test_predicate_assemble_words_word_clock_switch_off():
    """(assemble_words, word_clock) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "word_clock"}, disposition_enabled=False)
        is False
    )


def test_predicate_assemble_words_word_sequence_switch_on():
    """(assemble_words, word_sequence) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "word_sequence"}, disposition_enabled=True)
        is True
    )


def test_predicate_assemble_words_word_sequence_switch_off():
    """(assemble_words, word_sequence) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "word_sequence"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_assemble_words_vad_nonfinite_switch_on():
    """(assemble_words, vad_nonfinite) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "vad_nonfinite"}, disposition_enabled=True)
        is True
    )


def test_predicate_assemble_words_vad_nonfinite_switch_off():
    """(assemble_words, vad_nonfinite) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "vad_nonfinite"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_assemble_words_vad_order_switch_on():
    """(assemble_words, vad_order) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "vad_order"}, disposition_enabled=True)
        is True
    )


def test_predicate_assemble_words_vad_order_switch_off():
    """(assemble_words, vad_order) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "vad_order"}, disposition_enabled=False)
        is False
    )


def test_predicate_assemble_words_vad_bounds_switch_on():
    """(assemble_words, vad_bounds) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "vad_bounds"}, disposition_enabled=True)
        is True
    )


def test_predicate_assemble_words_vad_bounds_switch_off():
    """(assemble_words, vad_bounds) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "vad_bounds"}, disposition_enabled=False)
        is False
    )


def test_predicate_assemble_words_empty_asr_switch_on():
    """(assemble_words, empty_asr) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "empty_asr"}, disposition_enabled=True)
        is False
    )


def test_predicate_assemble_words_empty_asr_switch_off():
    """(assemble_words, empty_asr) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "empty_asr"}, disposition_enabled=False)
        is False
    )


def test_predicate_assemble_words_no_owned_words_switch_on():
    """(assemble_words, no_owned_words) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "no_owned_words"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_assemble_words_no_owned_words_switch_off():
    """(assemble_words, no_owned_words) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "no_owned_words"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_assemble_words_unsupported_language_switch_on():
    """(assemble_words, unsupported_language) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "unsupported_language"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_assemble_words_unsupported_language_switch_off():
    """(assemble_words, unsupported_language) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "unsupported_language"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_assemble_words_outside_admitted_source_switch_on():
    """(assemble_words, outside_admitted_source) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "outside_admitted_source"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_assemble_words_outside_admitted_source_switch_off():
    """(assemble_words, outside_admitted_source) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "assemble_words", "reason": "outside_admitted_source"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_assemble_words_unknown_switch_on():
    """(assemble_words, unknown) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "unknown"}, disposition_enabled=True)
        is False
    )


def test_predicate_assemble_words_unknown_switch_off():
    """(assemble_words, unknown) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "assemble_words", "reason": "unknown"}, disposition_enabled=False)
        is False
    )


def test_predicate_asr_recovery_staged_audio_invalid_switch_on():
    """(asr_recovery, staged_audio_invalid) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "staged_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_asr_recovery_staged_audio_invalid_switch_off():
    """(asr_recovery, staged_audio_invalid) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "staged_audio_invalid"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_asr_recovery_retained_audio_invalid_switch_on():
    """(asr_recovery, retained_audio_invalid) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "retained_audio_invalid"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_asr_recovery_retained_audio_invalid_switch_off():
    """(asr_recovery, retained_audio_invalid) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "retained_audio_invalid"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_asr_recovery_decoded_duration_mismatch_switch_on():
    """(asr_recovery, decoded_duration_mismatch) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_asr_recovery_decoded_duration_mismatch_switch_off():
    """(asr_recovery, decoded_duration_mismatch) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_asr_recovery_word_shape_switch_on():
    """(asr_recovery, word_shape) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "word_shape"}, disposition_enabled=True)
        is True
    )


def test_predicate_asr_recovery_word_shape_switch_off():
    """(asr_recovery, word_shape) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "word_shape"}, disposition_enabled=False)
        is False
    )


def test_predicate_asr_recovery_word_clock_switch_on():
    """(asr_recovery, word_clock) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "word_clock"}, disposition_enabled=True)
        is True
    )


def test_predicate_asr_recovery_word_clock_switch_off():
    """(asr_recovery, word_clock) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "word_clock"}, disposition_enabled=False)
        is False
    )


def test_predicate_asr_recovery_word_sequence_switch_on():
    """(asr_recovery, word_sequence) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "word_sequence"}, disposition_enabled=True)
        is True
    )


def test_predicate_asr_recovery_word_sequence_switch_off():
    """(asr_recovery, word_sequence) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "word_sequence"}, disposition_enabled=False)
        is False
    )


def test_predicate_asr_recovery_vad_nonfinite_switch_on():
    """(asr_recovery, vad_nonfinite) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "vad_nonfinite"}, disposition_enabled=True)
        is True
    )


def test_predicate_asr_recovery_vad_nonfinite_switch_off():
    """(asr_recovery, vad_nonfinite) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "vad_nonfinite"}, disposition_enabled=False)
        is False
    )


def test_predicate_asr_recovery_vad_order_switch_on():
    """(asr_recovery, vad_order) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "vad_order"}, disposition_enabled=True)
        is True
    )


def test_predicate_asr_recovery_vad_order_switch_off():
    """(asr_recovery, vad_order) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "vad_order"}, disposition_enabled=False)
        is False
    )


def test_predicate_asr_recovery_vad_bounds_switch_on():
    """(asr_recovery, vad_bounds) under switch on expects True."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "vad_bounds"}, disposition_enabled=True)
        is True
    )


def test_predicate_asr_recovery_vad_bounds_switch_off():
    """(asr_recovery, vad_bounds) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "vad_bounds"}, disposition_enabled=False)
        is False
    )


def test_predicate_asr_recovery_empty_asr_switch_on():
    """(asr_recovery, empty_asr) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "empty_asr"}, disposition_enabled=True)
        is False
    )


def test_predicate_asr_recovery_empty_asr_switch_off():
    """(asr_recovery, empty_asr) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "empty_asr"}, disposition_enabled=False)
        is False
    )


def test_predicate_asr_recovery_no_owned_words_switch_on():
    """(asr_recovery, no_owned_words) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "no_owned_words"}, disposition_enabled=True)
        is False
    )


def test_predicate_asr_recovery_no_owned_words_switch_off():
    """(asr_recovery, no_owned_words) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "no_owned_words"}, disposition_enabled=False)
        is False
    )


def test_predicate_asr_recovery_unsupported_language_switch_on():
    """(asr_recovery, unsupported_language) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "unsupported_language"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_asr_recovery_unsupported_language_switch_off():
    """(asr_recovery, unsupported_language) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "unsupported_language"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_asr_recovery_outside_admitted_source_switch_on():
    """(asr_recovery, outside_admitted_source) under switch on expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "outside_admitted_source"}, disposition_enabled=True
        )
        is False
    )


def test_predicate_asr_recovery_outside_admitted_source_switch_off():
    """(asr_recovery, outside_admitted_source) under switch off expects False."""
    assert (
        validation_disposition_failure(
            {"stage": "asr_recovery", "reason": "outside_admitted_source"}, disposition_enabled=False
        )
        is False
    )


def test_predicate_asr_recovery_unknown_switch_on():
    """(asr_recovery, unknown) under switch on expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "unknown"}, disposition_enabled=True)
        is False
    )


def test_predicate_asr_recovery_unknown_switch_off():
    """(asr_recovery, unknown) under switch off expects False."""
    assert (
        validation_disposition_failure({"stage": "asr_recovery", "reason": "unknown"}, disposition_enabled=False)
        is False
    )


def test_predicate_hostile_none_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'none' demotes under neither switch position."""
    failure = None
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_empty_dict_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'empty_dict' demotes under neither switch position."""
    failure = {}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_list_shape_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'list_shape' demotes under neither switch position."""
    failure = ['fetch_decode', 'staged_audio_invalid']
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_string_shape_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'string_shape' demotes under neither switch position."""
    failure = 'fetch_decode'
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_int_shape_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'int_shape' demotes under neither switch position."""
    failure = 7
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_extra_field_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'extra_field' demotes under neither switch position."""
    failure = {"stage": "fetch_decode", "reason": "staged_audio_invalid", "site": "audio.py"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_missing_reason_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'missing_reason' demotes under neither switch position."""
    failure = {"stage": "fetch_decode"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_missing_stage_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'missing_stage' demotes under neither switch position."""
    failure = {"reason": "staged_audio_invalid"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_non_str_stage_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'non_str_stage' demotes under neither switch position."""
    failure = {"stage": 7, "reason": "staged_audio_invalid"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_non_str_reason_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'non_str_reason' demotes under neither switch position."""
    failure = {"stage": "fetch_decode", "reason": 7}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_bool_stage_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'bool_stage' demotes under neither switch position."""
    failure = {"stage": True, "reason": "staged_audio_invalid"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_bool_reason_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'bool_reason' demotes under neither switch position."""
    failure = {"stage": "fetch_decode", "reason": False}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_none_stage_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'none_stage' demotes under neither switch position."""
    failure = {"stage": None, "reason": "staged_audio_invalid"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_none_reason_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'none_reason' demotes under neither switch position."""
    failure = {"stage": "fetch_decode", "reason": None}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_unicode_stage_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'unicode_stage' demotes under neither switch position."""
    failure = {"stage": "fetch_dec\u00f6de", "reason": "staged_audio_invalid"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_unicode_reason_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'unicode_reason' demotes under neither switch position."""
    failure = {"stage": "fetch_decode", "reason": "staged_audio_invalid\u0301"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_upper_stage_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'upper_stage' demotes under neither switch position."""
    failure = {"stage": "FETCH_DECODE", "reason": "staged_audio_invalid"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_upper_reason_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'upper_reason' demotes under neither switch position."""
    failure = {"stage": "fetch_decode", "reason": "STAGED_AUDIO_INVALID"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_whitespace_stage_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'whitespace_stage' demotes under neither switch position."""
    failure = {"stage": " fetch_decode", "reason": "staged_audio_invalid"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_whitespace_reason_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'whitespace_reason' demotes under neither switch position."""
    failure = {"stage": "fetch_decode", "reason": "staged_audio_invalid "}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_plural_reason_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'plural_reason' demotes under neither switch position."""
    failure = {"stage": "fetch_decode", "reason": "staged_audio_invalids"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_foreign_reason_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'foreign_reason' demotes under neither switch position."""
    failure = {"stage": "fetch_decode", "reason": "totally_unknown_token"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_nested_stage_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'nested_stage' demotes under neither switch position."""
    failure = {"stage": {"k": "fetch_decode"}, "reason": "staged_audio_invalid"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_nested_reason_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'nested_reason' demotes under neither switch position."""
    failure = {"stage": "fetch_decode", "reason": ["staged_audio_invalid"]}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False


def test_predicate_hostile_tuple_shape_keeps_fault_classification_under_both_switch_positions():
    """Hostile shape 'tuple_shape' demotes under neither switch position."""
    failure = {"stage": ("fetch_decode",), "reason": "staged_audio_invalid"}
    assert validation_disposition_failure(failure, disposition_enabled=True) is False
    assert validation_disposition_failure(failure, disposition_enabled=False) is False
