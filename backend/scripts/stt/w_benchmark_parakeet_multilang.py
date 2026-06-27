"""
Benchmark: Multi-language + code-switching — Deepgram vs Parakeet pre-recorded.

Uses the same multi-lang audio samples from PR #7142 (edge-tts generated,
8 single-language + 3 code-switching). Measures WER per language and
code-switching handling.

Setup:
    curl -o /tmp/multilang.tar.gz https://storage.googleapis.com/omi-pr-assets/pr-7142/stt_benchmark_multilang_11.tar.gz
    mkdir -p /tmp/stt_benchmark_multilang && tar xzf /tmp/multilang.tar.gz -C /tmp/stt_benchmark_multilang

Usage:
    cd backend && python scripts/stt/w_benchmark_parakeet_multilang.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from jiwer import wer as compute_wer
from tabulate import tabulate

from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes, parakeet_prerecorded_from_bytes

PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)
AUDIO_DIR = Path('/tmp/stt_benchmark_multilang')
RESULTS_DIR = Path('/tmp/stt_benchmark_results')


def normalize_for_wer(text: str) -> str:
    return PUNCT_RE.sub('', text).lower().strip()


def load_manifest() -> List[dict]:
    manifest_path = AUDIO_DIR / 'manifest.json'
    if not manifest_path.exists():
        print('ERROR: Multi-lang samples not found. Download:')
        print(
            '  curl -o /tmp/multilang.tar.gz https://storage.googleapis.com/omi-pr-assets/pr-7142/stt_benchmark_multilang_11.tar.gz'
        )
        print(
            '  mkdir -p /tmp/stt_benchmark_multilang && tar xzf /tmp/multilang.tar.gz -C /tmp/stt_benchmark_multilang'
        )
        sys.exit(1)
    with open(manifest_path) as f:
        return json.load(f)


def run_provider(fn, wav_bytes, provider_name):
    try:
        start = time.monotonic()
        result = fn(wav_bytes, sample_rate=16000, diarize=False, return_language=True)
        elapsed = time.monotonic() - start
        if isinstance(result, tuple):
            words, detected_lang = result
        else:
            words, detected_lang = result, 'unknown'
        text = ' '.join(w['text'] for w in words)
        return text, detected_lang, elapsed
    except Exception as e:
        return f'ERROR: {e}', 'error', 0.0


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

    single_lang = [s for s in manifest if not s['id'].startswith('mix_')]
    code_switch = [s for s in manifest if s['id'].startswith('mix_')]

    print(f'\n{"=" * 100}')
    print(f'Multi-language Benchmark: Deepgram nova-3 vs Parakeet')
    print(f'  Single-language: {len(single_lang)} samples')
    print(f'  Code-switching: {len(code_switch)} samples')
    print(f'  Parakeet: {parakeet_url}')
    print(f'{"=" * 100}\n')

    results = []

    print('--- SINGLE-LANGUAGE ---\n')
    for sample in single_lang:
        wav_path = AUDIO_DIR / sample['wav']
        wav_bytes = wav_path.read_bytes()
        ref_text = sample.get('text', '')
        ref_norm = normalize_for_wer(ref_text)

        print(f"  [{sample['id']}] {sample['description']}")

        row = {'id': sample['id'], 'language': sample.get('language', ''), 'ref_text': ref_text, 'type': 'single'}

        dg_text, dg_lang, dg_lat = run_provider(deepgram_prerecorded_from_bytes, wav_bytes, 'deepgram')
        if not dg_text.startswith('ERROR'):
            dg_wer = compute_wer(ref_norm, normalize_for_wer(dg_text)) if ref_norm else 1.0
            row.update({'dg_text': dg_text, 'dg_wer': dg_wer, 'dg_lang': dg_lang, 'dg_lat': dg_lat})
            print(f"    DG:  WER={dg_wer:.0%}  det={dg_lang}  lat={dg_lat:.2f}s")
        else:
            row.update({'dg_text': dg_text, 'dg_wer': None})
            print(f"    DG:  {dg_text}")

        pk_text, pk_lang, pk_lat = run_provider(parakeet_prerecorded_from_bytes, wav_bytes, 'parakeet')
        if not pk_text.startswith('ERROR'):
            pk_wer = compute_wer(ref_norm, normalize_for_wer(pk_text)) if ref_norm else 1.0
            row.update({'pk_text': pk_text, 'pk_wer': pk_wer, 'pk_lang': pk_lang, 'pk_lat': pk_lat})
            print(f"    PK:  WER={pk_wer:.0%}  det={pk_lang}  lat={pk_lat:.2f}s")
        else:
            row.update({'pk_text': pk_text, 'pk_wer': None})
            print(f"    PK:  {pk_text}")

        results.append(row)

    print('\n--- CODE-SWITCHING ---\n')
    for sample in code_switch:
        wav_path = AUDIO_DIR / sample['wav']
        wav_bytes = wav_path.read_bytes()
        ref_text = sample.get('full_text', sample.get('text', ''))
        ref_norm = normalize_for_wer(ref_text)

        print(f"  [{sample['id']}] {sample['description']}")
        print(f"    REF: {ref_text}")

        row = {'id': sample['id'], 'language': 'mixed', 'ref_text': ref_text, 'type': 'code-switch'}

        dg_text, dg_lang, dg_lat = run_provider(deepgram_prerecorded_from_bytes, wav_bytes, 'deepgram')
        if not dg_text.startswith('ERROR'):
            dg_wer = compute_wer(ref_norm, normalize_for_wer(dg_text)) if ref_norm else 1.0
            row.update({'dg_text': dg_text, 'dg_wer': dg_wer, 'dg_lang': dg_lang, 'dg_lat': dg_lat})
            print(f"    DG:  WER={dg_wer:.0%}  → {dg_text}")
        else:
            row.update({'dg_text': dg_text, 'dg_wer': None})
            print(f"    DG:  {dg_text}")

        pk_text, pk_lang, pk_lat = run_provider(parakeet_prerecorded_from_bytes, wav_bytes, 'parakeet')
        if not pk_text.startswith('ERROR'):
            pk_wer = compute_wer(ref_norm, normalize_for_wer(pk_text)) if ref_norm else 1.0
            row.update({'pk_text': pk_text, 'pk_wer': pk_wer, 'pk_lang': pk_lang, 'pk_lat': pk_lat})
            print(f"    PK:  WER={pk_wer:.0%}  → {pk_text}")
        else:
            row.update({'pk_text': pk_text, 'pk_wer': None})
            print(f"    PK:  {pk_text}")

        results.append(row)

    print(f'\n{"=" * 100}')
    print('RESULTS SUMMARY')
    print(f'{"=" * 100}\n')

    table = []
    for r in results:
        dg_w = r.get('dg_wer')
        pk_w = r.get('pk_wer')
        table.append(
            [
                r['id'],
                r['language'],
                r['type'],
                f"{dg_w:.0%}" if dg_w is not None else 'ERR',
                f"{pk_w:.0%}" if pk_w is not None else 'ERR',
                f"{r.get('dg_lat', 0):.2f}s" if r.get('dg_lat') else '-',
                f"{r.get('pk_lat', 0):.2f}s" if r.get('pk_lat') else '-',
            ]
        )

    print(tabulate(table, headers=['ID', 'Lang', 'Type', 'DG WER', 'PK WER', 'DG Lat', 'PK Lat'], tablefmt='grid'))

    single_results = [r for r in results if r['type'] == 'single']
    cs_results = [r for r in results if r['type'] == 'code-switch']

    dg_single = [r['dg_wer'] for r in single_results if r.get('dg_wer') is not None]
    pk_single = [r['pk_wer'] for r in single_results if r.get('pk_wer') is not None]
    dg_cs = [r['dg_wer'] for r in cs_results if r.get('dg_wer') is not None]
    pk_cs = [r['pk_wer'] for r in cs_results if r.get('pk_wer') is not None]

    print('\nSINGLE-LANGUAGE:')
    if dg_single:
        print(f"  Deepgram avg WER: {sum(dg_single)/len(dg_single):.0%}")
    if pk_single:
        print(f"  Parakeet avg WER: {sum(pk_single)/len(pk_single):.0%}")

    print('\nCODE-SWITCHING:')
    if dg_cs:
        print(f"  Deepgram avg WER: {sum(dg_cs)/len(dg_cs):.0%}")
    if pk_cs:
        print(f"  Parakeet avg WER: {sum(pk_cs)/len(pk_cs):.0%}")

    print('\nTRANSCRIPTS:')
    for r in results:
        print(f"\n  [{r['id']}] {r['language']} ({r['type']})")
        print(f"    REF: {r['ref_text']}")
        print(f"    DG:  {r.get('dg_text', 'N/A')}")
        print(f"    PK:  {r.get('pk_text', 'N/A')}")

    output_path = RESULTS_DIR / 'parakeet_multilang_benchmark.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f'\nResults saved to: {output_path}')


if __name__ == '__main__':
    main()
