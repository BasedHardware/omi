from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from scripts import smoke_what_matters_now


class _Response:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_smoke_uses_admin_auth_without_reading_or_reporting_the_response_body(capsys):
    captured = {}

    def http_open(request, timeout):
        captured['url'] = request.full_url
        captured['authorization'] = request.get_header('Authorization')
        captured['timeout'] = timeout
        return _Response(200)

    status = smoke_what_matters_now.run_smoke(
        smoke_what_matters_now.SmokeConfig(
            base_url='https://api.omi.dev/', uid='private-test-uid', admin_key='private-key', timeout_seconds=7
        ),
        http_open=http_open,
    )

    assert status == 200
    assert captured == {
        'url': 'https://api.omi.dev/v1/what-matters-now',
        'authorization': 'Bearer private-keyprivate-test-uid',
        'timeout': 7,
    }
    output = capsys.readouterr().out
    assert 'HTTP 200' in output
    assert 'private' not in output


def test_smoke_fails_on_a_backend_5xx_without_exposing_the_response_body():
    def http_open(_request, timeout):
        raise HTTPError('https://api.omi.dev/v1/what-matters-now', 500, 'boom', {}, None)

    with pytest.raises(RuntimeError, match='HTTP 500'):
        smoke_what_matters_now.run_smoke(
            smoke_what_matters_now.SmokeConfig(
                base_url='https://api.omi.dev', uid='private-test-uid', admin_key='private-key', timeout_seconds=7
            ),
            http_open=http_open,
        )


def test_smoke_rejects_non_http_base_urls():
    with pytest.raises(ValueError, match='absolute HTTP'):
        smoke_what_matters_now.run_smoke(
            smoke_what_matters_now.SmokeConfig(
                base_url='not-a-url', uid='private-test-uid', admin_key='private-key', timeout_seconds=7
            ),
            http_open=SimpleNamespace(),
        )
