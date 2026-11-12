"""Evidence vocabulary grid for worker-flight salvage.

Every cell pins one cell of the closed-vocabulary contract the salvage evidence
rides: ``transient_failure_evidence`` maps a stage/reason pair to the exact
durable dict or ``None``, ``validate_worker_failure_evidence`` accepts exactly
the closed stages with the strict reason superset (``unknown`` included),
``validate_worker_failure`` (the terminal gate) rejects ``unknown``, and the
three designed-handoff predicates never claim an ``unknown``-reason escape.
Literal expectations, computed from docs/batch-flight-escape-salvage.md.

Failure-Class: FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine
"""

import pytest

from diarizer.batch_pipeline import transient_failure_evidence
from utils.batch_pipeline.errors import (
    error_site_field,
    empty_ladder_recovery_failure,
    validation_disposition_failure,
    language_guard_redrive_failure,
    validate_worker_failure,
    validate_worker_failure_evidence,
    WORKER_VALIDATION_REASONS,
    WORKER_VALIDATION_STAGES,
)
from utils.observability.reasons import (
    ReasonFamily,
    WorkerValidationReason,
    WorkerValidationStage,
    reason_label,
    reason_values,
)

FC = 'FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine'

CLOSED_STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery', 'persist')
ALL_STAGES = CLOSED_STAGES + ('unknown', 'asr', 'diarize')
TYPED_REASONS = tuple(member.value for member in WorkerValidationReason if member.value != 'unknown')
ALL_REASONS = TYPED_REASONS + ('unknown', 'gibberish_payload')


def test_evidence_grid_fetch_decode_staged_audio_invalid():
    assert transient_failure_evidence('fetch_decode', 'staged_audio_invalid') == {
        'stage': 'fetch_decode',
        'reason': 'staged_audio_invalid',
    }


def test_evidence_grid_fetch_decode_retained_audio_invalid():
    assert transient_failure_evidence('fetch_decode', 'retained_audio_invalid') == {
        'stage': 'fetch_decode',
        'reason': 'retained_audio_invalid',
    }


def test_evidence_grid_fetch_decode_decoded_duration_mismatch():
    assert transient_failure_evidence('fetch_decode', 'decoded_duration_mismatch') == {
        'stage': 'fetch_decode',
        'reason': 'decoded_duration_mismatch',
    }


def test_evidence_grid_fetch_decode_word_shape():
    assert transient_failure_evidence('fetch_decode', 'word_shape') == {'stage': 'fetch_decode', 'reason': 'word_shape'}


def test_evidence_grid_fetch_decode_word_clock():
    assert transient_failure_evidence('fetch_decode', 'word_clock') == {'stage': 'fetch_decode', 'reason': 'word_clock'}


def test_evidence_grid_fetch_decode_word_sequence():
    assert transient_failure_evidence('fetch_decode', 'word_sequence') == {
        'stage': 'fetch_decode',
        'reason': 'word_sequence',
    }


def test_evidence_grid_fetch_decode_vad_nonfinite():
    assert transient_failure_evidence('fetch_decode', 'vad_nonfinite') == {
        'stage': 'fetch_decode',
        'reason': 'vad_nonfinite',
    }


def test_evidence_grid_fetch_decode_vad_order():
    assert transient_failure_evidence('fetch_decode', 'vad_order') == {'stage': 'fetch_decode', 'reason': 'vad_order'}


def test_evidence_grid_fetch_decode_vad_bounds():
    assert transient_failure_evidence('fetch_decode', 'vad_bounds') == {'stage': 'fetch_decode', 'reason': 'vad_bounds'}


def test_evidence_grid_fetch_decode_empty_asr():
    assert transient_failure_evidence('fetch_decode', 'empty_asr') == {'stage': 'fetch_decode', 'reason': 'empty_asr'}


def test_evidence_grid_fetch_decode_no_owned_words():
    assert transient_failure_evidence('fetch_decode', 'no_owned_words') == {
        'stage': 'fetch_decode',
        'reason': 'no_owned_words',
    }


def test_evidence_grid_fetch_decode_unsupported_language():
    assert transient_failure_evidence('fetch_decode', 'unsupported_language') == {
        'stage': 'fetch_decode',
        'reason': 'unsupported_language',
    }


def test_evidence_grid_fetch_decode_outside_admitted_source():
    assert transient_failure_evidence('fetch_decode', 'outside_admitted_source') == {
        'stage': 'fetch_decode',
        'reason': 'outside_admitted_source',
    }


def test_evidence_grid_fetch_decode_unknown():
    assert transient_failure_evidence('fetch_decode', 'unknown') == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_evidence_grid_fetch_decode_gibberish_payload():
    assert transient_failure_evidence('fetch_decode', 'gibberish_payload') == {
        'stage': 'fetch_decode',
        'reason': 'unknown',
    }


def test_evidence_grid_vad_windows_staged_audio_invalid():
    assert transient_failure_evidence('vad_windows', 'staged_audio_invalid') == {
        'stage': 'vad_windows',
        'reason': 'staged_audio_invalid',
    }


def test_evidence_grid_vad_windows_retained_audio_invalid():
    assert transient_failure_evidence('vad_windows', 'retained_audio_invalid') == {
        'stage': 'vad_windows',
        'reason': 'retained_audio_invalid',
    }


def test_evidence_grid_vad_windows_decoded_duration_mismatch():
    assert transient_failure_evidence('vad_windows', 'decoded_duration_mismatch') == {
        'stage': 'vad_windows',
        'reason': 'decoded_duration_mismatch',
    }


def test_evidence_grid_vad_windows_word_shape():
    assert transient_failure_evidence('vad_windows', 'word_shape') == {'stage': 'vad_windows', 'reason': 'word_shape'}


def test_evidence_grid_vad_windows_word_clock():
    assert transient_failure_evidence('vad_windows', 'word_clock') == {'stage': 'vad_windows', 'reason': 'word_clock'}


def test_evidence_grid_vad_windows_word_sequence():
    assert transient_failure_evidence('vad_windows', 'word_sequence') == {
        'stage': 'vad_windows',
        'reason': 'word_sequence',
    }


def test_evidence_grid_vad_windows_vad_nonfinite():
    assert transient_failure_evidence('vad_windows', 'vad_nonfinite') == {
        'stage': 'vad_windows',
        'reason': 'vad_nonfinite',
    }


def test_evidence_grid_vad_windows_vad_order():
    assert transient_failure_evidence('vad_windows', 'vad_order') == {'stage': 'vad_windows', 'reason': 'vad_order'}


def test_evidence_grid_vad_windows_vad_bounds():
    assert transient_failure_evidence('vad_windows', 'vad_bounds') == {'stage': 'vad_windows', 'reason': 'vad_bounds'}


def test_evidence_grid_vad_windows_empty_asr():
    assert transient_failure_evidence('vad_windows', 'empty_asr') == {'stage': 'vad_windows', 'reason': 'empty_asr'}


def test_evidence_grid_vad_windows_no_owned_words():
    assert transient_failure_evidence('vad_windows', 'no_owned_words') == {
        'stage': 'vad_windows',
        'reason': 'no_owned_words',
    }


def test_evidence_grid_vad_windows_unsupported_language():
    assert transient_failure_evidence('vad_windows', 'unsupported_language') == {
        'stage': 'vad_windows',
        'reason': 'unsupported_language',
    }


def test_evidence_grid_vad_windows_outside_admitted_source():
    assert transient_failure_evidence('vad_windows', 'outside_admitted_source') == {
        'stage': 'vad_windows',
        'reason': 'outside_admitted_source',
    }


def test_evidence_grid_vad_windows_unknown():
    assert transient_failure_evidence('vad_windows', 'unknown') == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_evidence_grid_vad_windows_gibberish_payload():
    assert transient_failure_evidence('vad_windows', 'gibberish_payload') == {
        'stage': 'vad_windows',
        'reason': 'unknown',
    }


def test_evidence_grid_word_clocks_staged_audio_invalid():
    assert transient_failure_evidence('word_clocks', 'staged_audio_invalid') == {
        'stage': 'word_clocks',
        'reason': 'staged_audio_invalid',
    }


def test_evidence_grid_word_clocks_retained_audio_invalid():
    assert transient_failure_evidence('word_clocks', 'retained_audio_invalid') == {
        'stage': 'word_clocks',
        'reason': 'retained_audio_invalid',
    }


def test_evidence_grid_word_clocks_decoded_duration_mismatch():
    assert transient_failure_evidence('word_clocks', 'decoded_duration_mismatch') == {
        'stage': 'word_clocks',
        'reason': 'decoded_duration_mismatch',
    }


def test_evidence_grid_word_clocks_word_shape():
    assert transient_failure_evidence('word_clocks', 'word_shape') == {'stage': 'word_clocks', 'reason': 'word_shape'}


def test_evidence_grid_word_clocks_word_clock():
    assert transient_failure_evidence('word_clocks', 'word_clock') == {'stage': 'word_clocks', 'reason': 'word_clock'}


def test_evidence_grid_word_clocks_word_sequence():
    assert transient_failure_evidence('word_clocks', 'word_sequence') == {
        'stage': 'word_clocks',
        'reason': 'word_sequence',
    }


def test_evidence_grid_word_clocks_vad_nonfinite():
    assert transient_failure_evidence('word_clocks', 'vad_nonfinite') == {
        'stage': 'word_clocks',
        'reason': 'vad_nonfinite',
    }


def test_evidence_grid_word_clocks_vad_order():
    assert transient_failure_evidence('word_clocks', 'vad_order') == {'stage': 'word_clocks', 'reason': 'vad_order'}


def test_evidence_grid_word_clocks_vad_bounds():
    assert transient_failure_evidence('word_clocks', 'vad_bounds') == {'stage': 'word_clocks', 'reason': 'vad_bounds'}


def test_evidence_grid_word_clocks_empty_asr():
    assert transient_failure_evidence('word_clocks', 'empty_asr') == {'stage': 'word_clocks', 'reason': 'empty_asr'}


def test_evidence_grid_word_clocks_no_owned_words():
    assert transient_failure_evidence('word_clocks', 'no_owned_words') == {
        'stage': 'word_clocks',
        'reason': 'no_owned_words',
    }


def test_evidence_grid_word_clocks_unsupported_language():
    assert transient_failure_evidence('word_clocks', 'unsupported_language') == {
        'stage': 'word_clocks',
        'reason': 'unsupported_language',
    }


def test_evidence_grid_word_clocks_outside_admitted_source():
    assert transient_failure_evidence('word_clocks', 'outside_admitted_source') == {
        'stage': 'word_clocks',
        'reason': 'outside_admitted_source',
    }


def test_evidence_grid_word_clocks_unknown():
    assert transient_failure_evidence('word_clocks', 'unknown') == {'stage': 'word_clocks', 'reason': 'unknown'}


def test_evidence_grid_word_clocks_gibberish_payload():
    assert transient_failure_evidence('word_clocks', 'gibberish_payload') == {
        'stage': 'word_clocks',
        'reason': 'unknown',
    }


def test_evidence_grid_assemble_words_staged_audio_invalid():
    assert transient_failure_evidence('assemble_words', 'staged_audio_invalid') == {
        'stage': 'assemble_words',
        'reason': 'staged_audio_invalid',
    }


def test_evidence_grid_assemble_words_retained_audio_invalid():
    assert transient_failure_evidence('assemble_words', 'retained_audio_invalid') == {
        'stage': 'assemble_words',
        'reason': 'retained_audio_invalid',
    }


def test_evidence_grid_assemble_words_decoded_duration_mismatch():
    assert transient_failure_evidence('assemble_words', 'decoded_duration_mismatch') == {
        'stage': 'assemble_words',
        'reason': 'decoded_duration_mismatch',
    }


def test_evidence_grid_assemble_words_word_shape():
    assert transient_failure_evidence('assemble_words', 'word_shape') == {
        'stage': 'assemble_words',
        'reason': 'word_shape',
    }


def test_evidence_grid_assemble_words_word_clock():
    assert transient_failure_evidence('assemble_words', 'word_clock') == {
        'stage': 'assemble_words',
        'reason': 'word_clock',
    }


def test_evidence_grid_assemble_words_word_sequence():
    assert transient_failure_evidence('assemble_words', 'word_sequence') == {
        'stage': 'assemble_words',
        'reason': 'word_sequence',
    }


def test_evidence_grid_assemble_words_vad_nonfinite():
    assert transient_failure_evidence('assemble_words', 'vad_nonfinite') == {
        'stage': 'assemble_words',
        'reason': 'vad_nonfinite',
    }


def test_evidence_grid_assemble_words_vad_order():
    assert transient_failure_evidence('assemble_words', 'vad_order') == {
        'stage': 'assemble_words',
        'reason': 'vad_order',
    }


def test_evidence_grid_assemble_words_vad_bounds():
    assert transient_failure_evidence('assemble_words', 'vad_bounds') == {
        'stage': 'assemble_words',
        'reason': 'vad_bounds',
    }


def test_evidence_grid_assemble_words_empty_asr():
    assert transient_failure_evidence('assemble_words', 'empty_asr') == {
        'stage': 'assemble_words',
        'reason': 'empty_asr',
    }


def test_evidence_grid_assemble_words_no_owned_words():
    assert transient_failure_evidence('assemble_words', 'no_owned_words') == {
        'stage': 'assemble_words',
        'reason': 'no_owned_words',
    }


def test_evidence_grid_assemble_words_unsupported_language():
    assert transient_failure_evidence('assemble_words', 'unsupported_language') == {
        'stage': 'assemble_words',
        'reason': 'unsupported_language',
    }


def test_evidence_grid_assemble_words_outside_admitted_source():
    assert transient_failure_evidence('assemble_words', 'outside_admitted_source') == {
        'stage': 'assemble_words',
        'reason': 'outside_admitted_source',
    }


def test_evidence_grid_assemble_words_unknown():
    assert transient_failure_evidence('assemble_words', 'unknown') == {'stage': 'assemble_words', 'reason': 'unknown'}


def test_evidence_grid_assemble_words_gibberish_payload():
    assert transient_failure_evidence('assemble_words', 'gibberish_payload') == {
        'stage': 'assemble_words',
        'reason': 'unknown',
    }


def test_evidence_grid_asr_recovery_staged_audio_invalid():
    assert transient_failure_evidence('asr_recovery', 'staged_audio_invalid') == {
        'stage': 'asr_recovery',
        'reason': 'staged_audio_invalid',
    }


def test_evidence_grid_asr_recovery_retained_audio_invalid():
    assert transient_failure_evidence('asr_recovery', 'retained_audio_invalid') == {
        'stage': 'asr_recovery',
        'reason': 'retained_audio_invalid',
    }


def test_evidence_grid_asr_recovery_decoded_duration_mismatch():
    assert transient_failure_evidence('asr_recovery', 'decoded_duration_mismatch') == {
        'stage': 'asr_recovery',
        'reason': 'decoded_duration_mismatch',
    }


def test_evidence_grid_asr_recovery_word_shape():
    assert transient_failure_evidence('asr_recovery', 'word_shape') == {'stage': 'asr_recovery', 'reason': 'word_shape'}


def test_evidence_grid_asr_recovery_word_clock():
    assert transient_failure_evidence('asr_recovery', 'word_clock') == {'stage': 'asr_recovery', 'reason': 'word_clock'}


def test_evidence_grid_asr_recovery_word_sequence():
    assert transient_failure_evidence('asr_recovery', 'word_sequence') == {
        'stage': 'asr_recovery',
        'reason': 'word_sequence',
    }


def test_evidence_grid_asr_recovery_vad_nonfinite():
    assert transient_failure_evidence('asr_recovery', 'vad_nonfinite') == {
        'stage': 'asr_recovery',
        'reason': 'vad_nonfinite',
    }


def test_evidence_grid_asr_recovery_vad_order():
    assert transient_failure_evidence('asr_recovery', 'vad_order') == {'stage': 'asr_recovery', 'reason': 'vad_order'}


def test_evidence_grid_asr_recovery_vad_bounds():
    assert transient_failure_evidence('asr_recovery', 'vad_bounds') == {'stage': 'asr_recovery', 'reason': 'vad_bounds'}


def test_evidence_grid_asr_recovery_empty_asr():
    assert transient_failure_evidence('asr_recovery', 'empty_asr') == {'stage': 'asr_recovery', 'reason': 'empty_asr'}


def test_evidence_grid_asr_recovery_no_owned_words():
    assert transient_failure_evidence('asr_recovery', 'no_owned_words') == {
        'stage': 'asr_recovery',
        'reason': 'no_owned_words',
    }


def test_evidence_grid_asr_recovery_unsupported_language():
    assert transient_failure_evidence('asr_recovery', 'unsupported_language') == {
        'stage': 'asr_recovery',
        'reason': 'unsupported_language',
    }


def test_evidence_grid_asr_recovery_outside_admitted_source():
    assert transient_failure_evidence('asr_recovery', 'outside_admitted_source') == {
        'stage': 'asr_recovery',
        'reason': 'outside_admitted_source',
    }


def test_evidence_grid_asr_recovery_unknown():
    assert transient_failure_evidence('asr_recovery', 'unknown') == {'stage': 'asr_recovery', 'reason': 'unknown'}


def test_evidence_grid_asr_recovery_gibberish_payload():
    assert transient_failure_evidence('asr_recovery', 'gibberish_payload') == {
        'stage': 'asr_recovery',
        'reason': 'unknown',
    }


def test_evidence_grid_unknown_staged_audio_invalid():
    assert transient_failure_evidence('unknown', 'staged_audio_invalid') == None


def test_evidence_grid_unknown_retained_audio_invalid():
    assert transient_failure_evidence('unknown', 'retained_audio_invalid') == None


def test_evidence_grid_unknown_decoded_duration_mismatch():
    assert transient_failure_evidence('unknown', 'decoded_duration_mismatch') == None


def test_evidence_grid_unknown_word_shape():
    assert transient_failure_evidence('unknown', 'word_shape') == None


def test_evidence_grid_unknown_word_clock():
    assert transient_failure_evidence('unknown', 'word_clock') == None


def test_evidence_grid_unknown_word_sequence():
    assert transient_failure_evidence('unknown', 'word_sequence') == None


def test_evidence_grid_unknown_vad_nonfinite():
    assert transient_failure_evidence('unknown', 'vad_nonfinite') == None


def test_evidence_grid_unknown_vad_order():
    assert transient_failure_evidence('unknown', 'vad_order') == None


def test_evidence_grid_unknown_vad_bounds():
    assert transient_failure_evidence('unknown', 'vad_bounds') == None


def test_evidence_grid_unknown_empty_asr():
    assert transient_failure_evidence('unknown', 'empty_asr') == None


def test_evidence_grid_unknown_no_owned_words():
    assert transient_failure_evidence('unknown', 'no_owned_words') == None


def test_evidence_grid_unknown_unsupported_language():
    assert transient_failure_evidence('unknown', 'unsupported_language') == None


def test_evidence_grid_unknown_outside_admitted_source():
    assert transient_failure_evidence('unknown', 'outside_admitted_source') == None


def test_evidence_grid_unknown_unknown():
    assert transient_failure_evidence('unknown', 'unknown') == None


def test_evidence_grid_unknown_gibberish_payload():
    assert transient_failure_evidence('unknown', 'gibberish_payload') == None


def test_evidence_grid_asr_staged_audio_invalid():
    assert transient_failure_evidence('asr', 'staged_audio_invalid') == None


def test_evidence_grid_asr_retained_audio_invalid():
    assert transient_failure_evidence('asr', 'retained_audio_invalid') == None


def test_evidence_grid_asr_decoded_duration_mismatch():
    assert transient_failure_evidence('asr', 'decoded_duration_mismatch') == None


def test_evidence_grid_asr_word_shape():
    assert transient_failure_evidence('asr', 'word_shape') == None


def test_evidence_grid_asr_word_clock():
    assert transient_failure_evidence('asr', 'word_clock') == None


def test_evidence_grid_asr_word_sequence():
    assert transient_failure_evidence('asr', 'word_sequence') == None


def test_evidence_grid_asr_vad_nonfinite():
    assert transient_failure_evidence('asr', 'vad_nonfinite') == None


def test_evidence_grid_asr_vad_order():
    assert transient_failure_evidence('asr', 'vad_order') == None


def test_evidence_grid_asr_vad_bounds():
    assert transient_failure_evidence('asr', 'vad_bounds') == None


def test_evidence_grid_asr_empty_asr():
    assert transient_failure_evidence('asr', 'empty_asr') == None


def test_evidence_grid_asr_no_owned_words():
    assert transient_failure_evidence('asr', 'no_owned_words') == None


def test_evidence_grid_asr_unsupported_language():
    assert transient_failure_evidence('asr', 'unsupported_language') == None


def test_evidence_grid_asr_outside_admitted_source():
    assert transient_failure_evidence('asr', 'outside_admitted_source') == None


def test_evidence_grid_asr_unknown():
    assert transient_failure_evidence('asr', 'unknown') == None


def test_evidence_grid_asr_gibberish_payload():
    assert transient_failure_evidence('asr', 'gibberish_payload') == None


def test_evidence_grid_persist_staged_audio_invalid():
    assert transient_failure_evidence('persist', 'staged_audio_invalid') == {
        'stage': 'persist',
        'reason': 'staged_audio_invalid',
    }


def test_evidence_grid_persist_retained_audio_invalid():
    assert transient_failure_evidence('persist', 'retained_audio_invalid') == {
        'stage': 'persist',
        'reason': 'retained_audio_invalid',
    }


def test_evidence_grid_persist_decoded_duration_mismatch():
    assert transient_failure_evidence('persist', 'decoded_duration_mismatch') == {
        'stage': 'persist',
        'reason': 'decoded_duration_mismatch',
    }


def test_evidence_grid_persist_word_shape():
    assert transient_failure_evidence('persist', 'word_shape') == {'stage': 'persist', 'reason': 'word_shape'}


def test_evidence_grid_persist_word_clock():
    assert transient_failure_evidence('persist', 'word_clock') == {'stage': 'persist', 'reason': 'word_clock'}


def test_evidence_grid_persist_word_sequence():
    assert transient_failure_evidence('persist', 'word_sequence') == {'stage': 'persist', 'reason': 'word_sequence'}


def test_evidence_grid_persist_vad_nonfinite():
    assert transient_failure_evidence('persist', 'vad_nonfinite') == {'stage': 'persist', 'reason': 'vad_nonfinite'}


def test_evidence_grid_persist_vad_order():
    assert transient_failure_evidence('persist', 'vad_order') == {'stage': 'persist', 'reason': 'vad_order'}


def test_evidence_grid_persist_vad_bounds():
    assert transient_failure_evidence('persist', 'vad_bounds') == {'stage': 'persist', 'reason': 'vad_bounds'}


def test_evidence_grid_persist_empty_asr():
    assert transient_failure_evidence('persist', 'empty_asr') == {'stage': 'persist', 'reason': 'empty_asr'}


def test_evidence_grid_persist_no_owned_words():
    assert transient_failure_evidence('persist', 'no_owned_words') == {'stage': 'persist', 'reason': 'no_owned_words'}


def test_evidence_grid_persist_unsupported_language():
    assert transient_failure_evidence('persist', 'unsupported_language') == {
        'stage': 'persist',
        'reason': 'unsupported_language',
    }


def test_evidence_grid_persist_outside_admitted_source():
    assert transient_failure_evidence('persist', 'outside_admitted_source') == {
        'stage': 'persist',
        'reason': 'outside_admitted_source',
    }


def test_evidence_grid_persist_unknown():
    assert transient_failure_evidence('persist', 'unknown') == {'stage': 'persist', 'reason': 'unknown'}


def test_evidence_grid_persist_gibberish_payload():
    assert transient_failure_evidence('persist', 'gibberish_payload') == {'stage': 'persist', 'reason': 'unknown'}


def test_evidence_grid_diarize_staged_audio_invalid():
    assert transient_failure_evidence('diarize', 'staged_audio_invalid') == None


def test_evidence_grid_diarize_retained_audio_invalid():
    assert transient_failure_evidence('diarize', 'retained_audio_invalid') == None


def test_evidence_grid_diarize_decoded_duration_mismatch():
    assert transient_failure_evidence('diarize', 'decoded_duration_mismatch') == None


def test_evidence_grid_diarize_word_shape():
    assert transient_failure_evidence('diarize', 'word_shape') == None


def test_evidence_grid_diarize_word_clock():
    assert transient_failure_evidence('diarize', 'word_clock') == None


def test_evidence_grid_diarize_word_sequence():
    assert transient_failure_evidence('diarize', 'word_sequence') == None


def test_evidence_grid_diarize_vad_nonfinite():
    assert transient_failure_evidence('diarize', 'vad_nonfinite') == None


def test_evidence_grid_diarize_vad_order():
    assert transient_failure_evidence('diarize', 'vad_order') == None


def test_evidence_grid_diarize_vad_bounds():
    assert transient_failure_evidence('diarize', 'vad_bounds') == None


def test_evidence_grid_diarize_empty_asr():
    assert transient_failure_evidence('diarize', 'empty_asr') == None


def test_evidence_grid_diarize_no_owned_words():
    assert transient_failure_evidence('diarize', 'no_owned_words') == None


def test_evidence_grid_diarize_unsupported_language():
    assert transient_failure_evidence('diarize', 'unsupported_language') == None


def test_evidence_grid_diarize_outside_admitted_source():
    assert transient_failure_evidence('diarize', 'outside_admitted_source') == None


def test_evidence_grid_diarize_unknown():
    assert transient_failure_evidence('diarize', 'unknown') == None


def test_evidence_grid_diarize_gibberish_payload():
    assert transient_failure_evidence('diarize', 'gibberish_payload') == None


def test_evidence_validator_accepts_fetch_decode_unknown():
    validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': 'unknown'})


def test_evidence_validator_accepts_fetch_decode_empty_asr():
    validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': 'empty_asr'})


def test_evidence_validator_accepts_fetch_decode_vad_bounds():
    validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': 'vad_bounds'})


def test_evidence_validator_accepts_fetch_decode_word_clock():
    validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': 'word_clock'})


def test_evidence_validator_accepts_vad_windows_unknown():
    validate_worker_failure_evidence({'stage': 'vad_windows', 'reason': 'unknown'})


def test_evidence_validator_accepts_vad_windows_empty_asr():
    validate_worker_failure_evidence({'stage': 'vad_windows', 'reason': 'empty_asr'})


def test_evidence_validator_accepts_vad_windows_vad_bounds():
    validate_worker_failure_evidence({'stage': 'vad_windows', 'reason': 'vad_bounds'})


def test_evidence_validator_accepts_vad_windows_word_clock():
    validate_worker_failure_evidence({'stage': 'vad_windows', 'reason': 'word_clock'})


def test_evidence_validator_accepts_word_clocks_unknown():
    validate_worker_failure_evidence({'stage': 'word_clocks', 'reason': 'unknown'})


def test_evidence_validator_accepts_word_clocks_empty_asr():
    validate_worker_failure_evidence({'stage': 'word_clocks', 'reason': 'empty_asr'})


def test_evidence_validator_accepts_word_clocks_vad_bounds():
    validate_worker_failure_evidence({'stage': 'word_clocks', 'reason': 'vad_bounds'})


def test_evidence_validator_accepts_word_clocks_word_clock():
    validate_worker_failure_evidence({'stage': 'word_clocks', 'reason': 'word_clock'})


def test_evidence_validator_accepts_assemble_words_unknown():
    validate_worker_failure_evidence({'stage': 'assemble_words', 'reason': 'unknown'})


def test_evidence_validator_accepts_assemble_words_empty_asr():
    validate_worker_failure_evidence({'stage': 'assemble_words', 'reason': 'empty_asr'})


def test_evidence_validator_accepts_assemble_words_vad_bounds():
    validate_worker_failure_evidence({'stage': 'assemble_words', 'reason': 'vad_bounds'})


def test_evidence_validator_accepts_assemble_words_word_clock():
    validate_worker_failure_evidence({'stage': 'assemble_words', 'reason': 'word_clock'})


def test_evidence_validator_accepts_asr_recovery_unknown():
    validate_worker_failure_evidence({'stage': 'asr_recovery', 'reason': 'unknown'})


def test_evidence_validator_accepts_asr_recovery_empty_asr():
    validate_worker_failure_evidence({'stage': 'asr_recovery', 'reason': 'empty_asr'})


def test_evidence_validator_accepts_asr_recovery_vad_bounds():
    validate_worker_failure_evidence({'stage': 'asr_recovery', 'reason': 'vad_bounds'})


def test_evidence_validator_accepts_asr_recovery_word_clock():
    validate_worker_failure_evidence({'stage': 'asr_recovery', 'reason': 'word_clock'})


def test_terminal_gate_rejects_unknown_fetch_decode():
    with pytest.raises(ValueError):
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'unknown'})


def test_terminal_gate_accepts_typed_fetch_decode():
    validate_worker_failure({'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'})


def test_terminal_gate_rejects_unknown_vad_windows():
    with pytest.raises(ValueError):
        validate_worker_failure({'stage': 'vad_windows', 'reason': 'unknown'})


def test_terminal_gate_accepts_typed_vad_windows():
    validate_worker_failure({'stage': 'vad_windows', 'reason': 'vad_bounds'})


def test_terminal_gate_rejects_unknown_word_clocks():
    with pytest.raises(ValueError):
        validate_worker_failure({'stage': 'word_clocks', 'reason': 'unknown'})


def test_terminal_gate_accepts_typed_word_clocks():
    validate_worker_failure({'stage': 'word_clocks', 'reason': 'word_clock'})


def test_terminal_gate_rejects_unknown_assemble_words():
    with pytest.raises(ValueError):
        validate_worker_failure({'stage': 'assemble_words', 'reason': 'unknown'})


def test_terminal_gate_accepts_typed_assemble_words():
    validate_worker_failure({'stage': 'assemble_words', 'reason': 'empty_asr'})


def test_terminal_gate_rejects_unknown_asr_recovery():
    with pytest.raises(ValueError):
        validate_worker_failure({'stage': 'asr_recovery', 'reason': 'unknown'})


def test_terminal_gate_accepts_typed_asr_recovery():
    validate_worker_failure({'stage': 'asr_recovery', 'reason': 'empty_asr'})


def test_predicates_reject_unknown_fetch_decode():
    diagnosis = {'stage': 'fetch_decode', 'reason': 'unknown'}
    assert language_guard_redrive_failure(diagnosis) is False
    assert empty_ladder_recovery_failure(diagnosis) is False
    assert validation_disposition_failure(diagnosis, disposition_enabled=True) is False


def test_predicates_reject_unknown_vad_windows():
    diagnosis = {'stage': 'vad_windows', 'reason': 'unknown'}
    assert language_guard_redrive_failure(diagnosis) is False
    assert empty_ladder_recovery_failure(diagnosis) is False
    assert validation_disposition_failure(diagnosis, disposition_enabled=True) is False


def test_predicates_reject_unknown_word_clocks():
    diagnosis = {'stage': 'word_clocks', 'reason': 'unknown'}
    assert language_guard_redrive_failure(diagnosis) is False
    assert empty_ladder_recovery_failure(diagnosis) is False
    assert validation_disposition_failure(diagnosis, disposition_enabled=True) is False


def test_predicates_reject_unknown_assemble_words():
    diagnosis = {'stage': 'assemble_words', 'reason': 'unknown'}
    assert language_guard_redrive_failure(diagnosis) is False
    assert empty_ladder_recovery_failure(diagnosis) is False
    assert validation_disposition_failure(diagnosis, disposition_enabled=True) is False


def test_predicates_reject_unknown_asr_recovery():
    diagnosis = {'stage': 'asr_recovery', 'reason': 'unknown'}
    assert language_guard_redrive_failure(diagnosis) is False
    assert empty_ladder_recovery_failure(diagnosis) is False
    assert validation_disposition_failure(diagnosis, disposition_enabled=True) is False


def test_predicates_reject_unknown_unknown():
    diagnosis = {'stage': 'unknown', 'reason': 'unknown'}
    assert language_guard_redrive_failure(diagnosis) is False
    assert empty_ladder_recovery_failure(diagnosis) is False
    assert validation_disposition_failure(diagnosis, disposition_enabled=True) is False


def test_predicate_language_guard_hostile_none():
    shape = None
    assert language_guard_redrive_failure(shape) is False


def test_predicate_language_guard_hostile_empty_dict():
    shape = {}
    assert language_guard_redrive_failure(shape) is False


def test_predicate_language_guard_hostile_missing_reason():
    shape = {'stage': 'vad_windows'}
    assert language_guard_redrive_failure(shape) is False


def test_predicate_language_guard_hostile_extra_key():
    shape = {'stage': 'vad_windows', 'reason': 'unknown', 'site': 'x.py:1'}
    assert language_guard_redrive_failure(shape) is False


def test_predicate_language_guard_hostile_none_reason():
    shape = {'stage': 'vad_windows', 'reason': None}
    assert language_guard_redrive_failure(shape) is False


def test_predicate_language_guard_hostile_int_stage():
    shape = {5: 'vad_windows', 'reason': 'unknown'}
    assert language_guard_redrive_failure(shape) is False


def test_predicate_language_guard_hostile_plain_string():
    shape = 'vad_windows:unknown'
    assert language_guard_redrive_failure(shape) is False


def test_predicate_empty_ladder_hostile_none():
    shape = None
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_empty_ladder_hostile_empty_dict():
    shape = {}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_empty_ladder_hostile_missing_reason():
    shape = {'stage': 'vad_windows'}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_empty_ladder_hostile_extra_key():
    shape = {'stage': 'vad_windows', 'reason': 'unknown', 'site': 'x.py:1'}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_empty_ladder_hostile_none_reason():
    shape = {'stage': 'vad_windows', 'reason': None}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_empty_ladder_hostile_int_stage():
    shape = {5: 'vad_windows', 'reason': 'unknown'}
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_empty_ladder_hostile_plain_string():
    shape = 'vad_windows:unknown'
    assert empty_ladder_recovery_failure(shape) is False


def test_predicate_disposition_hostile_none():
    shape = None
    assert validation_disposition_failure(shape, disposition_enabled=True) is False


def test_predicate_disposition_hostile_empty_dict():
    shape = {}
    assert validation_disposition_failure(shape, disposition_enabled=True) is False


def test_predicate_disposition_hostile_missing_reason():
    shape = {'stage': 'vad_windows'}
    assert validation_disposition_failure(shape, disposition_enabled=True) is False


def test_predicate_disposition_hostile_extra_key():
    shape = {'stage': 'vad_windows', 'reason': 'unknown', 'site': 'x.py:1'}
    assert validation_disposition_failure(shape, disposition_enabled=True) is False


def test_predicate_disposition_hostile_none_reason():
    shape = {'stage': 'vad_windows', 'reason': None}
    assert validation_disposition_failure(shape, disposition_enabled=True) is False


def test_predicate_disposition_hostile_int_stage():
    shape = {5: 'vad_windows', 'reason': 'unknown'}
    assert validation_disposition_failure(shape, disposition_enabled=True) is False


def test_predicate_disposition_hostile_plain_string():
    shape = 'vad_windows:unknown'
    assert validation_disposition_failure(shape, disposition_enabled=True) is False


def test_stage_vocabulary_fetch_decode():
    assert 'fetch_decode' in WORKER_VALIDATION_STAGES
    assert WorkerValidationStage('fetch_decode').value == 'fetch_decode'


def test_stage_vocabulary_vad_windows():
    assert 'vad_windows' in WORKER_VALIDATION_STAGES
    assert WorkerValidationStage('vad_windows').value == 'vad_windows'


def test_stage_vocabulary_word_clocks():
    assert 'word_clocks' in WORKER_VALIDATION_STAGES
    assert WorkerValidationStage('word_clocks').value == 'word_clocks'


def test_stage_vocabulary_assemble_words():
    assert 'assemble_words' in WORKER_VALIDATION_STAGES
    assert WorkerValidationStage('assemble_words').value == 'assemble_words'


def test_stage_vocabulary_asr_recovery():
    assert 'asr_recovery' in WORKER_VALIDATION_STAGES
    assert WorkerValidationStage('asr_recovery').value == 'asr_recovery'


def test_reason_vocabulary_staged_audio_invalid():
    assert 'staged_audio_invalid' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('staged_audio_invalid').value == 'staged_audio_invalid'


def test_reason_vocabulary_retained_audio_invalid():
    assert 'retained_audio_invalid' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('retained_audio_invalid').value == 'retained_audio_invalid'


def test_reason_vocabulary_decoded_duration_mismatch():
    assert 'decoded_duration_mismatch' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('decoded_duration_mismatch').value == 'decoded_duration_mismatch'


def test_reason_vocabulary_word_shape():
    assert 'word_shape' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('word_shape').value == 'word_shape'


def test_reason_vocabulary_word_clock():
    assert 'word_clock' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('word_clock').value == 'word_clock'


def test_reason_vocabulary_word_sequence():
    assert 'word_sequence' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('word_sequence').value == 'word_sequence'


def test_reason_vocabulary_vad_nonfinite():
    assert 'vad_nonfinite' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('vad_nonfinite').value == 'vad_nonfinite'


def test_reason_vocabulary_vad_order():
    assert 'vad_order' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('vad_order').value == 'vad_order'


def test_reason_vocabulary_vad_bounds():
    assert 'vad_bounds' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('vad_bounds').value == 'vad_bounds'


def test_reason_vocabulary_empty_asr():
    assert 'empty_asr' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('empty_asr').value == 'empty_asr'


def test_reason_vocabulary_no_owned_words():
    assert 'no_owned_words' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('no_owned_words').value == 'no_owned_words'


def test_reason_vocabulary_unsupported_language():
    assert 'unsupported_language' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('unsupported_language').value == 'unsupported_language'


def test_reason_vocabulary_outside_admitted_source():
    assert 'outside_admitted_source' in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason('outside_admitted_source').value == 'outside_admitted_source'


def test_reason_label_vad_bounds():
    assert reason_label(ReasonFamily.WORKER_VALIDATION, 'vad_bounds', WorkerValidationReason) == 'vad_bounds'


def test_reason_label_gibberish():
    assert reason_label(ReasonFamily.WORKER_VALIDATION, 'gibberish', WorkerValidationReason) == 'unknown'


def test_reason_label_nonstring_None():
    assert reason_label(ReasonFamily.WORKER_VALIDATION, None, WorkerValidationReason) == 'unknown'


def test_reason_label_nonstring_5():
    assert reason_label(ReasonFamily.WORKER_VALIDATION, 5, WorkerValidationReason) == 'unknown'


def _site_helper():
    raise RuntimeError('secret payload never surfaces')


def test_site_field_names_this_file():
    try:
        _site_helper()
    except RuntimeError as error:
        site = error_site_field(error)
    assert site.startswith(' site=')
    assert 'secret' not in site


def test_site_field_is_basename_only():
    try:
        _site_helper()
    except RuntimeError as error:
        site = error_site_field(error)
    assert '/' not in site
    assert ':' in site


def test_site_field_empty_without_traceback():
    error = RuntimeError('bare')
    assert error_site_field(error) == ''


def test_site_field_walks_the_raised_error_only():
    try:
        _site_helper()
    except RuntimeError as error:
        site = error_site_field(error)
    assert site == ' site=' + __file__.rsplit('/', 1)[-1] + ':' + str(_site_helper.__code__.co_firstlineno + 1)


def test_site_field_never_contains_the_message_of_a_value_error():
    try:
        raise ValueError('owner-id-123 leaked?')
    except ValueError as error:
        site = error_site_field(error)
    assert 'owner-id-123' not in site


def test_site_field_for_a_key_error_names_the_raise_site():
    try:
        {}['missing-key']
    except KeyError as error:
        site = error_site_field(error)
    assert 'missing-key' not in site
    assert site.startswith(' site=')
