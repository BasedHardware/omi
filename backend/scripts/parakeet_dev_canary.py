#!/usr/bin/env python3
"""Probe the already-running dev Parakeet service with two small licensed fixtures."""

from __future__ import annotations

import hashlib
import json
import time
import unicodedata
import urllib.request
import wave
from pathlib import Path

BASE_URL = 'http://127.0.0.1:18080'
FIXTURES = Path(__file__).resolve().parents[1] / 'testing/release_fixtures'
MANIFESTS = ('transcription-release-probe.json', 'parakeet-canary-pt.json')
EXPECTED_WORDS = {'en': 'wizard', 'pt': 'musica'}
MAX_LATENCY_SECONDS = 30.0


def normalized(text: str) -> str:
    plain = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in plain.lower() if c.isascii() and c.isalnum())


def load_fixture(manifest_name: str) -> tuple[dict, bytes]:
    manifest = json.loads((FIXTURES / manifest_name).read_text(encoding='utf-8'))
    audio_path = FIXTURES / manifest['fixture_filename']
    audio = audio_path.read_bytes()
    if hashlib.sha256(audio).hexdigest() != manifest['sha256']:
        raise AssertionError(f'{manifest_name}: audio hash mismatch')
    with wave.open(str(audio_path), 'rb') as wav:
        duration = wav.getnframes() / wav.getframerate()
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
            raise AssertionError(f'{manifest_name}: expected mono 16 kHz PCM16')
        if not 2 <= duration <= 12:
            raise AssertionError(f'{manifest_name}: unexpected duration {duration:.1f}s')
    return manifest, audio


def wait_for_health() -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(BASE_URL + '/health', timeout=3) as response:
                if response.status == 200 and json.load(response).get('ready') is True:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise AssertionError('dev Parakeet port-forward did not become healthy within 20s')


def transcribe(manifest: dict, audio: bytes) -> tuple[dict, float]:
    boundary = 'omi-parakeet-dev-canary'
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="canary.wav"\r\n'
            'Content-Type: audio/wav\r\n\r\n'
        ).encode()
        + audio
        + (
            f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="diarize"\r\n\r\n' f'false\r\n--{boundary}--\r\n'
        ).encode()
    )
    request = urllib.request.Request(
        BASE_URL + '/v2/transcribe',
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
        method='POST',
    )
    start = time.monotonic()
    with urllib.request.urlopen(request, timeout=MAX_LATENCY_SECONDS + 5) as response:
        if response.status != 200:
            raise AssertionError(f'{manifest["language"]}: HTTP {response.status}')
        result = json.load(response)
    return result, time.monotonic() - start


def check_result(manifest: dict, result: dict, latency: float) -> None:
    language = manifest['language']
    transcript = result.get('text')
    if not isinstance(transcript, str) or not transcript.strip():
        raise AssertionError(f'{language}: empty transcript')
    if result.get('detected_language') != language:
        raise AssertionError(f'{language}: detected language {result.get("detected_language")!r}')
    if EXPECTED_WORDS[language] not in normalized(transcript):
        raise AssertionError(f'{language}: expected fixture word absent from transcript')
    if latency > MAX_LATENCY_SECONDS:
        raise AssertionError(f'{language}: latency {latency:.1f}s exceeds {MAX_LATENCY_SECONDS:.0f}s')
    print(f'PASS dev Parakeet /v2/transcribe language={language} latency={latency:.2f}s')


def main() -> None:
    wait_for_health()
    for manifest_name in MANIFESTS:
        manifest, audio = load_fixture(manifest_name)
        result, latency = transcribe(manifest, audio)
        check_result(manifest, result, latency)


if __name__ == '__main__':
    main()
