"""
Benchmark Suite 02: Deepgram vs Modulate — Streaming transcription.

Uses real human speech from LibriSpeech test-clean dataset (12 samples,
12 speakers, 2-27s duration, 4-62 words). Ground truth transcripts for
accurate WER measurement. Streams at real-time pace (3200 bytes/100ms).

Setup:
    1. Download LibriSpeech test-clean:
       curl -L -o /tmp/test-clean.tar.gz https://www.openslr.org/resources/12/test-clean.tar.gz
    2. Prepare samples (shared with pre-recorded benchmark):
       python scripts/stt/n_benchmark_02_prerecorded.py --prepare

Usage:
    cd backend && python scripts/stt/o_benchmark_02_streaming.py
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

from jiwer import wer as compute_wer
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.stt.streaming import process_audio_dg, process_audio_modulate

PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)


def normalize_for_wer(text: str) -> str:
    return PUNCT_RE.sub('', text).lower().strip()


def count_punctuation(text: str) -> dict:
    marks = re.findall(r'[^\w\s]', text)
    return {'total': len(marks), 'detail': dict(sorted(((m, marks.count(m)) for m in set(marks)), key=lambda x: -x[1]))}


AUDIO_DIR = Path('/tmp/stt_benchmark_audio_02')
RESULTS_DIR = Path('/tmp/stt_benchmark_results')

CHUNK_SIZE = 3200
CHUNK_INTERVAL = 0.1


def load_manifest() -> List[dict]:
    manifest_path = AUDIO_DIR / 'manifest.json'
    if not manifest_path.exists():
        print('ERROR: Samples not prepared. Run first:')
        print('  python scripts/stt/n_benchmark_02_prerecorded.py --prepare')
        sys.exit(1)
    with open(manifest_path) as f:
        return json.load(f)


def read_pcm_from_wav(wav_path: Path) -> bytes:
    data = wav_path.read_bytes()
    if data[:4] == b'RIFF':
        return data[44:]
    return data


async def stream_to_deepgram(audio_pcm: bytes, language: str) -> dict:
    segments_received = []
    first_segment_time = [None]
    connect_start = time.monotonic()

    def stream_transcript(segments):
        if first_segment_time[0] is None:
            first_segment_time[0] = time.monotonic()
        segments_received.extend(segments)

    try:
        socket = await asyncio.wait_for(
            process_audio_dg(stream_transcript, language, 16000, 1, model='nova-3'),
            timeout=15,
        )
    except Exception as e:
        return {'error': str(e), 'connect_time': -1}

    connect_time = time.monotonic() - connect_start
    stream_start = time.monotonic()

    offset = 0
    while offset < len(audio_pcm):
        chunk = audio_pcm[offset : offset + CHUNK_SIZE]
        socket.send(chunk)
        offset += CHUNK_SIZE
        await asyncio.sleep(CHUNK_INTERVAL)

    socket.finish()
    await asyncio.sleep(3)

    total_time = time.monotonic() - stream_start
    text = ' '.join(s.get('text', '') for s in segments_received).strip()
    first_seg_latency = (first_segment_time[0] - stream_start) if first_segment_time[0] else -1

    return {
        'connect_time': connect_time,
        'first_segment_latency': first_seg_latency,
        'total_time': total_time,
        'segments': len(segments_received),
        'text': text,
        'words': len(text.split()) if text else 0,
    }


async def stream_to_modulate(audio_pcm: bytes, language: str) -> dict:
    segments_received = []
    first_segment_time = [None]
    connect_start = time.monotonic()

    def stream_transcript(segments):
        if first_segment_time[0] is None:
            first_segment_time[0] = time.monotonic()
        segments_received.extend(segments)

    try:
        socket = await asyncio.wait_for(
            process_audio_modulate(stream_transcript, 16000, language),
            timeout=15,
        )
    except Exception as e:
        return {'error': str(e), 'connect_time': -1}

    connect_time = time.monotonic() - connect_start
    stream_start = time.monotonic()

    offset = 0
    while offset < len(audio_pcm):
        chunk = audio_pcm[offset : offset + CHUNK_SIZE]
        socket.send(chunk)
        offset += CHUNK_SIZE
        await asyncio.sleep(CHUNK_INTERVAL)

    try:
        await asyncio.wait_for(socket.drain_and_close(), timeout=30)
    except (asyncio.TimeoutError, Exception):
        pass

    total_time = time.monotonic() - stream_start
    text = ' '.join(s.get('text', '') for s in segments_received).strip()
    first_seg_latency = (first_segment_time[0] - stream_start) if first_segment_time[0] else -1

    return {
        'connect_time': connect_time,
        'first_segment_latency': first_seg_latency,
        'total_time': total_time,
        'segments': len(segments_received),
        'text': text,
        'words': len(text.split()) if text else 0,
    }


async def run_benchmark():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    dg_key = os.getenv('DEEPGRAM_API_KEY')
    mod_key = os.getenv('MODULATE_API_KEY')
    if not dg_key:
        print('ERROR: DEEPGRAM_API_KEY not set')
        sys.exit(1)
    if not mod_key:
        print('ERROR: MODULATE_API_KEY not set')
        sys.exit(1)

    manifest = load_manifest()
    print(f'\nBenchmark Suite 02 — Streaming ({len(manifest)} samples, real human speech)')
    print(f'Source: LibriSpeech test-clean (CC BY 4.0)')
    print(f'Streaming at real-time pace: {CHUNK_SIZE} bytes / {CHUNK_INTERVAL}s = 16kHz mono s16le\n')

    results = []
    for case in manifest:
        wav_path = AUDIO_DIR / f"{case['id']}.wav"
        audio_pcm = read_pcm_from_wav(wav_path)
        ref_norm = normalize_for_wer(case['text'])
        lang = 'en'

        row = {
            'id': case['id'],
            'uid': case['uid'],
            'description': case['description'],
            'speaker': case['speaker'],
            'ref_words': case['word_count'],
            'duration_s': case['duration_s'],
            'audio_kb': len(audio_pcm) / 1024,
            'ref_text': case['text'],
        }

        print(f"  [{case['id']}] {case['description']} (speaker {case['speaker']})")

        try:
            dg_result = await stream_to_deepgram(audio_pcm, lang)
            if 'error' in dg_result:
                raise RuntimeError(dg_result['error'])
            dg_wer = compute_wer(ref_norm, normalize_for_wer(dg_result['text'])) if dg_result['text'] else 1.0
            dg_punct = count_punctuation(dg_result['text']) if dg_result['text'] else {'total': 0, 'detail': {}}
            row.update(
                {
                    'dg_connect': dg_result['connect_time'],
                    'dg_first_seg': dg_result['first_segment_latency'],
                    'dg_total': dg_result['total_time'],
                    'dg_segments': dg_result['segments'],
                    'dg_words': dg_result['words'],
                    'dg_wer': dg_wer,
                    'dg_text': dg_result['text'],
                    'dg_punct': dg_punct['total'],
                    'dg_punct_detail': dg_punct['detail'],
                }
            )
            print(
                f"    Deepgram:  connect={dg_result['connect_time']:.2f}s  "
                f"first_seg={dg_result['first_segment_latency']:.2f}s  "
                f"total={dg_result['total_time']:.2f}s  "
                f"segs={dg_result['segments']}  WER={dg_wer:.2%}  punct={dg_punct['total']}"
            )
        except Exception as e:
            print(f"    Deepgram:  ERROR - {e}")
            row.update(
                {
                    'dg_connect': -1,
                    'dg_first_seg': -1,
                    'dg_total': -1,
                    'dg_segments': 0,
                    'dg_words': 0,
                    'dg_wer': 1.0,
                    'dg_text': f'ERROR: {e}',
                    'dg_punct': 0,
                    'dg_punct_detail': {},
                }
            )

        try:
            mod_result = await stream_to_modulate(audio_pcm, lang)
            if 'error' in mod_result:
                raise RuntimeError(mod_result['error'])
            mod_wer = compute_wer(ref_norm, normalize_for_wer(mod_result['text'])) if mod_result['text'] else 1.0
            mod_punct = count_punctuation(mod_result['text']) if mod_result['text'] else {'total': 0, 'detail': {}}
            row.update(
                {
                    'mod_connect': mod_result['connect_time'],
                    'mod_first_seg': mod_result['first_segment_latency'],
                    'mod_total': mod_result['total_time'],
                    'mod_segments': mod_result['segments'],
                    'mod_words': mod_result['words'],
                    'mod_wer': mod_wer,
                    'mod_text': mod_result['text'],
                    'mod_punct': mod_punct['total'],
                    'mod_punct_detail': mod_punct['detail'],
                }
            )
            print(
                f"    Modulate:  connect={mod_result['connect_time']:.2f}s  "
                f"first_seg={mod_result['first_segment_latency']:.2f}s  "
                f"total={mod_result['total_time']:.2f}s  "
                f"segs={mod_result['segments']}  WER={mod_wer:.2%}  punct={mod_punct['total']}"
            )
        except Exception as e:
            print(f"    Modulate:  ERROR - {e}")
            row.update(
                {
                    'mod_connect': -1,
                    'mod_first_seg': -1,
                    'mod_total': -1,
                    'mod_segments': 0,
                    'mod_words': 0,
                    'mod_wer': 1.0,
                    'mod_text': f'ERROR: {e}',
                    'mod_punct': 0,
                    'mod_punct_detail': {},
                }
            )

        results.append(row)

    print('\n' + '=' * 130)
    print('SUITE 02 — STREAMING BENCHMARK RESULTS (Real Human Speech — LibriSpeech test-clean)')
    print('=' * 130)

    def fmt_time(v):
        return f"{v:.2f}s" if v >= 0 else 'ERR'

    table_data = []
    for r in results:
        table_data.append(
            [
                r['id'],
                r['ref_words'],
                f"{r['duration_s']:.1f}s",
                fmt_time(r.get('dg_connect', -1)),
                fmt_time(r.get('dg_first_seg', -1)),
                fmt_time(r.get('dg_total', -1)),
                r.get('dg_segments', 0),
                f"{r.get('dg_wer', 1):.0%}",
                r.get('dg_punct', 0),
                fmt_time(r.get('mod_connect', -1)),
                fmt_time(r.get('mod_first_seg', -1)),
                fmt_time(r.get('mod_total', -1)),
                r.get('mod_segments', 0),
                f"{r.get('mod_wer', 1):.0%}",
                r.get('mod_punct', 0),
            ]
        )

    print(
        tabulate(
            table_data,
            headers=[
                'Case',
                'Words',
                'Duration',
                'DG Conn',
                'DG 1st Seg',
                'DG Total',
                'DG Segs',
                'DG WER',
                'DG Punct',
                'Mod Conn',
                'Mod 1st Seg',
                'Mod Total',
                'Mod Segs',
                'Mod WER',
                'Mod Punct',
            ],
            tablefmt='grid',
        )
    )

    valid_dg = [r for r in results if r.get('dg_total', -1) >= 0]
    valid_mod = [r for r in results if r.get('mod_total', -1) >= 0]

    print('\nSUMMARY (WER computed after stripping punctuation):')
    if valid_dg:
        dg_first_segs = [r['dg_first_seg'] for r in valid_dg if r['dg_first_seg'] >= 0]
        avg_dg_punct = sum(r.get('dg_punct', 0) for r in valid_dg) / len(valid_dg)
        print(
            f"  Deepgram:  "
            f"avg_connect={sum(r['dg_connect'] for r in valid_dg) / len(valid_dg):.2f}s  "
            f"avg_first_seg={sum(dg_first_segs) / max(1, len(dg_first_segs)):.2f}s  "
            f"avg_total={sum(r['dg_total'] for r in valid_dg) / len(valid_dg):.2f}s  "
            f"avg_WER={sum(r['dg_wer'] for r in valid_dg) / len(valid_dg):.1%}  "
            f"avg_punct={avg_dg_punct:.1f}  "
            f"cases={len(valid_dg)}"
        )
    if valid_mod:
        mod_first_segs = [r['mod_first_seg'] for r in valid_mod if r['mod_first_seg'] >= 0]
        avg_mod_punct = sum(r.get('mod_punct', 0) for r in valid_mod) / len(valid_mod)
        print(
            f"  Modulate:  "
            f"avg_connect={sum(r['mod_connect'] for r in valid_mod) / len(valid_mod):.2f}s  "
            f"avg_first_seg={sum(mod_first_segs) / max(1, len(mod_first_segs)):.2f}s  "
            f"avg_total={sum(r['mod_total'] for r in valid_mod) / len(valid_mod):.2f}s  "
            f"avg_WER={sum(r['mod_wer'] for r in valid_mod) / len(valid_mod):.1%}  "
            f"avg_punct={avg_mod_punct:.1f}  "
            f"cases={len(valid_mod)}"
        )

    print('\nTRANSCRIPT COMPARISON:')
    for r in results:
        print(f"\n  [{r['id']}] {r['description']}")
        print(f"    REF:      {r.get('ref_text', 'N/A')}")
        if r.get('dg_text', '').startswith('ERROR'):
            print(f"    DEEPGRAM: {r.get('dg_text', 'N/A')}")
        else:
            print(
                f"    DEEPGRAM: {r.get('dg_text', 'N/A')}  (WER={r.get('dg_wer', 1):.1%}, punct={r.get('dg_punct', 0)})"
            )
        if r.get('mod_text', '').startswith('ERROR'):
            print(f"    MODULATE: {r.get('mod_text', 'N/A')}")
        else:
            print(
                f"    MODULATE: {r.get('mod_text', 'N/A')}  (WER={r.get('mod_wer', 1):.1%}, punct={r.get('mod_punct', 0)})"
            )

    output_path = RESULTS_DIR / 'suite02_streaming_benchmark.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nDetailed results saved to: {output_path}')


def main():
    asyncio.run(run_benchmark())


if __name__ == '__main__':
    main()
