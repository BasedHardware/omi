from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from scripts import smoke_cloud_run_health


class _Response:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_health_smoke_uses_serverless_identity_header_and_never_reads_body(capsys):
    captured = {}

    def http_open(request, timeout):
        captured['url'] = request.full_url
        captured['identity'] = request.get_header('X-serverless-authorization')
        captured['timeout'] = timeout
        return _Response()

    status = smoke_cloud_run_health.run_smoke(
        smoke_cloud_run_health.HealthSmokeConfig(
            base_url='https://candidate.example/',
            cloud_run_identity_token='identity-token-that-must-not-leak',
            timeout_seconds=7,
            attempts=1,
            retry_delay_seconds=0,
        ),
        http_open=http_open,
    )

    assert status == 204
    assert captured == {
        'url': 'https://candidate.example/v1/health',
        'identity': 'Bearer identity-token-that-must-not-leak',
        'timeout': 7,
    }
    assert 'identity-token' not in capsys.readouterr().out


def test_health_smoke_retries_bounded_http_failures_then_succeeds():
    attempts = []
    delays = []

    def http_open(_request, timeout):
        assert timeout == 7
        attempts.append(1)
        if len(attempts) == 1:
            raise HTTPError('https://candidate.example/v1/health', 503, 'unavailable', {}, None)
        return _Response()

    assert (
        smoke_cloud_run_health.run_smoke(
            smoke_cloud_run_health.HealthSmokeConfig(
                base_url='https://candidate.example',
                cloud_run_identity_token='',
                timeout_seconds=7,
                attempts=2,
                retry_delay_seconds=1,
            ),
            http_open=http_open,
            sleep=delays.append,
        )
        == 204
    )
    assert len(attempts) == 2
    assert delays == [1]


def test_health_smoke_fails_when_candidate_never_returns_success():
    def http_open(_request, timeout):
        assert timeout == 7
        raise HTTPError('https://candidate.example/v1/health', 503, 'unavailable', {}, None)

    with pytest.raises(RuntimeError, match='HTTP 503'):
        smoke_cloud_run_health.run_smoke(
            smoke_cloud_run_health.HealthSmokeConfig(
                base_url='https://candidate.example',
                cloud_run_identity_token='',
                timeout_seconds=7,
                attempts=1,
                retry_delay_seconds=0,
            ),
            http_open=http_open,
        )
