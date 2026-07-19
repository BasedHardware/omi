import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    backend = Path(__file__).resolve().parents[2]
    script_path = backend / 'scripts' / 'transcription_capability_probe.py'
    spec = importlib.util.spec_from_file_location('transcription_capability_probe', script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self, _size=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _urlopen_responses(*responses):
    calls = []
    queued = list(responses)

    def _urlopen(request, *, timeout):
        calls.append((request, timeout))
        assert queued, 'unexpected HTTP request'
        return queued.pop(0)

    return _urlopen, calls


def _fixture_paths(tmp_path, *, audio=b'fixture-audio-secret', expected_phrase='Hello Omi', language='en'):
    fixture_path = tmp_path / 'transcription-release-probe.wav'
    fixture_path.write_bytes(audio)
    manifest_path = tmp_path / 'transcription-release-probe.json'
    manifest_path.write_text(
        json.dumps(
            {
                'schema_version': 1,
                'fixture_filename': fixture_path.name,
                'sha256': hashlib.sha256(audio).hexdigest(),
                'expected_transcript': expected_phrase,
                'language': language,
                'source': {'license': 'CC-BY-4.0'},
            }
        ),
        encoding='utf-8',
    )
    return fixture_path, manifest_path


def _token_file(tmp_path, token='probe-token-that-must-not-leak'):
    token_file = tmp_path / 'probe-token'
    token_file.write_text(token, encoding='utf-8')
    token_file.chmod(0o600)
    return token_file


def _config(module, tmp_path, **overrides):
    fixture_path, manifest_path = _fixture_paths(tmp_path)
    values = {
        'fixture_path': fixture_path,
        'manifest_path': manifest_path,
        'api_url': 'https://candidate.invalid',
        'bearer_token': 'probe-token-that-must-not-leak',
        'timeout_seconds': 3.0,
    }
    values.update(overrides)
    return module.ProbeConfig(**values)


def _headers(request):
    return {name.lower(): value for name, value in request.header_items()}


def _unexpected_network(*_args, **_kwargs):
    raise AssertionError('unexpected HTTP request')


def test_full_route_posts_versioned_fixture_and_validates_exact_candidate_contract(monkeypatch, tmp_path):
    module = _load_module()
    fake_urlopen, calls = _urlopen_responses(
        _Response(200, json.dumps({'outcome': 'success', 'transcript': '  HELLO, omi! '}).encode())
    )
    monkeypatch.setattr(module.urllib.request, 'urlopen', fake_urlopen)

    report = module.build_report(_config(module, tmp_path))

    assert report['status'] == 'PASS'
    full_route = report['checks'][0]
    assert full_route['status'] == 'PASS'
    assert full_route['details'] == {
        'configured': True,
        'http_status': 200,
        'fixture_available': True,
        'json_object': True,
        'outcome_success': True,
        'phrase_match': True,
        'authority': 'candidate_gate',
    }
    assert len(calls) == 1
    request, _ = calls[0]
    assert request.full_url == 'https://candidate.invalid/v2/voice-message/transcribe'
    assert request.get_method() == 'POST'
    headers = _headers(request)
    assert headers['authorization'] == 'Bearer probe-token-that-must-not-leak'
    assert headers['content-type'].startswith('multipart/form-data; boundary=')
    assert b'name="files"; filename="transcription-release-probe.wav"' in request.data
    assert b'Content-Disposition: form-data; name="language"\r\n\r\nen\r\n' in request.data
    assert b'Content-Type: audio/wav' in request.data
    assert b'fixture-audio-secret' in request.data

    encoded = json.dumps(report)
    for sensitive in ('fixture-audio-secret', 'probe-token-that-must-not-leak', 'Hello Omi', 'candidate.invalid'):
        assert sensitive not in encoded


def test_full_route_rejects_success_with_incorrect_transcript(monkeypatch, tmp_path):
    module = _load_module()
    fake_urlopen, _ = _urlopen_responses(_Response(200, b'{"outcome":"success","transcript":"hello omi extra"}'))
    monkeypatch.setattr(module.urllib.request, 'urlopen', fake_urlopen)

    report = module.build_report(_config(module, tmp_path))

    full_route = report['checks'][0]
    assert report['status'] == 'FAIL'
    assert full_route['status'] == 'FAIL'
    assert full_route['details']['outcome_success'] is True
    assert full_route['details']['phrase_match'] is False
    assert 'hello omi extra' not in json.dumps(report)


def test_fixture_digest_mismatch_fails_closed_without_calling_candidate(monkeypatch, tmp_path):
    module = _load_module()
    fixture_path, manifest_path = _fixture_paths(tmp_path)
    fixture_path.write_bytes(b'changed-audio')
    monkeypatch.setattr(module.urllib.request, 'urlopen', _unexpected_network)

    report = module.build_report(
        module.ProbeConfig(
            fixture_path=fixture_path,
            manifest_path=manifest_path,
            api_url='https://candidate.invalid',
            bearer_token='probe-token-that-must-not-leak',
            timeout_seconds=3.0,
        )
    )

    assert report['status'] == 'FAIL'
    assert report['checks'][0]['details'] == {
        'configured': True,
        'error_kind': 'fixture_invalid',
        'fixture_available': False,
        'authority': 'candidate_gate',
    }


def test_auth_failure_from_candidate_is_redacted_and_fails_closed(monkeypatch, tmp_path):
    module = _load_module()
    fake_urlopen, _ = _urlopen_responses(_Response(401, b'{"detail":"never expose this"}'))
    monkeypatch.setattr(module.urllib.request, 'urlopen', fake_urlopen)

    report = module.build_report(_config(module, tmp_path))

    assert report['status'] == 'FAIL'
    assert report['checks'][0]['details']['http_status'] == 401
    assert 'never expose this' not in json.dumps(report)


def test_token_file_must_not_be_group_or_world_readable(tmp_path):
    module = _load_module()
    token_file = _token_file(tmp_path)
    token_file.chmod(0o644)

    config = module.config_from_args(
        module.parse_args(
            [
                '--candidate-api-url',
                'https://candidate.invalid/',
                '--fixture-path',
                str(_fixture_paths(tmp_path)[0]),
                '--manifest-path',
                str(_fixture_paths(tmp_path)[1]),
                '--bearer-token-file',
                str(token_file),
            ]
        )
    )

    assert config.api_url == 'https://candidate.invalid'
    assert config.bearer_token is None


def test_missing_token_fails_main_without_network_or_sensitive_output(monkeypatch, tmp_path, capsys):
    module = _load_module()
    fixture_path, manifest_path = _fixture_paths(tmp_path)
    missing_token = tmp_path / 'missing-token'
    monkeypatch.setattr(module.urllib.request, 'urlopen', _unexpected_network)

    exit_code = module.main(
        [
            '--candidate-api-url',
            'https://candidate.invalid',
            '--fixture-path',
            str(fixture_path),
            '--manifest-path',
            str(manifest_path),
            '--bearer-token-file',
            str(missing_token),
            '--json-only',
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report['status'] == 'FAIL'
    assert report['checks'][0]['details']['missing_config'] == ['bearer_token']
