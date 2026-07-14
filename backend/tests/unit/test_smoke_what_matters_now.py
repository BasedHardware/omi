from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from scripts import smoke_what_matters_now
from config.what_matters_now_smoke_fixture import WHAT_MATTERS_NOW_SMOKE_UID


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
        smoke_what_matters_now.SmokeConfig(base_url='https://api.omi.dev/', admin_key='private-key', timeout_seconds=7),
        http_open=http_open,
    )

    assert status == 200
    assert captured == {
        'url': 'https://api.omi.dev/v1/what-matters-now',
        'authorization': f'Bearer private-key{WHAT_MATTERS_NOW_SMOKE_UID}',
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
                base_url='https://api.omi.dev', admin_key='private-key', timeout_seconds=7
            ),
            http_open=http_open,
        )


def test_smoke_rejects_non_http_base_urls():
    with pytest.raises(ValueError, match='absolute HTTP'):
        smoke_what_matters_now.run_smoke(
            smoke_what_matters_now.SmokeConfig(base_url='not-a-url', admin_key='private-key', timeout_seconds=7),
            http_open=SimpleNamespace(),
        )


def test_main_uses_the_code_owned_fixture_without_a_uid_environment_variable(monkeypatch):
    captured = {}
    monkeypatch.setenv('ADMIN_KEY', 'private-key')
    monkeypatch.delenv('OMI_TASK_INTELLIGENCE_SMOKE_UID', raising=False)
    monkeypatch.setattr(smoke_what_matters_now.sys, 'argv', ['smoke', '--base-url', 'https://api.omi.dev'])
    monkeypatch.setattr(
        smoke_what_matters_now, 'run_smoke', lambda config: captured.setdefault('config', config) or 200
    )

    assert smoke_what_matters_now.main() == 0
    assert captured['config'] == smoke_what_matters_now.SmokeConfig(
        base_url='https://api.omi.dev', admin_key='private-key', timeout_seconds=30.0
    )


def test_auto_dev_smoke_resolves_the_backend_cloud_run_url_with_existing_auth():
    root = Path(__file__).resolve().parents[3]
    workflow = (root / '.github' / 'workflows' / 'gcp_backend_auto_dev.yml').read_text(encoding='utf-8')

    assert 'OMI_TASK_INTELLIGENCE_SMOKE_UID' not in workflow
    assert '--secret=ADMIN_KEY' in workflow
    assert 'BACKEND_URL="$(gcloud run services describe backend' in workflow
    assert '--project="$PROJECT_ID"' in workflow
    assert "--region=\"${{ env.REGION }}\"" in workflow
    assert "--format='value(status.url)')\"" in workflow
    assert 'test -n "$BACKEND_URL"' in workflow
    assert 'smoke_what_matters_now.py --base-url "$BACKEND_URL"' in workflow
    assert 'smoke_what_matters_now.py --base-url https://api.omi.dev' not in workflow


def test_manual_development_smoke_keeps_its_existing_external_hostname_path():
    root = Path(__file__).resolve().parents[3]
    workflow = (root / '.github' / 'workflows' / 'gcp_backend.yml').read_text(encoding='utf-8')

    assert 'OMI_TASK_INTELLIGENCE_SMOKE_UID' not in workflow
    assert '--secret=ADMIN_KEY' in workflow
    assert 'smoke_what_matters_now.py --base-url https://api.omi.dev' in workflow
