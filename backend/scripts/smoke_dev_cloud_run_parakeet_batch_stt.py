#!/usr/bin/env python3
"""Safely smoke-test the deployed dev Cloud Run batch-STT route with a spoken fixture.

The command is dry-run by default.  ``--execute`` accepts only the dev public
endpoint (or localhost), synthesizes a short spoken PCM clip with macOS ``say``,
and asserts that the routed batch endpoint reports Parakeet plus the expected
transcript.  Pass an already-generated 16 kHz mono PCM file on non-macOS hosts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

DEFAULT_DEV_URL = 'https://api.omiapi.com'
FIXTURE_TEXT = 'Omi Parakeet health check one two three'
ALLOWED_HOSTS = frozenset({'api.omiapi.com', 'localhost', '127.0.0.1', '::1'})


def _normalize(text: str) -> str:
    return ''.join(character for character in text.lower() if character.isalnum())


def _validate_dev_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {'http', 'https'} or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError('refusing to target anything other than the dev endpoint or localhost')
    return base_url.rstrip('/')


def _synthesize_pcm(text: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix='omi-parakeet-smoke-') as temp_dir:
        aiff_path = Path(temp_dir) / 'fixture.aiff'
        wav_path = Path(temp_dir) / 'fixture.wav'
        subprocess.run(['say', '-o', str(aiff_path), text], check=True)
        subprocess.run(
            ['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', str(aiff_path), str(wav_path)],
            check=True,
        )
        with wave.open(str(wav_path), 'rb') as audio:
            if audio.getframerate() != 16000 or audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                raise ValueError('synthesized fixture was not 16 kHz 16-bit mono PCM')
            return audio.readframes(audio.getnframes())


def _load_pcm(pcm_file: Path | None, fixture_text: str) -> bytes:
    if pcm_file is not None:
        audio = pcm_file.read_bytes()
        if not audio:
            raise ValueError(f'{pcm_file} is empty')
        return audio
    return _synthesize_pcm(fixture_text)


def _execute(base_url: str, authorization: str, pcm: bytes, expected_transcript: str) -> None:
    query = urllib.parse.urlencode({'language': 'en', 'sample_rate': '16000', 'encoding': 'linear16', 'channels': '1'})
    request = urllib.request.Request(
        f'{base_url}/v2/voice-message/transcribe?{query}',
        data=pcm,
        headers={'Authorization': authorization, 'Content-Type': 'application/octet-stream'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'dev batch-STT request failed with HTTP {error.code}') from error

    if payload.get('stt_provider') != 'parakeet' or payload.get('stt_model') != 'parakeet':
        raise RuntimeError(
            'dev batch-STT route did not select Parakeet '
            f"(provider={payload.get('stt_provider')!r}, model={payload.get('stt_model')!r})"
        )
    transcript = str(payload.get('transcript') or '')
    if _normalize(expected_transcript) not in _normalize(transcript):
        raise RuntimeError('dev batch-STT transcript did not contain the expected spoken fixture text')
    print(f"PASS provider=parakeet model=parakeet transcript={transcript!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=DEFAULT_DEV_URL, help=f'dev Cloud Run base URL (default: {DEFAULT_DEV_URL})')
    parser.add_argument('--authorization', help='Authorization header value for the dev endpoint')
    parser.add_argument('--pcm-file', type=Path, help='16 kHz mono PCM fixture; skips macOS speech synthesis')
    parser.add_argument('--expected-transcript', default=FIXTURE_TEXT)
    parser.add_argument(
        '--execute', action='store_true', help='send the request; otherwise print the safe execution plan'
    )
    args = parser.parse_args()

    try:
        base_url = _validate_dev_url(args.url)
    except ValueError as error:
        parser.error(str(error))

    if not args.execute:
        print(
            'DRY RUN: would synthesize a spoken fixture and POST it only to '
            f'{base_url}/v2/voice-message/transcribe; pass --execute with --authorization to run.'
        )
        return 0
    if not args.authorization:
        parser.error('--authorization is required with --execute')

    try:
        pcm = _load_pcm(args.pcm_file, args.expected_transcript)
        _execute(base_url, args.authorization, pcm, args.expected_transcript)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
