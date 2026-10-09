"""Regression: POST /v1/apps/enable gate failures map to bounded, actionable responses.

The setup_completed_url check used to surface every upstream fault as the same
400 "App setup is not completed" (or a 500 on a null external_integration), and
it logged the raw developer-controlled response body. These tests pin the gate
order (missing -> disabled -> private -> unpaid -> external setup) and the
status/detail contract for each failure class through a real FastAPI TestClient
request with stub DB seams and a stub webhook client. No live services.
"""

import os
from contextlib import ExitStack
from copy import copy
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import routers.apps as apps_router
from utils.http_client import UnsafeWebhookURLError
from utils.other import endpoints as auth

COMPLETED = b'{"is_setup_completed": true}'


class _Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    async def get(self, url, **_kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


def _response(status: int, content: bytes = COMPLETED) -> httpx.Response:
    return httpx.Response(status, content=content, headers={'Content-Type': 'application/json'})


def _app_dict(**overrides):
    data = {
        'id': 'app-1',
        'name': 'Test App',
        'image': 'https://example.com/app.png',
        'author': 'Test Author',
        'uid': 'owner-uid',
        'email': 'dev@example.com',
        'category': 'productivity-and-organization',
        'description': 'test app',
        'capabilities': set(),
        'deleted': False,
        'private': False,
        'disabled': False,
        'is_paid': False,
        'external_integration': None,
    }
    data.update(overrides)
    return data


def _external_app(setup_url='https://provider.test/status', integration=None, **overrides):
    return _app_dict(
        capabilities={'external_integration'},
        external_integration=integration or {'setup_completed_url': setup_url},
        **overrides,
    )


def _enable(app, client=None, *, user_paid=False, tester=False):
    """POST /v1/apps/enable through TestClient; return (response, client, enable_calls)."""
    enable_calls = []
    client = client or _Client(response=_response(200))
    fastapi_app = FastAPI()
    target_router = copy(apps_router.router)
    target_router.routes = [
        route
        for route in apps_router.router.routes
        if getattr(route, 'path', None) == '/v1/apps/enable' and 'POST' in (getattr(route, 'methods', None) or set())
    ]
    assert len(target_router.routes) == 1
    fastapi_app.include_router(target_router)
    fastapi_app.dependency_overrides[auth.get_current_user_uid] = lambda: 'user-1'
    with ExitStack() as stack:
        stack.enter_context(
            # safe_request_targets does real DNS resolution; hermetic tests must pin without network.
            patch.object(
                apps_router,
                'safe_request_targets',
                lambda url: [(url, {'headers': {}, 'extensions': {}})],
            )
        )
        stack.enter_context(patch.object(apps_router, 'get_available_app_by_id', lambda _id, _uid: app))
        stack.enter_context(patch.object(apps_router, 'get_pinned_delivery_client', lambda: client))
        stack.enter_context(patch.object(apps_router, 'is_tester', lambda _uid: tester))
        stack.enter_context(patch.object(apps_router, 'get_is_user_paid_app', lambda _id, _uid: user_paid))
        stack.enter_context(patch.object(apps_router, 'enable_app', lambda _uid, _id: enable_calls.append(_id) or True))
        stack.enter_context(patch.object(apps_router, 'increase_app_installs_count', lambda _id: None))
        response = TestClient(fastapi_app).post('/v1/apps/enable', params={'app_id': 'app-1'})
    return response, client, enable_calls


def test_ordinary_chat_app_without_external_integration_still_installs():
    client = _Client()
    response, client, enable_calls = _enable(_app_dict(capabilities={'chat'}), client)
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert client.calls == 0
    assert enable_calls == ['app-1']


def test_minimal_legacy_app_with_no_setup_state_installs():
    response, client, enable_calls = _enable(_app_dict())
    assert response.status_code == 200
    assert client.calls == 0
    assert enable_calls == ['app-1']


def test_missing_app_returns_404():
    response, _, enable_calls = _enable(None)
    assert response.status_code == 404
    assert enable_calls == []


def test_disabled_app_keeps_existing_400_detail():
    response, _, enable_calls = _enable(_app_dict(disabled=True, disabled_at='2026-01-01T00:00:00Z'))
    assert response.status_code == 400
    assert 'disabled' in response.json()['detail']
    assert enable_calls == []


def test_private_app_unauthorized_returns_403():
    response, _, enable_calls = _enable(_app_dict(private=True))
    assert response.status_code == 403
    assert enable_calls == []


def test_unpaid_paid_app_returns_403_without_setup_callback_or_enable():
    client = _Client(response=_response(200))
    response, client, enable_calls = _enable(_external_app(is_paid=True), client, user_paid=False)
    assert response.status_code == 403
    assert 'paid subscription' in response.json()['detail']
    assert client.calls == 0
    assert enable_calls == []


def test_paid_user_with_completed_setup_enables():
    response, client, enable_calls = _enable(_external_app(is_paid=True), user_paid=True)
    assert response.status_code == 200
    assert client.calls == 1
    assert enable_calls == ['app-1']


def test_external_capability_without_integration_returns_422():
    response, client, enable_calls = _enable(_app_dict(capabilities={'external_integration'}))
    assert response.status_code == 422
    assert 'integration setup configuration' in response.json()['detail']
    assert client.calls == 0
    assert enable_calls == []


def test_unsafe_setup_url_returns_422():
    client = _Client(error=UnsafeWebhookURLError('resolves to non-public address'))
    response, _, enable_calls = _enable(_external_app(), client)
    assert response.status_code == 422
    assert 'invalid setup endpoint' in response.json()['detail']
    assert enable_calls == []


@pytest.mark.parametrize(
    'error',
    [httpx.ConnectError('refused'), httpx.ReadTimeout('timeout')],
    ids=['connect', 'read-timeout'],
)
def test_setup_request_error_returns_503(error):
    response, _, enable_calls = _enable(_external_app(), _Client(error=error))
    assert response.status_code == 503, error
    assert 'Unable to verify app setup' in response.json()['detail']
    assert enable_calls == []


@pytest.mark.parametrize('status', [400, 500, 503])
def test_upstream_non_200_returns_503(status):
    response, _, enable_calls = _enable(_external_app(), _Client(response=_response(status)))
    assert response.status_code == 503, status
    assert 'Unable to verify app setup' in response.json()['detail']
    assert enable_calls == []


@pytest.mark.parametrize('body', [b'{"is_setup_completed": false}', b'{}', b'true', b'not json'])
def test_incomplete_or_malformed_setup_returns_400(body):
    response, _, enable_calls = _enable(_external_app(), _Client(response=_response(200, body)))
    assert response.status_code == 400, body
    detail = response.json()['detail']
    assert 'setup is not completed' in detail
    # Guidance matches the app's actual setup surface: in-app instructions when
    # configured, otherwise the developer-side completion path.
    assert 'setup instructions' in detail or 'developer side' in detail
    assert enable_calls == []


@pytest.mark.parametrize('body', [b'{"is_setup_completed": false}', b'not json'])
def test_incomplete_setup_with_setup_ui_points_at_the_instructions(body):
    app = _external_app(
        integration={
            'setup_completed_url': 'https://provider.test/status',
            'setup_instructions_file_path': 'instructions.md',
        }
    )
    response, _, enable_calls = _enable(app, _Client(response=_response(200, body)))
    assert response.status_code == 400, body
    detail = response.json()['detail']
    assert 'setup instructions' in detail
    assert enable_calls == []


def test_completed_setup_enables_exactly_once():
    response, client, enable_calls = _enable(_external_app())
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert client.calls == 1
    assert enable_calls == ['app-1']


def test_setup_probe_uses_the_pinned_target():
    """The setup check must connect to the validated/pinned URL with its Host/SNI metadata,
    not the raw developer-controlled string (SSRF / DNS-rebinding guard)."""
    seen = {}

    class _CaptureClient:
        async def get(self, url, **kwargs):
            seen['url'] = url
            seen['kwargs'] = kwargs
            return _response(200)

    def _pin(url):
        seen['pinned_from'] = url
        return [
            (
                'https://93.184.216.34/status',
                {
                    'headers': {'Host': 'provider.test'},
                    'extensions': {'sni_hostname': 'provider.test'},
                },
            )
        ]

    fastapi_app = FastAPI()
    target_router = copy(apps_router.router)
    target_router.routes = [
        route
        for route in apps_router.router.routes
        if getattr(route, 'path', None) == '/v1/apps/enable' and 'POST' in (getattr(route, 'methods', None) or set())
    ]
    fastapi_app.include_router(target_router)
    fastapi_app.dependency_overrides[auth.get_current_user_uid] = lambda: 'user-1'
    with ExitStack() as stack:
        stack.enter_context(patch.object(apps_router, 'get_available_app_by_id', lambda _id, _uid: _external_app()))
        stack.enter_context(patch.object(apps_router, 'get_pinned_delivery_client', lambda: _CaptureClient()))
        stack.enter_context(patch.object(apps_router, 'safe_request_targets', _pin))
        stack.enter_context(patch.object(apps_router, 'is_tester', lambda _uid: False))
        stack.enter_context(patch.object(apps_router, 'get_is_user_paid_app', lambda _id, _uid: False))
        stack.enter_context(patch.object(apps_router, 'enable_app', lambda _uid, _id: True))
        stack.enter_context(patch.object(apps_router, 'increase_app_installs_count', lambda _id: None))
        response = TestClient(fastapi_app).post('/v1/apps/enable', params={'app_id': 'app-1'})

    assert response.status_code == 200
    assert seen['pinned_from'] == 'https://provider.test/status'
    assert seen['url'] == 'https://93.184.216.34/status?uid=user-1'
    assert seen['kwargs']['headers'] == {'Host': 'provider.test'}
    assert seen['kwargs']['extensions'] == {'sni_hostname': 'provider.test'}
    assert seen['kwargs']['follow_redirects'] is False


def test_setup_probe_tries_every_safe_address_before_reporting_unavailable():
    """A multi-A / dual-stack setup hostname must not fail 503 on the first
    unreachable address: pinning replaced HTTPX's normal address fallback, so
    the probe tries every safe resolved address (webhook delivery parity)."""
    attempts = []

    class _FlakyClient:
        async def get(self, url, **_kwargs):
            attempts.append(url)
            if '93.184.216.34' in url:
                raise httpx.ConnectError('first address unreachable')
            return _response(200)

    def _pin(url):
        return [
            ('https://93.184.216.34/status', {'headers': {}, 'extensions': {}}),
            ('https://93.184.216.35/status', {'headers': {}, 'extensions': {}}),
        ]

    fastapi_app = FastAPI()
    target_router = copy(apps_router.router)
    target_router.routes = [
        route
        for route in apps_router.router.routes
        if getattr(route, 'path', None) == '/v1/apps/enable' and 'POST' in (getattr(route, 'methods', None) or set())
    ]
    fastapi_app.include_router(target_router)
    fastapi_app.dependency_overrides[auth.get_current_user_uid] = lambda: 'user-1'
    with ExitStack() as stack:
        stack.enter_context(patch.object(apps_router, 'get_available_app_by_id', lambda _id, _uid: _external_app()))
        stack.enter_context(patch.object(apps_router, 'get_pinned_delivery_client', lambda: _FlakyClient()))
        stack.enter_context(patch.object(apps_router, 'safe_request_targets', _pin))
        stack.enter_context(patch.object(apps_router, 'is_tester', lambda _uid: False))
        stack.enter_context(patch.object(apps_router, 'get_is_user_paid_app', lambda _id, _uid: False))
        stack.enter_context(patch.object(apps_router, 'enable_app', lambda _uid, _id: True))
        stack.enter_context(patch.object(apps_router, 'increase_app_installs_count', lambda _id: None))
        response = TestClient(fastapi_app).post('/v1/apps/enable', params={'app_id': 'app-1'})

    assert response.status_code == 200
    assert attempts == [
        'https://93.184.216.34/status?uid=user-1',
        'https://93.184.216.35/status?uid=user-1',
    ]


def test_enable_failure_logs_carry_no_body_or_identity(caplog):
    client = _Client(response=_response(500, b'secret-body-content user@mail.test'))
    with caplog.at_level('WARNING'):
        response, _, _ = _enable(_external_app(), client)
    assert response.status_code == 503
    messages = ' '.join(record.getMessage() for record in caplog.records)
    assert 'app_install_failure class=setup_unavailable status=500' in messages
    assert 'secret-body-content' not in messages
    assert 'user@mail.test' not in messages
    assert 'provider.test' not in messages
    assert 'user-1' not in messages
