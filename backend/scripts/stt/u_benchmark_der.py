"""
Benchmark: Diarization Error Rate (DER) — Deepgram vs Modulate.

Generates multi-speaker conversations using edge-tts with distinct voices,
then measures how well each provider identifies who spoke when.

DER = (false alarm + missed speech + speaker confusion) / total reference speech

Setup:
    pip install edge-tts pyannote.metrics jiwer tabulate

Usage:
    cd backend && python scripts/stt/u_benchmark_der.py --prepare
    cd backend && python scripts/stt/u_benchmark_der.py --compare
"""

import argparse
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

AUDIO_DIR = Path('/tmp/stt_benchmark_der')
RESULTS_DIR = Path('/tmp/stt_benchmark_results')

CONVERSATIONS = [
    {
        'id': 'conv_2spk_en',
        'description': '2-speaker English conversation',
        'language': 'en',
        'turns': [
            {
                'speaker': 0,
                'voice': 'en-US-GuyNeural',
                'text': 'Good morning, I wanted to discuss the quarterly results with you.',
            },
            {
                'speaker': 1,
                'voice': 'en-US-JennyNeural',
                'text': 'Of course. The revenue numbers look strong this quarter.',
            },
            {
                'speaker': 0,
                'voice': 'en-US-GuyNeural',
                'text': 'Yes, we exceeded our target by fifteen percent. The new product line performed exceptionally well.',
            },
            {
                'speaker': 1,
                'voice': 'en-US-JennyNeural',
                'text': 'That is great news. What about the customer acquisition costs?',
            },
            {
                'speaker': 0,
                'voice': 'en-US-GuyNeural',
                'text': 'They went down by about eight percent compared to last quarter.',
            },
            {
                'speaker': 1,
                'voice': 'en-US-JennyNeural',
                'text': 'Excellent. I think we should present these findings at the board meeting next week.',
            },
        ],
    },
    {
        'id': 'conv_3spk_en',
        'description': '3-speaker English meeting',
        'language': 'en',
        'turns': [
            {'speaker': 0, 'voice': 'en-US-GuyNeural', 'text': 'Welcome everyone to the project kickoff meeting.'},
            {
                'speaker': 1,
                'voice': 'en-US-JennyNeural',
                'text': 'Thank you for organizing this. I have the design documents ready.',
            },
            {
                'speaker': 2,
                'voice': 'en-GB-RyanNeural',
                'text': 'And I have prepared the technical architecture overview.',
            },
            {
                'speaker': 0,
                'voice': 'en-US-GuyNeural',
                'text': 'Perfect. Let us start with the design first, then move to the architecture.',
            },
            {
                'speaker': 1,
                'voice': 'en-US-JennyNeural',
                'text': 'Sure. The main design goal is to create a seamless user experience across all platforms.',
            },
            {
                'speaker': 2,
                'voice': 'en-GB-RyanNeural',
                'text': 'From a technical perspective, we plan to use a microservices architecture with event driven communication.',
            },
            {'speaker': 0, 'voice': 'en-US-GuyNeural', 'text': 'How long do you estimate the first phase will take?'},
            {
                'speaker': 1,
                'voice': 'en-US-JennyNeural',
                'text': 'Based on our estimates, about six to eight weeks for the initial prototype.',
            },
            {
                'speaker': 2,
                'voice': 'en-GB-RyanNeural',
                'text': 'I agree with that timeline. The backend infrastructure should be ready in four weeks.',
            },
        ],
    },
    {
        'id': 'conv_2spk_short',
        'description': '2-speaker short exchange',
        'language': 'en',
        'turns': [
            {'speaker': 0, 'voice': 'en-US-GuyNeural', 'text': 'Did you finish the report?'},
            {'speaker': 1, 'voice': 'en-US-JennyNeural', 'text': 'Yes, I sent it to you this morning.'},
            {'speaker': 0, 'voice': 'en-US-GuyNeural', 'text': 'Great, I will review it after lunch.'},
            {'speaker': 1, 'voice': 'en-US-JennyNeural', 'text': 'Sounds good. Let me know if you have any questions.'},
        ],
    },
    {
        'id': 'conv_2spk_long',
        'description': '2-speaker extended discussion',
        'language': 'en',
        'turns': [
            {
                'speaker': 0,
                'voice': 'en-US-GuyNeural',
                'text': 'I have been thinking about the artificial intelligence strategy for next year.',
            },
            {
                'speaker': 1,
                'voice': 'en-US-JennyNeural',
                'text': 'That is an important topic. What areas do you think we should focus on?',
            },
            {
                'speaker': 0,
                'voice': 'en-US-GuyNeural',
                'text': 'I believe natural language processing and computer vision are the two most promising areas for our business.',
            },
            {
                'speaker': 1,
                'voice': 'en-US-JennyNeural',
                'text': 'I agree. We already have some capabilities in natural language processing. We should build on that foundation.',
            },
            {
                'speaker': 0,
                'voice': 'en-US-GuyNeural',
                'text': 'Exactly. And for computer vision, we could partner with a specialized company rather than building everything from scratch.',
            },
            {
                'speaker': 1,
                'voice': 'en-US-JennyNeural',
                'text': 'That makes sense from both a cost and timeline perspective. Do you have any companies in mind?',
            },
            {
                'speaker': 0,
                'voice': 'en-US-GuyNeural',
                'text': 'I have shortlisted three companies that I think would be a good fit. I will share the details with you tomorrow.',
            },
            {
                'speaker': 1,
                'voice': 'en-US-JennyNeural',
                'text': 'Perfect. Let us schedule a follow up meeting to discuss the options in detail.',
            },
        ],
    },
]


async def generate_turn_audio(voice: str, text: str, output_path: Path):
    import edge_tts

    mp3_path = output_path.with_suffix('.mp3')
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(mp3_path))
    subprocess.run(
        ['ffmpeg', '-y', '-i', str(mp3_path), '-ar', '16000', '-ac', '1', '-sample_fmt', 's16', str(output_path)],
        capture_output=True,
    )
    mp3_path.unlink(missing_ok=True)


def get_wav_duration(path: Path) -> float:
    result = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def concatenate_wavs(wav_paths: List[Path], output: Path):
    list_file = output.with_suffix('.txt')
    with open(list_file, 'w') as f:
        for p in wav_paths:
            f.write(f"file '{p}'\n")
    subprocess.run(
        ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(list_file), '-ar', '16000', '-ac', '1', str(output)],
        capture_output=True,
    )
    list_file.unlink(missing_ok=True)


async def prepare_conversations():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    print(f'Generating {len(CONVERSATIONS)} multi-speaker conversations...\n')

    manifest = []
    for conv in CONVERSATIONS:
        print(f"  [{conv['id']}] {conv['description']}")
        turn_wavs = []
        ground_truth = []
        cursor_ms = 0

        for i, turn in enumerate(conv['turns']):
            turn_path = AUDIO_DIR / f"{conv['id']}_turn{i}.wav"
            await generate_turn_audio(turn['voice'], turn['text'], turn_path)
            duration_s = get_wav_duration(turn_path)
            duration_ms = int(duration_s * 1000)

            ground_truth.append(
                {
                    'speaker': turn['speaker'],
                    'start_ms': cursor_ms,
                    'end_ms': cursor_ms + duration_ms,
                    'text': turn['text'],
                }
            )
            cursor_ms += duration_ms
            turn_wavs.append(turn_path)

        output_wav = AUDIO_DIR / f"{conv['id']}.wav"
        concatenate_wavs(turn_wavs, output_wav)
        total_duration = get_wav_duration(output_wav)

        for p in turn_wavs:
            p.unlink(missing_ok=True)

        num_speakers = len(set(t['speaker'] for t in conv['turns']))
        entry = {
            'id': conv['id'],
            'description': conv['description'],
            'language': conv['language'],
            'wav': output_wav.name,
            'duration_s': round(total_duration, 2),
            'num_speakers': num_speakers,
            'ground_truth': ground_truth,
        }
        manifest.append(entry)
        print(
            f"    Generated: {output_wav.name} ({total_duration:.1f}s, {num_speakers} speakers, {len(conv['turns'])} turns)"
        )

    manifest_path = AUDIO_DIR / 'manifest.json'
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'\nManifest saved: {manifest_path} ({len(manifest)} conversations)')


def build_annotation(segments: list, label_prefix: str = 'SPEAKER'):
    from pyannote.core import Annotation, Segment

    ann = Annotation()
    for seg in segments:
        start = seg['start_ms'] / 1000.0
        end = seg['end_ms'] / 1000.0
        speaker = f"{label_prefix}_{seg['speaker']:02d}"
        ann[Segment(start, end)] = speaker
    return ann


def build_hypothesis_from_words(words: list) -> 'Annotation':
    from pyannote.core import Annotation, Segment

    ann = Annotation()
    if not words:
        return ann

    current_speaker = words[0].get('speaker', 'SPEAKER_00')
    seg_start = words[0]['timestamp'][0]
    seg_end = words[0]['timestamp'][1]

    for w in words[1:]:
        sp = w.get('speaker', 'SPEAKER_00')
        if sp == current_speaker:
            seg_end = w['timestamp'][1]
        else:
            ann[Segment(seg_start, seg_end)] = current_speaker
            current_speaker = sp
            seg_start = w['timestamp'][0]
            seg_end = w['timestamp'][1]
    ann[Segment(seg_start, seg_end)] = current_speaker
    return ann


def build_hypothesis_from_utterances(utterances: list) -> 'Annotation':
    from pyannote.core import Annotation, Segment

    ann = Annotation()
    for utt in utterances:
        start = utt['timestamp'][0]
        end = utt['timestamp'][1]
        speaker = utt.get('speaker', 'SPEAKER_00')
        if start < end:
            ann[Segment(start, end)] = speaker
    return ann


def compute_der(reference: 'Annotation', hypothesis: 'Annotation') -> dict:
    from pyannote.metrics.diarization import DiarizationErrorRate

    metric = DiarizationErrorRate(collar=0.25)
    detail = metric(reference, hypothesis, detailed=True)
    total = max(detail.get('total', 1), 1e-6)
    return {
        'der': round(detail.get('diarization error rate', 1.0), 4),
        'false_alarm': round(detail.get('false alarm', 0) / total, 4),
        'missed': round(detail.get('missed detection', 0) / total, 4),
        'confusion': round(detail.get('confusion', 0) / total, 4),
        'total': round(detail.get('total', 0), 2),
    }


def run_der_benchmark(manifest: list):
    from pyannote.metrics.diarization import DiarizationErrorRate
    from tabulate import tabulate
    from utils.stt.pre_recorded import (
        deepgram_prerecorded_from_bytes,
        modulate_prerecorded_from_bytes,
        parakeet_prerecorded_from_bytes,
    )

    print(f'\n=== Diarization Error Rate Benchmark ({len(manifest)} conversations) ===\n')

    results = []
    for conv in manifest:
        wav_path = AUDIO_DIR / conv['wav']
        wav_bytes = wav_path.read_bytes()
        gt = conv['ground_truth']
        ref_annotation = build_annotation(gt)

        print(f"  [{conv['id']}] {conv['description']} ({conv['num_speakers']} speakers, {conv['duration_s']:.1f}s)")

        row = {
            'id': conv['id'],
            'speakers': conv['num_speakers'],
            'duration_s': conv['duration_s'],
            'turns': len(gt),
        }

        providers = [
            ('deepgram', deepgram_prerecorded_from_bytes),
            ('modulate', modulate_prerecorded_from_bytes),
        ]
        if os.getenv('HOSTED_PARAKEET_API_URL'):
            providers.append(('parakeet', parakeet_prerecorded_from_bytes))

        for provider_name, fn in providers:
            try:
                t0 = time.monotonic()
                words = fn(wav_bytes, sample_rate=16000, diarize=True)
                elapsed = time.monotonic() - t0

                if provider_name == 'modulate':
                    hyp = build_hypothesis_from_utterances(words)
                else:
                    hyp = build_hypothesis_from_words(words)

                detected_speakers = len(set(w.get('speaker', 'SPEAKER_00') for w in words))
                der_result = compute_der(ref_annotation, hyp)

                row[f'{provider_name}_der'] = der_result['der']
                row[f'{provider_name}_false_alarm'] = der_result['false_alarm']
                row[f'{provider_name}_missed'] = der_result['missed']
                row[f'{provider_name}_confusion'] = der_result['confusion']
                row[f'{provider_name}_speakers'] = detected_speakers
                row[f'{provider_name}_latency'] = elapsed

                print(
                    f"    {provider_name:10s}  DER={der_result['der']:.1%}  speakers={detected_speakers}/{conv['num_speakers']}  "
                    f"(FA={der_result['false_alarm']:.1%} miss={der_result['missed']:.1%} conf={der_result['confusion']:.1%})  "
                    f"latency={elapsed:.1f}s"
                )
            except Exception as e:
                print(f"    {provider_name:10s}  ERROR: {e}")
                row[f'{provider_name}_der'] = 1.0

        results.append(row)

    print(f'\n{"=" * 130}')
    has_parakeet = any('parakeet_der' in r for r in results)
    table = []
    for r in results:
        row = [
            r['id'],
            r['speakers'],
            f"{r['duration_s']:.1f}s",
            r['turns'],
            f"{r.get('deepgram_der', 1):.1%}",
            f"{r.get('deepgram_speakers', '?')}/{r['speakers']}",
            f"{r.get('modulate_der', 1):.1%}",
            f"{r.get('modulate_speakers', '?')}/{r['speakers']}",
        ]
        if has_parakeet:
            row.extend(
                [
                    f"{r.get('parakeet_der', 1):.1%}",
                    f"{r.get('parakeet_speakers', '?')}/{r['speakers']}",
                ]
            )
        table.append(row)
    headers = ['Conv', 'Spk', 'Dur', 'Turns', 'DG DER', 'DG Spk', 'Mod DER', 'Mod Spk']
    if has_parakeet:
        headers.extend(['PK DER', 'PK Spk'])
    print(tabulate(table, headers=headers, tablefmt='grid'))

    valid_dg = [r for r in results if 'deepgram_der' in r]
    valid_mod = [r for r in results if 'modulate_der' in r]
    valid_pk = [r for r in results if 'parakeet_der' in r]
    print('\nSUMMARY:')
    if valid_dg:
        print(
            f"  Deepgram:   avg_DER={sum(r['deepgram_der'] for r in valid_dg)/len(valid_dg):.1%}  cases={len(valid_dg)}"
        )
    if valid_mod:
        print(
            f"  Modulate:   avg_DER={sum(r['modulate_der'] for r in valid_mod)/len(valid_mod):.1%}  cases={len(valid_mod)}"
        )
    if valid_pk:
        print(
            f"  Parakeet:   avg_DER={sum(r['parakeet_der'] for r in valid_pk)/len(valid_pk):.1%}  cases={len(valid_pk)}"
        )

    output_path = RESULTS_DIR / 'der_benchmark.json'
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nResults saved to: {output_path}')


def main():
    parser = argparse.ArgumentParser(description='DER benchmark')
    parser.add_argument('--prepare', action='store_true', help='Generate multi-speaker audio')
    parser.add_argument('--compare', action='store_true', help='Run DER comparison')
    args = parser.parse_args()

    if args.prepare:
        asyncio.run(prepare_conversations())
    elif args.compare:
        manifest_path = AUDIO_DIR / 'manifest.json'
        if not manifest_path.exists():
            print('ERROR: Run --prepare first')
            sys.exit(1)
        with open(manifest_path) as f:
            manifest = json.load(f)
        run_der_benchmark(manifest)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
