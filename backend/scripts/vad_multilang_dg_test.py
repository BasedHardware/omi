#!/usr/bin/env python3
"""
Multilingual VAD gate quality benchmark using Deepgram prerecorded as judge.

For each language and volume profile:
1) synthesize speech with gTTS
2) transcribe ungated audio with DG prerecorded (ground truth)
3) run audio through VADStreamingGate (threshold=0.65), transcribe gated output
4) compare gated transcript to ungated transcript and report savings/quality drops
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import requests
from gtts import gTTS
from gtts.lang import tts_langs

os.environ['VAD_GATE_SPEECH_THRESHOLD'] = '0.65'
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.stt.vad_gate import VADStreamingGate

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
CHUNK_MS = 30
DEFAULT_THRESHOLD = 0.65
DG_URL = 'https://api.deepgram.com/v1/listen'
QUALITY_DROP_THRESHOLD = 95.0
DEFAULT_OUTPUT = '/tmp/vad_multilang_results.json'

TEST_LANGUAGES = [
    'en',
    'es',
    'fr',
    'de',
    'it',
    'pt',
    'ja',
    'ko',
    'zh',
    'hi',
    'ar',
    'ru',
    'tr',
    'pl',
    'nl',
    'sv',
    'da',
    'fi',
    'no',
    'cs',
    'ro',
    'uk',
    'vi',
    'th',
    'id',
    'hu',
    'el',
    'bg',
    'sk',
    'ca',
    'lt',
    'lv',
    'et',
    'ms',
]

DG_SUPPORTED_LANGUAGES = {
    'bg',
    'ca',
    'cs',
    'da',
    'nl',
    'en',
    'et',
    'fi',
    'fr',
    'de',
    'el',
    'hi',
    'hu',
    'id',
    'it',
    'ja',
    'ko',
    'lv',
    'lt',
    'ms',
    'no',
    'pl',
    'pt',
    'ro',
    'ru',
    'sk',
    'es',
    'sv',
    'tr',
    'uk',
    'vi',
    'zh',
    'th',
    'multi',
}

GTTS_LANGUAGE_MAP = {
    'zh': 'zh-CN',
}

PHRASES = {
    'en': 'Hello, this is a test of the speech recognition system.',
    'es': 'Hola, esta es una prueba del sistema de reconocimiento de voz.',
    'fr': 'Bonjour, ceci est un test du systeme de reconnaissance vocale.',
    'de': 'Hallo, dies ist ein Test des Spracherkennungssystems.',
    'it': 'Ciao, questo e un test del sistema di riconoscimento vocale.',
    'pt': 'Ola, este e um teste do sistema de reconhecimento de fala.',
    'ja': 'こんにちは、これは音声認識システムのテストです。',
    'ko': '안녕하세요, 이것은 음성 인식 시스템 테스트입니다.',
    'zh': '你好，这是语音识别系统测试。',
    'hi': 'नमस्ते, यह वाक् पहचान प्रणाली का परीक्षण है।',
    'ar': 'مرحبا، هذا اختبار لنظام التعرف على الكلام.',
    'ru': 'Привет, это тест системы распознавания речи.',
    'tr': 'Merhaba, bu konusma tanima sisteminin bir testidir.',
    'pl': 'Czesc, to jest test systemu rozpoznawania mowy.',
    'nl': 'Hallo, dit is een test van het spraakherkenningssysteem.',
    'sv': 'Hej, det har ar ett test av taligenkanningssystemet.',
    'da': 'Hej, dette er en test af talegenkendelsessystemet.',
    'fi': 'Hei, tama on puheentunnistusjarjestelman testi.',
    'no': 'Hei, dette er en test av talegjenkjenningssystemet.',
    'cs': 'Ahoj, toto je test systemu rozpoznavani reci.',
    'ro': 'Salut, acesta este un test al sistemului de recunoastere vocala.',
    'uk': 'Привіт, це тест системи розпізнавання мовлення.',
    'vi': 'Xin chao, day la bai kiem tra he thong nhan dang giong noi.',
    'th': 'สวัสดี นี่คือการทดสอบระบบรู้จำเสียงพูด',
    'id': 'Halo, ini adalah tes sistem pengenalan suara.',
    'hu': 'Szia, ez a beszedfelismero rendszer tesztje.',
    'el': 'Γεια, αυτό είναι ένα τεστ του συστήματος αναγνώρισης ομιλίας.',
    'bg': 'Здравей, това е тест на системата за разпознаване на реч.',
    'sk': 'Ahoj, toto je test systemu rozpoznavania reci.',
    'ca': 'Hola, aquesta es una prova del sistema de reconeixement de veu.',
    'lt': 'Sveiki, tai yra kalbos atpazinimo sistemos testas.',
    'lv': 'Sveiki, sis ir runas atpazisanas sistemas tests.',
    'et': 'Tere, see on konetuvastussusteemi test.',
    'ms': 'Hai, ini ialah ujian sistem pengecaman pertuturan.',
}

VOLUMES: List[Tuple[str, float]] = [('normal_0dB', 0.0), ('quiet_-15dB', -15.0)]


@dataclass
class VolumeResult:
    volume: str
    volume_db: float
    dg_language: str
    ungated_transcript: str
    gated_transcript: str
    similarity_pct: float
    savings_pct: float
    quality_drop: bool
    passed: bool
    status: str
    error: str


def normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    lowered = re.sub(r'_+', ' ', lowered)
    lowered = re.sub(r'[^\w\s]', ' ', lowered, flags=re.UNICODE)
    lowered = re.sub(r'\s+', ' ', lowered).strip()
    return lowered


def similarity_pct(reference: str, candidate: str) -> float:
    ref = normalize_text(reference)
    cand = normalize_text(candidate)
    if not ref and not cand:
        return 100.0
    if not ref or not cand:
        return 0.0
    return SequenceMatcher(None, ref, cand).ratio() * 100.0


def pcm_to_wav_bytes(pcm_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm_bytes)
    wav_data = buffer.getvalue()
    return wav_data


def add_padding_silence(pcm_bytes: bytes, lead_ms: int = 500, tail_ms: int = 700) -> bytes:
    lead = b'\x00' * int((lead_ms / 1000.0) * SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH)
    tail = b'\x00' * int((tail_ms / 1000.0) * SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH)
    return lead + pcm_bytes + tail


def apply_volume_db(pcm_bytes: bytes, db: float) -> bytes:
    if db == 0.0:
        return pcm_bytes
    gain = 10 ** (db / 20.0)
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    samples *= gain
    np.clip(samples, -32768.0, 32767.0, out=samples)
    scaled = samples.astype(np.int16).tobytes()
    del samples
    return scaled


def dg_language_for(lang: str) -> str:
    if lang in DG_SUPPORTED_LANGUAGES:
        return lang
    return 'multi'


def transcribe_with_dg(wav_data: bytes, dg_api_key: str, language: str) -> str:
    response = requests.post(
        DG_URL,
        params={'model': 'nova-2', 'language': language},
        headers={'Authorization': f'Token {dg_api_key}', 'Content-Type': 'audio/wav'},
        data=wav_data,
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    transcript = payload.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0].get('transcript', '')
    del payload
    return transcript


def synthesize_pcm_with_gtts(lang_code: str, text: str, temp_dir: Path) -> bytes:
    mp3_path = temp_dir / f'{lang_code}.mp3'
    wav_path = temp_dir / f'{lang_code}.wav'

    last_error = None
    for attempt in range(1, 4):
        try:
            gTTS(text=text, lang=lang_code, slow=False).save(str(mp3_path))
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.0 * attempt)

    if last_error is not None:
        raise RuntimeError(f'gTTS failed after retries: {last_error}') from last_error

    subprocess.run(
        [
            'ffmpeg',
            '-y',
            '-loglevel',
            'error',
            '-i',
            str(mp3_path),
            '-ac',
            str(CHANNELS),
            '-ar',
            str(SAMPLE_RATE),
            '-f',
            'wav',
            str(wav_path),
        ],
        check=True,
    )

    with wave.open(str(wav_path), 'rb') as wav_file:
        if wav_file.getnchannels() != CHANNELS:
            raise RuntimeError(f'Unexpected channels for {lang_code}: {wav_file.getnchannels()}')
        if wav_file.getframerate() != SAMPLE_RATE:
            raise RuntimeError(f'Unexpected sample_rate for {lang_code}: {wav_file.getframerate()}')
        if wav_file.getsampwidth() != SAMPLE_WIDTH:
            raise RuntimeError(f'Unexpected sample width for {lang_code}: {wav_file.getsampwidth()}')
        pcm_data = wav_file.readframes(wav_file.getnframes())

    return pcm_data


def run_vad_gate(pcm_data: bytes, threshold: float, session_id: str) -> Tuple[bytes, Dict[str, float]]:
    gate = VADStreamingGate(
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        mode='active',
        uid='multilang-vad-test',
        session_id=session_id,
    )
    gate._speech_threshold = threshold

    chunk_bytes = int(SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH * (CHUNK_MS / 1000.0))
    wall_start = time.time()
    gated = bytearray()

    for chunk_index, start in enumerate(range(0, len(pcm_data), chunk_bytes)):
        chunk = pcm_data[start : start + chunk_bytes]
        if not chunk:
            continue
        wall_time = wall_start + (chunk_index * (CHUNK_MS / 1000.0))
        output = gate.process_audio(chunk, wall_time)
        if output.audio_to_send:
            gated.extend(output.audio_to_send)

    gated_bytes = bytes(gated)
    metrics = gate.get_metrics()
    gated.clear()
    return gated_bytes, metrics


def print_table(results: List[Dict[str, object]]) -> None:
    header = f"{'LANG':<5} {'VOL':<12} {'DG_LANG':<7} {'SIM%':>7} {'SAVE%':>7} " f"{'DROP':<5} {'PASS':<5} {'STATUS'}"
    print('\n' + header)
    print('-' * len(header))
    for entry in results:
        lang = str(entry['language'])
        for volume in entry['volumes']:
            sim_val = volume['similarity_pct']
            save_val = volume['savings_pct']
            sim_text = f'{sim_val:6.2f}' if sim_val is not None else '  n/a '
            save_text = f'{save_val:6.2f}' if save_val is not None else '  n/a '
            print(
                f"{lang:<5} {volume['volume']:<12} {volume['dg_language']:<7} {sim_text:>7} {save_text:>7} "
                f"{str(volume['quality_drop']):<5} {str(volume['passed']):<5} {volume['status']}"
            )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run multilingual VAD gate quality test against DG prerecorded.')
    parser.add_argument(
        '--output',
        default=DEFAULT_OUTPUT,
        help=f'Path to JSON output file (default: {DEFAULT_OUTPUT})',
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f'VAD speech threshold (default: {DEFAULT_THRESHOLD})',
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    dg_api_key = os.environ.get('DEEPGRAM_API_KEY', '').strip()
    if not dg_api_key:
        raise RuntimeError('DEEPGRAM_API_KEY is required.')

    gtts_supported = tts_langs()
    aggregate_results: List[Dict[str, object]] = []
    pass_count = 0
    fail_count = 0
    skip_count = 0
    error_count = 0

    with tempfile.TemporaryDirectory(prefix='vad_multilang_') as tmp:
        temp_dir = Path(tmp)

        for lang in TEST_LANGUAGES:
            phrase = PHRASES.get(lang, '')
            gtts_lang = GTTS_LANGUAGE_MAP.get(lang, lang)
            dg_lang = dg_language_for(lang)
            print(f'\n[{lang}] Preparing synthesis ({gtts_lang})...')

            if not phrase:
                aggregate_results.append(
                    {
                        'language': lang,
                        'gtts_language': gtts_lang,
                        'dg_language': dg_lang,
                        'status': 'skipped_no_phrase',
                        'volumes': [],
                    }
                )
                skip_count += 1
                continue

            if gtts_lang not in gtts_supported:
                print(f'[{lang}] Skipped: gTTS does not support language code "{gtts_lang}"')
                aggregate_results.append(
                    {
                        'language': lang,
                        'gtts_language': gtts_lang,
                        'dg_language': dg_lang,
                        'status': 'skipped_unsupported_gtts',
                        'volumes': [],
                    }
                )
                skip_count += 1
                continue

            try:
                base_pcm = synthesize_pcm_with_gtts(gtts_lang, phrase, temp_dir)
                base_pcm = add_padding_silence(base_pcm)
            except Exception as exc:
                print(f'[{lang}] Error during synthesis: {exc}')
                aggregate_results.append(
                    {
                        'language': lang,
                        'gtts_language': gtts_lang,
                        'dg_language': dg_lang,
                        'status': 'synthesis_error',
                        'error': str(exc),
                        'volumes': [],
                    }
                )
                error_count += 1
                continue

            language_result = {
                'language': lang,
                'gtts_language': gtts_lang,
                'dg_language': dg_lang,
                'status': 'ok',
                'volumes': [],
            }

            for volume_name, volume_db in VOLUMES:
                print(f'[{lang}] Testing volume={volume_name}...')
                vol_result = VolumeResult(
                    volume=volume_name,
                    volume_db=volume_db,
                    dg_language=dg_lang,
                    ungated_transcript='',
                    gated_transcript='',
                    similarity_pct=0.0,
                    savings_pct=0.0,
                    quality_drop=True,
                    passed=False,
                    status='pending',
                    error='',
                )

                try:
                    volume_pcm = apply_volume_db(base_pcm, volume_db)
                    ungated_wav = pcm_to_wav_bytes(volume_pcm)
                    ungated_text = transcribe_with_dg(ungated_wav, dg_api_key, dg_lang)

                    gated_pcm, gate_metrics = run_vad_gate(
                        volume_pcm,
                        threshold=args.threshold,
                        session_id=f'{lang}-{volume_name}',
                    )
                    gated_wav = pcm_to_wav_bytes(gated_pcm)
                    gated_text = transcribe_with_dg(gated_wav, dg_api_key, dg_lang) if gated_pcm else ''

                    sim = similarity_pct(ungated_text, gated_text)
                    savings = float(gate_metrics.get('bytes_saved_ratio', 0.0) * 100.0)
                    quality_drop = sim < QUALITY_DROP_THRESHOLD
                    passed = not quality_drop

                    vol_result.ungated_transcript = ungated_text
                    vol_result.gated_transcript = gated_text
                    vol_result.similarity_pct = sim
                    vol_result.savings_pct = savings
                    vol_result.quality_drop = quality_drop
                    vol_result.passed = passed
                    vol_result.status = 'ok'

                    if passed:
                        pass_count += 1
                    else:
                        fail_count += 1

                    del gated_pcm
                    del gate_metrics
                    del gated_wav
                    del ungated_wav
                    del volume_pcm
                except Exception as exc:
                    vol_result.status = 'error'
                    vol_result.error = str(exc)
                    error_count += 1

                language_result['volumes'].append(asdict(vol_result))

            aggregate_results.append(language_result)
            del base_pcm

    results_payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'vad_threshold': args.threshold,
        'quality_drop_threshold_similarity_pct': QUALITY_DROP_THRESHOLD,
        'languages_requested': TEST_LANGUAGES,
        'summary': {
            'volume_tests_total': len(TEST_LANGUAGES) * len(VOLUMES),
            'volume_tests_passed': pass_count,
            'volume_tests_failed': fail_count,
            'volume_tests_skipped_languages': skip_count,
            'volume_tests_errors': error_count,
        },
        'results': aggregate_results,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(results_payload, ensure_ascii=False, indent=2), encoding='utf-8')

    print_table(aggregate_results)
    print(f'\nSaved JSON results to: {output_path}')
    print(f"Summary: passed={pass_count}, failed={fail_count}, skipped_languages={skip_count}, errors={error_count}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
