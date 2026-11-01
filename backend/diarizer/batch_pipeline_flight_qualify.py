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

Two configurations are scored, serial against flag-on, on the same waveforms:

* ``speech_only`` (the Helm default, BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED
  on): packed segmentation feeds VAD, then the worker's speech-only
  ``_diarize_unit`` diarizes the compacted waveform through the per-file
  shared-trunk hook, against the same call on an unpatched pipeline.
* ``full_unit`` (speech-only off): full-unit ``diarize_many`` against serial
  full-unit diarization, plus raw segmentation and embeddings captured on the
  unpatched pipeline.

The exit status comes from the configuration the deployment runs
(``--speech-only``, default from the env, else on). A ``full_unit`` pass never
authorizes the flag while speech-only stays on.

Exit status: 0 gate passed, 1 gate failed, 2 insufficient evidence (fewer
multi-speaker units than required, or no positive serial CUDA baseline).
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

from config.batch_pipeline_providers import ProviderConfig
from diarizer.batch_pipeline import SAMPLE_RATE, PipelineWorker, vad_speech_spans
from diarizer.batch_pipeline_flight import FlightPyannote
from diarizer.batch_pipeline_models import PyannoteDiarizer, PyannoteVAD, decode_pcm16_wav
from diarizer.batch_pipeline_startup import DIARIZER_REVISION, ChainMemoryProbe, load_pyannote_pair
from utils.batch_pipeline.diarization_gate import speech_regions

CONFIGURATIONS = ('speech_only', 'full_unit')
SPEECH_ONLY_ENV = 'BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED'

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


def _cuda_delta(sample) -> int:
    return int(sample['gpu_allocated_peak_bytes']) - int(sample['gpu_allocated_baseline_bytes'])


def evaluate_gate(
    units: Sequence[dict], *, configuration, min_agreement, min_multispeaker_units, max_peak_ratio, memory
) -> dict:
    """Fail closed: every unit must actually be packed and match serial."""
    if configuration not in CONFIGURATIONS:
        raise ValueError(f'unknown configuration {configuration!r}')
    failures, multi = [], 0
    for u in units:
        scored = u.get(configuration) or {}
        if not u.get('packed'):
            failures.append(f"unit {u['unit']}: not packed (flight features missing)")
        if not u.get('vad_spans_equal'):
            failures.append(f"unit {u['unit']}: VAD spans differ")
        if 'packed_error' in scored or not scored:
            failures.append(f"unit {u['unit']}: {configuration} diarization unavailable")
            continue
        if scored['serial_speakers'] != scored['packed_speakers']:
            failures.append(
                f"unit {u['unit']}: speaker count {scored['serial_speakers']} -> {scored['packed_speakers']}"
            )
        if scored['serial_speakers'] >= 2:
            multi += 1
            if scored['assignment_agreement'] < min_agreement:
                failures.append(f"unit {u['unit']}: assignment agreement {scored['assignment_agreement']:.5f}")
    serial_delta, packed_delta = _cuda_delta(memory['serial']), _cuda_delta(memory['packed'])
    if serial_delta > 0 and packed_delta > serial_delta * max_peak_ratio:
        failures.append(f'packed CUDA working-set peak {packed_delta} > {max_peak_ratio} x serial {serial_delta}')
    insufficient = []
    if multi < min_multispeaker_units:
        insufficient.append(f'{multi} multi-speaker units < {min_multispeaker_units}')
    if serial_delta <= 0:
        insufficient.append('serial CUDA working-set delta is not positive; memory ratio unmeasured')
    if not units:
        insufficient.append('no units')
    status = 'fail' if failures else ('insufficient_evidence' if insufficient else 'pass')
    return {
        'configuration': configuration,
        'status': status,
        'failures': failures,
        'insufficient': insufficient,
        'multispeaker_units': multi,
    }


def _file(samples):
    return {'waveform': torch.from_numpy(samples).unsqueeze(0), 'sample_rate': SAMPLE_RATE}


def _timed(probe, fn):
    baseline = probe.begin()
    started = time.perf_counter()
    result = fn()
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    return result, elapsed, probe.finish(baseline)


def _evidence(samples, spans):
    seconds = len(samples) / SAMPLE_RATE
    return speech_regions(vad_speech_spans(spans, len(samples)), [], seconds)


class _SpeechOnly:
    """The worker's own speech-only diarization call, with speech-only forced on."""

    def __init__(self, diarizer):
        self.worker = PipelineWorker(
            decode=lambda item: None,
            vad=lambda samples: [],
            words_providers={'parakeet': None},
            diarizers={'pyannote': PyannoteDiarizer(diarizer)},
            persist=lambda item, payload: None,
            config=ProviderConfig(),
            io_concurrency=1,
        )

    def __call__(self, samples, spans):
        previous = os.environ.get(SPEECH_ONLY_ENV)
        os.environ[SPEECH_ONLY_ENV] = 'true'
        try:
            # VAD-only evidence (no ASR in this harness); word clocks would only add speech.
            evidence = _evidence(samples, spans)
            return self.worker._diarize_unit(samples, evidence, [])  # pyright: ignore[reportPrivateUsage]
        finally:
            if previous is None:
                os.environ.pop(SPEECH_ONLY_ENV, None)
            else:
                os.environ[SPEECH_ONLY_ENV] = previous


def _score(serial_turns, packed) -> dict:
    if isinstance(packed, BaseException):
        return {
            'serial_speakers': len({t['speaker'] for t in serial_turns['turns']}),
            'packed_speakers': -1,
            'packed_error': type(packed).__name__,
        }
    agreement = speaker_agreement(serial_turns['turns'], packed['turns'])
    return {
        'serial_speakers': agreement['reference_speakers'],
        'packed_speakers': agreement['speakers'],
        'assignment_agreement': agreement['agreement'],
        'turns_identical': serial_turns['turns'] == packed['turns'],
    }


def _guarded(fn):
    try:
        return fn()
    except Exception as exc:  # recorded per unit, scored as a failure
        return exc


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
    speech_only = _SpeechOnly(diarizer)

    # ---- serial references, all on the unpatched pipeline (before create) ----
    def serial_speech_only():
        spans = [PyannoteVAD(vad)(c) for c in clips]
        return spans, [speech_only(c, s) for c, s in zip(clips, spans)]

    (serial_spans, serial_compact), serial_so_s, serial_so_mem = _timed(probe, serial_speech_only)
    serial_full, serial_full_s, serial_full_mem = _timed(
        probe, lambda: ([PyannoteVAD(vad)(c) for c in clips], [PyannoteDiarizer(diarizer)(c) for c in clips])
    )
    serial_full = serial_full[1]
    raw_serial = [diarizer._segmentation(_file(c)) for c in clips]
    files = [_file(c) for c in clips]
    serial_embeddings = {}
    for i, (file, segmentation) in enumerate(zip(files, raw_serial)):
        count = diarizer.speaker_count(segmentation, diarizer._segmentation.model.receptive_field, warm_up=(0.0, 0.0))
        if np.nanmax(count.data) > 0:
            serial_embeddings[i] = diarizer.get_embeddings(
                file, segmentation, exclude_overlap=diarizer.embedding_exclude_overlap
            )

    flight = FlightPyannote.create(diarizer, vad, budget_seconds=budget_seconds)
    if flight is None:
        raise RuntimeError('flight packing refused this model layout; nothing to qualify')

    # ---- flag on ----
    def packed_vad():
        features = flight.segment(clips)
        spans = [flight.vad_spans(c, f) if f is not None else PyannoteVAD(vad)(c) for c, f in zip(clips, features)]
        return features, spans

    def packed_speech_only():
        features, spans = packed_vad()
        return features, spans, [_guarded(lambda c=c, s=s: speech_only(c, s)) for c, s in zip(clips, spans)]

    (features, packed_spans, packed_compact), packed_so_s, packed_so_mem = _timed(probe, packed_speech_only)

    def packed_full_unit():
        features, _ = packed_vad()
        return features, flight.diarize_many(list(zip(clips, features)))

    (full_features, packed_full), packed_full_s, packed_full_mem = _timed(probe, packed_full_unit)
    eligible = [i for i, f in enumerate(full_features) if f is not None and i in serial_embeddings]
    packed_embeddings = (
        dict(
            zip(
                eligible,
                flight.embed_group([files[i] for i in eligible], [full_features[i].segmentation for i in eligible]),
            )
        )
        if flight.shared_trunk and eligible
        else {}
    )

    units = []
    for i, clip in enumerate(clips):
        unit: dict[str, Any] = {
            'unit': i,
            'seconds': round(len(clip) / SAMPLE_RATE, 3),
            'packed': features[i] is not None and full_features[i] is not None,
            'vad_spans_equal': serial_spans[i] == packed_spans[i],
            'speech_only': _score(serial_compact[i], packed_compact[i]),
            'full_unit': _score(serial_full[i], packed_full[i]),
        }
        if full_features[i] is not None:
            a, b = raw_serial[i].data, full_features[i].segmentation.data
            same = a.shape == b.shape
            unit['full_unit']['segmentation_max_abs'] = float(np.max(np.abs(a - b))) if same else None
            unit['full_unit']['active_frame_disagreements'] = int(np.sum((a > 0.5) != (b > 0.5))) if same else None
        if i in packed_embeddings:
            reference, packed = serial_embeddings[i], packed_embeddings[i]
            unit['full_unit']['embedding_max_abs'] = float(np.nanmax(np.abs(reference - packed)))
            unit['full_unit']['embedding_nan_pattern_equal'] = bool(
                np.array_equal(np.isnan(reference), np.isnan(packed))
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
        'wall_seconds': {
            'speech_only': {'serial': round(serial_so_s, 3), 'packed': round(packed_so_s, 3)},
            'full_unit': {'serial': round(serial_full_s, 3), 'packed': round(packed_full_s, 3)},
        },
        'memory': {
            'speech_only': {'serial': serial_so_mem, 'packed': packed_so_mem},
            'full_unit': {'serial': serial_full_mem, 'packed': packed_full_mem},
        },
        'flight_counts': dict(flight.counts),
    }


def gate_receipt(receipt, *, speech_only, **thresholds) -> tuple[dict, int]:
    gates = {
        configuration: evaluate_gate(
            receipt['units'], configuration=configuration, memory=receipt['memory'][configuration], **thresholds
        )
        for configuration in CONFIGURATIONS
    }
    authoritative = 'speech_only' if speech_only else 'full_unit'
    status: str = gates[authoritative]['status']
    result = {
        'authoritative': authoritative,
        'status': status,
        'gates': gates,
        'thresholds': thresholds,
    }
    return result, {'pass': 0, 'fail': 1}.get(status, 2)


def main(argv=None):
    parser = argparse.ArgumentParser(description='L4 enablement gate for flight-packed pyannote.')
    parser.add_argument('--audio', nargs='+', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--unit-seconds', default=','.join(str(s) for s in DEFAULT_UNIT_SECONDS))
    parser.add_argument('--budget-seconds', type=float, default=1800)
    parser.add_argument('--batch-size', type=int, default=int(os.getenv('BATCH_PIPELINE_MODEL_BATCH_SIZE', '8')))
    parser.add_argument(
        '--speech-only',
        choices=('true', 'false'),
        default='false' if os.getenv(SPEECH_ONLY_ENV, 'true').strip().lower() == 'false' else 'true',
        help='the deployment speech-only setting whose configuration authorizes the flag',
    )
    parser.add_argument('--min-agreement', type=float, default=0.99)
    parser.add_argument('--min-multispeaker-units', type=int, default=5)
    parser.add_argument('--max-peak-ratio', type=float, default=1.10)
    args = parser.parse_args(argv)
    receipt = run(args.audio, [float(v) for v in args.unit_seconds.split(',')], args.budget_seconds, args.batch_size)
    receipt['gate'], status = gate_receipt(
        receipt,
        speech_only=args.speech_only == 'true',
        min_agreement=args.min_agreement,
        min_multispeaker_units=args.min_multispeaker_units,
        max_peak_ratio=args.max_peak_ratio,
    )
    Path(args.output).write_text(json.dumps(receipt, indent=1, sort_keys=True))
    print(json.dumps(receipt['gate'], indent=1))
    return status


if __name__ == '__main__':
    sys.exit(main())
