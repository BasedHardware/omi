"""Pure helpers of the L4 flight-packing qualification (no GPU needed)."""

import numpy as np

from diarizer import batch_pipeline_flight_qualify as qualify

RATE = 16000


def turns(*spans):
    return [{'start': s, 'end': e, 'speaker': who} for s, e, who in spans]


def test_cut_units_cycles_lengths_and_keeps_only_a_real_remainder():
    samples = np.zeros(int(100.5 * RATE), dtype=np.float32)
    units = qualify.cut_units(samples, [23, 41])
    assert [len(u) / RATE for u in units] == [23, 41, 23, 13.5]
    # A sub-second tail is dropped rather than emitted as a degenerate unit.
    assert [len(u) / RATE for u in qualify.cut_units(np.zeros(int(23.5 * RATE)), [23])] == [23]


def test_speaker_agreement_is_label_invariant_and_time_weighted():
    serial = turns((0, 10, 'SPEAKER_00'), (10, 20, 'SPEAKER_01'))
    renamed = turns((0, 10, 'SPEAKER_01'), (10, 20, 'SPEAKER_00'))
    assert qualify.speaker_agreement(serial, renamed)['agreement'] == 1.0
    shifted = turns((0, 11, 'SPEAKER_00'), (11, 20, 'SPEAKER_01'))
    result = qualify.speaker_agreement(serial, shifted)
    assert result['reference_speakers'] == result['speakers'] == 2
    assert abs(result['agreement'] - 19 / 21) < 1e-9
    merged = turns((0, 20, 'SPEAKER_00'))
    assert qualify.speaker_agreement(serial, merged)['speakers'] == 1
    assert qualify.speaker_agreement([], [])['agreement'] == 1.0


def memory(serial_peak, packed_peak):
    def sample(peak):
        return {'gpu_allocated_baseline_bytes': 100, 'gpu_allocated_peak_bytes': 100 + peak}

    return {'serial': sample(serial_peak), 'packed': sample(packed_peak)}


def scored(speakers=2, agreement=1.0, packed_speakers=None, error=None):
    result = {
        'serial_speakers': speakers,
        'packed_speakers': speakers if packed_speakers is None else packed_speakers,
        'assignment_agreement': agreement,
    }
    if error:
        result['packed_error'] = error
    return result


def unit(i, *, packed=True, vad=True, speech_only=None, full_unit=None):
    return {
        'unit': i,
        'packed': packed,
        'vad_spans_equal': vad,
        'speech_only': speech_only or scored(),
        'full_unit': full_unit or scored(),
    }


def gate(units, mem=None, minimum=2, configuration='speech_only'):
    return qualify.evaluate_gate(
        units,
        configuration=configuration,
        min_agreement=0.99,
        min_multispeaker_units=minimum,
        max_peak_ratio=1.10,
        memory=mem or memory(10, 10),
    )


def test_gate_requires_equal_vad_speakers_agreement_memory_and_evidence():
    assert gate([unit(0), unit(1), unit(2, speech_only=scored(speakers=1))])['status'] == 'pass'
    assert gate([unit(0), unit(1, speech_only=scored(speakers=1))])['status'] == 'insufficient_evidence'
    assert gate([unit(0), unit(1, vad=False)])['status'] == 'fail'
    assert gate([unit(0), unit(1, speech_only=scored(packed_speakers=3))])['status'] == 'fail'
    assert gate([unit(0), unit(1, speech_only=scored(agreement=0.98))])['status'] == 'fail'
    assert gate([unit(0), unit(1, speech_only=scored(error='RuntimeError'))])['status'] == 'fail'
    assert gate([unit(0), unit(1)], mem=memory(10, 12))['status'] == 'fail'


def test_gate_fails_closed_when_a_unit_was_not_packed():
    # Recoverable segmentation fallback: serial VAD, matching turns, but nothing packed.
    result = gate([unit(0), unit(1), unit(2, packed=False)])
    assert result['status'] == 'fail' and 'not packed' in result['failures'][0]


def test_zero_serial_cuda_baseline_is_insufficient_evidence_not_a_pass():
    result = gate([unit(0), unit(1)], mem=memory(0, 10**9))
    assert result['status'] == 'insufficient_evidence'
    assert any('CUDA' in reason for reason in result['insufficient'])


def receipt(units, speech_only_mem=None, full_mem=None):
    return {
        'units': units,
        'memory': {'speech_only': speech_only_mem or memory(10, 10), 'full_unit': full_mem or memory(10, 10)},
    }


THRESHOLDS = dict(min_agreement=0.99, min_multispeaker_units=2, max_peak_ratio=1.10)


def test_full_unit_pass_never_authorizes_speech_only_deployments():
    units = [unit(0, speech_only=scored(agreement=0.5)), unit(1)]
    result, status = qualify.gate_receipt(receipt(units), speech_only=True, **THRESHOLDS)
    assert result['gates']['full_unit']['status'] == 'pass'
    assert result['authoritative'] == 'speech_only' and result['status'] == 'fail' and status == 1
    result, status = qualify.gate_receipt(receipt(units), speech_only=False, **THRESHOLDS)
    assert result['authoritative'] == 'full_unit' and status == 0
    thin = qualify.gate_receipt(
        receipt([unit(0), unit(1)], speech_only_mem=memory(0, 5)), speech_only=True, **THRESHOLDS
    )
    assert thin[1] == 2


def test_speech_only_reference_is_the_workers_compacted_call_with_env_restored(monkeypatch):
    monkeypatch.setenv(qualify.SPEECH_ONLY_ENV, 'false')
    harness = qualify._SpeechOnly(diarizer=object())
    seen = []
    harness.worker.diarize = lambda samples: seen.append(len(samples)) or {'turns': []}
    samples = np.zeros(60 * RATE, dtype=np.float32)
    harness(samples, [(10.0, 12.0), (40.0, 41.0)])
    # Sparse speech: the diarizer saw a compacted waveform, not the 60s unit.
    assert seen and seen[0] < len(samples)
    assert qualify.os.environ[qualify.SPEECH_ONLY_ENV] == 'false'
