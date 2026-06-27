"""
Benchmark: Pre-recorded STT via API endpoints (sync-local-files + voice-message/transcribe).

Tests the full HTTP path that production uses — not just the STT function.
Exercises STT_PRERECORDED_MODEL routing end-to-end.

Uses LibriSpeech test-clean samples (shared with suite 02).

Setup:
    1. Prepare samples (if not already done):
       python scripts/stt/n_benchmark_02_prerecorded.py --prepare
    2. Start local backend:
       python -m uvicorn main:app --host 0.0.0.0 --port 8700

Usage:
    # Test pre-recorded functions directly (no running server needed)
    cd backend && python scripts/stt/s_benchmark_prerecorded_api.py --mode direct

    # Test via /v2/voice-message/transcribe endpoint (needs running server)
    cd backend && python scripts/stt/s_benchmark_prerecorded_api.py --mode api --port 8700

    # Compare DG vs Modulate routing
    cd backend && python scripts/stt/s_benchmark_prerecorded_api.py --mode direct --compare
"""

import argparse
import json
import os
import re
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import List, Tuple
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from jiwer import wer as compute_wer
from tabulate import tabulate

PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)
AUDIO_DIR = Path('/tmp/stt_benchmark_audio_02')
RESULTS_DIR = Path('/tmp/stt_benchmark_results')


def normalize_for_wer(text: str) -> str:
    return PUNCT_RE.sub('', text).lower().strip()


def load_manifest() -> List[dict]:
    manifest_path = AUDIO_DIR / 'manifest.json'
    if not manifest_path.exists():
        print('ERROR: Samples not prepared. Run first:')
        print('  python scripts/stt/n_benchmark_02_prerecorded.py --prepare')
        sys.exit(1)
    with open(manifest_path) as f:
        return json.load(f)


def read_wav_bytes(wav_path: Path) -> bytes:
    return wav_path.read_bytes()


# ---------------------------------------------------------------------------
# Mode: direct — call pre-recorded functions directly
# ---------------------------------------------------------------------------


def run_direct_deepgram(wav_bytes: bytes, language: str) -> dict:
    from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes

    start = time.monotonic()
    words, detected_lang = deepgram_prerecorded_from_bytes(
        wav_bytes,
        sample_rate=16000,
        diarize=True,
        return_language=True,
        language=language,
    )
    elapsed = time.monotonic() - start
    text = ' '.join(w['text'] for w in words)
    return {
        'provider': 'deepgram',
        'text': text,
        'words': len(words),
        'language': detected_lang,
        'latency': elapsed,
    }


def run_direct_modulate(wav_bytes: bytes, language: str) -> dict:
    from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

    start = time.monotonic()
    words, detected_lang = modulate_prerecorded_from_bytes(
        wav_bytes,
        sample_rate=16000,
        diarize=True,
        return_language=True,
    )
    elapsed = time.monotonic() - start
    text = ' '.join(w['text'] for w in words)
    return {
        'provider': 'modulate',
        'text': text,
        'words': len(words),
        'language': detected_lang,
        'latency': elapsed,
    }


def run_direct_routed(wav_bytes: bytes, language: str, model_env: str) -> dict:
    """Test get_prerecorded_service routing with a specific STT_PRERECORDED_MODEL value."""
    from utils.stt.pre_recorded import (
        PrerecordedSTTService,
        deepgram_prerecorded_from_bytes,
        get_prerecorded_service,
        modulate_prerecorded_from_bytes,
    )

    with patch('utils.stt.pre_recorded.stt_prerecorded_model', model_env):
        svc, stt_lang, stt_model = get_prerecorded_service(language)

    start = time.monotonic()
    if svc == PrerecordedSTTService.MODULATE:
        words, detected_lang = modulate_prerecorded_from_bytes(
            wav_bytes,
            sample_rate=16000,
            diarize=True,
            return_language=True,
        )
    else:
        words, detected_lang = deepgram_prerecorded_from_bytes(
            wav_bytes,
            sample_rate=16000,
            diarize=True,
            return_language=True,
            language=stt_lang,
            model=stt_model,
        )
    elapsed = time.monotonic() - start
    text = ' '.join(w['text'] for w in words)
    return {
        'provider': f'{svc} (routed via {model_env})',
        'text': text,
        'words': len(words),
        'language': detected_lang,
        'latency': elapsed,
        'stt_service': svc,
        'stt_lang': stt_lang,
        'stt_model': stt_model,
    }


# ---------------------------------------------------------------------------
# Mode: api — call HTTP endpoints
# ---------------------------------------------------------------------------


def run_api_voice_transcribe(wav_bytes: bytes, host: str, port: int, token: str) -> dict:
    import httpx

    url = f'http://{host}:{port}/v2/voice-message/transcribe'
    headers = {'Authorization': f'Bearer {token}'}
    files = {'file': ('audio.wav', BytesIO(wav_bytes), 'audio/wav')}

    start = time.monotonic()
    with httpx.Client(timeout=120) as client:
        resp = client.post(url, headers=headers, files=files)
    elapsed = time.monotonic() - start

    if resp.status_code != 200:
        return {'error': f'HTTP {resp.status_code}: {resp.text[:200]}', 'latency': elapsed}

    data = resp.json()
    return {
        'provider': 'api:voice-transcribe',
        'text': data.get('transcript', ''),
        'language': data.get('language', ''),
        'latency': elapsed,
    }


def run_api_sync_local_files(wav_bytes: bytes, host: str, port: int, token: str) -> dict:
    import httpx

    url = f'http://{host}:{port}/v1/sync-local-files'
    headers = {'Authorization': f'Bearer {token}'}
    files = [('files', ('segment.wav', BytesIO(wav_bytes), 'audio/wav'))]

    start = time.monotonic()
    with httpx.Client(timeout=120) as client:
        resp = client.post(url, headers=headers, files=files)
    elapsed = time.monotonic() - start

    if resp.status_code != 200:
        return {'error': f'HTTP {resp.status_code}: {resp.text[:200]}', 'latency': elapsed}

    data = resp.json()
    return {
        'provider': 'api:sync-local-files',
        'response': data,
        'latency': elapsed,
    }


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def run_direct_benchmark(manifest: List[dict], compare: bool, max_samples: int):
    print(f'\n=== Pre-recorded STT Benchmark (direct function calls) ===')
    print(f'Samples: {len(manifest[:max_samples])} (LibriSpeech test-clean)\n')

    results = []
    for case in manifest[:max_samples]:
        wav_path = AUDIO_DIR / f"{case['id']}.wav"
        wav_bytes = read_wav_bytes(wav_path)
        ref_norm = normalize_for_wer(case['text'])

        print(f"  [{case['id']}] {case['description']} ({case['word_count']} words, {case['duration_s']:.1f}s)")

        row = {
            'id': case['id'],
            'ref_words': case['word_count'],
            'duration_s': case['duration_s'],
            'ref_text': case['text'],
        }

        if compare:
            for model_env in ['dg-nova-3', 'modulate-velma-2']:
                try:
                    result = run_direct_routed(wav_bytes, 'multi', model_env)
                    wer_val = compute_wer(ref_norm, normalize_for_wer(result['text'])) if result['text'] else 1.0
                    prefix = 'dg' if 'deepgram' in result.get('stt_service', '') else 'mod'
                    row[f'{prefix}_text'] = result['text']
                    row[f'{prefix}_wer'] = wer_val
                    row[f'{prefix}_latency'] = result['latency']
                    row[f'{prefix}_words'] = result.get('words', 0)
                    row[f'{prefix}_route'] = f"{result.get('stt_service')}:{result.get('stt_model')}"
                    print(
                        f"    {model_env:20s}  WER={wer_val:.1%}  latency={result['latency']:.2f}s  route={result.get('stt_service')}:{result.get('stt_model')}"
                    )
                except Exception as e:
                    print(f"    {model_env:20s}  ERROR: {e}")
                    row[f'{"dg" if "dg" in model_env else "mod"}_wer'] = 1.0
        else:
            try:
                result = run_direct_routed(wav_bytes, 'multi', os.getenv('STT_PRERECORDED_MODEL', 'dg-nova-3'))
                wer_val = compute_wer(ref_norm, normalize_for_wer(result['text'])) if result['text'] else 1.0
                row['text'] = result['text']
                row['wer'] = wer_val
                row['latency'] = result['latency']
                row['provider'] = result['provider']
                print(f"    {result['provider']:40s}  WER={wer_val:.1%}  latency={result['latency']:.2f}s")
            except Exception as e:
                print(f"    ERROR: {e}")
                row['wer'] = 1.0

        results.append(row)

    # Summary
    print(f'\n{"=" * 100}')
    if compare:
        valid_dg = [r for r in results if 'dg_wer' in r and r.get('dg_wer', 1) < 1]
        valid_mod = [r for r in results if 'mod_wer' in r and r.get('mod_wer', 1) < 1]

        table = []
        for r in results:
            table.append(
                [
                    r['id'],
                    r['ref_words'],
                    f"{r['duration_s']:.1f}s",
                    f"{r.get('dg_wer', 1):.1%}",
                    f"{r.get('dg_latency', -1):.2f}s",
                    f"{r.get('mod_wer', 1):.1%}",
                    f"{r.get('mod_latency', -1):.2f}s",
                ]
            )
        print(
            tabulate(
                table, headers=['Case', 'Words', 'Dur', 'DG WER', 'DG Time', 'Mod WER', 'Mod Time'], tablefmt='grid'
            )
        )

        print('\nSUMMARY:')
        if valid_dg:
            print(
                f"  Deepgram (routed):   avg_WER={sum(r['dg_wer'] for r in valid_dg)/len(valid_dg):.1%}  avg_latency={sum(r['dg_latency'] for r in valid_dg)/len(valid_dg):.2f}s  cases={len(valid_dg)}"
            )
        if valid_mod:
            print(
                f"  Modulate (routed):   avg_WER={sum(r['mod_wer'] for r in valid_mod)/len(valid_mod):.1%}  avg_latency={sum(r['mod_latency'] for r in valid_mod)/len(valid_mod):.2f}s  cases={len(valid_mod)}"
            )

        print('\nTRANSCRIPT COMPARISON:')
        for r in results:
            print(f"\n  [{r['id']}] {r.get('ref_text', '')[:80]}")
            print(f"    REF:      {r.get('ref_text', 'N/A')}")
            print(f"    DEEPGRAM: {r.get('dg_text', 'N/A')}  (WER={r.get('dg_wer', 1):.1%})")
            print(f"    MODULATE: {r.get('mod_text', 'N/A')}  (WER={r.get('mod_wer', 1):.1%})")
    else:
        valid = [r for r in results if r.get('wer', 1) < 1]
        if valid:
            print(
                f"  avg_WER={sum(r['wer'] for r in valid)/len(valid):.1%}  avg_latency={sum(r['latency'] for r in valid)/len(valid):.2f}s  cases={len(valid)}"
            )

    output_path = RESULTS_DIR / 'prerecorded_api_benchmark.json'
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nResults saved to: {output_path}')


def run_api_benchmark(manifest: List[dict], host: str, port: int, token: str, max_samples: int):
    print(f'\n=== Pre-recorded STT Benchmark (HTTP API endpoints) ===')
    print(f'Server: http://{host}:{port}')
    print(f'Samples: {len(manifest[:max_samples])}\n')

    if not token:
        print('ERROR: --token required for API mode (Firebase auth token)')
        print('  Get one via: beast omi dev auth-token')
        sys.exit(1)

    results = []
    for case in manifest[:max_samples]:
        wav_path = AUDIO_DIR / f"{case['id']}.wav"
        wav_bytes = read_wav_bytes(wav_path)
        ref_norm = normalize_for_wer(case['text'])

        print(f"  [{case['id']}] {case['description']} ({case['word_count']} words)")

        # Test voice-message/transcribe
        try:
            result = run_api_voice_transcribe(wav_bytes, host, port, token)
            if 'error' in result:
                print(f"    voice-transcribe: {result['error']}")
            else:
                wer_val = compute_wer(ref_norm, normalize_for_wer(result['text'])) if result['text'] else 1.0
                print(f"    voice-transcribe:  WER={wer_val:.1%}  latency={result['latency']:.2f}s")
                result['wer'] = wer_val
        except Exception as e:
            print(f"    voice-transcribe:  ERROR - {e}")
            result = {'error': str(e)}

        results.append({'case': case['id'], 'endpoint': 'voice-transcribe', **result})

    output_path = RESULTS_DIR / 'prerecorded_api_endpoint_benchmark.json'
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nResults saved to: {output_path}')


def main():
    parser = argparse.ArgumentParser(description='Pre-recorded STT benchmark via API paths')
    parser.add_argument(
        '--mode', choices=['direct', 'api'], default='direct', help='direct: call functions; api: call HTTP endpoints'
    )
    parser.add_argument('--compare', action='store_true', help='Compare DG vs Modulate routing (direct mode only)')
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=8700)
    parser.add_argument('--token', default=os.getenv('OMI_AUTH_TOKEN', ''), help='Firebase auth token for API mode')
    parser.add_argument('--samples', type=int, default=12, help='Max samples to test (default: all 12)')
    args = parser.parse_args()

    manifest = load_manifest()

    if args.mode == 'direct':
        run_direct_benchmark(manifest, args.compare, args.samples)
    elif args.mode == 'api':
        run_api_benchmark(manifest, args.host, args.port, args.token, args.samples)


if __name__ == '__main__':
    main()
