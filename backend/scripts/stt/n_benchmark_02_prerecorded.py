"""
STT Benchmark Suite 02 — Pre-recorded (real human speech)

Compares Deepgram and Modulate pre-recorded STT on LibriSpeech test-clean
samples, reporting WER (after punctuation stripping), latency, and
punctuation retention.

Usage:
    cd backend && python3 scripts/stt/n_benchmark_02_prerecorded.py --prepare   # one-time sample prep
    cd backend && python3 scripts/stt/n_benchmark_02_prerecorded.py             # run benchmark
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple, cast

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

from jiwer import wer as compute_wer
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.stt.pre_recorded import deepgram_prerecorded_from_bytes, modulate_prerecorded_from_bytes

PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)


def normalize_for_wer(text: str) -> str:
    return PUNCT_RE.sub('', text).lower().strip()


def count_punctuation(text: str) -> Dict[str, Any]:
    marks = re.findall(r'[^\w\s]', text)
    return {'total': len(marks), 'detail': dict(sorted(((m, marks.count(m)) for m in set(marks)), key=lambda x: -x[1]))}


AUDIO_DIR = Path('/tmp/stt_benchmark_audio_02')
RESULTS_DIR = Path('/tmp/stt_benchmark_results')
LIBRISPEECH_TAR = Path('/tmp/test-clean.tar.gz')
LIBRISPEECH_DIR = Path('/tmp/librispeech/LibriSpeech/test-clean')

SAMPLE_PICKS = [
    {'uid': '5683-32865-0000', 'desc': 'Short utterance (4 words, 2.2s)'},
    {'uid': '672-122797-0057', 'desc': 'Short sentence (7 words, 6.6s)'},
    {'uid': '2830-3980-0027', 'desc': 'Short phrase (8 words, 2.3s)'},
    {'uid': '3570-5694-0004', 'desc': 'Medium sentence (16 words, 5.3s)'},
    {'uid': '5142-33396-0012', 'desc': 'Medium dialog (18 words, 4.6s)'},
    {'uid': '8463-287645-0008', 'desc': 'Medium phrase (10 words, 3.3s)'},
    {'uid': '1580-141084-0024', 'desc': 'Long narrative (27 words, 9.2s)'},
    {'uid': '4970-29093-0019', 'desc': 'Long narrative (23 words, 7.5s)'},
    {'uid': '1284-1180-0006', 'desc': 'Long descriptive (22 words, 6.9s)'},
    {'uid': '4077-13751-0009', 'desc': 'Very long passage (33 words, 12.2s)'},
    {'uid': '2961-960-0000', 'desc': 'Very long passage (51 words, 27.2s)'},
    {'uid': '3729-6852-0006', 'desc': 'Very long passage (62 words, 23.7s)'},
]


def prepare_samples() -> List[Dict[str, Any]]:
    if not LIBRISPEECH_TAR.exists():
        print(f'ERROR: Download LibriSpeech test-clean first:')
        print(f'  curl -L -o {LIBRISPEECH_TAR} https://www.openslr.org/resources/12/test-clean.tar.gz')
        sys.exit(1)

    if not LIBRISPEECH_DIR.exists():
        print('Extracting LibriSpeech test-clean...')
        LIBRISPEECH_DIR.parent.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['tar', 'xzf', str(LIBRISPEECH_TAR), '-C', str(LIBRISPEECH_DIR.parent.parent)], check=True)

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    manifest: List[Dict[str, Any]] = []

    for i, pick in enumerate(SAMPLE_PICKS):
        uid = pick['uid']
        parts = uid.split('-')
        speaker, chapter = parts[0], parts[1]
        flac_path = LIBRISPEECH_DIR / speaker / chapter / f'{uid}.flac'

        if not flac_path.exists():
            print(f'ERROR: FLAC not found: {flac_path}')
            continue

        trans_file = flac_path.parent / f'{speaker}-{chapter}.trans.txt'
        transcript = ''
        for line in trans_file.read_text().strip().split('\n'):
            line_parts = line.split(' ', 1)
            if line_parts[0] == uid:
                transcript = line_parts[1]
                break

        wav_path = AUDIO_DIR / f'sample_{i + 1:02d}.wav'
        subprocess.run(
            ['ffmpeg', '-y', '-i', str(flac_path), '-ar', '16000', '-ac', '1', '-sample_fmt', 's16', str(wav_path)],
            capture_output=True,
            check=True,
        )

        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(wav_path)],
            capture_output=True,
            text=True,
        )
        duration = float(result.stdout.strip())

        manifest.append(
            {
                'id': f'sample_{i + 1:02d}',
                'uid': uid,
                'speaker': speaker,
                'text': transcript,
                'description': pick['desc'],
                'word_count': len(transcript.split()),
                'duration_s': round(duration, 2),
                'size_kb': round(wav_path.stat().st_size / 1024, 1),
            }
        )
        print(f'  Prepared: sample_{i + 1:02d}.wav  {duration:.1f}s  {len(transcript.split())}w  speaker={speaker}')

    with open(AUDIO_DIR / 'manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'\n{len(manifest)} samples prepared in {AUDIO_DIR}')
    return manifest


def load_manifest() -> List[Dict[str, Any]]:
    manifest_path = AUDIO_DIR / 'manifest.json'
    if not manifest_path.exists():
        print('Samples not prepared yet. Running preparation...')
        return prepare_samples()
    with open(manifest_path) as f:
        return cast(List[Dict[str, Any]], json.load(f))


def run_deepgram(audio_bytes: bytes) -> Tuple[str, float, int]:
    t0 = time.monotonic()
    result = cast(List[Dict[str, Any]], deepgram_prerecorded_from_bytes(audio_bytes, sample_rate=16000, diarize=True))
    elapsed = time.monotonic() - t0
    text = ' '.join(str(w.get('text', '') or w.get('word', '')) for w in result).strip()
    return text, elapsed, len(result)


def run_modulate(audio_bytes: bytes) -> Tuple[str, float, int]:
    t0 = time.monotonic()
    result = cast(List[Dict[str, Any]], modulate_prerecorded_from_bytes(audio_bytes, sample_rate=16000, diarize=True))
    elapsed = time.monotonic() - t0
    text = ' '.join(str(w.get('text', '')) for w in result).strip()
    return text, elapsed, len(result)


def main() -> None:
    if '--prepare' in sys.argv:
        prepare_samples()
        return

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
    print(f'\nBenchmark Suite 02 — Pre-recorded ({len(manifest)} samples, real human speech)')
    print(f'Source: LibriSpeech test-clean (CC BY 4.0)\n')

    results: List[Dict[str, Any]] = []
    for case in manifest:
        wav_path = AUDIO_DIR / f"{case['id']}.wav"
        audio_bytes = wav_path.read_bytes()
        ref_norm = normalize_for_wer(cast(str, case['text']))

        row: Dict[str, Any] = {
            'id': case['id'],
            'uid': case['uid'],
            'description': case['description'],
            'speaker': case['speaker'],
            'ref_words': case['word_count'],
            'duration_s': case['duration_s'],
            'audio_kb': case['size_kb'],
            'ref_text': case['text'],
        }

        print(f"  [{case['id']}] {case['description']} (speaker {case['speaker']})")

        try:
            dg_text, dg_time, dg_segments = run_deepgram(audio_bytes)
            dg_wer = compute_wer(ref_norm, normalize_for_wer(dg_text)) if dg_text else 1.0
            dg_punct: Dict[str, Any] = count_punctuation(dg_text) if dg_text else {'total': 0, 'detail': {}}
            row.update(
                {
                    'dg_time': dg_time,
                    'dg_words': len(dg_text.split()) if dg_text else 0,
                    'dg_wer': dg_wer,
                    'dg_text': dg_text,
                    'dg_segments': dg_segments,
                    'dg_punct': dg_punct['total'],
                    'dg_punct_detail': dg_punct['detail'],
                }
            )
            print(
                f"    Deepgram:  {dg_time:.2f}s  WER={dg_wer:.2%}  words={len(dg_text.split())}  punct={dg_punct['total']}"
            )
        except Exception as e:
            print(f"    Deepgram:  ERROR - {e}")
            row.update(
                {
                    'dg_time': -1,
                    'dg_words': 0,
                    'dg_wer': 1.0,
                    'dg_text': f'ERROR: {e}',
                    'dg_segments': 0,
                    'dg_punct': 0,
                    'dg_punct_detail': {},
                }
            )

        try:
            mod_text, mod_time, mod_segments = run_modulate(audio_bytes)
            mod_wer = compute_wer(ref_norm, normalize_for_wer(mod_text)) if mod_text else 1.0
            mod_punct: Dict[str, Any] = count_punctuation(mod_text) if mod_text else {'total': 0, 'detail': {}}
            row.update(
                {
                    'mod_time': mod_time,
                    'mod_words': len(mod_text.split()) if mod_text else 0,
                    'mod_wer': mod_wer,
                    'mod_text': mod_text,
                    'mod_segments': mod_segments,
                    'mod_punct': mod_punct['total'],
                    'mod_punct_detail': mod_punct['detail'],
                }
            )
            print(
                f"    Modulate:  {mod_time:.2f}s  WER={mod_wer:.2%}  words={len(mod_text.split())}  punct={mod_punct['total']}"
            )
        except Exception as e:
            print(f"    Modulate:  ERROR - {e}")
            row.update(
                {
                    'mod_time': -1,
                    'mod_words': 0,
                    'mod_wer': 1.0,
                    'mod_text': f'ERROR: {e}',
                    'mod_segments': 0,
                    'mod_punct': 0,
                    'mod_punct_detail': {},
                }
            )

        results.append(row)

    print('\n' + '=' * 110)
    print('SUITE 02 — PRE-RECORDED BENCHMARK RESULTS (Real Human Speech — LibriSpeech test-clean)')
    print('=' * 110)

    table_data: List[List[Any]] = []
    for r in results:
        table_data.append(
            [
                r['id'],
                r['ref_words'],
                f"{r['duration_s']:.1f}s",
                f"{r.get('dg_time', -1):.2f}s" if r.get('dg_time', -1) >= 0 else 'ERR',
                f"{r.get('dg_wer', 1):.1%}",
                r.get('dg_words', 0),
                r.get('dg_punct', 0),
                f"{r.get('mod_time', -1):.2f}s" if r.get('mod_time', -1) >= 0 else 'ERR',
                f"{r.get('mod_wer', 1):.1%}",
                r.get('mod_words', 0),
                r.get('mod_punct', 0),
            ]
        )

    print(
        tabulate(
            table_data,
            headers=[
                'Case',
                'Ref Words',
                'Duration',
                'DG Time',
                'DG WER',
                'DG Words',
                'DG Punct',
                'Mod Time',
                'Mod WER',
                'Mod Words',
                'Mod Punct',
            ],
            tablefmt='grid',
        )
    )

    valid_dg = [r for r in results if r.get('dg_time', -1) >= 0]
    valid_mod = [r for r in results if r.get('mod_time', -1) >= 0]

    print('\nSUMMARY (WER computed after stripping punctuation):')
    if valid_dg:
        avg_dg_time = sum(r['dg_time'] for r in valid_dg) / len(valid_dg)
        avg_dg_wer = sum(r['dg_wer'] for r in valid_dg) / len(valid_dg)
        avg_dg_punct = sum(r.get('dg_punct', 0) for r in valid_dg) / len(valid_dg)
        print(
            f"  Deepgram:  avg_latency={avg_dg_time:.2f}s  avg_WER={avg_dg_wer:.1%}  "
            f"avg_punct={avg_dg_punct:.1f}  cases={len(valid_dg)}"
        )
    if valid_mod:
        avg_mod_time = sum(r['mod_time'] for r in valid_mod) / len(valid_mod)
        avg_mod_wer = sum(r['mod_wer'] for r in valid_mod) / len(valid_mod)
        avg_mod_punct = sum(r.get('mod_punct', 0) for r in valid_mod) / len(valid_mod)
        print(
            f"  Modulate:  avg_latency={avg_mod_time:.2f}s  avg_WER={avg_mod_wer:.1%}  "
            f"avg_punct={avg_mod_punct:.1f}  cases={len(valid_mod)}"
        )

    print('\nTRANSCRIPT COMPARISON:')
    for r in results:
        print(f"\n  [{r['id']}] {r['description']}")
        print(f"    REF:      {r['ref_text']}")
        if str(r.get('dg_text', '')).startswith('ERROR'):
            print(f"    DEEPGRAM: {r.get('dg_text', 'N/A')}")
        else:
            print(
                f"    DEEPGRAM: {r.get('dg_text', 'N/A')}  (WER={r.get('dg_wer', 1):.1%}, punct={r.get('dg_punct', 0)})"
            )
        if str(r.get('mod_text', '')).startswith('ERROR'):
            print(f"    MODULATE: {r.get('mod_text', 'N/A')}")
        else:
            print(
                f"    MODULATE: {r.get('mod_text', 'N/A')}  (WER={r.get('mod_wer', 1):.1%}, punct={r.get('mod_punct', 0)})"
            )

    output_path = RESULTS_DIR / 'suite02_prerecorded_benchmark.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nDetailed results saved to: {output_path}')


if __name__ == '__main__':
    main()
