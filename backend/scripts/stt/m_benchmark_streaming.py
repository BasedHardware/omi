"""
Benchmark: Deepgram vs Modulate — Streaming transcription.

Generates 10+ diverse test audio samples and streams them through both
providers, measuring connection latency, first-segment latency, total
segments, transcription time, and WER against reference text.

Usage:
    cd backend && python scripts/stt/m_benchmark_streaming.py
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

from jiwer import wer as compute_wer
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.stt.streaming import process_audio_dg, process_audio_modulate

AUDIO_DIR = Path('/tmp/stt_benchmark_audio')
RESULTS_DIR = Path('/tmp/stt_benchmark_results')

BENCHMARK_CASES: List[dict] = [
    {
        'id': 'short_greeting',
        'text': 'Hello, how are you doing today?',
        'lang': 'en',
        'description': 'Short greeting (5 words)',
    },
    {
        'id': 'medium_sentence',
        'text': 'The quick brown fox jumps over the lazy dog near the old oak tree in the park.',
        'lang': 'en',
        'description': 'Medium sentence (17 words)',
    },
    {
        'id': 'technical_jargon',
        'text': 'The server processes incoming websocket connections on port eight thousand and eighty, using TLS encryption for secure data transmission.',
        'lang': 'en',
        'description': 'Technical content with numbers',
    },
    {
        'id': 'conversational',
        'text': "Well, I think we should probably go to the store and pick up some groceries before it closes. What do you think?",
        'lang': 'en',
        'description': 'Conversational with fillers',
    },
    {
        'id': 'numbers_dates',
        'text': 'The meeting is scheduled for January fifteenth, twenty twenty six, at three thirty in the afternoon.',
        'lang': 'en',
        'description': 'Numbers and dates',
    },
    {
        'id': 'medical_terms',
        'text': 'The patient was diagnosed with bilateral pneumonia and prescribed amoxicillin for ten days along with regular monitoring.',
        'lang': 'en',
        'description': 'Medical terminology',
    },
    {
        'id': 'long_paragraph',
        'text': (
            'Artificial intelligence has transformed many industries over the past decade. '
            'Machine learning models can now understand natural language, generate images, '
            'and even write code. However, there are still significant challenges in ensuring '
            'these systems are reliable, safe, and aligned with human values.'
        ),
        'lang': 'en',
        'description': 'Long paragraph (40+ words)',
    },
    {
        'id': 'names_places',
        'text': 'Doctor Sarah Chen from Stanford University presented her findings at the conference in San Francisco, California.',
        'lang': 'en',
        'description': 'Proper nouns (names, places)',
    },
    {
        'id': 'question_answer',
        'text': "What is the capital of France? The capital of France is Paris, which is located along the Seine River.",
        'lang': 'en',
        'description': 'Question and answer format',
    },
    {
        'id': 'instructions',
        'text': (
            'First, open the application settings. Then navigate to the audio section. '
            'Select the input device and set the sample rate to sixteen thousand hertz. '
            'Finally, click save to apply your changes.'
        ),
        'lang': 'en',
        'description': 'Step-by-step instructions',
    },
    {
        'id': 'emotional_speech',
        'text': "This is absolutely incredible! I can't believe we finally got it working after all these months of effort.",
        'lang': 'en',
        'description': 'Emotional/exclamatory speech',
    },
    {
        'id': 'multi_speaker_sim',
        'text': (
            'Good morning everyone. Today we will discuss the quarterly results. '
            'Revenue increased by fifteen percent compared to last quarter. '
            'Our customer satisfaction scores have also improved significantly.'
        ),
        'lang': 'en',
        'description': 'Meeting-style multi-sentence',
    },
]

CHUNK_SIZE = 3200
CHUNK_INTERVAL = 0.1


def generate_audio(case: dict, output_path: Path) -> None:
    tmp_raw = output_path.with_suffix('.raw.wav')
    subprocess.run(
        ['espeak-ng', '-v', case['lang'], '-w', str(tmp_raw), '--', case['text']],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ['ffmpeg', '-y', '-i', str(tmp_raw), '-ar', '16000', '-ac', '1', '-sample_fmt', 's16', str(output_path)],
        check=True,
        capture_output=True,
    )
    tmp_raw.unlink(missing_ok=True)


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
        await asyncio.wait_for(socket.drain_and_close(), timeout=20)
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
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    dg_key = os.getenv('DEEPGRAM_API_KEY')
    mod_key = os.getenv('MODULATE_API_KEY')
    if not dg_key:
        print('ERROR: DEEPGRAM_API_KEY not set')
        sys.exit(1)
    if not mod_key:
        print('ERROR: MODULATE_API_KEY not set')
        sys.exit(1)

    print(f'Generating {len(BENCHMARK_CASES)} test audio samples...')
    for case in BENCHMARK_CASES:
        wav_path = AUDIO_DIR / f"{case['id']}.wav"
        if not wav_path.exists():
            generate_audio(case, wav_path)
            print(f"  Generated: {case['id']} ({wav_path.stat().st_size / 1024:.1f} KB)")
        else:
            print(f"  Cached:    {case['id']}")

    print(f'\nRunning streaming benchmarks ({len(BENCHMARK_CASES)} cases x 2 providers)...\n')

    results = []
    for case in BENCHMARK_CASES:
        wav_path = AUDIO_DIR / f"{case['id']}.wav"
        audio_pcm = read_pcm_from_wav(wav_path)
        ref_text = case['text'].lower()
        lang = case['lang']

        row = {
            'id': case['id'],
            'description': case['description'],
            'ref_words': len(case['text'].split()),
            'audio_kb': len(audio_pcm) / 1024,
        }

        print(f"  [{case['id']}] {case['description']}")

        try:
            dg_result = await stream_to_deepgram(audio_pcm, lang)
            if 'error' in dg_result:
                raise RuntimeError(dg_result['error'])
            dg_wer = compute_wer(ref_text, dg_result['text'].lower()) if dg_result['text'] else 1.0
            row.update(
                {
                    'dg_connect': dg_result['connect_time'],
                    'dg_first_seg': dg_result['first_segment_latency'],
                    'dg_total': dg_result['total_time'],
                    'dg_segments': dg_result['segments'],
                    'dg_words': dg_result['words'],
                    'dg_wer': dg_wer,
                    'dg_text': dg_result['text'],
                }
            )
            print(
                f"    Deepgram:  connect={dg_result['connect_time']:.2f}s  "
                f"first_seg={dg_result['first_segment_latency']:.2f}s  "
                f"total={dg_result['total_time']:.2f}s  "
                f"segs={dg_result['segments']}  WER={dg_wer:.2%}"
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
                }
            )

        try:
            mod_result = await stream_to_modulate(audio_pcm, lang)
            if 'error' in mod_result:
                raise RuntimeError(mod_result['error'])
            mod_wer = compute_wer(ref_text, mod_result['text'].lower()) if mod_result['text'] else 1.0
            row.update(
                {
                    'mod_connect': mod_result['connect_time'],
                    'mod_first_seg': mod_result['first_segment_latency'],
                    'mod_total': mod_result['total_time'],
                    'mod_segments': mod_result['segments'],
                    'mod_words': mod_result['words'],
                    'mod_wer': mod_wer,
                    'mod_text': mod_result['text'],
                }
            )
            print(
                f"    Modulate:  connect={mod_result['connect_time']:.2f}s  "
                f"first_seg={mod_result['first_segment_latency']:.2f}s  "
                f"total={mod_result['total_time']:.2f}s  "
                f"segs={mod_result['segments']}  WER={mod_wer:.2%}"
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
                }
            )

        results.append(row)

    print('\n' + '=' * 120)
    print('STREAMING BENCHMARK RESULTS')
    print('=' * 120)

    table_data = []
    for r in results:

        def fmt_time(v):
            return f"{v:.2f}s" if v >= 0 else 'ERR'

        table_data.append(
            [
                r['id'],
                r['ref_words'],
                fmt_time(r.get('dg_connect', -1)),
                fmt_time(r.get('dg_first_seg', -1)),
                fmt_time(r.get('dg_total', -1)),
                r.get('dg_segments', 0),
                f"{r.get('dg_wer', 1):.0%}",
                fmt_time(r.get('mod_connect', -1)),
                fmt_time(r.get('mod_first_seg', -1)),
                fmt_time(r.get('mod_total', -1)),
                r.get('mod_segments', 0),
                f"{r.get('mod_wer', 1):.0%}",
            ]
        )

    print(
        tabulate(
            table_data,
            headers=[
                'Case',
                'Words',
                'DG Conn',
                'DG 1st Seg',
                'DG Total',
                'DG Segs',
                'DG WER',
                'Mod Conn',
                'Mod 1st Seg',
                'Mod Total',
                'Mod Segs',
                'Mod WER',
            ],
            tablefmt='grid',
        )
    )

    valid_dg = [r for r in results if r.get('dg_total', -1) >= 0]
    valid_mod = [r for r in results if r.get('mod_total', -1) >= 0]

    print('\nSUMMARY:')
    if valid_dg:
        print(
            f"  Deepgram:  "
            f"avg_connect={sum(r['dg_connect'] for r in valid_dg) / len(valid_dg):.2f}s  "
            f"avg_first_seg={sum(r['dg_first_seg'] for r in valid_dg if r['dg_first_seg'] >= 0) / max(1, len([r for r in valid_dg if r['dg_first_seg'] >= 0])):.2f}s  "
            f"avg_total={sum(r['dg_total'] for r in valid_dg) / len(valid_dg):.2f}s  "
            f"avg_WER={sum(r['dg_wer'] for r in valid_dg) / len(valid_dg):.1%}  "
            f"cases={len(valid_dg)}"
        )
    if valid_mod:
        print(
            f"  Modulate:  "
            f"avg_connect={sum(r['mod_connect'] for r in valid_mod) / len(valid_mod):.2f}s  "
            f"avg_first_seg={sum(r['mod_first_seg'] for r in valid_mod if r['mod_first_seg'] >= 0) / max(1, len([r for r in valid_mod if r['mod_first_seg'] >= 0])):.2f}s  "
            f"avg_total={sum(r['mod_total'] for r in valid_mod) / len(valid_mod):.2f}s  "
            f"avg_WER={sum(r['mod_wer'] for r in valid_mod) / len(valid_mod):.1%}  "
            f"cases={len(valid_mod)}"
        )

    output_path = RESULTS_DIR / 'streaming_benchmark.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nDetailed results saved to: {output_path}')


def main():
    asyncio.run(run_benchmark())


if __name__ == '__main__':
    main()
