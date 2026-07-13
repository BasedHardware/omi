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


def _config(module, **overrides):
    values = {
        'audio_url': 'https://fixture.invalid/known.wav',
        'api_url': 'https://candidate.invalid',
        'bearer_token': 'probe-token-that-must-not-leak',
        'expected_phrase': 'Hello Omi',
        'synthetic_language': 'en',
        'expected_provider': None,
        'expected_model': None,
        'direct_url': None,
        'timeout_seconds': 3.0,
        'require_direct': False,
        'require_route_identity': False,
    }
    values.update(overrides)
    return module.ProbeConfig(**values)


def _headers(request):
    return {name.lower(): value for name, value in request.header_items()}


def _unexpected_network(*_args, **_kwargs):
    raise AssertionError('unexpected HTTP request')


def test_full_route_posts_real_multipart_and_validates_exact_candidate_contract(monkeypatch):
    module = _load_module()
    fixture = b'fixture-audio-secret'
    fake_urlopen, calls = _urlopen_responses(
        _Response(200, fixture),
        _Response(
            200,
            json.dumps(
                {
                    'outcome': 'success',
                    'transcript': '  HELLO, omi! ',
                    'stt_provider': 'parakeet',
                    'stt_model': 'parakeet-v3',
                }
            ).encode(),
        ),
    )
    monkeypatch.setattr(module.urllib.request, 'urlopen', fake_urlopen)

    report = module.build_report(
        _config(
            module,
            expected_provider='parakeet',
            expected_model='parakeet-v3',
            require_route_identity=True,
        )
    )

    assert report['status'] == 'PASS'
    full_route, direct = report['checks']
    assert full_route['status'] == 'PASS'
    assert full_route['details'] == {
        'configured': True,
        'http_status': 200,
        'fixture_available': True,
        'json_object': True,
        'outcome_success': True,
        'phrase_match': True,
        'provider_checked': True,
        'provider_match': True,
        'model_checked': True,
        'model_match': True,
        'authority': 'candidate_gate',
    }
    assert direct['status'] == 'NOT_RUN'
    assert len(calls) == 2
    fixture_request, _ = calls[0]
    full_request, _ = calls[1]
    assert fixture_request.full_url == 'https://fixture.invalid/known.wav'
    assert fixture_request.get_method() == 'GET'
    assert full_request.full_url == 'https://candidate.invalid/v2/voice-message/transcribe'
    assert full_request.get_method() == 'POST'
    headers = _headers(full_request)
    assert headers['authorization'] == 'Bearer probe-token-that-must-not-leak'
    assert headers['content-type'].startswith('multipart/form-data; boundary=')
    assert b'name="files"; filename="known-audio.wav"' in full_request.data
    assert b'Content-Disposition: form-data; name="language"\r\n\r\nen\r\n' in full_request.data
    assert b'Content-Type: audio/wav' in full_request.data
    assert fixture in full_request.data

    encoded = json.dumps(report)
    for sensitive in ('fixture-audio-secret', 'probe-token-that-must-not-leak', 'Hello Omi', 'candidate.invalid'):
        assert sensitive not in encoded


def test_full_route_rejects_success_with_extra_words_instead_of_substring_match(monkeypatch):
    module = _load_module()
    fake_urlopen, _ = _urlopen_responses(
        _Response(200, b'fixture-audio-secret'),
        _Response(200, b'{"outcome":"success","transcript":"hello omi extra"}'),
    )
    monkeypatch.setattr(module.urllib.request, 'urlopen', fake_urlopen)

    report = module.build_report(_config(module))

    full_route = report['checks'][0]
    assert report['status'] == 'FAIL'
    assert full_route['status'] == 'FAIL'
    assert full_route['details']['outcome_success'] is True
    assert full_route['details']['phrase_match'] is False
    assert 'hello omi extra' not in json.dumps(report)


def test_full_route_requires_http_200_and_success_outcome(monkeypatch):
    module = _load_module()
    fake_urlopen, _ = _urlopen_responses(
        _Response(200, b'fixture-audio-secret'),
        _Response(503, b'{"outcome":"expected_silence","transcript":"hello omi"}'),
    )
    monkeypatch.setattr(module.urllib.request, 'urlopen', fake_urlopen)

    report = module.build_report(_config(module))

    full_route = report['checks'][0]
    assert report['status'] == 'FAIL'
    assert full_route['details']['http_status'] == 503
    assert full_route['details']['outcome_success'] is False
    assert full_route['details']['phrase_match'] is True
    assert 'expected_silence' not in json.dumps(report)


def test_direct_parakeet_is_a_protected_diagnostic_with_its_own_multipart_shape(monkeypatch):
    module = _load_module()
    fixture = b'fixture-audio-secret'
    fake_urlopen, calls = _urlopen_responses(
        _Response(200, fixture),
        _Response(200, b'{"outcome":"success","transcript":"hello omi"}'),
        _Response(200, b'{"text":"HELLO, OMI!"}'),
    )
    monkeypatch.setattr(module.urllib.request, 'urlopen', fake_urlopen)

    report = module.build_report(
        _config(module, direct_url='http://private-parakeet.invalid/v1/transcribe', require_direct=True)
    )

    assert report['status'] == 'PASS'
    assert report['full_route_authoritative'] is True
    assert report['direct_diagnostic_only'] is True
    direct = report['checks'][1]
    assert direct['status'] == 'PASS'
    assert direct['details']['authority'] == 'diagnostic_only'
    assert len(calls) == 3
    direct_request, _ = calls[2]
    assert direct_request.full_url == 'http://private-parakeet.invalid/v1/transcribe'
    headers = _headers(direct_request)
    assert 'authorization' not in headers
    assert b'name="file"; filename="known-audio.wav"' in direct_request.data
    assert b'name="language"' not in direct_request.data
    assert fixture in direct_request.data
    assert 'private-parakeet.invalid' not in json.dumps(report)


def test_direct_is_not_run_by_default_but_is_required_when_requested():
    module = _load_module()
    optional = module._probe_direct(_config(module, direct_url=None, require_direct=False), None, {})
    required = module._probe_direct(_config(module, direct_url=None, require_direct=True), None, {})

    assert optional['status'] == 'NOT_RUN'
    assert optional['details']['configured'] is False
    assert required['status'] == 'FAIL'
    assert required['details']['missing_config'] == ['direct_url']


def test_optional_direct_failure_does_not_block_the_full_route_candidate_gate(monkeypatch):
    module = _load_module()
    fake_urlopen, _ = _urlopen_responses(
        _Response(200, b'fixture-audio-secret'),
        _Response(200, b'{"outcome":"success","transcript":"hello omi"}'),
        _Response(503, b'{"detail":"private diagnostic unavailable"}'),
    )
    monkeypatch.setattr(module.urllib.request, 'urlopen', fake_urlopen)

    report = module.build_report(
        _config(module, direct_url='http://private-parakeet.invalid/v1/transcribe', require_direct=False)
    )

    assert report['checks'][0]['status'] == 'PASS'
    assert report['checks'][1]['status'] == 'FAIL'
    assert report['status'] == 'PASS'


def test_require_direct_makes_a_direct_diagnostic_failure_blocking(monkeypatch):
    module = _load_module()
    fake_urlopen, _ = _urlopen_responses(
        _Response(200, b'fixture-audio-secret'),
        _Response(200, b'{"outcome":"success","transcript":"hello omi"}'),
        _Response(503, b'{"detail":"private diagnostic unavailable"}'),
    )
    monkeypatch.setattr(module.urllib.request, 'urlopen', fake_urlopen)

    report = module.build_report(
        _config(module, direct_url='http://private-parakeet.invalid/v1/transcribe', require_direct=True)
    )

    assert report['checks'][0]['status'] == 'PASS'
    assert report['checks'][1]['status'] == 'FAIL'
    assert report['status'] == 'FAIL'


def test_route_identity_flag_requires_protected_provider_and_model_without_network(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module.urllib.request, 'urlopen', _unexpected_network)

    report = module.build_report(_config(module, require_route_identity=True))

    assert report['status'] == 'FAIL'
    assert report['checks'][0]['details']['missing_config'] == ['expected_provider', 'expected_model']


def test_missing_full_route_config_fails_main_without_network_or_sensitive_output(monkeypatch, capsys):
    module = _load_module()
    for name in (
        'OMI_TRANSCRIPTION_SYNTHETIC_AUDIO_URL',
        'OMI_TRANSCRIPTION_SYNTHETIC_API_URL',
        'OMI_TRANSCRIPTION_SYNTHETIC_BEARER_TOKEN',
        'OMI_TRANSCRIPTION_SYNTHETIC_EXPECTED_PHRASE',
        'OMI_TRANSCRIPTION_SYNTHETIC_LANGUAGE',
        'OMI_TRANSCRIPTION_SYNTHETIC_DIRECT_URL',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(module.urllib.request, 'urlopen', _unexpected_network)

    exit_code = module.main(['--json-only'])

    output = capsys.readouterr().out
    report = json.loads(output)
    assert exit_code == 1
    assert report['status'] == 'FAIL'
    assert report['checks'][0]['details']['missing_config'] == [
        'audio_url',
        'api_url',
        'bearer_token',
        'expected_phrase',
        'synthetic_language',
    ]


def test_candidate_revision_flag_overrides_configured_api_url(monkeypatch):
    module = _load_module()
    monkeypatch.setenv('OMI_TRANSCRIPTION_SYNTHETIC_API_URL', 'https://production.invalid')

    config = module.config_from_args(
        module.parse_args(['--candidate-api-url', 'https://candidate.invalid/', '--require-route-identity'])
    )

    assert config.api_url == 'https://candidate.invalid'
    assert config.require_route_identity is True
