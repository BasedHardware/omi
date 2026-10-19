#!/usr/bin/env python3
"""Paired run gating ``BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED`` (#22368).

Two halves, both on one staging L4 with the batch-pipeline image built from a
SHA that contains #22368:

1. **Model-level qualification**: #22368's own
   ``diarizer/batch_pipeline_flight_qualify.py`` (serial vs packed pyannote on
   the same waveforms). This script re-verifies its receipt independently:
   revision ``3533c8cf...`` (prod pin), batch pin 8, an L4 device, gate status
   ``pass``, >= 5 multi-speaker units, and thresholds no looser than the PR's
   (agreement >= 0.99, packed CUDA peak <= 1.10x serial). The qualify script
   itself does not refuse a wrong revision or device; this does.
2. **End-to-end chain pair**: the production worker chain (``load_worker``)
   on identical multi-speaker units with the flag off, then on. Words must be
   identical; on every unit where the serial pass finds >= 2 speakers, the
   word-label agreement after optimal mapping must be >= 0.99 and the speaker
   counts equal. Wall time per pass is recorded (an L4 throughput hint, not
   the leases/min/node measurement, which is parity row 6).

    PYTHONPATH=/app BATCH_PIPELINE_MODEL_BATCH_SIZE=8 python testing/quality_corpus/paired_flight_batching.py run \\
        --audio /corpus/ami/ES2004a.Mix-Headset.wav /corpus/ami/IS1009a.Mix-Headset.wav \\
        --output /receipts/flight-paired.json
    python testing/quality_corpus/paired_flight_batching.py verify --receipt /receipts/flight-paired.json

Exit: 0 pass, 1 fail, 2 insufficient evidence. Receipts hold counts, hashes,
timings and revision identity only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PROD_DIARIZER_REVISION = '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee'
FLAG = 'BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED'
BATCH_PIN = 8
UNIT_SECONDS = (23.0, 41.0, 67.0, 95.0, 128.0, 30.5, 212.0)  # the PR's mixed flight
MIN_AGREEMENT = 0.99
MAX_PEAK_RATIO = 1.10
MIN_MULTISPEAKER_UNITS = 5


def verify_qualify_receipt(receipt: Mapping[str, Any]) -> list[str]:
    """Independent checks on #22368's qualification receipt; returns failure tokens."""
    failures = []
    if receipt.get('diarizer_revision') != PROD_DIARIZER_REVISION:
        failures.append('qualify_revision_not_prod')
    if receipt.get('model_batch_size') != BATCH_PIN:
        failures.append('qualify_batch_pin_not_8')
    if 'L4' not in str(receipt.get('device', '')):
        failures.append('qualify_device_not_l4')
    gate = receipt.get('gate') or {}
    thresholds = gate.get('thresholds') or {}
    if (
        thresholds.get('min_agreement', 0) < MIN_AGREEMENT
        or thresholds.get('max_peak_ratio', float('inf')) > MAX_PEAK_RATIO
        or thresholds.get('min_multispeaker_units', 0) < MIN_MULTISPEAKER_UNITS
    ):
        failures.append('qualify_thresholds_loosened')
    if gate.get('status') == 'insufficient_evidence':
        failures.append('qualify_insufficient_evidence')
    elif gate.get('status') != 'pass':
        failures.append('qualify_gate_' + str(gate.get('status')))
    return failures


def pair_unit(off_words: Sequence[dict], on_words: Sequence[dict]) -> dict[str, Any]:
    """Word identity plus label agreement after optimal 1:1 mapping of on-labels onto off-labels."""
    from scripts.parity.scorers import optimal_label_mapping

    identical = [(w['text'], w['start'], w['end']) for w in off_words] == [
        (w['text'], w['start'], w['end']) for w in on_words
    ]
    off_speakers = {w['speaker'] for w in off_words if w['speaker'] is not None}
    on_speakers = {w['speaker'] for w in on_words if w['speaker'] is not None}
    pairs = [
        (str(a['speaker']), str(b['speaker']))
        for a, b in zip(off_words, on_words)
        if a['speaker'] is not None and b['speaker'] is not None
    ]
    mapping = optimal_label_mapping(pairs)
    agree = sum(mapping.get(b) == a for a, b in pairs)
    abstain_changed = sum((a['speaker'] is None) != (b['speaker'] is None) for a, b in zip(off_words, on_words))
    return {
        'words': len(off_words),
        'words_identical': identical,
        'serial_speakers': len(off_speakers),
        'packed_speakers': len(on_speakers),
        'label_agreement': (agree / len(pairs)) if pairs else 1.0,
        'abstain_changed_words': abstain_changed,
    }


def evaluate_chain_pair(
    units: Sequence[dict], *, min_agreement=MIN_AGREEMENT, min_multispeaker_units=MIN_MULTISPEAKER_UNITS
) -> dict[str, Any]:
    failures = []
    multi = [u for u in units if u['serial_speakers'] >= 2]
    if any(not u['words_identical'] for u in units):
        failures.append('chain_words_differ')
    if any(u['serial_speakers'] != u['packed_speakers'] for u in units):
        failures.append('chain_speaker_count_differs')
    if any(u['label_agreement'] < min_agreement for u in multi):
        failures.append('chain_label_agreement_below_limit')
    status = 'fail' if failures else ('insufficient_evidence' if len(multi) < min_multispeaker_units else 'pass')
    return {
        'status': status,
        'failures': failures,
        'units': len(units),
        'multispeaker_units': len(multi),
        'min_label_agreement': min((u['label_agreement'] for u in multi), default=None),
        'abstain_changed_words': sum(u['abstain_changed_words'] for u in units),
    }


def combine(qualify_failures: list[str], chain: Mapping[str, Any]) -> tuple[str, int]:
    hard = [f for f in qualify_failures if f != 'qualify_insufficient_evidence']
    if hard or chain['status'] == 'fail':
        return 'fail', 1
    if qualify_failures or chain['status'] != 'pass':
        return 'insufficient_evidence', 2
    return 'pass', 0


def _cut(samples, seconds: Sequence[float], sample_rate: int = 16000):
    units, start, index = [], 0, 0
    while start < len(samples):
        stop = min(len(samples), start + int(seconds[index % len(seconds)] * sample_rate))
        if stop - start >= sample_rate:
            units.append(samples[start:stop])
        start, index = stop, index + 1
    return units


def run(args) -> int:
    from testing.quality_corpus.audio import load_audio
    from testing.quality_corpus.chain import labelled_words, run_chain, wav_bytes

    out_dir = Path(args.output).parent
    qualify_path = out_dir / 'flight-qualify.json'
    started = time.time()
    qualify = subprocess.run(
        [
            sys.executable,
            'diarizer/batch_pipeline_flight_qualify.py',
            '--audio',
            *args.audio,
            '--batch-size',
            str(BATCH_PIN),
            '--output',
            str(qualify_path),
        ],
        capture_output=True,
        text=True,
        timeout=7200,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    qualify_receipt = json.loads(qualify_path.read_text()) if qualify_path.exists() else {}
    qualify_failures = verify_qualify_receipt(qualify_receipt) if qualify_receipt else ['qualify_receipt_missing']

    clips = []
    for path in args.audio:
        clips.extend(_cut(load_audio(Path(path)), UNIT_SECONDS))
    units = {f'f{i:04d}': wav_bytes(c) for i, c in enumerate(clips)}
    overrides = {'BATCH_PIPELINE_MODEL_BATCH_SIZE': str(BATCH_PIN)}
    t0 = time.perf_counter()
    off = run_chain(units, {**overrides, FLAG: 'false'})
    t1 = time.perf_counter()
    on = run_chain(units, {**overrides, FLAG: 'true'})
    t2 = time.perf_counter()
    pairs = [
        pair_unit(labelled_words(off['payloads'].get(k) or {}), labelled_words(on['payloads'].get(k) or {}))
        for k in units
    ]
    chain = evaluate_chain_pair(pairs)
    status, code = combine(qualify_failures, chain)
    receipt = {
        'gate_for': '#22368 BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED',
        'status': status,
        'qualify': {
            'exit_code': qualify.returncode,
            'failures': qualify_failures,
            'gate': qualify_receipt.get('gate'),
            'device': qualify_receipt.get('device'),
            'diarizer_revision': qualify_receipt.get('diarizer_revision'),
            'model_batch_size': qualify_receipt.get('model_batch_size'),
            'wall_seconds': qualify_receipt.get('wall_seconds'),
            'sources': qualify_receipt.get('sources'),
        },
        'chain': {
            **chain,
            'wall_seconds': {'off_incl_load': round(t1 - t0, 2), 'on_incl_load': round(t2 - t1, 2)},
            'counts': {'off': off['counts'], 'on': on['counts']},
            'audio_seconds': round(sum(len(c) for c in clips) / 16000, 1),
        },
        'elapsed_seconds': round(time.time() - started, 1),
    }
    Path(args.output).write_text(json.dumps(receipt, indent=1, sort_keys=True))
    print(json.dumps({'status': status, 'qualify_failures': qualify_failures, 'chain': chain}, indent=1))
    return code


def verify(args) -> int:
    receipt = json.loads(Path(args.receipt).read_text())
    failures = verify_qualify_receipt(receipt.get('qualify') or {})
    status, code = combine(failures, receipt.get('chain') or {'status': 'insufficient_evidence'})
    print(json.dumps({'status': status, 'qualify_failures': failures}, indent=1))
    return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Paired run gating the #22368 flight-batching flag.')
    sub = parser.add_subparsers(dest='command', required=True)
    run_p = sub.add_parser('run')
    run_p.add_argument('--audio', nargs='+', required=True, help='public or consented multi-speaker audio')
    run_p.add_argument('--output', required=True)
    verify_p = sub.add_parser('verify')
    verify_p.add_argument('--receipt', required=True)
    args = parser.parse_args(argv)
    return run(args) if args.command == 'run' else verify(args)


if __name__ == '__main__':
    sys.exit(main())
