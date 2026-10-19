"""L4 enablement gate for BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED.

Paired run of the serial pyannote calls and the flight-packed path on the same
waveforms, the production community-1 revision and the worker's batch pin.
Run on one isolated dev L4 from ``backend/`` with HUGGINGFACE_TOKEN set:

    PYTHONPATH=. BATCH_PIPELINE_MODEL_BATCH_SIZE=8 python diarizer/batch_pipeline_flight_qualify.py \\
        --audio /public/ami/ES2004a.Mix-Headset.wav /public/pendant-two-voices.wav \\
        --unit-seconds 23,41,67,95,128,30.5,212 --output /receipts/flight-qualify.json

Inputs are canonical 16kHz mono PCM16 WAV (public or consented test audio only).
``--unit-seconds`` cuts each input into consecutive units of those lengths
(cycled), so a flight has mixed lengths and ragged last chunks share packed
forwards across units. The receipt holds timings, counts, hashes and agreement
numbers only; no audio, words or names.

Exit status: 0 gate passed, 1 gate failed, 2 insufficient multi-speaker evidence.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Sequence

import numpy as np

from scipy.optimize import linear_sum_assignment

try:
    import torch as _torch  # type: ignore[reportMissingImports]  # GPU runtime only
except ImportError:
    _torch = None

torch: Any = _torch

from diarizer.batch_pipeline import SAMPLE_RATE
from diarizer.batch_pipeline_flight import EMBEDDINGS_KEY, SEGMENTATION_KEY, FlightPyannote
from diarizer.batch_pipeline_models import PyannoteDiarizer, PyannoteVAD, decode_pcm16_wav
from diarizer.batch_pipeline_startup import DIARIZER_REVISION, ChainMemoryProbe, load_pyannote_pair

DEFAULT_UNIT_SECONDS = (23.0, 41.0, 67.0, 95.0, 128.0, 30.5, 212.0)


def cut_units(samples, unit_seconds: Sequence[float]):
    """Consecutive units of the cycled lengths; a trailing remainder >=1s is kept."""
    units, start, index = [], 0, 0
    while start < len(samples):
        stop = min(len(samples), start + int(unit_seconds[index % len(unit_seconds)] * SAMPLE_RATE))
        if stop - start >= SAMPLE_RATE:
            units.append(samples[start:stop])
        start, index = stop, index + 1
    return units


def _overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def speaker_agreement(reference: Sequence[dict], hypothesis: Sequence[dict]) -> dict:
    """Time-weighted agreement after the best one-to-one speaker mapping.

    agreement = mapped overlap / union of the two exclusive speech timelines.
    1.0 means identical turns up to label renaming.
    """
    ref_speakers = sorted({t['speaker'] for t in reference})
    hyp_speakers = sorted({t['speaker'] for t in hypothesis})
    ref_total = sum(t['end'] - t['start'] for t in reference)
    hyp_total = sum(t['end'] - t['start'] for t in hypothesis)
    if not ref_speakers or not hyp_speakers:
        same = not ref_speakers and not hyp_speakers
        return {
            'agreement': 1.0 if same else 0.0,
            'reference_speakers': len(ref_speakers),
            'speakers': len(hyp_speakers),
        }
    matrix = np.zeros((len(ref_speakers), len(hyp_speakers)))
    for r in reference:
        for h in hypothesis:
            matrix[ref_speakers.index(r['speaker']), hyp_speakers.index(h['speaker'])] += _overlap(
                (r['start'], r['end']), (h['start'], h['end'])
            )
    rows, cols = linear_sum_assignment(matrix, maximize=True)
    mapped = float(matrix[rows, cols].sum())
    union = ref_total + hyp_total - mapped
    return {
        'agreement': 1.0 if union <= 0 else mapped / union,
        'reference_speakers': len(ref_speakers),
        'speakers': len(hyp_speakers),
    }


def evaluate_gate(units: Sequence[dict], *, min_agreement, min_multispeaker_units, max_peak_ratio, memory) -> dict:
    multi = [u for u in units if u['serial_speakers'] >= 2]
    failures = []
    for u in units:
        if not u['vad_spans_equal']:
            failures.append(f"unit {u['unit']}: VAD spans differ")
        if u['serial_speakers'] != u['packed_speakers']:
            failures.append(f"unit {u['unit']}: speaker count {u['serial_speakers']} -> {u['packed_speakers']}")
        if u['serial_speakers'] >= 2 and u['assignment_agreement'] < min_agreement:
            failures.append(f"unit {u['unit']}: assignment agreement {u['assignment_agreement']:.5f}")
    serial_peak = memory['serial']['gpu_allocated_peak_bytes'] - memory['serial']['gpu_allocated_baseline_bytes']
    packed_peak = memory['packed']['gpu_allocated_peak_bytes'] - memory['packed']['gpu_allocated_baseline_bytes']
    if serial_peak > 0 and packed_peak > serial_peak * max_peak_ratio:
        failures.append(f'packed CUDA working-set peak {packed_peak} > {max_peak_ratio} x serial {serial_peak}')
    if failures:
        status = 'fail'
    elif len(multi) < min_multispeaker_units:
        status = 'insufficient_evidence'
    else:
        status = 'pass'
    return {'status': status, 'failures': failures, 'multispeaker_units': len(multi)}


def _file(samples):
    return {'waveform': torch.from_numpy(samples).unsqueeze(0), 'sample_rate': SAMPLE_RATE}


def _timed(probe, fn):
    baseline = probe.begin()
    started = time.perf_counter()
    result = fn()
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    return result, elapsed, probe.finish(baseline)


def run(paths, unit_seconds, budget_seconds, batch_size) -> dict[str, Any]:
    if torch is None or not torch.cuda.is_available():
        raise RuntimeError('qualification requires the batch GPU image on a CUDA device')
    diarizer, vad = load_pyannote_pair(batch_size)
    sources, clips = [], []
    for path in paths:
        body = Path(path).read_bytes()
        sources.append({'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)})
        clips.extend(cut_units(decode_pcm16_wav(body), unit_seconds))
    probe = ChainMemoryProbe()

    # Serial worker path first, before any feature hook is installed.
    serial, serial_s, serial_memory = _timed(
        probe, lambda: [(PyannoteVAD(vad)(c), PyannoteDiarizer(diarizer)(c)) for c in clips]
    )
    raw_serial = [diarizer._segmentation(_file(c)) for c in clips]
    flight = FlightPyannote.create(diarizer, vad, budget_seconds=budget_seconds)
    if flight is None:
        raise RuntimeError('flight packing refused this model layout; nothing to qualify')

    def packed_path():
        features = flight.segment(clips)
        spans = [flight.vad_spans(c, f) if f is not None else PyannoteVAD(vad)(c) for c, f in zip(clips, features)]
        return features, spans, flight.diarize_many(list(zip(clips, features)))

    (features, packed_spans, packed_diarization), packed_s, packed_memory = _timed(probe, packed_path)

    # Embedding comparison: one packed group (cross-unit tails) vs per-file serial.
    files = [_file(c) for c in clips]
    eligible = [i for i, f in enumerate(features) if f is not None and flight.speaking(f.segmentation)]
    packed_embeddings = (
        dict(
            zip(
                eligible,
                flight.embed_group([files[i] for i in eligible], [features[i].segmentation for i in eligible]),
            )
        )
        if flight.shared_trunk and eligible
        else {}
    )

    units = []
    for i, clip in enumerate(clips):
        (serial_spans, serial_turns), packed_turns = serial[i], packed_diarization[i]
        unit: dict[str, Any] = {
            'unit': i,
            'seconds': round(len(clip) / SAMPLE_RATE, 3),
            'packed': features[i] is not None,
        }
        if features[i] is not None:
            a, b = raw_serial[i].data, features[i].segmentation.data
            unit['segmentation_max_abs'] = float(np.max(np.abs(a - b))) if a.shape == b.shape else None
            unit['active_frame_disagreements'] = int(np.sum((a > 0.5) != (b > 0.5))) if a.shape == b.shape else None
        if i in packed_embeddings:
            file = {k: v for k, v in files[i].items() if k not in (SEGMENTATION_KEY, EMBEDDINGS_KEY)}
            reference = diarizer.get_embeddings(
                file, features[i].segmentation, exclude_overlap=diarizer.embedding_exclude_overlap
            )
            unit['embedding_max_abs'] = float(np.nanmax(np.abs(reference - packed_embeddings[i])))
            unit['embedding_nan_pattern_equal'] = bool(
                np.array_equal(np.isnan(reference), np.isnan(packed_embeddings[i]))
            )
        unit['vad_spans_equal'] = serial_spans == packed_spans[i]
        if isinstance(packed_turns, BaseException):
            unit.update(packed_error=type(packed_turns).__name__, packed_speakers=-1, assignment_agreement=0.0)
            unit['serial_speakers'] = len({t['speaker'] for t in serial_turns['turns']})
        else:
            agreement = speaker_agreement(serial_turns['turns'], packed_turns['turns'])
            unit.update(
                serial_speakers=agreement['reference_speakers'],
                packed_speakers=agreement['speakers'],
                assignment_agreement=agreement['agreement'],
                turns_identical=serial_turns['turns'] == packed_turns['turns'],
            )
        units.append(unit)
    return {
        'diarizer_revision': DIARIZER_REVISION,
        'model_batch_size': batch_size,
        'budget_seconds': budget_seconds,
        'device': torch.cuda.get_device_name(0),
        'torch': torch.__version__,
        'sources': sources,
        'units': units,
        'audio_seconds': round(sum(len(c) for c in clips) / SAMPLE_RATE, 3),
        'wall_seconds': {'serial': round(serial_s, 3), 'packed': round(packed_s, 3)},
        'memory': {'serial': serial_memory, 'packed': packed_memory},
        'flight_counts': dict(flight.counts),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='L4 enablement gate for flight-packed pyannote.')
    parser.add_argument('--audio', nargs='+', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--unit-seconds', default=','.join(str(s) for s in DEFAULT_UNIT_SECONDS))
    parser.add_argument('--budget-seconds', type=float, default=1800)
    parser.add_argument('--batch-size', type=int, default=int(os.getenv('BATCH_PIPELINE_MODEL_BATCH_SIZE', '8')))
    parser.add_argument('--min-agreement', type=float, default=0.99)
    parser.add_argument('--min-multispeaker-units', type=int, default=5)
    parser.add_argument('--max-peak-ratio', type=float, default=1.10)
    args = parser.parse_args(argv)
    receipt = run(
        args.audio,
        [float(v) for v in args.unit_seconds.split(',')],
        args.budget_seconds,
        args.batch_size,
    )
    receipt['gate'] = evaluate_gate(
        receipt['units'],
        min_agreement=args.min_agreement,
        min_multispeaker_units=args.min_multispeaker_units,
        max_peak_ratio=args.max_peak_ratio,
        memory=receipt['memory'],
    )
    receipt['gate']['thresholds'] = {
        'min_agreement': args.min_agreement,
        'min_multispeaker_units': args.min_multispeaker_units,
        'max_peak_ratio': args.max_peak_ratio,
    }
    Path(args.output).write_text(json.dumps(receipt, indent=1, sort_keys=True))
    print(json.dumps(receipt['gate'], indent=1))
    return {'pass': 0, 'fail': 1}.get(receipt['gate']['status'], 2)


if __name__ == '__main__':
    sys.exit(main())
