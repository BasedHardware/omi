import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from routers.x_connector import (
    DEFAULT_DEEP_LINK,
    OAuthUrlResponse,
    _redirect_html,
    is_safe_redirect_url,
    router,
)
from utils import x_connector


def test_is_safe_redirect_url_allowed_schemes():
    assert is_safe_redirect_url('omi://x/callback') is True
    assert is_safe_redirect_url('omi-computer-dev://x/callback?status=ready') is True
    assert is_safe_redirect_url('http://localhost:8000/callback') is True
    assert is_safe_redirect_url('http://127.0.0.1:3000/callback') is True


def test_is_safe_redirect_url_rejects_unsafe_schemes():
    assert is_safe_redirect_url('javascript:alert(1)') is False
    assert is_safe_redirect_url('data:text/html,<script>alert(1)</script>') is False
    assert is_safe_redirect_url('https://malicious-site.com/steal') is False
    assert is_safe_redirect_url('file:///etc/passwd') is False
    assert is_safe_redirect_url('ftp://evil.com') is False


def test_is_safe_redirect_url_rejects_control_characters():
    assert is_safe_redirect_url('omi://x/callback\r\nSet-Cookie: evil=1') is False
    assert is_safe_redirect_url('omi://x/callback\ninjected') is False
    assert is_safe_redirect_url('omi://x/callback\0') is False
    assert is_safe_redirect_url('omi://x/callback\tparam=1') is False


def test_is_safe_redirect_url_rejects_none_and_empty():
    assert is_safe_redirect_url(None) is False
    assert is_safe_redirect_url('') is False
    assert is_safe_redirect_url('   ') is False
    assert is_safe_redirect_url(123) is False  # type: ignore[arg-type]


def test_redirect_html_neutralizes_javascript_xss():
    resp = _redirect_html('javascript:alert(document.domain)', False, 'Error')
    html_content = resp.body.decode('utf-8')
    assert 'javascript:' not in html_content
    assert DEFAULT_DEEP_LINK in html_content


def test_redirect_html_escapes_script_breakout():
    malicious = 'omi://x/callback</script><script>alert(1)</script>'
    resp = _redirect_html(malicious, True, 'OK')
    html_content = resp.body.decode('utf-8')
    assert '</script><script>alert(1)</script>' not in html_content
    assert r'<\/script>' in html_content or DEFAULT_DEEP_LINK in html_content


def test_redirect_html_escapes_message_content():
    resp = _redirect_html(DEFAULT_DEEP_LINK, False, '<script>alert("hacked")</script>')
    html_content = resp.body.decode('utf-8')
    assert '<script>alert("hacked")</script>' not in html_content
    assert '&lt;script&gt;alert(&quot;hacked&quot;)&lt;/script&gt;' in html_content


def test_x_oauth_url_rejects_invalid_redirect_url():
    with patch('utils.x_connector.is_oauth_configured', return_value=True):
        from routers.x_connector import x_oauth_url

        res = x_oauth_url(success_redirect_url='https://evil.com/phish', uid='test_user')
        assert res.success is False
        assert res.error == 'invalid_redirect_url'
        assert res.auth_url is None


def test_x_oauth_url_accepts_valid_redirect_url():
    with patch('utils.x_connector.is_oauth_configured', return_value=True), patch(
        'utils.x_connector.build_authorize_url', return_value='https://twitter.com/oauth'
    ) as mock_build:
        from routers.x_connector import x_oauth_url

        res = x_oauth_url(success_redirect_url='omi://x/callback', uid='test_user')
        assert res.success is True
        assert res.auth_url == 'https://twitter.com/oauth'
        mock_build.assert_called_once_with('test_user', success_redirect_url='omi://x/callback')


def test_x_oauth_url_sanitizes_internal_exception(caplog):
    with patch('utils.x_connector.is_oauth_configured', return_value=True), patch(
        'utils.x_connector.build_authorize_url', side_effect=ValueError('sensitive_token_abc123')
    ):
        from routers.x_connector import x_oauth_url

        res = x_oauth_url(success_redirect_url=None, uid='test_user')
        assert res.success is False
        assert res.error == 'internal_error'


def test_oauth_state_json_serialization_roundtrip():
    fake_redis = {}

    def fake_setex(key, ttl, value):
        fake_redis[key] = value

    def fake_get(key):
        return fake_redis.get(key)

    def fake_delete(key):
        fake_redis.pop(key, None)

    with patch('database.redis_db.r.setex', side_effect=fake_setex), patch(
        'database.redis_db.r.get', side_effect=fake_get
    ), patch('database.redis_db.r.delete', side_effect=fake_delete), patch.object(
        x_connector, 'is_oauth_configured', return_value=True
    ):

        auth_url = x_connector.build_authorize_url('user_123', success_redirect_url='omi://x/callback')
        assert 'state=' in auth_url
        state = auth_url.split('state=')[1].split('&')[0]

        # Verify state is stored as JSON in redis
        stored_raw = fake_redis[f'{x_connector._STATE_PREFIX}{state}']
        parsed_json = json.loads(stored_raw)
        assert parsed_json['uid'] == 'user_123'
        assert parsed_json['success_redirect_url'] == 'omi://x/callback'
        assert 'verifier' in parsed_json

        # Verify consume_oauth_state decodes correctly
        consumed = x_connector.consume_oauth_state(state)
        assert consumed is not None
        assert consumed['uid'] == 'user_123'
        assert consumed['success_redirect_url'] == 'omi://x/callback'
        assert consumed['verifier'] == parsed_json['verifier']

        # Verify one-time use (deleted after consume)
        assert x_connector.consume_oauth_state(state) is None


def test_oauth_state_legacy_newline_fallback():
    legacy_raw = "legacy_uid_999\nlegacy_verifier_xyz\nomi://x/callback"

    with patch('database.redis_db.r.get', return_value=legacy_raw.encode('utf-8')), patch('database.redis_db.r.delete'):
        consumed = x_connector.consume_oauth_state('legacy_state_token')
        assert consumed is not None
        assert consumed['uid'] == 'legacy_uid_999'
        assert consumed['verifier'] == 'legacy_verifier_xyz'
        assert consumed['success_redirect_url'] == 'omi://x/callback'


@pytest.mark.asyncio
async def test_x_oauth_callback_fallback_on_unsafe_state_redirect():
    fake_state = {
        'uid': 'user_456',
        'verifier': 'verifier_123',
        'success_redirect_url': 'javascript:alert(1)',
    }

    with patch('utils.x_connector.consume_oauth_state', return_value=fake_state), patch(
        'utils.x_connector.exchange_code', new_callable=AsyncMock
    ) as mock_exchange, patch('utils.x_connector.fetch_me', new_callable=AsyncMock) as mock_me, patch(
        'routers.x_connector.run_blocking', new_callable=AsyncMock
    ), patch(
        'routers.x_connector.start_background_task'
    ):

        mock_exchange.return_value = {'access_token': 'test_token'}
        mock_me.return_value = {'username': 'testuser', 'id': '987'}

        from routers.x_connector import x_oauth_callback

        mock_req = MagicMock()
        resp = await x_oauth_callback(mock_req, code='auth_code', state='valid_state', error=None)
        html_body = resp.body.decode('utf-8')
        assert 'javascript:alert(1)' not in html_body
        assert DEFAULT_DEEP_LINK in html_body
        assert 'X connected' in html_body
