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


def unit(i, speakers=2, agreement=1.0, vad=True, packed_speakers=None):
    return {
        'unit': i,
        'serial_speakers': speakers,
        'packed_speakers': speakers if packed_speakers is None else packed_speakers,
        'assignment_agreement': agreement,
        'vad_spans_equal': vad,
    }


def gate(units, mem=None, minimum=2):
    return qualify.evaluate_gate(
        units, min_agreement=0.99, min_multispeaker_units=minimum, max_peak_ratio=1.10, memory=mem or memory(10, 10)
    )


def test_gate_requires_equal_vad_speakers_agreement_memory_and_evidence():
    assert gate([unit(0), unit(1), unit(2, speakers=1)])['status'] == 'pass'
    assert gate([unit(0), unit(1, speakers=1)])['status'] == 'insufficient_evidence'
    assert gate([unit(0), unit(1, vad=False)])['status'] == 'fail'
    assert gate([unit(0), unit(1, packed_speakers=3)])['status'] == 'fail'
    assert gate([unit(0), unit(1, agreement=0.98)])['status'] == 'fail'
    assert gate([unit(0), unit(1)], mem=memory(10, 12))['status'] == 'fail'
