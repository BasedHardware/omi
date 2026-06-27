"""
Benchmark: Deepgram vs Modulate — Pre-recorded transcription.

Generates 10+ diverse test audio samples and runs both providers,
measuring latency, word count, and WER against reference text.

Usage:
    cd backend && python scripts/stt/l_benchmark_prerecorded.py
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

from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes, modulate_prerecorded_from_bytes

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


def run_deepgram(audio_bytes: bytes) -> Tuple[str, float, int]:
    t0 = time.monotonic()
    result = deepgram_prerecorded_from_bytes(audio_bytes, sample_rate=16000, diarize=True)
    elapsed = time.monotonic() - t0
    text = ' '.join(w.get('text', '') or w.get('word', '') for w in result).strip()
    return text, elapsed, len(result)


def run_modulate(audio_bytes: bytes) -> Tuple[str, float, int]:
    t0 = time.monotonic()
    result = modulate_prerecorded_from_bytes(audio_bytes, sample_rate=16000, diarize=True)
    elapsed = time.monotonic() - t0
    text = ' '.join(w.get('text', '') for w in result).strip()
    return text, elapsed, len(result)


def main():
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

    print(f'\nRunning pre-recorded benchmarks ({len(BENCHMARK_CASES)} cases x 2 providers)...\n')

    results = []
    for case in BENCHMARK_CASES:
        wav_path = AUDIO_DIR / f"{case['id']}.wav"
        audio_bytes = wav_path.read_bytes()
        ref_text = case['text'].lower()

        row = {
            'id': case['id'],
            'description': case['description'],
            'ref_words': len(case['text'].split()),
            'audio_kb': wav_path.stat().st_size / 1024,
        }

        print(f"  [{case['id']}] {case['description']}")

        try:
            dg_text, dg_time, dg_segments = run_deepgram(audio_bytes)
            dg_wer = compute_wer(ref_text, dg_text.lower()) if dg_text else 1.0
            row.update(
                {
                    'dg_time': dg_time,
                    'dg_words': len(dg_text.split()) if dg_text else 0,
                    'dg_wer': dg_wer,
                    'dg_text': dg_text,
                    'dg_segments': dg_segments,
                }
            )
            print(f"    Deepgram:  {dg_time:.2f}s  WER={dg_wer:.2%}  words={len(dg_text.split())}")
        except Exception as e:
            print(f"    Deepgram:  ERROR - {e}")
            row.update({'dg_time': -1, 'dg_words': 0, 'dg_wer': 1.0, 'dg_text': f'ERROR: {e}', 'dg_segments': 0})

        try:
            mod_text, mod_time, mod_segments = run_modulate(audio_bytes)
            mod_wer = compute_wer(ref_text, mod_text.lower()) if mod_text else 1.0
            row.update(
                {
                    'mod_time': mod_time,
                    'mod_words': len(mod_text.split()) if mod_text else 0,
                    'mod_wer': mod_wer,
                    'mod_text': mod_text,
                    'mod_segments': mod_segments,
                }
            )
            print(f"    Modulate:  {mod_time:.2f}s  WER={mod_wer:.2%}  words={len(mod_text.split())}")
        except Exception as e:
            print(f"    Modulate:  ERROR - {e}")
            row.update({'mod_time': -1, 'mod_words': 0, 'mod_wer': 1.0, 'mod_text': f'ERROR: {e}', 'mod_segments': 0})

        results.append(row)

    print('\n' + '=' * 100)
    print('PRE-RECORDED BENCHMARK RESULTS')
    print('=' * 100)

    table_data = []
    for r in results:
        table_data.append(
            [
                r['id'],
                r['ref_words'],
                f"{r['audio_kb']:.1f}",
                f"{r.get('dg_time', -1):.2f}s" if r.get('dg_time', -1) >= 0 else 'ERR',
                f"{r.get('dg_wer', 1):.1%}",
                r.get('dg_words', 0),
                f"{r.get('mod_time', -1):.2f}s" if r.get('mod_time', -1) >= 0 else 'ERR',
                f"{r.get('mod_wer', 1):.1%}",
                r.get('mod_words', 0),
            ]
        )

    print(
        tabulate(
            table_data,
            headers=[
                'Case',
                'Ref Words',
                'Audio KB',
                'DG Time',
                'DG WER',
                'DG Words',
                'Mod Time',
                'Mod WER',
                'Mod Words',
            ],
            tablefmt='grid',
        )
    )

    valid_dg = [r for r in results if r.get('dg_time', -1) >= 0]
    valid_mod = [r for r in results if r.get('mod_time', -1) >= 0]

    print('\nSUMMARY:')
    if valid_dg:
        avg_dg_time = sum(r['dg_time'] for r in valid_dg) / len(valid_dg)
        avg_dg_wer = sum(r['dg_wer'] for r in valid_dg) / len(valid_dg)
        print(f"  Deepgram:  avg_latency={avg_dg_time:.2f}s  avg_WER={avg_dg_wer:.1%}  cases={len(valid_dg)}")
    if valid_mod:
        avg_mod_time = sum(r['mod_time'] for r in valid_mod) / len(valid_mod)
        avg_mod_wer = sum(r['mod_wer'] for r in valid_mod) / len(valid_mod)
        print(f"  Modulate:  avg_latency={avg_mod_time:.2f}s  avg_WER={avg_mod_wer:.1%}  cases={len(valid_mod)}")

    output_path = RESULTS_DIR / 'prerecorded_benchmark.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nDetailed results saved to: {output_path}')


if __name__ == '__main__':
    main()
