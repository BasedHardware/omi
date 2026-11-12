#!/usr/bin/env python3
"""Frozen worker-failure evidence mappings at the persist boundary.

Every cell freezes ``transient_failure_evidence`` for one closed stage/reason pair or one hostile pair: closed evidence keeps its closed reason, anything off the closed vocabulary collapses to ``unknown`` or vanishes, and no exception text ever enters durable evidence. A failing cell means the evidence contract drifted.

Failure-Class: FC-persist-socket-transport-loss-discards-completed-gpu-results
"""

import pytest

from diarizer import batch_pipeline as bp
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage

STAGES = ['asr_recovery', 'assemble_words', 'fetch_decode', 'vad_windows', 'word_clocks']
REASONS = [
    'word_clock',
    'unsupported_language',
    'vad_bounds',
    'no_owned_words',
    'vad_nonfinite',
    'decoded_duration_mismatch',
    'retained_audio_invalid',
    'word_sequence',
    'empty_asr',
    'vad_order',
    'word_shape',
    'outside_admitted_source',
    'staged_audio_invalid',
]


def test_cell_0000():
    assert bp.transient_failure_evidence('asr_recovery', 'word_clock') == {
        'stage': 'asr_recovery',
        'reason': 'word_clock',
    }


def test_cell_0001():
    assert bp.transient_failure_evidence('asr_recovery', 'unsupported_language') == {
        'stage': 'asr_recovery',
        'reason': 'unsupported_language',
    }


def test_cell_0002():
    assert bp.transient_failure_evidence('asr_recovery', 'vad_bounds') == {
        'stage': 'asr_recovery',
        'reason': 'vad_bounds',
    }


def test_cell_0003():
    assert bp.transient_failure_evidence('asr_recovery', 'no_owned_words') == {
        'stage': 'asr_recovery',
        'reason': 'no_owned_words',
    }


def test_cell_0004():
    assert bp.transient_failure_evidence('asr_recovery', 'vad_nonfinite') == {
        'stage': 'asr_recovery',
        'reason': 'vad_nonfinite',
    }


def test_cell_0005():
    assert bp.transient_failure_evidence('asr_recovery', 'decoded_duration_mismatch') == {
        'stage': 'asr_recovery',
        'reason': 'decoded_duration_mismatch',
    }


def test_cell_0006():
    assert bp.transient_failure_evidence('asr_recovery', 'retained_audio_invalid') == {
        'stage': 'asr_recovery',
        'reason': 'retained_audio_invalid',
    }


def test_cell_0007():
    assert bp.transient_failure_evidence('asr_recovery', 'word_sequence') == {
        'stage': 'asr_recovery',
        'reason': 'word_sequence',
    }


def test_cell_0008():
    assert bp.transient_failure_evidence('asr_recovery', 'empty_asr') == {
        'stage': 'asr_recovery',
        'reason': 'empty_asr',
    }


def test_cell_0009():
    assert bp.transient_failure_evidence('asr_recovery', 'vad_order') == {
        'stage': 'asr_recovery',
        'reason': 'vad_order',
    }


def test_cell_0010():
    assert bp.transient_failure_evidence('asr_recovery', 'word_shape') == {
        'stage': 'asr_recovery',
        'reason': 'word_shape',
    }


def test_cell_0011():
    assert bp.transient_failure_evidence('asr_recovery', 'outside_admitted_source') == {
        'stage': 'asr_recovery',
        'reason': 'outside_admitted_source',
    }


def test_cell_0012():
    assert bp.transient_failure_evidence('asr_recovery', 'staged_audio_invalid') == {
        'stage': 'asr_recovery',
        'reason': 'staged_audio_invalid',
    }


def test_cell_0013():
    assert bp.transient_failure_evidence('assemble_words', 'word_clock') == {
        'stage': 'assemble_words',
        'reason': 'word_clock',
    }


def test_cell_0014():
    assert bp.transient_failure_evidence('assemble_words', 'unsupported_language') == {
        'stage': 'assemble_words',
        'reason': 'unsupported_language',
    }


def test_cell_0015():
    assert bp.transient_failure_evidence('assemble_words', 'vad_bounds') == {
        'stage': 'assemble_words',
        'reason': 'vad_bounds',
    }


def test_cell_0016():
    assert bp.transient_failure_evidence('assemble_words', 'no_owned_words') == {
        'stage': 'assemble_words',
        'reason': 'no_owned_words',
    }


def test_cell_0017():
    assert bp.transient_failure_evidence('assemble_words', 'vad_nonfinite') == {
        'stage': 'assemble_words',
        'reason': 'vad_nonfinite',
    }


def test_cell_0018():
    assert bp.transient_failure_evidence('assemble_words', 'decoded_duration_mismatch') == {
        'stage': 'assemble_words',
        'reason': 'decoded_duration_mismatch',
    }


def test_cell_0019():
    assert bp.transient_failure_evidence('assemble_words', 'retained_audio_invalid') == {
        'stage': 'assemble_words',
        'reason': 'retained_audio_invalid',
    }


def test_cell_0020():
    assert bp.transient_failure_evidence('assemble_words', 'word_sequence') == {
        'stage': 'assemble_words',
        'reason': 'word_sequence',
    }


def test_cell_0021():
    assert bp.transient_failure_evidence('assemble_words', 'empty_asr') == {
        'stage': 'assemble_words',
        'reason': 'empty_asr',
    }


def test_cell_0022():
    assert bp.transient_failure_evidence('assemble_words', 'vad_order') == {
        'stage': 'assemble_words',
        'reason': 'vad_order',
    }


def test_cell_0023():
    assert bp.transient_failure_evidence('assemble_words', 'word_shape') == {
        'stage': 'assemble_words',
        'reason': 'word_shape',
    }


def test_cell_0024():
    assert bp.transient_failure_evidence('assemble_words', 'outside_admitted_source') == {
        'stage': 'assemble_words',
        'reason': 'outside_admitted_source',
    }


def test_cell_0025():
    assert bp.transient_failure_evidence('assemble_words', 'staged_audio_invalid') == {
        'stage': 'assemble_words',
        'reason': 'staged_audio_invalid',
    }


def test_cell_0026():
    assert bp.transient_failure_evidence('fetch_decode', 'word_clock') == {
        'stage': 'fetch_decode',
        'reason': 'word_clock',
    }


def test_cell_0027():
    assert bp.transient_failure_evidence('fetch_decode', 'unsupported_language') == {
        'stage': 'fetch_decode',
        'reason': 'unsupported_language',
    }


def test_cell_0028():
    assert bp.transient_failure_evidence('fetch_decode', 'vad_bounds') == {
        'stage': 'fetch_decode',
        'reason': 'vad_bounds',
    }


def test_cell_0029():
    assert bp.transient_failure_evidence('fetch_decode', 'no_owned_words') == {
        'stage': 'fetch_decode',
        'reason': 'no_owned_words',
    }


def test_cell_0030():
    assert bp.transient_failure_evidence('fetch_decode', 'vad_nonfinite') == {
        'stage': 'fetch_decode',
        'reason': 'vad_nonfinite',
    }


def test_cell_0031():
    assert bp.transient_failure_evidence('fetch_decode', 'decoded_duration_mismatch') == {
        'stage': 'fetch_decode',
        'reason': 'decoded_duration_mismatch',
    }


def test_cell_0032():
    assert bp.transient_failure_evidence('fetch_decode', 'retained_audio_invalid') == {
        'stage': 'fetch_decode',
        'reason': 'retained_audio_invalid',
    }


def test_cell_0033():
    assert bp.transient_failure_evidence('fetch_decode', 'word_sequence') == {
        'stage': 'fetch_decode',
        'reason': 'word_sequence',
    }


def test_cell_0034():
    assert bp.transient_failure_evidence('fetch_decode', 'empty_asr') == {
        'stage': 'fetch_decode',
        'reason': 'empty_asr',
    }


def test_cell_0035():
    assert bp.transient_failure_evidence('fetch_decode', 'vad_order') == {
        'stage': 'fetch_decode',
        'reason': 'vad_order',
    }


def test_cell_0036():
    assert bp.transient_failure_evidence('fetch_decode', 'word_shape') == {
        'stage': 'fetch_decode',
        'reason': 'word_shape',
    }


def test_cell_0037():
    assert bp.transient_failure_evidence('fetch_decode', 'outside_admitted_source') == {
        'stage': 'fetch_decode',
        'reason': 'outside_admitted_source',
    }


def test_cell_0038():
    assert bp.transient_failure_evidence('fetch_decode', 'staged_audio_invalid') == {
        'stage': 'fetch_decode',
        'reason': 'staged_audio_invalid',
    }


def test_cell_0039():
    assert bp.transient_failure_evidence('vad_windows', 'word_clock') == {
        'stage': 'vad_windows',
        'reason': 'word_clock',
    }


def test_cell_0040():
    assert bp.transient_failure_evidence('vad_windows', 'unsupported_language') == {
        'stage': 'vad_windows',
        'reason': 'unsupported_language',
    }


def test_cell_0041():
    assert bp.transient_failure_evidence('vad_windows', 'vad_bounds') == {
        'stage': 'vad_windows',
        'reason': 'vad_bounds',
    }


def test_cell_0042():
    assert bp.transient_failure_evidence('vad_windows', 'no_owned_words') == {
        'stage': 'vad_windows',
        'reason': 'no_owned_words',
    }


def test_cell_0043():
    assert bp.transient_failure_evidence('vad_windows', 'vad_nonfinite') == {
        'stage': 'vad_windows',
        'reason': 'vad_nonfinite',
    }


def test_cell_0044():
    assert bp.transient_failure_evidence('vad_windows', 'decoded_duration_mismatch') == {
        'stage': 'vad_windows',
        'reason': 'decoded_duration_mismatch',
    }


def test_cell_0045():
    assert bp.transient_failure_evidence('vad_windows', 'retained_audio_invalid') == {
        'stage': 'vad_windows',
        'reason': 'retained_audio_invalid',
    }


def test_cell_0046():
    assert bp.transient_failure_evidence('vad_windows', 'word_sequence') == {
        'stage': 'vad_windows',
        'reason': 'word_sequence',
    }


def test_cell_0047():
    assert bp.transient_failure_evidence('vad_windows', 'empty_asr') == {'stage': 'vad_windows', 'reason': 'empty_asr'}


def test_cell_0048():
    assert bp.transient_failure_evidence('vad_windows', 'vad_order') == {'stage': 'vad_windows', 'reason': 'vad_order'}


def test_cell_0049():
    assert bp.transient_failure_evidence('vad_windows', 'word_shape') == {
        'stage': 'vad_windows',
        'reason': 'word_shape',
    }


def test_cell_0050():
    assert bp.transient_failure_evidence('vad_windows', 'outside_admitted_source') == {
        'stage': 'vad_windows',
        'reason': 'outside_admitted_source',
    }


def test_cell_0051():
    assert bp.transient_failure_evidence('vad_windows', 'staged_audio_invalid') == {
        'stage': 'vad_windows',
        'reason': 'staged_audio_invalid',
    }


def test_cell_0052():
    assert bp.transient_failure_evidence('word_clocks', 'word_clock') == {
        'stage': 'word_clocks',
        'reason': 'word_clock',
    }


def test_cell_0053():
    assert bp.transient_failure_evidence('word_clocks', 'unsupported_language') == {
        'stage': 'word_clocks',
        'reason': 'unsupported_language',
    }


def test_cell_0054():
    assert bp.transient_failure_evidence('word_clocks', 'vad_bounds') == {
        'stage': 'word_clocks',
        'reason': 'vad_bounds',
    }


def test_cell_0055():
    assert bp.transient_failure_evidence('word_clocks', 'no_owned_words') == {
        'stage': 'word_clocks',
        'reason': 'no_owned_words',
    }


def test_cell_0056():
    assert bp.transient_failure_evidence('word_clocks', 'vad_nonfinite') == {
        'stage': 'word_clocks',
        'reason': 'vad_nonfinite',
    }


def test_cell_0057():
    assert bp.transient_failure_evidence('word_clocks', 'decoded_duration_mismatch') == {
        'stage': 'word_clocks',
        'reason': 'decoded_duration_mismatch',
    }


def test_cell_0058():
    assert bp.transient_failure_evidence('word_clocks', 'retained_audio_invalid') == {
        'stage': 'word_clocks',
        'reason': 'retained_audio_invalid',
    }


def test_cell_0059():
    assert bp.transient_failure_evidence('word_clocks', 'word_sequence') == {
        'stage': 'word_clocks',
        'reason': 'word_sequence',
    }


def test_cell_0060():
    assert bp.transient_failure_evidence('word_clocks', 'empty_asr') == {'stage': 'word_clocks', 'reason': 'empty_asr'}


def test_cell_0061():
    assert bp.transient_failure_evidence('word_clocks', 'vad_order') == {'stage': 'word_clocks', 'reason': 'vad_order'}


def test_cell_0062():
    assert bp.transient_failure_evidence('word_clocks', 'word_shape') == {
        'stage': 'word_clocks',
        'reason': 'word_shape',
    }


def test_cell_0063():
    assert bp.transient_failure_evidence('word_clocks', 'outside_admitted_source') == {
        'stage': 'word_clocks',
        'reason': 'outside_admitted_source',
    }


def test_cell_0064():
    assert bp.transient_failure_evidence('word_clocks', 'staged_audio_invalid') == {
        'stage': 'word_clocks',
        'reason': 'staged_audio_invalid',
    }


def test_cell_0065():
    assert bp.transient_failure_evidence('asr_recovery', 'not_a_reason') == {
        'stage': 'asr_recovery',
        'reason': 'unknown',
    }


def test_cell_0066():
    assert bp.transient_failure_evidence('asr_recovery', '') == {'stage': 'asr_recovery', 'reason': 'unknown'}


def test_cell_0067():
    assert bp.transient_failure_evidence('asr_recovery', None) == {'stage': 'asr_recovery', 'reason': 'unknown'}


def test_cell_0068():
    assert bp.transient_failure_evidence('asr_recovery', 3.5) == {'stage': 'asr_recovery', 'reason': 'unknown'}


def test_cell_0069():
    assert bp.transient_failure_evidence('assemble_words', 'not_a_reason') == {
        'stage': 'assemble_words',
        'reason': 'unknown',
    }


def test_cell_0070():
    assert bp.transient_failure_evidence('assemble_words', '') == {'stage': 'assemble_words', 'reason': 'unknown'}


def test_cell_0071():
    assert bp.transient_failure_evidence('assemble_words', None) == {'stage': 'assemble_words', 'reason': 'unknown'}


def test_cell_0072():
    assert bp.transient_failure_evidence('assemble_words', 3.5) == {'stage': 'assemble_words', 'reason': 'unknown'}


def test_cell_0073():
    assert bp.transient_failure_evidence('fetch_decode', 'not_a_reason') == {
        'stage': 'fetch_decode',
        'reason': 'unknown',
    }


def test_cell_0074():
    assert bp.transient_failure_evidence('fetch_decode', '') == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_cell_0075():
    assert bp.transient_failure_evidence('fetch_decode', None) == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_cell_0076():
    assert bp.transient_failure_evidence('fetch_decode', 3.5) == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_cell_0077():
    assert bp.transient_failure_evidence('vad_windows', 'not_a_reason') == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_cell_0078():
    assert bp.transient_failure_evidence('vad_windows', '') == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_cell_0079():
    assert bp.transient_failure_evidence('vad_windows', None) == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_cell_0080():
    assert bp.transient_failure_evidence('vad_windows', 3.5) == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_cell_0081():
    assert bp.transient_failure_evidence('word_clocks', 'not_a_reason') == {'stage': 'word_clocks', 'reason': 'unknown'}


def test_cell_0082():
    assert bp.transient_failure_evidence('word_clocks', '') == {'stage': 'word_clocks', 'reason': 'unknown'}


def test_cell_0083():
    assert bp.transient_failure_evidence('word_clocks', None) == {'stage': 'word_clocks', 'reason': 'unknown'}


def test_cell_0084():
    assert bp.transient_failure_evidence('word_clocks', 3.5) == {'stage': 'word_clocks', 'reason': 'unknown'}


def test_cell_0085():
    assert bp.transient_failure_evidence('not_a_stage', 'not_a_reason') == None


def test_cell_0086():
    assert bp.transient_failure_evidence('not_a_stage', '') == None


def test_cell_0087():
    assert bp.transient_failure_evidence('not_a_stage', None) == None


def test_cell_0088():
    assert bp.transient_failure_evidence('not_a_stage', 3.5) == None


def test_cell_0089():
    assert bp.transient_failure_evidence('', 'not_a_reason') == None


def test_cell_0090():
    assert bp.transient_failure_evidence('', '') == None


def test_cell_0091():
    assert bp.transient_failure_evidence('', None) == None


def test_cell_0092():
    assert bp.transient_failure_evidence('', 3.5) == None


def test_cell_0093():
    assert bp.transient_failure_evidence(None, 'not_a_reason') == None


def test_cell_0094():
    assert bp.transient_failure_evidence(None, '') == None


def test_cell_0095():
    assert bp.transient_failure_evidence(None, None) == None


def test_cell_0096():
    assert bp.transient_failure_evidence(None, 3.5) == None


def test_cell_0097():
    assert bp.transient_failure_evidence(7, 'not_a_reason') == None


def test_cell_0098():
    assert bp.transient_failure_evidence(7, '') == None


def test_cell_0099():
    assert bp.transient_failure_evidence(7, None) == None


def test_cell_0100():
    assert bp.transient_failure_evidence(7, 3.5) == None
