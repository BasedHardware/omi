"""
Benchmark Suite: Parakeet/Nemotron ASR — Streaming transcription.

Compares Parakeet against Deepgram nova-3 streaming using LibriSpeech
test-clean samples. Streams at real-time pace (3200 bytes/100ms) matching
the Omi wearable output format.

Setup:
    1. Prepare samples:
       python scripts/stt/n_benchmark_02_prerecorded.py --prepare
    2. Set env vars:
       HOSTED_PARAKEET_API_URL=http://<parakeet-service>:8080
       DEEPGRAM_API_KEY=<key>

Usage:
    cd backend && python scripts/stt/v_benchmark_parakeet_streaming.py
"""

import asyncio
import json
import os
import re
import sys
import time
import wave as _wave
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

from jiwer import wer as compute_wer
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.stt.streaming import process_audio_dg, process_audio_parakeet

PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)

AUDIO_DIR = Path('/tmp/stt_benchmark_audio_02')
RESULTS_DIR = Path('/tmp/stt_benchmark_results')

CHUNK_SIZE = 3200
CHUNK_INTERVAL = 0.1


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


def read_pcm_from_wav(wav_path: Path) -> bytes:
    with _wave.open(str(wav_path), 'rb') as wf:
        return wf.readframes(wf.getnframes())


async def stream_to_deepgram(audio_pcm: bytes, language: str) -> dict:
    segments_received = []
    first_segment_time = [None]
    connect_start = time.monotonic()

    def stream_transcript(segments):
        if first_segment_time[0] is None:
            first_segment_time[0] = time.monotonic()
        segments_received.extend(segments)

    sock = await process_audio_dg(stream_transcript, language, 16000, 1)
    connect_time = time.monotonic() - connect_start

    stream_start = time.monotonic()
    for i in range(0, len(audio_pcm), CHUNK_SIZE):
        chunk = audio_pcm[i : i + CHUNK_SIZE]
        sock.send(chunk)
        await asyncio.sleep(CHUNK_INTERVAL)

    sock.finish()
    await sock.drain_and_close()
    total_time = time.monotonic() - stream_start

    text = ' '.join(s.get('text', '') for s in segments_received).strip()
    first_seg = (first_segment_time[0] - stream_start) if first_segment_time[0] else None

    return {
        'text': text,
        'connect_time': round(connect_time, 3),
        'first_segment_s': round(first_seg, 3) if first_seg else None,
        'total_time': round(total_time, 3),
        'segments': len(segments_received),
    }


async def stream_to_parakeet(audio_pcm: bytes, language: str) -> dict:
    segments_received = []
    first_segment_time = [None]
    connect_start = time.monotonic()

    def stream_transcript(segments):
        if first_segment_time[0] is None:
            first_segment_time[0] = time.monotonic()
        segments_received.extend(segments)

    sock = await process_audio_parakeet(stream_transcript, language, 16000, 1)
    connect_time = time.monotonic() - connect_start

    stream_start = time.monotonic()
    for i in range(0, len(audio_pcm), CHUNK_SIZE):
        chunk = audio_pcm[i : i + CHUNK_SIZE]
        sock.send(chunk)
        await asyncio.sleep(CHUNK_INTERVAL)

    sock.finish()
    await sock.drain_and_close()
    total_time = time.monotonic() - stream_start

    text = ' '.join(s.get('text', '') for s in segments_received).strip()
    first_seg = (first_segment_time[0] - stream_start) if first_segment_time[0] else None

    return {
        'text': text,
        'connect_time': round(connect_time, 3),
        'first_segment_s': round(first_seg, 3) if first_seg else None,
        'total_time': round(total_time, 3),
        'segments': len(segments_received),
    }


async def main():
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
    print(f'\nBenchmark: Deepgram nova-3 vs Parakeet — Streaming ({len(manifest)} samples)')
    print(f'Parakeet endpoint: {parakeet_url}')
    print(f'Chunk: {CHUNK_SIZE} bytes / {CHUNK_INTERVAL}s (real-time pace)\n')

    results = []
    for case in manifest:
        wav_path = AUDIO_DIR / f"{case['id']}.wav"
        audio_pcm = read_pcm_from_wav(wav_path)
        ref_norm = normalize_for_wer(case['text'])

        row = {
            'id': case['id'],
            'description': case['description'],
            'duration_s': case['duration_s'],
            'ref_words': case['word_count'],
            'ref_text': case['text'],
        }

        print(f"  [{case['id']}] {case['description']}")

        try:
            dg = await stream_to_deepgram(audio_pcm, 'en')
            dg_norm = normalize_for_wer(dg['text'])
            dg_wer = compute_wer(ref_norm, dg_norm) if ref_norm and dg_norm else 1.0
            row.update(
                {
                    'dg_text': dg['text'],
                    'dg_wer': round(dg_wer * 100, 1),
                    'dg_connect_s': dg['connect_time'],
                    'dg_first_seg_s': dg['first_segment_s'],
                    'dg_total_s': dg['total_time'],
                    'dg_segments': dg['segments'],
                }
            )
            print(f"    DG: WER={dg_wer*100:.1f}% first_seg={dg['first_segment_s']}s segs={dg['segments']}")
        except Exception as e:
            print(f"    DG ERROR: {e}")

        try:
            pk = await stream_to_parakeet(audio_pcm, 'en')
            pk_norm = normalize_for_wer(pk['text'])
            pk_wer = compute_wer(ref_norm, pk_norm) if ref_norm and pk_norm else 1.0
            row.update(
                {
                    'pk_text': pk['text'],
                    'pk_wer': round(pk_wer * 100, 1),
                    'pk_connect_s': pk['connect_time'],
                    'pk_first_seg_s': pk['first_segment_s'],
                    'pk_total_s': pk['total_time'],
                    'pk_segments': pk['segments'],
                }
            )
            print(f"    PK: WER={pk_wer*100:.1f}% first_seg={pk['first_segment_s']}s segs={pk['segments']}")
        except Exception as e:
            print(f"    PK ERROR: {e}")

        results.append(row)

    with open(RESULTS_DIR / 'parakeet_streaming_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print('\n' + '=' * 80)
    print('RESULTS SUMMARY')
    print('=' * 80)

    table = []
    for r in results:
        table.append(
            [
                r['id'],
                f"{r['duration_s']:.1f}s",
                f"{r.get('dg_wer', 'ERR')}%",
                f"{r.get('pk_wer', 'ERR')}%",
                f"{r.get('dg_first_seg_s', 'ERR')}s",
                f"{r.get('pk_first_seg_s', 'ERR')}s",
                r.get('dg_segments', '-'),
                r.get('pk_segments', '-'),
            ]
        )

    print(tabulate(table, headers=['Sample', 'Dur', 'DG WER', 'PK WER', 'DG 1st', 'PK 1st', 'DG Seg', 'PK Seg']))
    print(f'\n  Results saved to: {RESULTS_DIR / "parakeet_streaming_results.json"}')


if __name__ == '__main__':
    asyncio.run(main())
