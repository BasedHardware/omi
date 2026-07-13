#!/usr/bin/env python3
"""Probe a deployed transcription candidate with a protected known-audio fixture.

All URLs, credentials, the fixture, and the expected words are external runtime
configuration.  This script deliberately never prints them.  The full
``/v2/voice-message/transcribe`` path is the mandatory candidate gate.  An
optional direct Parakeet target is diagnostic only and must be supplied by a
VPC-capable runner; it must not make the Parakeet ILB public or become the
public paging authority.

Required full-route environment:
    OMI_TRANSCRIPTION_SYNTHETIC_AUDIO_URL
    OMI_TRANSCRIPTION_SYNTHETIC_API_URL
    OMI_TRANSCRIPTION_SYNTHETIC_BEARER_TOKEN
    OMI_TRANSCRIPTION_SYNTHETIC_EXPECTED_PHRASE
    OMI_TRANSCRIPTION_SYNTHETIC_LANGUAGE

Optional environment:
    OMI_TRANSCRIPTION_SYNTHETIC_EXPECTED_PROVIDER
    OMI_TRANSCRIPTION_SYNTHETIC_EXPECTED_MODEL
    OMI_TRANSCRIPTION_SYNTHETIC_DIRECT_URL

``--candidate-api-url`` overrides the API base URL for a tagged Cloud Run
revision before promotion.  Keep credentials and fixture configuration in the
protected runner environment rather than command-line arguments.

Use ``--require-route-identity`` from the promotion workflow so the configured
provider and model are part of the mandatory full-route candidate contract.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

FULL_ROUTE_PATH = '/v2/voice-message/transcribe'
STATUS_PASS = 'PASS'
STATUS_FAIL = 'FAIL'
STATUS_NOT_RUN = 'NOT_RUN'

MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_RAW_TRANSCRIPT_CHARS = 4096
MAX_NORMALIZED_TRANSCRIPT_CHARS = 512
LANGUAGE_PATTERN = re.compile(r'^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})?$')


@dataclass(frozen=True)
class ProbeConfig:
    audio_url: str | None
    api_url: str | None
    bearer_token: str | None
    expected_phrase: str | None
    synthetic_language: str | None
    expected_provider: str | None
    expected_model: str | None
    direct_url: str | None
    timeout_seconds: float
    require_direct: bool
    require_route_identity: bool


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: bytes
    error_kind: str | None
    oversized: bool = False


def _env(name: str) -> str | None:
    return (os.environ.get(name) or '').strip() or None


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


def config_from_args(args: argparse.Namespace) -> ProbeConfig:
    api_url = (args.candidate_api_url or _env('OMI_TRANSCRIPTION_SYNTHETIC_API_URL') or '').strip() or None
    return ProbeConfig(
        audio_url=_env('OMI_TRANSCRIPTION_SYNTHETIC_AUDIO_URL'),
        api_url=api_url.rstrip('/') if api_url else None,
        bearer_token=_env('OMI_TRANSCRIPTION_SYNTHETIC_BEARER_TOKEN'),
        expected_phrase=_env('OMI_TRANSCRIPTION_SYNTHETIC_EXPECTED_PHRASE'),
        synthetic_language=_env('OMI_TRANSCRIPTION_SYNTHETIC_LANGUAGE'),
        expected_provider=_env('OMI_TRANSCRIPTION_SYNTHETIC_EXPECTED_PROVIDER'),
        expected_model=_env('OMI_TRANSCRIPTION_SYNTHETIC_EXPECTED_MODEL'),
        direct_url=_env('OMI_TRANSCRIPTION_SYNTHETIC_DIRECT_URL'),
        timeout_seconds=args.timeout_seconds,
        require_direct=args.require_direct,
        require_route_identity=args.require_route_identity,
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
        # Consume only a bounded amount so a large error response cannot retain
        # fixture or transcript data. Its body is never reported.
        try:
            _read_response(error, max_bytes)
        except OSError:
            pass
        return HttpResult(status_code=error.code, body=b'', error_kind='http_error')
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return HttpResult(status_code=None, body=b'', error_kind='network_error')


def build_multipart(field_name: str, audio: bytes, *, language: str | None = None) -> tuple[str, bytes]:
    """Encode the real FastAPI UploadFile multipart shape for a WAV fixture."""
    boundary = f'----omi-transcription-probe-{uuid.uuid4().hex}'
    language_part = b''
    if language:
        language_part = (
            f'--{boundary}\r\n' 'Content-Disposition: form-data; name="language"\r\n\r\n' f'{language}\r\n'
        ).encode('ascii')
    prefix = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="{field_name}"; filename="known-audio.wav"\r\n'
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
    provider_checked: bool | None = None,
    provider_match: bool | None = None,
    model_checked: bool | None = None,
    model_match: bool | None = None,
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
    if provider_checked is not None:
        details['provider_checked'] = provider_checked
    if provider_match is not None:
        details['provider_match'] = provider_match
    if model_checked is not None:
        details['model_checked'] = model_checked
    if model_match is not None:
        details['model_match'] = model_match
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


def _fetch_fixture(config: ProbeConfig) -> tuple[bytes | None, dict[str, Any]]:
    if not config.audio_url:
        return None, _details(configured=False, error_kind='configuration', missing_config=('audio_url',))
    result = request_bytes(
        urllib.request.Request(config.audio_url, method='GET', headers={'Accept': 'audio/wav'}),
        config.timeout_seconds,
        MAX_AUDIO_BYTES,
    )
    if result.status_code != 200 or result.oversized or not result.body:
        return None, _details(
            configured=True,
            http_status=result.status_code,
            error_kind='fixture_unavailable' if not result.error_kind else result.error_kind,
            fixture_available=False,
        )
    return result.body, _details(configured=True, http_status=result.status_code, fixture_available=True)


def _missing_full_route_config(config: ProbeConfig) -> tuple[str, ...]:
    required = {
        'audio_url': config.audio_url,
        'api_url': config.api_url,
        'bearer_token': config.bearer_token,
        'expected_phrase': config.expected_phrase if normalize_phrase(config.expected_phrase) else None,
        'synthetic_language': config.synthetic_language if normalize_language(config.synthetic_language) else None,
    }
    missing = [name for name, value in required.items() if not value]
    if config.require_route_identity:
        if not config.expected_provider:
            missing.append('expected_provider')
        if not config.expected_model:
            missing.append('expected_model')
    return tuple(missing)


def _probe_full_route(config: ProbeConfig, audio: bytes | None, fixture_details: dict[str, Any]) -> dict[str, Any]:
    missing_config = _missing_full_route_config(config)
    if missing_config:
        return {
            'name': 'full_route',
            'status': STATUS_FAIL,
            'details': _details(configured=False, error_kind='configuration', missing_config=missing_config),
        }
    if audio is None:
        return {
            'name': 'full_route',
            'status': STATUS_FAIL,
            'details': {**fixture_details, 'authority': 'candidate_gate'},
        }

    content_type, body = build_multipart('files', audio, language=normalize_language(config.synthetic_language))
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
    expected_phrase = normalize_phrase(config.expected_phrase)
    outcome_success = payload is not None and payload.get('outcome') == 'success'
    phrase_match = payload is not None and normalize_phrase(payload.get('transcript')) == expected_phrase
    provider_checked = config.expected_provider is not None
    model_checked = config.expected_model is not None
    provider_match = (
        payload is not None and payload.get('stt_provider') == config.expected_provider if provider_checked else None
    )
    model_match = payload is not None and payload.get('stt_model') == config.expected_model if model_checked else None
    passed = (
        result.status_code == 200
        and payload is not None
        and outcome_success
        and phrase_match
        and (not provider_checked or provider_match)
        and (not model_checked or model_match)
    )
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
            provider_checked=provider_checked,
            provider_match=provider_match,
            model_checked=model_checked,
            model_match=model_match,
            authority='candidate_gate',
        ),
    }


def _probe_direct(config: ProbeConfig, audio: bytes | None, fixture_details: dict[str, Any]) -> dict[str, Any]:
    if not config.direct_url:
        return {
            'name': 'direct_parakeet_diagnostic',
            'status': STATUS_FAIL if config.require_direct else STATUS_NOT_RUN,
            'details': _details(
                configured=False,
                error_kind='configuration' if config.require_direct else None,
                missing_config=('direct_url',) if config.require_direct else (),
                authority='diagnostic_only',
            ),
        }
    if not config.audio_url or not normalize_phrase(config.expected_phrase):
        missing_config = tuple(
            name
            for name, value in {
                'audio_url': config.audio_url,
                'expected_phrase': config.expected_phrase if normalize_phrase(config.expected_phrase) else None,
            }.items()
            if not value
        )
        return {
            'name': 'direct_parakeet_diagnostic',
            'status': STATUS_FAIL,
            'details': _details(configured=False, error_kind='configuration', missing_config=missing_config),
        }
    if audio is None:
        return {
            'name': 'direct_parakeet_diagnostic',
            'status': STATUS_FAIL,
            'details': {**fixture_details, 'authority': 'diagnostic_only'},
        }

    content_type, body = build_multipart('file', audio)
    result = request_bytes(
        urllib.request.Request(
            config.direct_url,
            data=body,
            method='POST',
            headers={'Accept': 'application/json', 'Content-Type': content_type},
        ),
        config.timeout_seconds,
        MAX_RESPONSE_BYTES,
    )
    del body
    payload = _parse_json_object(result)
    phrase_match = payload is not None and normalize_phrase(payload.get('text')) == normalize_phrase(
        config.expected_phrase
    )
    passed = result.status_code == 200 and payload is not None and phrase_match
    return {
        'name': 'direct_parakeet_diagnostic',
        'status': STATUS_PASS if passed else STATUS_FAIL,
        'details': _details(
            configured=True,
            http_status=result.status_code,
            error_kind=result.error_kind or ('invalid_response' if payload is None else None),
            fixture_available=True,
            json_object=payload is not None,
            phrase_match=phrase_match,
            authority='diagnostic_only',
        ),
    }


def build_report(config: ProbeConfig) -> dict[str, Any]:
    full_missing = _missing_full_route_config(config)
    direct_enabled = config.direct_url is not None
    needs_fixture = not full_missing or direct_enabled
    audio: bytes | None = None
    fixture_details = _details(configured=False, fixture_available=None)
    if needs_fixture:
        audio, fixture_details = _fetch_fixture(config)
    try:
        full_route = _probe_full_route(config, audio, fixture_details)
        direct = _probe_direct(config, audio, fixture_details)
    finally:
        if audio is not None:
            del audio
    checks = [full_route, direct]
    status = STATUS_FAIL if full_route['status'] == STATUS_FAIL else STATUS_PASS
    if config.require_direct and direct['status'] == STATUS_FAIL:
        status = STATUS_FAIL
    return {
        'suite': 'omi_transcription_capability_probe',
        'status': status,
        'full_route_authoritative': True,
        'direct_diagnostic_only': True,
        'checks': checks,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--candidate-api-url',
        '--api-url',
        dest='candidate_api_url',
        help='Tagged candidate revision base URL; overrides protected API URL configuration.',
    )
    parser.add_argument(
        '--require-direct',
        action='store_true',
        help='Fail if the protected direct diagnostic is not configured.',
    )
    parser.add_argument(
        '--require-route-identity',
        action='store_true',
        help='Require configured expected provider and model for the full-route candidate gate.',
    )
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
