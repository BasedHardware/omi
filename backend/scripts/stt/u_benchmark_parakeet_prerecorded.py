"""
Benchmark Suite: Parakeet/Nemotron ASR — Pre-recorded transcription.

Compares Parakeet against Deepgram nova-3 using the same LibriSpeech test-clean
samples as the Modulate benchmark (n_benchmark_02_prerecorded.py).

Setup:
    1. Prepare samples (shared with other benchmarks):
       python scripts/stt/n_benchmark_02_prerecorded.py --prepare
    2. Set env vars:
       HOSTED_PARAKEET_API_URL=http://<parakeet-service>:8080
       ENCRYPTION_SECRET=<shared-secret>
       DEEPGRAM_API_KEY=<key>

Usage:
    cd backend && python scripts/stt/u_benchmark_parakeet_prerecorded.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

from jiwer import wer as compute_wer
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes, parakeet_prerecorded_from_bytes

PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)

AUDIO_DIR = Path('/tmp/stt_benchmark_audio_02')
RESULTS_DIR = Path('/tmp/stt_benchmark_results')


def normalize_for_wer(text: str) -> str:
    return PUNCT_RE.sub('', text).lower().strip()


def count_punctuation(text: str) -> dict:
    marks = re.findall(r'[^\w\s]', text)
    return {'total': len(marks), 'detail': dict(sorted(((m, marks.count(m)) for m in set(marks)), key=lambda x: -x[1]))}


def load_manifest() -> List[dict]:
    manifest_path = AUDIO_DIR / 'manifest.json'
    if not manifest_path.exists():
        print('ERROR: Samples not prepared. Run first:')
        print('  python scripts/stt/n_benchmark_02_prerecorded.py --prepare')
        sys.exit(1)
    with open(manifest_path) as f:
        return json.load(f)


def run_deepgram(audio_bytes: bytes) -> Tuple[str, float, int]:
    t0 = time.monotonic()
    result = deepgram_prerecorded_from_bytes(audio_bytes, sample_rate=16000, diarize=True)
    elapsed = time.monotonic() - t0
    text = ' '.join(w.get('text', '') or w.get('word', '') for w in result).strip()
    return text, elapsed, len(result)


def run_parakeet(audio_bytes: bytes) -> Tuple[str, float, int]:
    t0 = time.monotonic()
    result = parakeet_prerecorded_from_bytes(audio_bytes, sample_rate=16000, diarize=False)
    elapsed = time.monotonic() - t0
    text = ' '.join(w.get('text', '') for w in result).strip()
    return text, elapsed, len(result)


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

    manifest = load_manifest()
    print(f'\nBenchmark: Deepgram nova-3 vs Parakeet — Pre-recorded ({len(manifest)} samples)')
    print(f'Parakeet endpoint: {parakeet_url}')
    print(f'Source: LibriSpeech test-clean (CC BY 4.0)\n')

    results = []
    for case in manifest:
        wav_path = AUDIO_DIR / f"{case['id']}.wav"
        audio_bytes = wav_path.read_bytes()
        ref_norm = normalize_for_wer(case['text'])

        row = {
            'id': case['id'],
            'uid': case['uid'],
            'description': case['description'],
            'speaker': case['speaker'],
            'ref_words': case['word_count'],
            'duration_s': case['duration_s'],
            'ref_text': case['text'],
        }

        print(f"  [{case['id']}] {case['description']} (speaker {case['speaker']})")

        try:
            dg_text, dg_time, dg_words = run_deepgram(audio_bytes)
            dg_norm = normalize_for_wer(dg_text)
            dg_wer = compute_wer(ref_norm, dg_norm) if ref_norm and dg_norm else 1.0
            dg_punct = count_punctuation(dg_text)
            row.update(
                {
                    'dg_text': dg_text,
                    'dg_wer': round(dg_wer * 100, 1),
                    'dg_latency_s': round(dg_time, 2),
                    'dg_words': dg_words,
                    'dg_punct': dg_punct['total'],
                }
            )
            print(f"    DG: WER={dg_wer*100:.1f}% lat={dg_time:.2f}s words={dg_words}")
        except Exception as e:
            print(f"    DG ERROR: {e}")
            row.update({'dg_text': f'ERROR: {e}', 'dg_wer': None, 'dg_latency_s': None})

        try:
            pk_text, pk_time, pk_segments = run_parakeet(audio_bytes)
            pk_norm = normalize_for_wer(pk_text)
            pk_wer = compute_wer(ref_norm, pk_norm) if ref_norm and pk_norm else 1.0
            pk_punct = count_punctuation(pk_text)
            row.update(
                {
                    'pk_text': pk_text,
                    'pk_wer': round(pk_wer * 100, 1),
                    'pk_latency_s': round(pk_time, 2),
                    'pk_segments': pk_segments,
                    'pk_punct': pk_punct['total'],
                }
            )
            print(f"    PK: WER={pk_wer*100:.1f}% lat={pk_time:.2f}s segs={pk_segments}")
        except Exception as e:
            print(f"    PK ERROR: {e}")
            row.update({'pk_text': f'ERROR: {e}', 'pk_wer': None, 'pk_latency_s': None})

        results.append(row)

    with open(RESULTS_DIR / 'parakeet_prerecorded_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print('\n' + '=' * 80)
    print('RESULTS SUMMARY')
    print('=' * 80)

    table = []
    dg_wers, pk_wers = [], []
    dg_lats, pk_lats = [], []
    for r in results:
        dg_w = r.get('dg_wer')
        pk_w = r.get('pk_wer')
        if dg_w is not None:
            dg_wers.append(dg_w)
        if pk_w is not None:
            pk_wers.append(pk_w)
        if r.get('dg_latency_s') is not None:
            dg_lats.append(r['dg_latency_s'])
        if r.get('pk_latency_s') is not None:
            pk_lats.append(r['pk_latency_s'])

        table.append(
            [
                r['id'],
                f"{r['duration_s']:.1f}s",
                r['ref_words'],
                f"{dg_w:.1f}%" if dg_w is not None else 'ERR',
                f"{pk_w:.1f}%" if pk_w is not None else 'ERR',
                f"{r.get('dg_latency_s', 0):.2f}s" if r.get('dg_latency_s') else 'ERR',
                f"{r.get('pk_latency_s', 0):.2f}s" if r.get('pk_latency_s') else 'ERR',
            ]
        )

    print(tabulate(table, headers=['Sample', 'Duration', 'Words', 'DG WER', 'PK WER', 'DG Lat', 'PK Lat']))

    print(f'\n  Deepgram avg WER:  {sum(dg_wers)/len(dg_wers):.1f}%' if dg_wers else '')
    print(f'  Parakeet avg WER:  {sum(pk_wers)/len(pk_wers):.1f}%' if pk_wers else '')
    print(f'  Deepgram avg lat:  {sum(dg_lats)/len(dg_lats):.2f}s' if dg_lats else '')
    print(f'  Parakeet avg lat:  {sum(pk_lats)/len(pk_lats):.2f}s' if pk_lats else '')
    print(f'\n  Results saved to: {RESULTS_DIR / "parakeet_prerecorded_results.json"}')


if __name__ == '__main__':
    main()
