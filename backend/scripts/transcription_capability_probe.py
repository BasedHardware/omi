#!/usr/bin/env python3
"""Probe a deployed transcription candidate with a versioned known-audio fixture.

The full ``/v2/voice-message/transcribe`` path is the release authority. The
fixture, its expected transcript, and language are checked into the repository
with its provenance in a manifest; they are never fetched from a protected URL
or read from deploy settings. The only runtime credential is a short-lived
Firebase ID token supplied in a mode-0600 file by the release-probe action.

Reports deliberately contain only booleans and status codes. They never expose
the token, the fixture body, the transcript, the candidate URL, or API errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_PATH = ROOT / 'backend/testing/release_fixtures/transcription-release-probe.wav'
DEFAULT_MANIFEST_PATH = ROOT / 'backend/testing/release_fixtures/transcription-release-probe.json'
FULL_ROUTE_PATH = '/v2/voice-message/transcribe'
STATUS_PASS = 'PASS'
STATUS_FAIL = 'FAIL'

MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_RAW_TRANSCRIPT_CHARS = 4096
MAX_NORMALIZED_TRANSCRIPT_CHARS = 512
MAX_BEARER_TOKEN_CHARS = 8192
LANGUAGE_PATTERN = re.compile(r'^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})?$')
SHA256_PATTERN = re.compile(r'^[0-9a-f]{64}$')


@dataclass(frozen=True)
class ProbeConfig:
    fixture_path: Path
    manifest_path: Path
    api_url: str | None
    bearer_token: str | None
    timeout_seconds: float


@dataclass(frozen=True)
class ProbeFixture:
    audio: bytes
    expected_phrase: str
    language: str


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: bytes
    error_kind: str | None
    oversized: bool = False


def normalize_phrase(value: Any) -> str | None:
    """Return an exact, bounded comparison form without preserving transcript text."""
    if not isinstance(value, str) or len(value) > MAX_RAW_TRANSCRIPT_CHARS:
        return None
    normalized = ''.join(char.casefold() if char.isalnum() else ' ' for char in value)
    normalized = ' '.join(normalized.split())
    if not normalized or len(normalized) > MAX_NORMALIZED_TRANSCRIPT_CHARS:
        return None
    return normalized


def normalize_language(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate if LANGUAGE_PATTERN.fullmatch(candidate) else None


def _read_bearer_token(path: Path | None) -> str | None:
    if path is None:
        return None
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_mode & 0o077:
            os.close(descriptor)
            descriptor = -1
            return None
        with os.fdopen(descriptor, encoding='utf-8') as handle:
            descriptor = -1
            token = handle.read().strip()
    except (OSError, UnicodeDecodeError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return token if 0 < len(token) <= MAX_BEARER_TOKEN_CHARS else None


def config_from_args(args: argparse.Namespace) -> ProbeConfig:
    api_url = (args.candidate_api_url or '').strip() or None
    return ProbeConfig(
        fixture_path=args.fixture_path,
        manifest_path=args.manifest_path,
        api_url=api_url.rstrip('/') if api_url else None,
        bearer_token=_read_bearer_token(args.bearer_token_file),
        timeout_seconds=args.timeout_seconds,
    )


def _read_response(response: Any, max_bytes: int) -> tuple[bytes, bool]:
    body = response.read(max_bytes + 1)
    return body[:max_bytes], len(body) > max_bytes


def request_bytes(request: urllib.request.Request, timeout_seconds: float, max_bytes: int) -> HttpResult:
    """Make one bounded request without retaining a printable error body."""
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body, oversized = _read_response(response, max_bytes)
            return HttpResult(status_code=int(response.status), body=body, error_kind=None, oversized=oversized)
    except urllib.error.HTTPError as error:
        # Do not read or print an error body: it can contain request-sensitive
        # data echoed by a proxy or upstream service.
        return HttpResult(status_code=error.code, body=b'', error_kind='http_error')
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return HttpResult(status_code=None, body=b'', error_kind='network_error')


def build_multipart(audio: bytes, language: str) -> tuple[str, bytes]:
    """Encode the real FastAPI UploadFile multipart shape for the WAV fixture."""
    boundary = f'----omi-transcription-probe-{uuid.uuid4().hex}'
    language_part = (
        f'--{boundary}\r\n' 'Content-Disposition: form-data; name="language"\r\n\r\n' f'{language}\r\n'
    ).encode('ascii')
    prefix = (
        f'--{boundary}\r\n'
        'Content-Disposition: form-data; name="files"; filename="transcription-release-probe.wav"\r\n'
        'Content-Type: audio/wav\r\n\r\n'
    ).encode('ascii')
    suffix = f'\r\n--{boundary}--\r\n'.encode('ascii')
    return f'multipart/form-data; boundary={boundary}', language_part + prefix + audio + suffix


def _details(
    *,
    configured: bool,
    http_status: int | None = None,
    error_kind: str | None = None,
    fixture_available: bool | None = None,
    json_object: bool | None = None,
    outcome_success: bool | None = None,
    phrase_match: bool | None = None,
    authority: str | None = None,
    missing_config: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return a deliberately typed, redacted report shape."""
    details: dict[str, Any] = {'configured': configured}
    if http_status is not None:
        details['http_status'] = http_status
    if error_kind is not None:
        details['error_kind'] = error_kind
    if fixture_available is not None:
        details['fixture_available'] = fixture_available
    if json_object is not None:
        details['json_object'] = json_object
    if outcome_success is not None:
        details['outcome_success'] = outcome_success
    if phrase_match is not None:
        details['phrase_match'] = phrase_match
    if authority is not None:
        details['authority'] = authority
    if missing_config:
        details['missing_config'] = list(missing_config)
    return details


def _parse_json_object(result: HttpResult) -> dict[str, Any] | None:
    if result.oversized:
        return None
    try:
        decoded = json.loads(result.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _load_fixture(config: ProbeConfig) -> tuple[ProbeFixture | None, dict[str, Any]]:
    try:
        manifest = json.loads(config.manifest_path.read_text(encoding='utf-8'))
        if not isinstance(manifest, dict):
            raise ValueError('manifest is not an object')
        expected_phrase = normalize_phrase(manifest.get('expected_transcript'))
        language = normalize_language(manifest.get('language'))
        expected_filename = manifest.get('fixture_filename')
        expected_sha256 = manifest.get('sha256')
        if (
            manifest.get('schema_version') != 1
            or not expected_phrase
            or not language
            or expected_filename != config.fixture_path.name
            or not isinstance(expected_sha256, str)
            or not SHA256_PATTERN.fullmatch(expected_sha256)
        ):
            raise ValueError('manifest has an invalid release fixture contract')
        audio = config.fixture_path.read_bytes()
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            raise ValueError('fixture size is invalid')
        if hashlib.sha256(audio).hexdigest() != expected_sha256:
            raise ValueError('fixture digest differs from manifest')
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None, _details(configured=True, error_kind='fixture_invalid', fixture_available=False)
    return (
        ProbeFixture(audio=audio, expected_phrase=expected_phrase, language=language),
        _details(configured=True, fixture_available=True),
    )


def _missing_full_route_config(config: ProbeConfig) -> tuple[str, ...]:
    required = {
        'api_url': config.api_url,
        'bearer_token': config.bearer_token,
    }
    return tuple(name for name, value in required.items() if not value)


def _probe_full_route(
    config: ProbeConfig, fixture: ProbeFixture | None, fixture_details: dict[str, Any]
) -> dict[str, Any]:
    missing_config = _missing_full_route_config(config)
    if missing_config:
        return {
            'name': 'full_route',
            'status': STATUS_FAIL,
            'details': _details(configured=False, error_kind='configuration', missing_config=missing_config),
        }
    if fixture is None:
        return {
            'name': 'full_route',
            'status': STATUS_FAIL,
            'details': {**fixture_details, 'authority': 'candidate_gate'},
        }

    content_type, body = build_multipart(fixture.audio, fixture.language)
    result = request_bytes(
        urllib.request.Request(
            f'{config.api_url}{FULL_ROUTE_PATH}',
            data=body,
            method='POST',
            headers={
                'Accept': 'application/json',
                'Authorization': f'Bearer {config.bearer_token}',
                'Content-Type': content_type,
            },
        ),
        config.timeout_seconds,
        MAX_RESPONSE_BYTES,
    )
    del body
    payload = _parse_json_object(result)
    outcome_success = payload is not None and payload.get('outcome') == 'success'
    phrase_match = payload is not None and normalize_phrase(payload.get('transcript')) == fixture.expected_phrase
    passed = result.status_code == 200 and payload is not None and outcome_success and phrase_match
    return {
        'name': 'full_route',
        'status': STATUS_PASS if passed else STATUS_FAIL,
        'details': _details(
            configured=True,
            http_status=result.status_code,
            error_kind=result.error_kind or ('invalid_response' if payload is None else None),
            fixture_available=True,
            json_object=payload is not None,
            outcome_success=outcome_success,
            phrase_match=phrase_match,
            authority='candidate_gate',
        ),
    }


def build_report(config: ProbeConfig) -> dict[str, Any]:
    fixture, fixture_details = _load_fixture(config)
    try:
        full_route = _probe_full_route(config, fixture, fixture_details)
    finally:
        if fixture is not None:
            del fixture
    return {
        'suite': 'omi_transcription_capability_probe',
        'status': full_route['status'],
        'full_route_authoritative': True,
        'checks': [full_route],
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--candidate-api-url',
        '--api-url',
        dest='candidate_api_url',
        required=True,
        help='Tagged candidate revision base URL.',
    )
    parser.add_argument('--fixture-path', type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument('--manifest-path', type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument('--bearer-token-file', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=float, default=30.0)
    parser.add_argument('--json-only', action='store_true', help='Emit only the redacted machine-readable report.')
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.timeout_seconds <= 0:
        raise SystemExit('--timeout-seconds must be positive')
    report = build_report(config_from_args(args))
    if not args.json_only:
        print(f"Omi transcription capability probe: {report['status']}")
        for check in report['checks']:
            print(f"- {check['status']} {check['name']}")
    print(json.dumps(report, sort_keys=True))
    return 1 if report['status'] == STATUS_FAIL else 0


if __name__ == '__main__':
    raise SystemExit(main())
