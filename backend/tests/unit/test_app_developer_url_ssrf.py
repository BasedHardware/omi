"""Behavioral coverage for FC-APPS-002 developer-URL SSRF protection.

The app-enable setup check, OAuth auto-enable setup check, and chat-tools
manifest fetch are the three server-side GETs covered by the ruling. They must
all use ``safe_request_target`` so the connection is pinned to the address that
passed validation, and they must not automatically follow redirects.
"""

import asyncio
import os
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
os.environ.setdefault('PINECONE_API_KEY', 'test-pinecone-key-not-real')

import routers.apps as apps_router  # noqa: E402
import utils.apps as apps_utils  # noqa: E402
import utils.http_client as http_client  # noqa: E402
from tests.unit.test_oauth_token_async_boundaries import _loaded_oauth_router  # noqa: E402
from utils.http_client import UnsafeWebhookURLError  # noqa: E402

SETUP_URL = 'https://setup.example.test/completed'
MANIFEST_URL = 'https://manifest.example.test/.well-known/omi-tools.json'
PINNED_IP = '8.8.8.8'
PIN_KWARGS = {
    'headers': {'Host': 'setup.example.test'},
    'extensions': {'sni_hostname': 'setup.example.test'},
}


def _external_app() -> dict:
    return {
        'id': 'app-1',
        'name': 'External App',
        'category': 'other',
        'author': 'Developer',
        'description': 'Test app',
        'image': '',
        'capabilities': {'external_integration'},
        'external_integration': {'setup_completed_url': SETUP_URL},
    }


async def _direct_run_blocking(_executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)


class _AsyncResponseClient:
    def __init__(self, status_code: int = 200, json_body: object | None = None):
        self.status_code = status_code
        self.json_body = {'is_setup_completed': True} if json_body is None else json_body
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url: str, **kwargs) -> httpx.Response:
        self.calls.append((url, kwargs))
        headers = {'location': 'http://169.254.169.254/latest/meta-data'} if self.status_code == 302 else {}
        return httpx.Response(
            self.status_code,
            json=self.json_body,
            headers=headers,
            request=httpx.Request('GET', url),
        )


def _install_enable_fakes(monkeypatch, client: _AsyncResponseClient) -> list[tuple[str, str]]:
    writes: list[tuple[str, str]] = []

    async def get_pinned_once(url, pin_kwargs, **kwargs):
        return await client.get(url, pin_kwargs=pin_kwargs, **kwargs)

    monkeypatch.setattr(apps_router, 'run_blocking', _direct_run_blocking)
    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda _app_id, _uid: _external_app())
    monkeypatch.setattr(apps_router, 'get_pinned_http_url_once', get_pinned_once)
    monkeypatch.setattr(apps_router, 'enable_app', lambda uid, app_id: writes.append((uid, app_id)))
    monkeypatch.setattr(apps_router, 'increase_app_installs_count', lambda _app_id: None)
    monkeypatch.setattr(apps_router, 'is_tester', lambda _uid: False)
    return writes


def test_enable_rejects_private_setup_target_before_http(monkeypatch) -> None:
    client = _AsyncResponseClient()
    _install_enable_fakes(monkeypatch, client)
    monkeypatch.setattr(
        apps_router,
        'safe_request_target',
        lambda _url: (_ for _ in ()).throw(UnsafeWebhookURLError('private address')),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(apps_router.enable_app_endpoint('app-1', uid='user-1'))

    assert exc.value.status_code == 400
    assert 'not a public address' in exc.value.detail
    assert client.calls == []


def test_enable_uses_pinned_target_and_does_not_follow_redirects(monkeypatch) -> None:
    client = _AsyncResponseClient()
    writes = _install_enable_fakes(monkeypatch, client)
    validations: list[str] = []

    def safe_target(url: str):
        validations.append(url)
        return f'https://{PINNED_IP}/completed', PIN_KWARGS

    monkeypatch.setattr(apps_router, 'safe_request_target', safe_target)

    assert asyncio.run(apps_router.enable_app_endpoint('app-1', uid='user-1')) == {'status': 'ok'}
    assert validations == [SETUP_URL]
    assert writes == [('user-1', 'app-1')]
    assert len(client.calls) == 1
    request_url, request_kwargs = client.calls[0]
    assert request_url == f'https://{PINNED_IP}/completed?uid=user-1'
    assert request_kwargs['pin_kwargs'] == PIN_KWARGS
    assert request_kwargs['timeout'].connect == 2.0
    assert request_kwargs['timeout'].read == 30.0


def test_enable_does_not_traverse_redirect_to_private_target(monkeypatch) -> None:
    client = _AsyncResponseClient(status_code=302)
    writes = _install_enable_fakes(monkeypatch, client)
    monkeypatch.setattr(
        apps_router,
        'safe_request_target',
        lambda _url: (f'https://{PINNED_IP}/completed', PIN_KWARGS),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(apps_router.enable_app_endpoint('app-1', uid='user-1'))

    assert exc.value.status_code == 400
    assert len(client.calls) == 1
    assert writes == []


class _SyncResponseClient:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, url: str, **kwargs) -> httpx.Response:
        self.calls.append((url, kwargs))
        headers = {'location': 'http://127.0.0.1/admin'} if self.status_code == 302 else {}
        return httpx.Response(
            self.status_code,
            json={
                'tools': [
                    {
                        'name': 'safe_tool',
                        'description': 'A safe test tool',
                        'endpoint': '/tools/safe',
                    }
                ]
            },
            headers=headers,
            request=httpx.Request('GET', url),
        )


def _install_manifest_fakes(monkeypatch, client: _SyncResponseClient) -> None:
    monkeypatch.setattr(apps_utils, 'get_generic_cache', lambda _key: None)
    monkeypatch.setattr(apps_utils, 'set_generic_cache', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(http_client.httpx, 'Client', lambda **_kwargs: client)


def test_manifest_rejects_credential_target_before_logging_cache_or_http(monkeypatch, caplog) -> None:
    client = _SyncResponseClient()
    _install_manifest_fakes(monkeypatch, client)
    cache_reads: list[str] = []
    monkeypatch.setattr(apps_utils, 'get_generic_cache', lambda key: cache_reads.append(key))
    credential_url = 'https://manifest-user:manifest-password@manifest.example.test/tools.json'

    assert apps_utils.fetch_app_chat_tools_from_manifest(credential_url) is None
    assert cache_reads == []
    assert client.calls == []
    assert credential_url not in caplog.text
    assert 'manifest-user' not in caplog.text
    assert 'manifest-password' not in caplog.text


def test_manifest_uses_pinned_target_and_safe_url_still_works(monkeypatch) -> None:
    client = _SyncResponseClient()
    _install_manifest_fakes(monkeypatch, client)
    monkeypatch.setattr(
        apps_utils,
        'safe_request_target',
        lambda _url: (
            f'https://{PINNED_IP}/.well-known/omi-tools.json',
            {
                'headers': {'Host': 'manifest.example.test'},
                'extensions': {'sni_hostname': 'manifest.example.test'},
            },
        ),
    )

    result = apps_utils.fetch_app_chat_tools_from_manifest(MANIFEST_URL)

    assert result is not None
    assert result['tools'][0]['name'] == 'safe_tool'
    assert client.calls[0][0] == f'https://{PINNED_IP}/.well-known/omi-tools.json'
    assert client.calls[0][1]['headers']['Host'] == 'manifest.example.test'
    assert client.calls[0][1]['extensions'] == {'sni_hostname': 'manifest.example.test'}
    assert client.calls[0][1]['follow_redirects'] is False


def test_manifest_does_not_traverse_redirect_to_private_target(monkeypatch) -> None:
    client = _SyncResponseClient(status_code=302)
    _install_manifest_fakes(monkeypatch, client)
    monkeypatch.setattr(
        apps_utils,
        'safe_request_target',
        lambda _url: (
            f'https://{PINNED_IP}/.well-known/omi-tools.json',
            {
                'headers': {'Host': 'manifest.example.test'},
                'extensions': {'sni_hostname': 'manifest.example.test'},
            },
        ),
    )

    assert apps_utils.fetch_app_chat_tools_from_manifest(MANIFEST_URL) is None
    assert len(client.calls) == 1
    assert client.calls[0][1]['follow_redirects'] is False


def _install_oauth_external_app(oauth) -> None:
    class _ExternalApp(oauth.AppModel):
        def __init__(self, **values):
            super().__init__(**values)
            self.external_integration = SimpleNamespace(
                app_home_url='https://app.example.test/complete',
                setup_completed_url=SETUP_URL,
                actions=[],
                triggers_on=None,
            )

        def works_externally(self) -> bool:
            return True

    oauth.AppModel = _ExternalApp
    oauth.is_user_app_enabled = lambda _uid, _app_id: False


def _exchange_oauth(oauth):
    return asyncio.run(
        oauth.oauth_token(
            firebase_id_token='token',
            app_id='app-1',
            csrf_token='matching-csrf-token',
            oauth_csrf_cookie='matching-csrf-token',
        )
    )


def test_oauth_rejects_private_setup_target_before_http() -> None:
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        _install_oauth_external_app(oauth)
        oauth.safe_request_target = lambda _url: (_ for _ in ()).throw(oauth.UnsafeWebhookURLError('private'))
        oauth.get_pinned_http_url_once = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError('HTTP client must not be created')
        )

        with pytest.raises(HTTPException) as exc:
            _exchange_oauth(oauth)

        assert exc.value.status_code == 400
        assert 'not a public address' in exc.value.detail


def test_oauth_uses_pinned_target_and_safe_url_still_works() -> None:
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        _install_oauth_external_app(oauth)
        calls: list[tuple[str, dict, dict]] = []
        oauth.safe_request_target = lambda _url: (f'https://{PINNED_IP}/completed', PIN_KWARGS)

        async def get_pinned_once(url, pin_kwargs, **kwargs):
            calls.append((url, pin_kwargs, kwargs))
            return httpx.Response(
                200,
                json={'is_setup_completed': True},
                request=httpx.Request('GET', url),
            )

        oauth.get_pinned_http_url_once = get_pinned_once

        assert _exchange_oauth(oauth)['redirect_url'] == 'https://app.example.test/complete'
        assert len(calls) == 1
        assert calls[0][0] == f'https://{PINNED_IP}/completed?uid=user-1'
        assert calls[0][1] == PIN_KWARGS
        assert calls[0][2]['timeout'].connect == 2.0


def test_oauth_does_not_traverse_redirect_to_private_target() -> None:
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        _install_oauth_external_app(oauth)
        calls: list[str] = []
        oauth.safe_request_target = lambda _url: (f'https://{PINNED_IP}/completed', PIN_KWARGS)

        async def get_pinned_once(url, _pin_kwargs, **_kwargs):
            calls.append(url)
            return httpx.Response(
                302,
                headers={'location': 'http://169.254.169.254/latest/meta-data'},
                request=httpx.Request('GET', url),
            )

        oauth.get_pinned_http_url_once = get_pinned_once

        with pytest.raises(HTTPException) as exc:
            _exchange_oauth(oauth)

        assert exc.value.status_code == 503
        assert calls == [f'https://{PINNED_IP}/completed?uid=user-1']
