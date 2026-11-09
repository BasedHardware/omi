"""Generated grid: the closed demotion predicates over their full vocabulary.

Every (stage, reason, switch) cell pins the exact bool the REAL predicates answer,
so any future vocabulary move shows up as the moved cells in the diff.

Failure-Class: FC-permanent-retained-decode-failure-burns-retry-ladder
"""

import pytest

from utils.batch_pipeline.errors import (
    empty_ladder_recovery_failure,
    language_guard_redrive_failure,
    validation_disposition_failure,
    validate_worker_failure,
    validate_worker_failure_evidence,
    WORKER_VALIDATION_REASON_TOKENS,
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
)


def test_disposition_on_asr_recovery_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_asr_recovery_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_asr_recovery_decoded_duration_mismatch():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}) is False


def test_language_guard_asr_recovery_decoded_duration_mismatch():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}) is False


def test_disposition_on_asr_recovery_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_asr_recovery_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_asr_recovery_empty_asr():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}) is False


def test_language_guard_asr_recovery_empty_asr():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'}) is False


def test_disposition_on_asr_recovery_no_owned_words():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_asr_recovery_no_owned_words():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_asr_recovery_no_owned_words():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}) is False


def test_language_guard_asr_recovery_no_owned_words():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'no_owned_words'}) is False


def test_disposition_on_asr_recovery_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_asr_recovery_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_asr_recovery_outside_admitted_source():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}) is False


def test_language_guard_asr_recovery_outside_admitted_source():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}) is False


def test_disposition_on_asr_recovery_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_asr_recovery_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_asr_recovery_retained_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}) is False


def test_language_guard_asr_recovery_retained_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}) is False


def test_disposition_on_asr_recovery_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_asr_recovery_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_asr_recovery_staged_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}) is False


def test_language_guard_asr_recovery_staged_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}) is False


def test_disposition_on_asr_recovery_unknown():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_asr_recovery_unknown():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_asr_recovery_unknown():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'unknown'}) is False


def test_language_guard_asr_recovery_unknown():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'unknown'}) is False


def test_disposition_on_asr_recovery_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_asr_recovery_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'asr_recovery', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_asr_recovery_unsupported_language():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'unsupported_language'}) is False


def test_language_guard_asr_recovery_unsupported_language():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'unsupported_language'}) is True


def test_disposition_on_asr_recovery_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_asr_recovery_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_asr_recovery_vad_bounds():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}) is False


def test_language_guard_asr_recovery_vad_bounds():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'vad_bounds'}) is False


def test_disposition_on_asr_recovery_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_asr_recovery_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_asr_recovery_vad_nonfinite():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}) is False


def test_language_guard_asr_recovery_vad_nonfinite():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}) is False


def test_disposition_on_asr_recovery_vad_order():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_asr_recovery_vad_order():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_asr_recovery_vad_order():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}) is False


def test_language_guard_asr_recovery_vad_order():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'vad_order'}) is False


def test_disposition_on_asr_recovery_word_clock():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_asr_recovery_word_clock():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_asr_recovery_word_clock():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}) is False


def test_language_guard_asr_recovery_word_clock():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'word_clock'}) is False


def test_disposition_on_asr_recovery_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_asr_recovery_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_asr_recovery_word_sequence():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}) is False


def test_language_guard_asr_recovery_word_sequence():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'word_sequence'}) is False


def test_disposition_on_asr_recovery_word_shape():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_asr_recovery_word_shape():
    assert (
        validation_disposition_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_asr_recovery_word_shape():
    assert empty_ladder_recovery_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}) is False


def test_language_guard_asr_recovery_word_shape():
    assert language_guard_redrive_failure({'stage': 'asr_recovery', 'reason': 'word_shape'}) is False


def test_disposition_on_assemble_words_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_assemble_words_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_assemble_words_decoded_duration_mismatch():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}) is False


def test_language_guard_assemble_words_decoded_duration_mismatch():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}) is False


def test_disposition_on_assemble_words_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_assemble_words_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_assemble_words_empty_asr():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}) is True


def test_language_guard_assemble_words_empty_asr():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'empty_asr'}) is False


def test_disposition_on_assemble_words_no_owned_words():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'no_owned_words'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_assemble_words_no_owned_words():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'no_owned_words'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_assemble_words_no_owned_words():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'no_owned_words'}) is True


def test_language_guard_assemble_words_no_owned_words():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'no_owned_words'}) is False


def test_disposition_on_assemble_words_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_assemble_words_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_assemble_words_outside_admitted_source():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'outside_admitted_source'}) is False


def test_language_guard_assemble_words_outside_admitted_source():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'outside_admitted_source'}) is False


def test_disposition_on_assemble_words_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_assemble_words_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_assemble_words_retained_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}) is False


def test_language_guard_assemble_words_retained_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}) is False


def test_disposition_on_assemble_words_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_assemble_words_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_assemble_words_staged_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}) is False


def test_language_guard_assemble_words_staged_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}) is False


def test_disposition_on_assemble_words_unknown():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_assemble_words_unknown():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_assemble_words_unknown():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'unknown'}) is False


def test_language_guard_assemble_words_unknown():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'unknown'}) is False


def test_disposition_on_assemble_words_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_assemble_words_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_assemble_words_unsupported_language():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'unsupported_language'}) is False


def test_language_guard_assemble_words_unsupported_language():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'unsupported_language'}) is True


def test_disposition_on_assemble_words_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_assemble_words_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_assemble_words_vad_bounds():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}) is False


def test_language_guard_assemble_words_vad_bounds():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'vad_bounds'}) is False


def test_disposition_on_assemble_words_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_assemble_words_vad_nonfinite():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'vad_nonfinite'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_assemble_words_vad_nonfinite():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}) is False


def test_language_guard_assemble_words_vad_nonfinite():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'vad_nonfinite'}) is False


def test_disposition_on_assemble_words_vad_order():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_assemble_words_vad_order():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_assemble_words_vad_order():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'vad_order'}) is False


def test_language_guard_assemble_words_vad_order():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'vad_order'}) is False


def test_disposition_on_assemble_words_word_clock():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_assemble_words_word_clock():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_assemble_words_word_clock():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'word_clock'}) is False


def test_language_guard_assemble_words_word_clock():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'word_clock'}) is False


def test_disposition_on_assemble_words_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_assemble_words_word_sequence():
    assert (
        validation_disposition_failure(
            {'stage': 'assemble_words', 'reason': 'word_sequence'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_assemble_words_word_sequence():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'word_sequence'}) is False


def test_language_guard_assemble_words_word_sequence():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'word_sequence'}) is False


def test_disposition_on_assemble_words_word_shape():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_assemble_words_word_shape():
    assert (
        validation_disposition_failure({'stage': 'assemble_words', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_assemble_words_word_shape():
    assert empty_ladder_recovery_failure({'stage': 'assemble_words', 'reason': 'word_shape'}) is False


def test_language_guard_assemble_words_word_shape():
    assert language_guard_redrive_failure({'stage': 'assemble_words', 'reason': 'word_shape'}) is False


def test_disposition_on_fetch_decode_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is True
    )


def test_disposition_off_fetch_decode_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is True
    )


def test_empty_ladder_fetch_decode_decoded_duration_mismatch():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}) is False


def test_language_guard_fetch_decode_decoded_duration_mismatch():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}) is False


def test_disposition_on_fetch_decode_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_fetch_decode_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_fetch_decode_empty_asr():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}) is False


def test_language_guard_fetch_decode_empty_asr():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'empty_asr'}) is False


def test_disposition_on_fetch_decode_no_owned_words():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_fetch_decode_no_owned_words():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_fetch_decode_no_owned_words():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}) is False


def test_language_guard_fetch_decode_no_owned_words():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'no_owned_words'}) is False


def test_disposition_on_fetch_decode_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_fetch_decode_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_fetch_decode_outside_admitted_source():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}) is False


def test_language_guard_fetch_decode_outside_admitted_source():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}) is False


def test_disposition_on_fetch_decode_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_disposition_off_fetch_decode_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_empty_ladder_fetch_decode_retained_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}) is False


def test_language_guard_fetch_decode_retained_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}) is False


def test_disposition_on_fetch_decode_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is True
    )


def test_disposition_off_fetch_decode_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is True
    )


def test_empty_ladder_fetch_decode_staged_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}) is False


def test_language_guard_fetch_decode_staged_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}) is False


def test_disposition_on_fetch_decode_unknown():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'unknown'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_fetch_decode_unknown():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_fetch_decode_unknown():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'unknown'}) is False


def test_language_guard_fetch_decode_unknown():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'unknown'}) is False


def test_disposition_on_fetch_decode_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_fetch_decode_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_fetch_decode_unsupported_language():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'unsupported_language'}) is False


def test_language_guard_fetch_decode_unsupported_language():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'unsupported_language'}) is True


def test_disposition_on_fetch_decode_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_fetch_decode_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_fetch_decode_vad_bounds():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}) is False


def test_language_guard_fetch_decode_vad_bounds():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'vad_bounds'}) is False


def test_disposition_on_fetch_decode_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_fetch_decode_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_fetch_decode_vad_nonfinite():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}) is False


def test_language_guard_fetch_decode_vad_nonfinite():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}) is False


def test_disposition_on_fetch_decode_vad_order():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_fetch_decode_vad_order():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_fetch_decode_vad_order():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}) is False


def test_language_guard_fetch_decode_vad_order():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'vad_order'}) is False


def test_disposition_on_fetch_decode_word_clock():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_fetch_decode_word_clock():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_fetch_decode_word_clock():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}) is False


def test_language_guard_fetch_decode_word_clock():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'word_clock'}) is False


def test_disposition_on_fetch_decode_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_fetch_decode_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_fetch_decode_word_sequence():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}) is False


def test_language_guard_fetch_decode_word_sequence():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'word_sequence'}) is False


def test_disposition_on_fetch_decode_word_shape():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_fetch_decode_word_shape():
    assert (
        validation_disposition_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_fetch_decode_word_shape():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}) is False


def test_language_guard_fetch_decode_word_shape():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'word_shape'}) is False


def test_disposition_on_unknown_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'unknown', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_unknown_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'unknown', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_unknown_decoded_duration_mismatch():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'decoded_duration_mismatch'}) is False


def test_language_guard_unknown_decoded_duration_mismatch():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'decoded_duration_mismatch'}) is False


def test_disposition_on_unknown_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'empty_asr'}, disposition_enabled=True) is False
    )


def test_disposition_off_unknown_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'empty_asr'}, disposition_enabled=False) is False
    )


def test_empty_ladder_unknown_empty_asr():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'empty_asr'}) is False


def test_language_guard_unknown_empty_asr():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'empty_asr'}) is False


def test_disposition_on_unknown_no_owned_words():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_unknown_no_owned_words():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_unknown_no_owned_words():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'no_owned_words'}) is False


def test_language_guard_unknown_no_owned_words():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'no_owned_words'}) is False


def test_disposition_on_unknown_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'unknown', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_unknown_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'unknown', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_unknown_outside_admitted_source():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'outside_admitted_source'}) is False


def test_language_guard_unknown_outside_admitted_source():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'outside_admitted_source'}) is False


def test_disposition_on_unknown_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'unknown', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_unknown_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'unknown', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_unknown_retained_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'retained_audio_invalid'}) is False


def test_language_guard_unknown_retained_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'retained_audio_invalid'}) is False


def test_disposition_on_unknown_staged_audio_invalid():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'staged_audio_invalid'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_unknown_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'unknown', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_unknown_staged_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'staged_audio_invalid'}) is False


def test_language_guard_unknown_staged_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'staged_audio_invalid'}) is False


def test_disposition_on_unknown_unknown():
    assert validation_disposition_failure({'stage': 'unknown', 'reason': 'unknown'}, disposition_enabled=True) is False


def test_disposition_off_unknown_unknown():
    assert validation_disposition_failure({'stage': 'unknown', 'reason': 'unknown'}, disposition_enabled=False) is False


def test_empty_ladder_unknown_unknown():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'unknown'}) is False


def test_language_guard_unknown_unknown():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'unknown'}) is False


def test_disposition_on_unknown_unsupported_language():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'unsupported_language'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_unknown_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'unknown', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_unknown_unsupported_language():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'unsupported_language'}) is False


def test_language_guard_unknown_unsupported_language():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'unsupported_language'}) is False


def test_disposition_on_unknown_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'vad_bounds'}, disposition_enabled=True) is False
    )


def test_disposition_off_unknown_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'vad_bounds'}, disposition_enabled=False) is False
    )


def test_empty_ladder_unknown_vad_bounds():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'vad_bounds'}) is False


def test_language_guard_unknown_vad_bounds():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'vad_bounds'}) is False


def test_disposition_on_unknown_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_unknown_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_unknown_vad_nonfinite():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'vad_nonfinite'}) is False


def test_language_guard_unknown_vad_nonfinite():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'vad_nonfinite'}) is False


def test_disposition_on_unknown_vad_order():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'vad_order'}, disposition_enabled=True) is False
    )


def test_disposition_off_unknown_vad_order():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'vad_order'}, disposition_enabled=False) is False
    )


def test_empty_ladder_unknown_vad_order():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'vad_order'}) is False


def test_language_guard_unknown_vad_order():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'vad_order'}) is False


def test_disposition_on_unknown_word_clock():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'word_clock'}, disposition_enabled=True) is False
    )


def test_disposition_off_unknown_word_clock():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'word_clock'}, disposition_enabled=False) is False
    )


def test_empty_ladder_unknown_word_clock():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'word_clock'}) is False


def test_language_guard_unknown_word_clock():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'word_clock'}) is False


def test_disposition_on_unknown_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'word_sequence'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_unknown_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_unknown_word_sequence():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'word_sequence'}) is False


def test_language_guard_unknown_word_sequence():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'word_sequence'}) is False


def test_disposition_on_unknown_word_shape():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'word_shape'}, disposition_enabled=True) is False
    )


def test_disposition_off_unknown_word_shape():
    assert (
        validation_disposition_failure({'stage': 'unknown', 'reason': 'word_shape'}, disposition_enabled=False) is False
    )


def test_empty_ladder_unknown_word_shape():
    assert empty_ladder_recovery_failure({'stage': 'unknown', 'reason': 'word_shape'}) is False


def test_language_guard_unknown_word_shape():
    assert language_guard_redrive_failure({'stage': 'unknown', 'reason': 'word_shape'}) is False


def test_disposition_on_vad_windows_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_vad_windows_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_vad_windows_decoded_duration_mismatch():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}) is False


def test_language_guard_vad_windows_decoded_duration_mismatch():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}) is False


def test_disposition_on_vad_windows_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_vad_windows_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_vad_windows_empty_asr():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}) is False


def test_language_guard_vad_windows_empty_asr():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'empty_asr'}) is False


def test_disposition_on_vad_windows_no_owned_words():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_vad_windows_no_owned_words():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_vad_windows_no_owned_words():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}) is False


def test_language_guard_vad_windows_no_owned_words():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'no_owned_words'}) is False


def test_disposition_on_vad_windows_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_vad_windows_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_vad_windows_outside_admitted_source():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'outside_admitted_source'}) is False


def test_language_guard_vad_windows_outside_admitted_source():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'outside_admitted_source'}) is False


def test_disposition_on_vad_windows_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_vad_windows_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_vad_windows_retained_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}) is False


def test_language_guard_vad_windows_retained_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}) is False


def test_disposition_on_vad_windows_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_vad_windows_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_vad_windows_staged_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}) is False


def test_language_guard_vad_windows_staged_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}) is False


def test_disposition_on_vad_windows_unknown():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'unknown'}, disposition_enabled=True) is False
    )


def test_disposition_off_vad_windows_unknown():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_vad_windows_unknown():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'unknown'}) is False


def test_language_guard_vad_windows_unknown():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'unknown'}) is False


def test_disposition_on_vad_windows_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_vad_windows_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'vad_windows', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_vad_windows_unsupported_language():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'unsupported_language'}) is False


def test_language_guard_vad_windows_unsupported_language():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'unsupported_language'}) is True


def test_disposition_on_vad_windows_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_vad_windows_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_vad_windows_vad_bounds():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}) is False


def test_language_guard_vad_windows_vad_bounds():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'}) is False


def test_disposition_on_vad_windows_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_vad_windows_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_vad_windows_vad_nonfinite():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}) is False


def test_language_guard_vad_windows_vad_nonfinite():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'vad_nonfinite'}) is False


def test_disposition_on_vad_windows_vad_order():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_vad_windows_vad_order():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_vad_windows_vad_order():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'vad_order'}) is False


def test_language_guard_vad_windows_vad_order():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'vad_order'}) is False


def test_disposition_on_vad_windows_word_clock():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_vad_windows_word_clock():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_vad_windows_word_clock():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'word_clock'}) is False


def test_language_guard_vad_windows_word_clock():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'word_clock'}) is False


def test_disposition_on_vad_windows_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_vad_windows_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_vad_windows_word_sequence():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}) is False


def test_language_guard_vad_windows_word_sequence():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'word_sequence'}) is False


def test_disposition_on_vad_windows_word_shape():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_vad_windows_word_shape():
    assert (
        validation_disposition_failure({'stage': 'vad_windows', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_vad_windows_word_shape():
    assert empty_ladder_recovery_failure({'stage': 'vad_windows', 'reason': 'word_shape'}) is False


def test_language_guard_vad_windows_word_shape():
    assert language_guard_redrive_failure({'stage': 'vad_windows', 'reason': 'word_shape'}) is False


def test_disposition_on_word_clocks_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_word_clocks_decoded_duration_mismatch():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_word_clocks_decoded_duration_mismatch():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}) is False


def test_language_guard_word_clocks_decoded_duration_mismatch():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}) is False


def test_disposition_on_word_clocks_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_word_clocks_empty_asr():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_word_clocks_empty_asr():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}) is False


def test_language_guard_word_clocks_empty_asr():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'empty_asr'}) is False


def test_disposition_on_word_clocks_no_owned_words():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}, disposition_enabled=True)
        is False
    )


def test_disposition_off_word_clocks_no_owned_words():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_word_clocks_no_owned_words():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}) is False


def test_language_guard_word_clocks_no_owned_words():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'no_owned_words'}) is False


def test_disposition_on_word_clocks_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_word_clocks_outside_admitted_source():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_word_clocks_outside_admitted_source():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'outside_admitted_source'}) is False


def test_language_guard_word_clocks_outside_admitted_source():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'outside_admitted_source'}) is False


def test_disposition_on_word_clocks_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_word_clocks_retained_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_word_clocks_retained_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}) is False


def test_language_guard_word_clocks_retained_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}) is False


def test_disposition_on_word_clocks_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_word_clocks_staged_audio_invalid():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_word_clocks_staged_audio_invalid():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}) is False


def test_language_guard_word_clocks_staged_audio_invalid():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}) is False


def test_disposition_on_word_clocks_unknown():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'unknown'}, disposition_enabled=True) is False
    )


def test_disposition_off_word_clocks_unknown():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'unknown'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_word_clocks_unknown():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'unknown'}) is False


def test_language_guard_word_clocks_unknown():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'unknown'}) is False


def test_disposition_on_word_clocks_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'unsupported_language'}, disposition_enabled=True
        )
        is False
    )


def test_disposition_off_word_clocks_unsupported_language():
    assert (
        validation_disposition_failure(
            {'stage': 'word_clocks', 'reason': 'unsupported_language'}, disposition_enabled=False
        )
        is False
    )


def test_empty_ladder_word_clocks_unsupported_language():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'unsupported_language'}) is False


def test_language_guard_word_clocks_unsupported_language():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'unsupported_language'}) is True


def test_disposition_on_word_clocks_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_word_clocks_vad_bounds():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_word_clocks_vad_bounds():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}) is False


def test_language_guard_word_clocks_vad_bounds():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'vad_bounds'}) is False


def test_disposition_on_word_clocks_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_word_clocks_vad_nonfinite():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_word_clocks_vad_nonfinite():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}) is False


def test_language_guard_word_clocks_vad_nonfinite():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'vad_nonfinite'}) is False


def test_disposition_on_word_clocks_vad_order():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_order'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_word_clocks_vad_order():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'vad_order'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_word_clocks_vad_order():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'vad_order'}) is False


def test_language_guard_word_clocks_vad_order():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'vad_order'}) is False


def test_disposition_on_word_clocks_word_clock():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_clock'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_word_clocks_word_clock():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_clock'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_word_clocks_word_clock():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'word_clock'}) is False


def test_language_guard_word_clocks_word_clock():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'word_clock'}) is False


def test_disposition_on_word_clocks_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_word_clocks_word_sequence():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_word_clocks_word_sequence():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}) is False


def test_language_guard_word_clocks_word_sequence():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'word_sequence'}) is False


def test_disposition_on_word_clocks_word_shape():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_shape'}, disposition_enabled=True)
        is True
    )


def test_disposition_off_word_clocks_word_shape():
    assert (
        validation_disposition_failure({'stage': 'word_clocks', 'reason': 'word_shape'}, disposition_enabled=False)
        is False
    )


def test_empty_ladder_word_clocks_word_shape():
    assert empty_ladder_recovery_failure({'stage': 'word_clocks', 'reason': 'word_shape'}) is False


def test_language_guard_word_clocks_word_shape():
    assert language_guard_redrive_failure({'stage': 'word_clocks', 'reason': 'word_shape'}) is False


def test_hostile_0_disposition():
    assert validation_disposition_failure({}, disposition_enabled=True) is False


def test_hostile_0_empty_ladder_recovery():
    assert empty_ladder_recovery_failure({}) is False


def test_hostile_0_language_guard_redrive():
    assert language_guard_redrive_failure({}) is False


def test_hostile_1_disposition():
    assert validation_disposition_failure({'stage': 'fetch_decode'}, disposition_enabled=True) is False


def test_hostile_1_empty_ladder_recovery():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode'}) is False


def test_hostile_1_language_guard_redrive():
    assert language_guard_redrive_failure({'stage': 'fetch_decode'}) is False


def test_hostile_2_disposition():
    assert validation_disposition_failure({'reason': 'empty_asr'}, disposition_enabled=True) is False


def test_hostile_2_empty_ladder_recovery():
    assert empty_ladder_recovery_failure({'reason': 'empty_asr'}) is False


def test_hostile_2_language_guard_redrive():
    assert language_guard_redrive_failure({'reason': 'empty_asr'}) is False


def test_hostile_3_disposition():
    assert (
        validation_disposition_failure(
            {'stage': 'fetch_decode', 'reason': 'empty_asr', 'extra': 1}, disposition_enabled=True
        )
        is False
    )


def test_hostile_3_empty_ladder_recovery():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 'empty_asr', 'extra': 1}) is False


def test_hostile_3_language_guard_redrive():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 'empty_asr', 'extra': 1}) is False


def test_hostile_4_disposition():
    assert validation_disposition_failure({'stage': 1, 'reason': 'empty_asr'}, disposition_enabled=True) is False


def test_hostile_4_empty_ladder_recovery():
    assert empty_ladder_recovery_failure({'stage': 1, 'reason': 'empty_asr'}) is False


def test_hostile_4_language_guard_redrive():
    assert language_guard_redrive_failure({'stage': 1, 'reason': 'empty_asr'}) is False


def test_hostile_5_disposition():
    assert validation_disposition_failure({'stage': 'fetch_decode', 'reason': 1}, disposition_enabled=True) is False


def test_hostile_5_empty_ladder_recovery():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': 1}) is False


def test_hostile_5_language_guard_redrive():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': 1}) is False


def test_hostile_6_disposition():
    assert validation_disposition_failure(None, disposition_enabled=True) is False


def test_hostile_6_empty_ladder_recovery():
    assert empty_ladder_recovery_failure(None) is False


def test_hostile_6_language_guard_redrive():
    assert language_guard_redrive_failure(None) is False


def test_hostile_7_disposition():
    assert validation_disposition_failure('fetch_decode', disposition_enabled=True) is False


def test_hostile_7_empty_ladder_recovery():
    assert empty_ladder_recovery_failure('fetch_decode') is False


def test_hostile_7_language_guard_redrive():
    assert language_guard_redrive_failure('fetch_decode') is False


def test_hostile_8_disposition():
    assert validation_disposition_failure({'stage': 'fetch_decode', 'reason': ''}, disposition_enabled=True) is False


def test_hostile_8_empty_ladder_recovery():
    assert empty_ladder_recovery_failure({'stage': 'fetch_decode', 'reason': ''}) is False


def test_hostile_8_language_guard_redrive():
    assert language_guard_redrive_failure({'stage': 'fetch_decode', 'reason': ''}) is False


def test_hostile_9_disposition():
    assert validation_disposition_failure({'stage': '', 'reason': 'empty_asr'}, disposition_enabled=True) is False


def test_hostile_9_empty_ladder_recovery():
    assert empty_ladder_recovery_failure({'stage': '', 'reason': 'empty_asr'}) is False


def test_hostile_9_language_guard_redrive():
    assert language_guard_redrive_failure({'stage': '', 'reason': 'empty_asr'}) is False


def test_stage_vocabulary_is_closed():
    assert WORKER_VALIDATION_STAGES == frozenset(
        {'fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery'}
    )


def test_closed_reason_vocabulary_excludes_unknown():
    assert 'unknown' not in WORKER_VALIDATION_REASONS
    assert 'unknown' in WORKER_VALIDATION_REASON_TOKENS


def test_evidence_vocabulary_is_the_strict_superset():
    assert WORKER_VALIDATION_REASON_TOKENS == WORKER_VALIDATION_REASONS | {
        chr(117) + chr(110) + chr(107) + chr(110) + chr(111) + chr(119) + chr(110)
    }


def test_unconditional_demotion_family_is_exact():
    from utils.batch_pipeline.errors import (
        VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS,
        VALIDATION_DISPOSITION_FLAGGED_REASONS,
        VALIDATION_DISPOSITION_REASONS,
    )

    assert VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS == frozenset(
        {'staged_audio_invalid', 'retained_audio_invalid', 'decoded_duration_mismatch'}
    )


def test_flagged_demotion_family_is_exact():
    from utils.batch_pipeline.errors import VALIDATION_DISPOSITION_FLAGGED_REASONS

    assert VALIDATION_DISPOSITION_FLAGGED_REASONS == frozenset(
        {'vad_nonfinite', 'vad_order', 'vad_bounds', 'word_shape', 'word_clock', 'word_sequence'}
    )


def test_demotion_family_union_is_exact():
    from utils.batch_pipeline.errors import (
        VALIDATION_DISPOSITION_REASONS,
        VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS,
        VALIDATION_DISPOSITION_FLAGGED_REASONS,
    )

    assert (
        VALIDATION_DISPOSITION_REASONS
        == VALIDATION_DISPOSITION_UNCONDITIONAL_REASONS | VALIDATION_DISPOSITION_FLAGGED_REASONS
    )


def test_unconditional_stage_token_is_fetch_decode():
    from utils.batch_pipeline.errors import VALIDATION_DISPOSITION_UNCONDITIONAL_STAGE

    assert VALIDATION_DISPOSITION_UNCONDITIONAL_STAGE == 'fetch_decode'


def test_empty_family_and_stage_are_exact():
    from utils.batch_pipeline.errors import EMPTY_LADDER_RECOVERY_REASONS, EMPTY_LADDER_RECOVERY_STAGE

    assert EMPTY_LADDER_RECOVERY_REASONS == frozenset({'empty_asr', 'no_owned_words'})
    assert EMPTY_LADDER_RECOVERY_STAGE == 'assemble_words'


def test_language_guard_family_is_exact():
    from utils.batch_pipeline.errors import LANGUAGE_GUARD_REDRIVE_REASONS

    assert LANGUAGE_GUARD_REDRIVE_REASONS == frozenset({'unsupported_language'})


def test_terminal_work_validates_against_the_closed_set():
    from utils.batch_pipeline.contracts import ValidationFailureWork

    work = ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')
    validate_worker_failure({'stage': work.stage, 'reason': work.reason})
