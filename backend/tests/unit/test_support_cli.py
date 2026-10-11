"""Hermetic tests for the support CLI session and request shape."""

import json
import stat

import pytest

from scripts.support import cli


class _Response:
    def __init__(self, payload: dict, status: int = 200):
        self.status = status
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_login_page_posts_refresh_token_not_customer_content():
    page = cli.login_page(
        {'apiKey': 'public-web-key', 'authDomain': 'based-hardware.firebaseapp.com', 'projectId': 'based-hardware'},
        'state-token',
    )
    assert 'support person' in page
    assert 'refresh_token' in page
    assert 'state-token' in page
    assert 'transcript' not in page
    assert 'ADMIN_KEY' not in page


def test_session_file_is_owner_read_write(tmp_path, monkeypatch):
    path = tmp_path / 'session.json'
    monkeypatch.setattr(cli, 'SESSION_PATH', path)
    cli.save_session(
        {'refresh_token': 'refresh-secret', 'api_base': 'https://api.omi.me', 'project_id': 'based-hardware'}
    )
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    assert 'refresh-secret' in path.read_text()


def test_refresh_sends_refresh_grant_and_does_not_print_token(monkeypatch, capsys, tmp_path):
    path = tmp_path / 'session.json'
    monkeypatch.setattr(cli, 'SESSION_PATH', path)
    cli.save_session(
        {'refresh_token': 'refresh-secret', 'api_base': 'https://api.omi.me', 'project_id': 'based-hardware'}
    )
    captured = {}

    def fake_urlopen(request, timeout=30):
        captured.setdefault('urls', []).append(request.full_url)
        if request.data is not None:
            captured['body'] = request.data.decode()
        if 'securetoken' in request.full_url:
            return _Response({'id_token': _token(), 'refresh_token': 'rotated'})
        return _Response(
            {
                'email': 'customer@example.com',
                'uid': 'target',
                'plan': 'basic',
                'fair_use_stage': 'none',
                'transcription_seconds_used': 0,
            }
        )

    monkeypatch.setattr(cli.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(
        cli,
        'public_firebase_config',
        lambda: {
            'apiKey': 'public-web-key',
            'authDomain': 'based-hardware.firebaseapp.com',
            'projectId': 'based-hardware',
        },
    )
    cli.main(['--base-url', 'https://api.omi.me', 'lookup', 'customer@example.com'])
    out = capsys.readouterr().out
    assert 'grant_type=refresh_token' in captured['body']
    assert 'refresh-secret' in captured['body']
    assert 'Bearer' not in out
    assert 'refresh-secret' not in out
    assert 'plan: basic' in out
    assert any('securetoken.googleapis.com' in url for url in captured['urls'])
    assert any('/v1/support/lookup' in url for url in captured['urls'])


def test_missing_grant_names_the_support_doc():
    with pytest.raises(SystemExit) as raised:
        cli.explain_denial(
            403, {'detail': 'Support access denied'}, {'user_id': 'support-uid', 'email': 'support@example.com'}
        )
    assert 'supportData/support-uid' in str(raised.value)


def test_trace_requires_a_window():
    with pytest.raises(SystemExit):
        cli.main(['trace', 'customer@example.com'])


def _token() -> str:
    import base64

    payload = (
        base64.urlsafe_b64encode(json.dumps({'user_id': 'support-uid', 'email': 'support@example.com'}).encode())
        .decode()
        .rstrip('=')
    )
    return f'header.{payload}.sig'
