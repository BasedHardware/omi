"""
Benchmark: Diarization Error Rate (DER) — Deepgram vs Parakeet.

Uses multi-speaker interleaved LibriSpeech audio from L2 behavior test suite.
Ground truth: alternating speaker segments at fixed intervals (30s or 20s).

Setup:
    HOSTED_PARAKEET_API_URL=http://<parakeet-service>:8080
    DEEPGRAM_API_KEY=<key>

Usage:
    cd backend && python scripts/stt/x_benchmark_parakeet_der.py
"""

from io import BytesIO
import json
import os
import re
import sys
import time
import wave as _wave
from collections import defaultdict
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tabulate import tabulate

from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes, parakeet_prerecorded_from_bytes

L2_AUDIO_DIR = Path(os.path.expanduser('~/.claude/skills/omi-listen-behavior-test/test_audio_l2'))
RESULTS_DIR = Path('/tmp/stt_benchmark_results')

MAX_AUDIO_SECONDS = 120


def load_l2_manifest():
    manifest_path = L2_AUDIO_DIR / 'manifest.json'
    if not manifest_path.exists():
        print(f'ERROR: L2 audio not found at {L2_AUDIO_DIR}')
        sys.exit(1)
    with open(manifest_path) as f:
        return json.load(f)


def build_ground_truth(sample_info: dict) -> List[dict]:
    speakers = sample_info['speaker_ids']
    segment_dur = sample_info['segment_duration_s']
    total_dur = min(sample_info['duration_s'], MAX_AUDIO_SECONDS)
    num_speakers = sample_info['speakers']

    turns = []
    t = 0.0
    spk_idx = 0
    while t < total_dur:
        end = min(t + segment_dur, total_dur)
        turns.append({'start': t, 'end': end, 'speaker': speakers[spk_idx % num_speakers]})
        t = end
        spk_idx += 1
    return turns


def extract_speaker_turns(words: List[dict]) -> List[dict]:
    if not words:
        return []

    turns = []
    current_speaker = None
    current_start = None
    current_end = None

    for w in words:
        spk = w.get('speaker', 'SPEAKER_00')
        start = w['timestamp'][0] if 'timestamp' in w else w.get('start', 0)
        end = w['timestamp'][1] if 'timestamp' in w else w.get('end', 0)

        if spk != current_speaker:
            if current_speaker is not None:
                turns.append({'start': current_start, 'end': current_end, 'speaker': current_speaker})
            current_speaker = spk
            current_start = start
            current_end = end
        else:
            current_end = end

    if current_speaker is not None:
        turns.append({'start': current_start, 'end': current_end, 'speaker': current_speaker})

    return turns


def compute_der(ref_turns: List[dict], hyp_turns: List[dict], total_duration: float, collar: float = 0.25) -> dict:
    resolution = 0.01
    num_frames = int(total_duration / resolution) + 1

    ref_labels = [''] * num_frames
    hyp_labels = [''] * num_frames

    for turn in ref_turns:
        start_frame = int(turn['start'] / resolution)
        end_frame = int(turn['end'] / resolution)
        for i in range(max(0, start_frame), min(num_frames, end_frame)):
            ref_labels[i] = turn['speaker']

    for turn in hyp_turns:
        start_frame = int(turn['start'] / resolution)
        end_frame = int(turn['end'] / resolution)
        for i in range(max(0, start_frame), min(num_frames, end_frame)):
            hyp_labels[i] = turn['speaker']

    scored_frames = set()
    for turn in ref_turns:
        start_frame = int((turn['start'] + collar) / resolution)
        end_frame = int((turn['end'] - collar) / resolution)
        for i in range(max(0, start_frame), min(num_frames, end_frame)):
            scored_frames.add(i)

    ref_speakers = set(t['speaker'] for t in ref_turns)
    hyp_speakers = set(t['speaker'] for t in hyp_turns)

    best_mapping = _find_best_speaker_mapping(ref_labels, hyp_labels, ref_speakers, hyp_speakers, scored_frames)

    total_scored = len(scored_frames)
    if total_scored == 0:
        return {'der': 0.0, 'miss': 0.0, 'fa': 0.0, 'confusion': 0.0, 'scored_seconds': 0.0}

    miss_frames = 0
    fa_frames = 0
    confusion_frames = 0

    for i in scored_frames:
        ref_spk = ref_labels[i]
        hyp_spk = hyp_labels[i]
        mapped_hyp = best_mapping.get(hyp_spk, hyp_spk) if hyp_spk else ''

        if ref_spk and not hyp_spk:
            miss_frames += 1
        elif not ref_spk and hyp_spk:
            fa_frames += 1
        elif ref_spk and hyp_spk and ref_spk != mapped_hyp:
            confusion_frames += 1

    der = (miss_frames + fa_frames + confusion_frames) / total_scored
    return {
        'der': round(der * 100, 1),
        'miss': round(miss_frames / total_scored * 100, 1),
        'fa': round(fa_frames / total_scored * 100, 1),
        'confusion': round(confusion_frames / total_scored * 100, 1),
        'scored_seconds': round(total_scored * resolution, 1),
        'speaker_mapping': best_mapping,
        'ref_speakers': len(ref_speakers),
        'hyp_speakers': len(hyp_speakers),
    }


def _find_best_speaker_mapping(ref_labels, hyp_labels, ref_speakers, hyp_speakers, scored_frames):
    overlap = defaultdict(lambda: defaultdict(int))
    for i in scored_frames:
        r, h = ref_labels[i], hyp_labels[i]
        if r and h:
            overlap[h][r] += 1

    mapping = {}
    used_ref = set()
    sorted_hyp = sorted(overlap.keys(), key=lambda h: -max(overlap[h].values()) if overlap[h] else 0)
    for h in sorted_hyp:
        best_ref = max(overlap[h], key=overlap[h].get)
        if best_ref not in used_ref:
            mapping[h] = best_ref
            used_ref.add(best_ref)

    return mapping


def trim_wav(wav_path: Path, max_seconds: float) -> bytes:
    with _wave.open(str(wav_path), 'rb') as wf:
        sr = wf.getframerate()
        max_frames = int(max_seconds * sr)
        actual_frames = min(wf.getnframes(), max_frames)
        pcm = wf.readframes(actual_frames)

    buf = BytesIO()
    with _wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm)
    return buf.getvalue()


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    dg_key = os.getenv('DEEPGRAM_API_KEY')
    parakeet_url = os.getenv('HOSTED_PARAKEET_API_URL')
    if not dg_key:
        print('ERROR: DEEPGRAM_API_KEY not set')
        sys.exit(1)
    if not parakeet_url:
        print('ERROR: HOSTED_PARAKEET_API_URL not set')
        sys.exit(1)

    manifest = load_l2_manifest()
    samples = manifest.get('samples', {})

    print(f'\n{"=" * 90}')
    print(f'DER Benchmark: Deepgram nova-3 vs Parakeet')
    print(f'  Samples: {len(samples)} multi-speaker interleaved LibriSpeech')
    print(f'  Max duration: {MAX_AUDIO_SECONDS}s per sample (trimmed)')
    print(f'  Collar: 0.25s (standard forgiveness around speaker boundaries)')
    print(f'{"=" * 90}\n')

    results = []
    for wav_name, info in samples.items():
        wav_path = L2_AUDIO_DIR / wav_name
        if not wav_path.exists():
            print(f'  SKIP: {wav_name} not found')
            continue

        total_dur = min(info['duration_s'], MAX_AUDIO_SECONDS)
        ref_turns = build_ground_truth(info)
        print(
            f"  [{wav_name}] {info['speakers']} speakers, {info['segment_duration_s']}s segments, trimmed to {total_dur}s"
        )

        audio_bytes = trim_wav(wav_path, MAX_AUDIO_SECONDS)

        row = {
            'id': wav_name,
            'speakers': info['speakers'],
            'segment_duration_s': info['segment_duration_s'],
            'eval_duration_s': total_dur,
        }

        for provider_name, fn in [
            ('deepgram', deepgram_prerecorded_from_bytes),
            ('parakeet', parakeet_prerecorded_from_bytes),
        ]:
            try:
                t0 = time.monotonic()
                words = fn(audio_bytes, sample_rate=16000, diarize=True)
                elapsed = time.monotonic() - t0

                hyp_turns = extract_speaker_turns(words)
                der_result = compute_der(ref_turns, hyp_turns, total_dur)

                row[f'{provider_name}_der'] = der_result['der']
                row[f'{provider_name}_miss'] = der_result['miss']
                row[f'{provider_name}_fa'] = der_result['fa']
                row[f'{provider_name}_confusion'] = der_result['confusion']
                row[f'{provider_name}_hyp_speakers'] = der_result['hyp_speakers']
                row[f'{provider_name}_latency'] = round(elapsed, 2)
                row[f'{provider_name}_mapping'] = der_result.get('speaker_mapping', {})

                print(
                    f"    {provider_name:10s}  DER={der_result['der']:.1f}%  miss={der_result['miss']:.1f}%  fa={der_result['fa']:.1f}%  conf={der_result['confusion']:.1f}%  spk={der_result['hyp_speakers']}  lat={elapsed:.1f}s"
                )
            except Exception as e:
                print(f"    {provider_name:10s}  ERROR: {e}")
                row[f'{provider_name}_der'] = None

        results.append(row)

    print(f'\n{"=" * 90}')
    print('RESULTS SUMMARY')
    print(f'{"=" * 90}\n')

    table = []
    for r in results:
        table.append(
            [
                r['id'],
                r['speakers'],
                f"{r.get('deepgram_der', 'ERR')}%" if r.get('deepgram_der') is not None else 'ERR',
                f"{r.get('parakeet_der', 'ERR')}%" if r.get('parakeet_der') is not None else 'ERR',
                r.get('deepgram_hyp_speakers', '-'),
                r.get('parakeet_hyp_speakers', '-'),
                f"{r.get('deepgram_latency', 0):.1f}s",
                f"{r.get('parakeet_latency', 0):.1f}s",
            ]
        )

    print(tabulate(table, headers=['Sample', 'Ref Spk', 'DG DER', 'PK DER', 'DG Spk', 'PK Spk', 'DG Lat', 'PK Lat']))

    dg_ders = [r['deepgram_der'] for r in results if r.get('deepgram_der') is not None]
    pk_ders = [r['parakeet_der'] for r in results if r.get('parakeet_der') is not None]
    if dg_ders:
        print(f'\n  Deepgram avg DER: {sum(dg_ders)/len(dg_ders):.1f}%')
    if pk_ders:
        print(f'  Parakeet avg DER: {sum(pk_ders)/len(pk_ders):.1f}%')

    output_path = RESULTS_DIR / 'parakeet_der_benchmark.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f'\n  Results saved to: {output_path}')


if __name__ == '__main__':
    main()
