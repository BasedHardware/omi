# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The demotion oracle, pinned cell-by-cell against a literal expected-truth table.

For every (stage, reason) pair of the closed worker vocabularies the
scheduler-side predicate ``empty_ladder_recovery_failure`` must answer exactly
the literal truth written into the test — the assemble_words empty family
demotes, every synthetic cross-stage token, every guard token and every kept
fault keeps ``False``. The worker side is pinned to the same family by source:
it reads ``EMPTY_LADDER_RECOVERY_REASONS`` + ``EMPTY_LADDER_RECOVERY_STAGE``
directly, guards its demotion branch on the stage, and keeps exactly one
guard line and one fault line.
"""

import inspect
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

import diarizer.batch_pipeline as worker_module
import utils.batch_pipeline.scheduler as scheduler_module
from utils.batch_pipeline.errors import (
    EMPTY_LADDER_RECOVERY_REASONS,
    EMPTY_LADDER_RECOVERY_STAGE,
    empty_ladder_recovery_failure,
)

WORKER_SOURCE = inspect.getsource(worker_module)
SCHEDULER_SOURCE = inspect.getsource(scheduler_module)


def test_oracle_fetch_decode_staged_audio_invalid_is_false():
    """(fetch_decode, staged_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "staged_audio_invalid"}
    expected = 'fetch_decode' == "assemble_words" and 'staged_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_retained_audio_invalid_is_false():
    """(fetch_decode, retained_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "retained_audio_invalid"}
    expected = 'fetch_decode' == "assemble_words" and 'retained_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_decoded_duration_mismatch_is_false():
    """(fetch_decode, decoded_duration_mismatch) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}
    expected = 'fetch_decode' == "assemble_words" and 'decoded_duration_mismatch' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_word_shape_is_false():
    """(fetch_decode, word_shape) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "word_shape"}
    expected = 'fetch_decode' == "assemble_words" and 'word_shape' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_word_clock_is_false():
    """(fetch_decode, word_clock) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "word_clock"}
    expected = 'fetch_decode' == "assemble_words" and 'word_clock' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_word_sequence_is_false():
    """(fetch_decode, word_sequence) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "word_sequence"}
    expected = 'fetch_decode' == "assemble_words" and 'word_sequence' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_vad_nonfinite_is_false():
    """(fetch_decode, vad_nonfinite) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "vad_nonfinite"}
    expected = 'fetch_decode' == "assemble_words" and 'vad_nonfinite' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_vad_order_is_false():
    """(fetch_decode, vad_order) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "vad_order"}
    expected = 'fetch_decode' == "assemble_words" and 'vad_order' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_vad_bounds_is_false():
    """(fetch_decode, vad_bounds) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "vad_bounds"}
    expected = 'fetch_decode' == "assemble_words" and 'vad_bounds' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_empty_asr_is_false():
    """(fetch_decode, empty_asr) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "empty_asr"}
    expected = 'fetch_decode' == "assemble_words" and 'empty_asr' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_no_owned_words_is_false():
    """(fetch_decode, no_owned_words) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "no_owned_words"}
    expected = 'fetch_decode' == "assemble_words" and 'no_owned_words' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_unsupported_language_is_false():
    """(fetch_decode, unsupported_language) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "unsupported_language"}
    expected = 'fetch_decode' == "assemble_words" and 'unsupported_language' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_outside_admitted_source_is_false():
    """(fetch_decode, outside_admitted_source) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "outside_admitted_source"}
    expected = 'fetch_decode' == "assemble_words" and 'outside_admitted_source' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_fetch_decode_unknown_is_false():
    """(fetch_decode, unknown) -> False, straight from the literal rule table."""
    shape = {"stage": "fetch_decode", "reason": "unknown"}
    expected = 'fetch_decode' == "assemble_words" and 'unknown' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_staged_audio_invalid_is_false():
    """(vad_windows, staged_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "staged_audio_invalid"}
    expected = 'vad_windows' == "assemble_words" and 'staged_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_retained_audio_invalid_is_false():
    """(vad_windows, retained_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "retained_audio_invalid"}
    expected = 'vad_windows' == "assemble_words" and 'retained_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_decoded_duration_mismatch_is_false():
    """(vad_windows, decoded_duration_mismatch) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}
    expected = 'vad_windows' == "assemble_words" and 'decoded_duration_mismatch' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_word_shape_is_false():
    """(vad_windows, word_shape) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "word_shape"}
    expected = 'vad_windows' == "assemble_words" and 'word_shape' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_word_clock_is_false():
    """(vad_windows, word_clock) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "word_clock"}
    expected = 'vad_windows' == "assemble_words" and 'word_clock' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_word_sequence_is_false():
    """(vad_windows, word_sequence) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "word_sequence"}
    expected = 'vad_windows' == "assemble_words" and 'word_sequence' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_vad_nonfinite_is_false():
    """(vad_windows, vad_nonfinite) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "vad_nonfinite"}
    expected = 'vad_windows' == "assemble_words" and 'vad_nonfinite' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_vad_order_is_false():
    """(vad_windows, vad_order) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "vad_order"}
    expected = 'vad_windows' == "assemble_words" and 'vad_order' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_vad_bounds_is_false():
    """(vad_windows, vad_bounds) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    expected = 'vad_windows' == "assemble_words" and 'vad_bounds' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_empty_asr_is_false():
    """(vad_windows, empty_asr) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "empty_asr"}
    expected = 'vad_windows' == "assemble_words" and 'empty_asr' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_no_owned_words_is_false():
    """(vad_windows, no_owned_words) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "no_owned_words"}
    expected = 'vad_windows' == "assemble_words" and 'no_owned_words' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_unsupported_language_is_false():
    """(vad_windows, unsupported_language) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "unsupported_language"}
    expected = 'vad_windows' == "assemble_words" and 'unsupported_language' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_outside_admitted_source_is_false():
    """(vad_windows, outside_admitted_source) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "outside_admitted_source"}
    expected = 'vad_windows' == "assemble_words" and 'outside_admitted_source' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_vad_windows_unknown_is_false():
    """(vad_windows, unknown) -> False, straight from the literal rule table."""
    shape = {"stage": "vad_windows", "reason": "unknown"}
    expected = 'vad_windows' == "assemble_words" and 'unknown' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_staged_audio_invalid_is_false():
    """(word_clocks, staged_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "staged_audio_invalid"}
    expected = 'word_clocks' == "assemble_words" and 'staged_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_retained_audio_invalid_is_false():
    """(word_clocks, retained_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "retained_audio_invalid"}
    expected = 'word_clocks' == "assemble_words" and 'retained_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_decoded_duration_mismatch_is_false():
    """(word_clocks, decoded_duration_mismatch) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}
    expected = 'word_clocks' == "assemble_words" and 'decoded_duration_mismatch' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_word_shape_is_false():
    """(word_clocks, word_shape) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "word_shape"}
    expected = 'word_clocks' == "assemble_words" and 'word_shape' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_word_clock_is_false():
    """(word_clocks, word_clock) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "word_clock"}
    expected = 'word_clocks' == "assemble_words" and 'word_clock' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_word_sequence_is_false():
    """(word_clocks, word_sequence) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "word_sequence"}
    expected = 'word_clocks' == "assemble_words" and 'word_sequence' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_vad_nonfinite_is_false():
    """(word_clocks, vad_nonfinite) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "vad_nonfinite"}
    expected = 'word_clocks' == "assemble_words" and 'vad_nonfinite' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_vad_order_is_false():
    """(word_clocks, vad_order) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "vad_order"}
    expected = 'word_clocks' == "assemble_words" and 'vad_order' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_vad_bounds_is_false():
    """(word_clocks, vad_bounds) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "vad_bounds"}
    expected = 'word_clocks' == "assemble_words" and 'vad_bounds' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_empty_asr_is_false():
    """(word_clocks, empty_asr) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "empty_asr"}
    expected = 'word_clocks' == "assemble_words" and 'empty_asr' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_no_owned_words_is_false():
    """(word_clocks, no_owned_words) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "no_owned_words"}
    expected = 'word_clocks' == "assemble_words" and 'no_owned_words' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_unsupported_language_is_false():
    """(word_clocks, unsupported_language) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "unsupported_language"}
    expected = 'word_clocks' == "assemble_words" and 'unsupported_language' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_outside_admitted_source_is_false():
    """(word_clocks, outside_admitted_source) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "outside_admitted_source"}
    expected = 'word_clocks' == "assemble_words" and 'outside_admitted_source' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_word_clocks_unknown_is_false():
    """(word_clocks, unknown) -> False, straight from the literal rule table."""
    shape = {"stage": "word_clocks", "reason": "unknown"}
    expected = 'word_clocks' == "assemble_words" and 'unknown' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_staged_audio_invalid_is_false():
    """(assemble_words, staged_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "staged_audio_invalid"}
    expected = 'assemble_words' == "assemble_words" and 'staged_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_retained_audio_invalid_is_false():
    """(assemble_words, retained_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "retained_audio_invalid"}
    expected = 'assemble_words' == "assemble_words" and 'retained_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_decoded_duration_mismatch_is_false():
    """(assemble_words, decoded_duration_mismatch) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "decoded_duration_mismatch"}
    expected = 'assemble_words' == "assemble_words" and 'decoded_duration_mismatch' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_word_shape_is_false():
    """(assemble_words, word_shape) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "word_shape"}
    expected = 'assemble_words' == "assemble_words" and 'word_shape' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_word_clock_is_false():
    """(assemble_words, word_clock) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "word_clock"}
    expected = 'assemble_words' == "assemble_words" and 'word_clock' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_word_sequence_is_false():
    """(assemble_words, word_sequence) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "word_sequence"}
    expected = 'assemble_words' == "assemble_words" and 'word_sequence' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_vad_nonfinite_is_false():
    """(assemble_words, vad_nonfinite) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "vad_nonfinite"}
    expected = 'assemble_words' == "assemble_words" and 'vad_nonfinite' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_vad_order_is_false():
    """(assemble_words, vad_order) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "vad_order"}
    expected = 'assemble_words' == "assemble_words" and 'vad_order' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_vad_bounds_is_false():
    """(assemble_words, vad_bounds) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "vad_bounds"}
    expected = 'assemble_words' == "assemble_words" and 'vad_bounds' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_empty_asr_is_true():
    """(assemble_words, empty_asr) -> True, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    expected = 'assemble_words' == "assemble_words" and 'empty_asr' in ("empty_asr", "no_owned_words")
    assert expected is True
    assert empty_ladder_recovery_failure(shape) is True


def test_oracle_assemble_words_no_owned_words_is_true():
    """(assemble_words, no_owned_words) -> True, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "no_owned_words"}
    expected = 'assemble_words' == "assemble_words" and 'no_owned_words' in ("empty_asr", "no_owned_words")
    assert expected is True
    assert empty_ladder_recovery_failure(shape) is True


def test_oracle_assemble_words_unsupported_language_is_false():
    """(assemble_words, unsupported_language) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "unsupported_language"}
    expected = 'assemble_words' == "assemble_words" and 'unsupported_language' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_outside_admitted_source_is_false():
    """(assemble_words, outside_admitted_source) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "outside_admitted_source"}
    expected = 'assemble_words' == "assemble_words" and 'outside_admitted_source' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_assemble_words_unknown_is_false():
    """(assemble_words, unknown) -> False, straight from the literal rule table."""
    shape = {"stage": "assemble_words", "reason": "unknown"}
    expected = 'assemble_words' == "assemble_words" and 'unknown' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_staged_audio_invalid_is_false():
    """(asr_recovery, staged_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "staged_audio_invalid"}
    expected = 'asr_recovery' == "assemble_words" and 'staged_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_retained_audio_invalid_is_false():
    """(asr_recovery, retained_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "retained_audio_invalid"}
    expected = 'asr_recovery' == "assemble_words" and 'retained_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_decoded_duration_mismatch_is_false():
    """(asr_recovery, decoded_duration_mismatch) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}
    expected = 'asr_recovery' == "assemble_words" and 'decoded_duration_mismatch' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_word_shape_is_false():
    """(asr_recovery, word_shape) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "word_shape"}
    expected = 'asr_recovery' == "assemble_words" and 'word_shape' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_word_clock_is_false():
    """(asr_recovery, word_clock) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "word_clock"}
    expected = 'asr_recovery' == "assemble_words" and 'word_clock' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_word_sequence_is_false():
    """(asr_recovery, word_sequence) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "word_sequence"}
    expected = 'asr_recovery' == "assemble_words" and 'word_sequence' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_vad_nonfinite_is_false():
    """(asr_recovery, vad_nonfinite) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "vad_nonfinite"}
    expected = 'asr_recovery' == "assemble_words" and 'vad_nonfinite' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_vad_order_is_false():
    """(asr_recovery, vad_order) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "vad_order"}
    expected = 'asr_recovery' == "assemble_words" and 'vad_order' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_vad_bounds_is_false():
    """(asr_recovery, vad_bounds) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "vad_bounds"}
    expected = 'asr_recovery' == "assemble_words" and 'vad_bounds' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_empty_asr_is_false():
    """(asr_recovery, empty_asr) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "empty_asr"}
    expected = 'asr_recovery' == "assemble_words" and 'empty_asr' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_no_owned_words_is_false():
    """(asr_recovery, no_owned_words) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "no_owned_words"}
    expected = 'asr_recovery' == "assemble_words" and 'no_owned_words' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_unsupported_language_is_false():
    """(asr_recovery, unsupported_language) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "unsupported_language"}
    expected = 'asr_recovery' == "assemble_words" and 'unsupported_language' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_outside_admitted_source_is_false():
    """(asr_recovery, outside_admitted_source) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "outside_admitted_source"}
    expected = 'asr_recovery' == "assemble_words" and 'outside_admitted_source' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_asr_recovery_unknown_is_false():
    """(asr_recovery, unknown) -> False, straight from the literal rule table."""
    shape = {"stage": "asr_recovery", "reason": "unknown"}
    expected = 'asr_recovery' == "assemble_words" and 'unknown' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_staged_audio_invalid_is_false():
    """(unknown, staged_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "staged_audio_invalid"}
    expected = 'unknown' == "assemble_words" and 'staged_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_retained_audio_invalid_is_false():
    """(unknown, retained_audio_invalid) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "retained_audio_invalid"}
    expected = 'unknown' == "assemble_words" and 'retained_audio_invalid' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_decoded_duration_mismatch_is_false():
    """(unknown, decoded_duration_mismatch) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "decoded_duration_mismatch"}
    expected = 'unknown' == "assemble_words" and 'decoded_duration_mismatch' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_word_shape_is_false():
    """(unknown, word_shape) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "word_shape"}
    expected = 'unknown' == "assemble_words" and 'word_shape' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_word_clock_is_false():
    """(unknown, word_clock) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "word_clock"}
    expected = 'unknown' == "assemble_words" and 'word_clock' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_word_sequence_is_false():
    """(unknown, word_sequence) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "word_sequence"}
    expected = 'unknown' == "assemble_words" and 'word_sequence' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_vad_nonfinite_is_false():
    """(unknown, vad_nonfinite) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "vad_nonfinite"}
    expected = 'unknown' == "assemble_words" and 'vad_nonfinite' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_vad_order_is_false():
    """(unknown, vad_order) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "vad_order"}
    expected = 'unknown' == "assemble_words" and 'vad_order' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_vad_bounds_is_false():
    """(unknown, vad_bounds) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "vad_bounds"}
    expected = 'unknown' == "assemble_words" and 'vad_bounds' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_empty_asr_is_false():
    """(unknown, empty_asr) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "empty_asr"}
    expected = 'unknown' == "assemble_words" and 'empty_asr' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_no_owned_words_is_false():
    """(unknown, no_owned_words) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "no_owned_words"}
    expected = 'unknown' == "assemble_words" and 'no_owned_words' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_unsupported_language_is_false():
    """(unknown, unsupported_language) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "unsupported_language"}
    expected = 'unknown' == "assemble_words" and 'unsupported_language' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_outside_admitted_source_is_false():
    """(unknown, outside_admitted_source) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "outside_admitted_source"}
    expected = 'unknown' == "assemble_words" and 'outside_admitted_source' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_oracle_unknown_unknown_is_false():
    """(unknown, unknown) -> False, straight from the literal rule table."""
    shape = {"stage": "unknown", "reason": "unknown"}
    expected = 'unknown' == "assemble_words" and 'unknown' in ("empty_asr", "no_owned_words")
    assert expected is False
    assert empty_ladder_recovery_failure(shape) is False


def test_worker_source_reads_the_family_set():
    assert "EMPTY_LADDER_RECOVERY_REASONS" in WORKER_SOURCE


def test_worker_source_reads_the_family_stage():
    assert "EMPTY_LADDER_RECOVERY_STAGE" in WORKER_SOURCE


def test_worker_source_guards_the_demotion_on_the_stage():
    assert "failure_stage == EMPTY_LADDER_RECOVERY_STAGE and reason in EMPTY_LADDER_RECOVERY_REASONS" in WORKER_SOURCE


def test_worker_source_has_exactly_one_empty_ladder_line():
    assert WORKER_SOURCE.count("event=batch_empty_ladder") == 1
    assert "outcome=recovery_handoff" in WORKER_SOURCE


def test_scheduler_source_calls_the_predicate_once():
    assert SCHEDULER_SOURCE.count("empty_ladder_recovery_failure(") == 1
    assert "outcome=held_for_recovery" in SCHEDULER_SOURCE


def test_worker_source_has_exactly_one_guard_line():
    assert WORKER_SOURCE.count("event=batch_language_guard") == 1


def test_scheduler_source_has_exactly_one_guard_line():
    assert SCHEDULER_SOURCE.count("event=batch_language_guard") == 1


def test_worker_source_keeps_the_fault_line():
    assert "event=batch_worker_failed" in WORKER_SOURCE


def test_scheduler_source_keeps_the_quarantine_line():
    assert "event=batch_quarantined" in SCHEDULER_SOURCE


def test_predicate_is_referenced_only_by_errors_and_scheduler():
    hits = [
        p.name
        for p in (BACKEND / "utils" / "batch_pipeline").glob("*.py")
        if "empty_ladder_recovery_failure" in p.read_text() and p.name != "__init__.py"
    ]
    assert sorted(hits) == ["errors.py", "scheduler.py"]


def test_empty_ladder_event_appears_only_in_the_two_source_files():
    hits = [
        str(p.relative_to(BACKEND))
        for p in list((BACKEND / "utils").rglob("*.py")) + list((BACKEND / "diarizer").rglob("*.py"))
        if "event=batch_empty_ladder" in p.read_text()
    ]
    assert sorted(hits) == ["diarizer/batch_pipeline.py", "utils/batch_pipeline/scheduler.py"]


def test_oracle_uppercase_stage_is_false():
    assert empty_ladder_recovery_failure({"stage": "ASSEMBLE_WORDS", "reason": "empty_asr"}) is False


def test_oracle_uppercase_reason_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words", "reason": "EMPTY_ASR"}) is False


def test_oracle_trailing_space_stage_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words ", "reason": "empty_asr"}) is False


def test_oracle_trailing_space_reason_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words", "reason": "empty_asr "}) is False


def test_oracle_singular_word_reason_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words", "reason": "no_owned_word"}) is False


def test_oracle_unknown_stage_with_family_reason_is_false():
    assert empty_ladder_recovery_failure({"stage": "unknown", "reason": "empty_asr"}) is False


def test_oracle_unknown_reason_with_family_stage_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words", "reason": "unknown"}) is False


def test_oracle_guard_reason_with_family_stage_is_false():
    assert empty_ladder_recovery_failure({"stage": "assemble_words", "reason": "unsupported_language"}) is False
