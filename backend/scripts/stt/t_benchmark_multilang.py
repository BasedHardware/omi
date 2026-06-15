"""
Benchmark: Multi-language STT — Deepgram vs Modulate pre-recorded.

Generates test audio in multiple languages using edge-tts, then
transcribes with both providers and measures WER.

Setup:
    pip install edge-tts jiwer tabulate

Usage:
    cd backend && python scripts/stt/t_benchmark_multilang.py --prepare
    cd backend && python scripts/stt/t_benchmark_multilang.py --compare
    cd backend && python scripts/stt/t_benchmark_multilang.py --compare --streaming
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)
AUDIO_DIR = Path('/tmp/stt_benchmark_multilang')
RESULTS_DIR = Path('/tmp/stt_benchmark_results')

MULTILANG_SAMPLES = [
    {
        'id': 'es_01',
        'language': 'es',
        'voice': 'es-MX-DaliaNeural',
        'text': 'Buenos dias, hoy vamos a hablar sobre la importancia de la tecnologia en la educacion moderna.',
        'description': 'Spanish (Mexico) — technology in education',
    },
    {
        'id': 'fr_01',
        'language': 'fr',
        'voice': 'fr-FR-DeniseNeural',
        'text': "Bonjour, je suis ravie de vous presenter notre nouveau projet de recherche scientifique.",
        'description': 'French — research project introduction',
    },
    {
        'id': 'de_01',
        'language': 'de',
        'voice': 'de-DE-KatjaNeural',
        'text': 'Guten Tag, wir freuen uns sehr, Sie heute hier willkommen zu heissen.',
        'description': 'German — welcome greeting',
    },
    {
        'id': 'pt_01',
        'language': 'pt',
        'voice': 'pt-BR-FranciscaNeural',
        'text': 'Boa tarde, gostaria de compartilhar algumas informacoes importantes sobre o nosso projeto.',
        'description': 'Portuguese (Brazil) — project information',
    },
    {
        'id': 'ja_01',
        'language': 'ja',
        'voice': 'ja-JP-NanamiNeural',
        'text': 'こんにちは、本日は人工知能の最新の進歩についてお話しします。',
        'description': 'Japanese — AI advances',
    },
    {
        'id': 'zh_01',
        'language': 'zh',
        'voice': 'zh-CN-XiaoxiaoNeural',
        'text': '大家好，今天我们来讨论一下人工智能在医疗领域的应用。',
        'description': 'Chinese (Mandarin) — AI in healthcare',
    },
    {
        'id': 'hi_01',
        'language': 'hi',
        'voice': 'hi-IN-SwaraNeural',
        'text': 'नमस्ते, आज हम प्रौद्योगिकी के भविष्य के बारे में बात करेंगे।',
        'description': 'Hindi — future of technology',
    },
    {
        'id': 'ko_01',
        'language': 'ko',
        'voice': 'ko-KR-SunHiNeural',
        'text': '안녕하세요, 오늘은 인공지능 기술의 발전에 대해 이야기하겠습니다.',
        'description': 'Korean — AI technology development',
    },
]


def normalize_for_wer(text: str) -> str:
    return PUNCT_RE.sub('', text).lower().strip()


async def generate_audio(sample: dict, output_dir: Path):
    import edge_tts

    output_path = output_dir / f"{sample['id']}.wav"
    mp3_path = output_dir / f"{sample['id']}.mp3"

    communicate = edge_tts.Communicate(sample['text'], sample['voice'])
    await communicate.save(str(mp3_path))

    subprocess.run(
        ['ffmpeg', '-y', '-i', str(mp3_path), '-ar', '16000', '-ac', '1', '-sample_fmt', 's16', str(output_path)],
        capture_output=True,
    )
    mp3_path.unlink(missing_ok=True)
    return output_path


async def prepare_samples():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    print(f'Generating {len(MULTILANG_SAMPLES)} multi-language audio samples...\n')

    manifest = []
    for sample in MULTILANG_SAMPLES:
        print(f"  [{sample['id']}] {sample['description']} ({sample['language']})")
        try:
            wav_path = await generate_audio(sample, AUDIO_DIR)
            size_kb = wav_path.stat().st_size / 1024
            print(f"    Generated: {wav_path.name} ({size_kb:.1f} KB)")
            manifest.append({**sample, 'wav': wav_path.name, 'size_kb': round(size_kb, 1)})
        except Exception as e:
            print(f"    ERROR: {e}")

    manifest_path = AUDIO_DIR / 'manifest.json'
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f'\nManifest saved: {manifest_path} ({len(manifest)} samples)')


def run_prerecorded_compare(manifest: List[dict]):
    from jiwer import wer as compute_wer
    from tabulate import tabulate
    from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes, modulate_prerecorded_from_bytes

    print(f'\n=== Multi-language Pre-recorded Benchmark ({len(manifest)} samples) ===\n')

    results = []
    for sample in manifest:
        wav_path = AUDIO_DIR / sample['wav']
        wav_bytes = wav_path.read_bytes()
        ref_text = sample['text']
        lang = sample['language']

        print(f"  [{sample['id']}] {sample['description']}")

        row = {'id': sample['id'], 'language': lang, 'ref_text': ref_text}

        for provider_name, fn in [
            ('deepgram', deepgram_prerecorded_from_bytes),
            ('modulate', modulate_prerecorded_from_bytes),
        ]:
            try:
                start = time.monotonic()
                words, detected_lang = fn(wav_bytes, sample_rate=16000, diarize=False, return_language=True)
                elapsed = time.monotonic() - start
                text = ' '.join(w['text'] for w in words)
                wer_val = compute_wer(normalize_for_wer(ref_text), normalize_for_wer(text)) if text else 1.0
                row[f'{provider_name}_text'] = text
                row[f'{provider_name}_wer'] = wer_val
                row[f'{provider_name}_lang'] = detected_lang
                row[f'{provider_name}_latency'] = elapsed
                print(f"    {provider_name:10s}  WER={wer_val:.1%}  detected={detected_lang}  latency={elapsed:.2f}s")
            except Exception as e:
                print(f"    {provider_name:10s}  ERROR: {e}")
                row[f'{provider_name}_wer'] = 1.0
                row[f'{provider_name}_text'] = f'ERROR: {e}'

        results.append(row)

    print(f'\n{"=" * 100}')
    table = []
    for r in results:
        table.append(
            [
                r['id'],
                r['language'],
                f"{r.get('deepgram_wer', 1):.0%}",
                r.get('deepgram_lang', '?'),
                f"{r.get('deepgram_latency', -1):.2f}s",
                f"{r.get('modulate_wer', 1):.0%}",
                r.get('modulate_lang', '?'),
                f"{r.get('modulate_latency', -1):.2f}s",
            ]
        )
    print(
        tabulate(
            table,
            headers=['ID', 'Lang', 'DG WER', 'DG Det', 'DG Time', 'Mod WER', 'Mod Det', 'Mod Time'],
            tablefmt='grid',
        )
    )

    valid_dg = [r for r in results if r.get('deepgram_wer', 1) < 1]
    valid_mod = [r for r in results if r.get('modulate_wer', 1) < 1]
    print('\nSUMMARY:')
    if valid_dg:
        print(
            f"  Deepgram:   avg_WER={sum(r['deepgram_wer'] for r in valid_dg)/len(valid_dg):.1%}  cases={len(valid_dg)}/{len(results)}"
        )
    if valid_mod:
        print(
            f"  Modulate:   avg_WER={sum(r['modulate_wer'] for r in valid_mod)/len(valid_mod):.1%}  cases={len(valid_mod)}/{len(results)}"
        )

    print('\nTRANSCRIPTS:')
    for r in results:
        print(f"\n  [{r['id']}] {r['language']}")
        print(f"    REF:      {r['ref_text']}")
        print(f"    DEEPGRAM: {r.get('deepgram_text', 'N/A')}")
        print(f"    MODULATE: {r.get('modulate_text', 'N/A')}")

    output_path = RESULTS_DIR / 'multilang_prerecorded_benchmark.json'
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f'\nResults saved to: {output_path}')


async def run_streaming_compare(manifest: List[dict]):
    from jiwer import wer as compute_wer
    from tabulate import tabulate
    from utils.stt.streaming import process_audio_dg, process_audio_modulate

    print(f'\n=== Multi-language Streaming Benchmark ({len(manifest)} samples) ===\n')

    CHUNK_SIZE = 3200
    CHUNK_INTERVAL = 0.1

    results = []
    for sample in manifest:
        wav_path = AUDIO_DIR / sample['wav']
        audio_data = wav_path.read_bytes()
        audio_pcm = audio_data[44:] if audio_data[:4] == b'RIFF' else audio_data
        ref_text = sample['text']
        lang = sample['language']

        print(f"  [{sample['id']}] {sample['description']}")

        row = {'id': sample['id'], 'language': lang, 'ref_text': ref_text}

        for provider_name, create_fn in [
            ('deepgram', lambda cb, l: process_audio_dg(cb, l, 16000, 1)),
            ('modulate', lambda cb, l: process_audio_modulate(cb, 16000, l)),
        ]:
            segments_received = []

            def stream_cb(segs, _buf=segments_received):
                _buf.extend(segs)

            try:
                socket = await asyncio.wait_for(create_fn(stream_cb, lang), timeout=15)
                start = time.monotonic()
                offset = 0
                while offset < len(audio_pcm):
                    chunk = audio_pcm[offset : offset + CHUNK_SIZE]
                    socket.send(chunk)
                    offset += CHUNK_SIZE
                    await asyncio.sleep(CHUNK_INTERVAL)

                if hasattr(socket, 'drain_and_close'):
                    await asyncio.wait_for(socket.drain_and_close(), timeout=30)
                else:
                    socket.finish()
                    await asyncio.sleep(3)

                elapsed = time.monotonic() - start
                text = ' '.join(s.get('text', '') for s in segments_received).strip()
                wer_val = compute_wer(normalize_for_wer(ref_text), normalize_for_wer(text)) if text else 1.0
                row[f'{provider_name}_text'] = text
                row[f'{provider_name}_wer'] = wer_val
                row[f'{provider_name}_latency'] = elapsed
                print(
                    f"    {provider_name:10s}  WER={wer_val:.1%}  segs={len(segments_received)}  latency={elapsed:.2f}s"
                )
            except Exception as e:
                print(f"    {provider_name:10s}  ERROR: {e}")
                row[f'{provider_name}_wer'] = 1.0
                row[f'{provider_name}_text'] = f'ERROR: {e}'

        results.append(row)

    print(f'\n{"=" * 100}')
    table = []
    for r in results:
        table.append(
            [
                r['id'],
                r['language'],
                f"{r.get('deepgram_wer', 1):.0%}",
                f"{r.get('deepgram_latency', -1):.2f}s",
                f"{r.get('modulate_wer', 1):.0%}",
                f"{r.get('modulate_latency', -1):.2f}s",
            ]
        )
    print(tabulate(table, headers=['ID', 'Lang', 'DG WER', 'DG Time', 'Mod WER', 'Mod Time'], tablefmt='grid'))

    valid_dg = [r for r in results if r.get('deepgram_wer', 1) < 1]
    valid_mod = [r for r in results if r.get('modulate_wer', 1) < 1]
    print('\nSUMMARY:')
    if valid_dg:
        print(
            f"  Deepgram:   avg_WER={sum(r['deepgram_wer'] for r in valid_dg)/len(valid_dg):.1%}  cases={len(valid_dg)}/{len(results)}"
        )
    if valid_mod:
        print(
            f"  Modulate:   avg_WER={sum(r['modulate_wer'] for r in valid_mod)/len(valid_mod):.1%}  cases={len(valid_mod)}/{len(results)}"
        )

    output_path = RESULTS_DIR / 'multilang_streaming_benchmark.json'
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f'\nResults saved to: {output_path}')


def main():
    parser = argparse.ArgumentParser(description='Multi-language STT benchmark')
    parser.add_argument('--prepare', action='store_true', help='Generate multi-language audio samples')
    parser.add_argument('--compare', action='store_true', help='Run DG vs Modulate comparison')
    parser.add_argument('--streaming', action='store_true', help='Test streaming (default: pre-recorded)')
    args = parser.parse_args()

    if args.prepare:
        asyncio.run(prepare_samples())
    elif args.compare:
        manifest_path = AUDIO_DIR / 'manifest.json'
        if not manifest_path.exists():
            print('ERROR: Run --prepare first')
            sys.exit(1)
        with open(manifest_path) as f:
            manifest = json.load(f)
        if args.streaming:
            asyncio.run(run_streaming_compare(manifest))
        else:
            run_prerecorded_compare(manifest)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
