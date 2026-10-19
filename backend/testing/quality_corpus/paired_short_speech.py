#!/usr/bin/env python3
"""Paired run gating ``BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED`` (#22358).

The skip labels a unit ``SPEAKER_00`` without any model check when all of the
gate's evidence (VAD speech plus word clocks) forms one region of at most 2 s,
with pauses of at most 0.5 s joining. The enablement precondition is a paired
run on the prod pyannote revision showing the full diarizer returns a single
speaker on exactly the units where the gate fires, including two bursts at most
0.5 s apart.

Method (staging L4, batch-pipeline image, public audio with RTTM references):
1. Build 30 s units: a -55 dBFS noise bed with one excerpt placed inside it.
   Excerpts are isolated single-speaker turns (0.4-2.0 s) and two-burst pairs
   joined by a 0.10-0.50 s pause, from the SAME speaker and from DIFFERENT
   speakers (the adversarial case the skip cannot see).
2. Run the production chain (``load_worker``) twice on identical units:
   skip OFF (full diarization path, speech-only diarization at its prod default)
   and skip ON.
3. A unit "fires" when the ON payload carries ``single_evidence == short_speech``,
   i.e. the gate's own evidence decided, not a re-implementation of it.
4. For fired units, the OFF path's word labels must name one speaker. Any fired
   unit where the full diarizer assigns two or more speakers is a disagreement.

Pass (exit 0): revision == prod pin, CUDA device is an L4, words identical
across passes, >= --min-fired fired units, >= --min-fired-bursts fired two-burst
units, zero disagreements. Exit 1 on any failure, 2 on insufficient evidence.
The receipt holds counts, hashes and revision identity only.

    PYTHONPATH=/app python testing/quality_corpus/paired_short_speech.py \\
        --pair /corpus/ami/ES2004a.Mix-Headset.wav:/corpus/ami/ES2004a.rttm \\
        --pair /corpus/vox/abjxc.wav:/corpus/vox/abjxc.rttm --output /receipts/short-speech.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any, Sequence

import numpy as np

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from testing.quality_corpus.audio import (  # noqa: E402
    SAMPLE_RATE,
    Turn,
    load_audio,
    merge_turns,
    parse_rttm,
    quiet_bed,
)

PROD_DIARIZER_REVISION = '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee'
FLAG = 'BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED'
UNIT_SECONDS = 30.0
ISOLATION_SECONDS = 0.25
SINGLE_RANGE = (0.4, 2.0)
BURST_RANGE = (0.3, 0.75)
JOIN_PAUSES = (0.10, 0.25, 0.40, 0.50)


def isolated_turns(turns: Sequence[Turn], lo: float, hi: float, isolation: float = ISOLATION_SECONDS) -> list[Turn]:
    """Turns of length in [lo, hi] with no other turn (any speaker) within ``isolation`` seconds."""
    out = []
    for i, turn in enumerate(turns):
        if not lo <= turn.end - turn.start <= hi:
            continue
        clear = all(
            other.end <= turn.start - isolation or other.start >= turn.end + isolation
            for j, other in enumerate(turns)
            if j != i
        )
        if clear:
            out.append(turn)
    return out


def plan_excerpts(
    turns_by_source: dict[str, list[Turn]], seed: int, max_per_kind: int, isolation: float = ISOLATION_SECONDS
) -> list[dict]:
    """Excerpt specs: single, burst_same (same speaker), burst_diff (different speakers)."""
    rng = random.Random(seed)
    specs: list[dict] = []
    singles, bursts = [], []
    for source, turns in sorted(turns_by_source.items()):
        singles += [(source, t) for t in isolated_turns(turns, *SINGLE_RANGE, isolation=isolation)]
        bursts += [(source, t) for t in isolated_turns(turns, *BURST_RANGE, isolation=isolation)]
    rng.shuffle(singles)
    for source, t in singles[:max_per_kind]:
        specs.append({'kind': 'single', 'parts': [(source, t.start, t.end)], 'speakers': [t.speaker], 'pause': None})
    rng.shuffle(bursts)
    same, diff = [], []
    for i, (sa, a) in enumerate(bursts):
        for sb, b in bursts[i + 1 :]:
            pause = JOIN_PAUSES[(len(same) + len(diff)) % len(JOIN_PAUSES)]
            if (a.end - a.start) + pause + (b.end - b.start) > SINGLE_RANGE[1]:
                continue
            spec = {
                'parts': [(sa, a.start, a.end), (sb, b.start, b.end)],
                'speakers': [a.speaker, b.speaker],
                'pause': pause,
            }
            if sa == sb and a.speaker == b.speaker and len(same) < max_per_kind:
                same.append({**spec, 'kind': 'burst_same'})
            elif (sa, a.speaker) != (sb, b.speaker) and len(diff) < max_per_kind:
                diff.append({**spec, 'kind': 'burst_diff'})
            if len(same) >= max_per_kind and len(diff) >= max_per_kind:
                break
        if len(same) >= max_per_kind and len(diff) >= max_per_kind:
            break
    return specs + same + diff


def render_unit(spec: dict, audio: dict[str, np.ndarray], seed: int) -> np.ndarray:
    bed = quiet_bed(UNIT_SECONDS, seed)
    pieces = []
    for index, (source, start, end) in enumerate(spec['parts']):
        if index:
            pieces.append(np.zeros(int(spec['pause'] * SAMPLE_RATE), dtype=np.float32))
        pieces.append(audio[source][int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)])
    excerpt = np.concatenate(pieces)
    offset = int((8.0 + (seed % 10)) * SAMPLE_RATE)  # keep the excerpt well inside the unit
    bed[offset : offset + len(excerpt)] += excerpt
    return np.clip(bed, -1.0, 1.0)


def evaluate(units: Sequence[dict], identity: dict, *, min_fired: int, min_fired_bursts: int) -> dict[str, Any]:
    """Pure gate over per-unit pass results (see module docstring)."""
    failures = []
    if identity.get('diarizer_revision') != PROD_DIARIZER_REVISION:
        failures.append('diarizer_revision_not_prod')
    if 'L4' not in str(identity.get('device', '')):
        failures.append('device_not_l4')
    fired = [u for u in units if u['fired']]
    disagreements = [u for u in fired if u['off_word_speakers'] >= 2]
    words_changed = sum(1 for u in units if not u['words_identical'])
    if words_changed:
        failures.append('words_differ_between_passes')
    if disagreements:
        failures.append('full_diarizer_multi_speaker_on_fired_units')
    by_kind = {}
    for kind in ('single', 'burst_same', 'burst_diff'):
        rows = [u for u in units if u['kind'] == kind]
        by_kind[kind] = {
            'units': len(rows),
            'fired': sum(u['fired'] for u in rows),
            'fired_full_multi_speaker': sum(1 for u in rows if u['fired'] and u['off_word_speakers'] >= 2),
            'fired_reference_multi_speaker': sum(1 for u in rows if u['fired'] and u['reference_speakers'] >= 2),
        }
    fired_bursts = by_kind['burst_same']['fired'] + by_kind['burst_diff']['fired']
    if failures:
        status = 'fail'
    elif len(fired) < min_fired or fired_bursts < min_fired_bursts:
        status = 'insufficient_evidence'
    else:
        status = 'pass'
    return {
        'status': status,
        'failures': failures,
        'units': len(units),
        'fired': len(fired),
        'fired_bursts': fired_bursts,
        'disagreements': len(disagreements),
        'words_changed_units': words_changed,
        'by_kind': by_kind,
        'thresholds': {'min_fired': min_fired, 'min_fired_bursts': min_fired_bursts, 'max_disagreements': 0},
    }


def unit_result(spec: dict, off_payload: dict | None, on_payload: dict | None) -> dict[str, Any]:
    from testing.quality_corpus.chain import labelled_words

    off_words = labelled_words(off_payload) if off_payload else []
    on_words = labelled_words(on_payload) if on_payload else []
    fired = bool(on_payload and (on_payload.get('diarization') or {}).get('single_evidence') == 'short_speech')
    return {
        'kind': spec['kind'],
        'pause': spec['pause'],
        'reference_speakers': len(set(spec['speakers'])),
        'fired': fired,
        'off_word_speakers': len({w['speaker'] for w in off_words if w['speaker'] is not None}),
        'words': len(off_words),
        'words_identical': [(w['text'], w['start'], w['end']) for w in off_words]
        == [(w['text'], w['start'], w['end']) for w in on_words],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Paired run gating the #22358 short-speech skip.')
    parser.add_argument('--pair', action='append', required=True, help='AUDIO:RTTM (public or consented audio)')
    parser.add_argument('--output', required=True)
    parser.add_argument('--seed', type=int, default=22358)
    parser.add_argument('--max-per-kind', type=int, default=150)
    parser.add_argument('--isolation', type=float, default=ISOLATION_SECONDS)
    parser.add_argument('--min-fired', type=int, default=200)
    parser.add_argument('--min-fired-bursts', type=int, default=50)
    args = parser.parse_args(argv)

    import torch  # GPU image only

    from diarizer.batch_pipeline_startup import DIARIZER_REVISION
    from testing.quality_corpus.chain import run_chain, wav_bytes

    audio, turns_by_source, sources = {}, {}, []
    for pair in args.pair:
        audio_path, rttm_path = (Path(p) for p in pair.split(':', 1))
        body = audio_path.read_bytes()
        source = hashlib.sha256(body).hexdigest()[:16]
        sources.append({'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)})
        audio[source] = load_audio(audio_path)
        turns_by_source[source] = merge_turns(parse_rttm(rttm_path.read_text()))
    specs = plan_excerpts(turns_by_source, args.seed, args.max_per_kind, args.isolation)
    units = {f'u{i:05d}': wav_bytes(render_unit(s, audio, args.seed + i)) for i, s in enumerate(specs)}
    off = run_chain(units, {FLAG: 'false'})
    on = run_chain(units, {FLAG: 'true'})
    results = [unit_result(spec, off['payloads'].get(key), on['payloads'].get(key)) for spec, key in zip(specs, units)]
    identity = {
        'diarizer_revision': DIARIZER_REVISION,
        'device': torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none',
        'torch': torch.__version__,
    }
    gate = evaluate(results, identity, min_fired=args.min_fired, min_fired_bursts=args.min_fired_bursts)
    receipt = {
        'gate_for': '#22358 BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED',
        'identity': identity,
        'sources': sources,
        'seed': args.seed,
        'pass_counts': {'off': off['counts'], 'on': on['counts']},
        'outcomes_off': _histogram(off['outcomes'].values()),
        'outcomes_on': _histogram(on['outcomes'].values()),
        'gate': gate,
    }
    Path(args.output).write_text(json.dumps(receipt, indent=1, sort_keys=True))
    print(json.dumps(gate, indent=1, sort_keys=True))
    return {'pass': 0, 'fail': 1}.get(gate['status'], 2)


def _histogram(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out


if __name__ == '__main__':
    sys.exit(main())
