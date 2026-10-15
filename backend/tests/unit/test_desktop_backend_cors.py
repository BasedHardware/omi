import importlib

import pytest
from fastapi.testclient import TestClient

import desktop_backend
from utils.env_loader import load_backend_env


def _test_client(monkeypatch, app):
    monkeypatch.setattr(desktop_backend, "prepare_google_credentials", lambda: None)
    monkeypatch.setattr(desktop_backend, "_initialize_firebase_admin", lambda: None)

    async def close_clients():
        return None

    monkeypatch.setattr(desktop_backend, "close_all_clients", close_clients)
    return TestClient(app)


def test_desktop_backend_cors_reads_allowlist_from_backend_env_file(tmp_path, monkeypatch):
    (tmp_path / '.env').write_text(
        'CORS_ALLOWED_ORIGINS=https://app.example, https://admin.example\n',
        encoding='utf-8',
    )
    monkeypatch.delenv('CORS_ALLOWED_ORIGINS', raising=False)
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)

    load_backend_env(tmp_path)

    assert desktop_backend._cors_allowed_origins_from_env() == ['https://app.example', 'https://admin.example']


def test_desktop_backend_cors_rejects_wildcard(monkeypatch):
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS', 'https://app.example, *')

    with pytest.raises(RuntimeError, match='must not contain'):
        desktop_backend._cors_allowed_origins_from_env()


def test_desktop_backend_cors_rejects_wildcard_even_with_blank_entries(monkeypatch):
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS', 'https://app.example, , *')

    with pytest.raises(RuntimeError, match='must not contain'):
        desktop_backend._cors_allowed_origins_from_env()


def test_desktop_backend_cors_blank_only_origins_default_to_deny(monkeypatch):
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS', '   ')

    assert desktop_backend._cors_allowed_origins_from_env() == []


def test_desktop_backend_cors_unset_origins_default_to_deny(monkeypatch):
    monkeypatch.delenv('CORS_ALLOWED_ORIGINS', raising=False)
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)

    assert desktop_backend._cors_allowed_origins_from_env() == []


def test_desktop_backend_cors_empty_allowlist_denies_every_origin(monkeypatch):
    monkeypatch.delenv('CORS_ALLOWED_ORIGINS', raising=False)
    client = _test_client(monkeypatch, desktop_backend._build_app())

    with client:
        denied = client.options(
            '/',
            headers={
                'Origin': 'https://app.example',
                'Access-Control-Request-Method': 'GET',
            },
        )

    assert denied.status_code == 400
    assert 'access-control-allow-origin' not in denied.headers


def test_desktop_backend_cors_middleware_enforces_allowlist(monkeypatch):
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS', 'https://app.example')
    client = _test_client(monkeypatch, desktop_backend._build_app())

    with client:
        allowed = client.options(
            '/',
            headers={
                'Origin': 'https://app.example',
                'Access-Control-Request-Method': 'GET',
            },
        )
        denied = client.options(
            '/',
            headers={
                'Origin': 'https://evil.example',
                'Access-Control-Request-Method': 'GET',
            },
        )
        exposed = client.get('/', headers={'Origin': 'https://app.example'})
        without_origin = client.get('/')

    assert allowed.status_code == 200
    assert allowed.headers['access-control-allow-origin'] == 'https://app.example'
    assert denied.status_code == 400
    assert 'access-control-allow-origin' not in denied.headers
    exposed_headers = {name.strip().lower() for name in exposed.headers['access-control-expose-headers'].split(',')}
    assert {
        'x-omi-memory-belief-enabled',
        'x-omi-memory-next-cursor',
        'x-omi-list-truncated',
    } <= exposed_headers
    assert 'access-control-allow-origin' not in without_origin.headers


def test_create_app_loads_environment_before_building_cors(monkeypatch):
    def load_env():
        monkeypatch.setenv('CORS_ALLOWED_ORIGINS', 'https://app.example')

    monkeypatch.setattr(desktop_backend, 'load_backend_env', load_env)
    client = _test_client(monkeypatch, desktop_backend.create_app())

    with client:
        response = client.options(
            '/',
            headers={
                'Origin': 'https://app.example',
                'Access-Control-Request-Method': 'GET',
            },
        )

    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'https://app.example'


def test_module_level_app_loads_environment_before_building_cors(monkeypatch):
    import utils.env_loader as env_loader

    monkeypatch.delenv('CORS_ALLOWED_ORIGINS', raising=False)

    def load_env(path=None):
        monkeypatch.setenv('CORS_ALLOWED_ORIGINS', 'https://app.example')

    monkeypatch.setattr(env_loader, 'load_backend_env', load_env)
    reloaded = importlib.reload(desktop_backend)
    client = _test_client(monkeypatch, reloaded.app)

    with client:
        response = client.options(
            '/',
            headers={
                'Origin': 'https://app.example',
                'Access-Control-Request-Method': 'GET',
            },
        )

    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'https://app.example'


def test_desktop_backend_metrics_route_is_fail_closed(monkeypatch):
    monkeypatch.delenv('CORS_ALLOWED_ORIGINS', raising=False)
    monkeypatch.delenv('PROMETHEUS_SIDECAR_PORT', raising=False)
    monkeypatch.setenv('METRICS_SECRET', 'test-metrics-token')
    client = _test_client(monkeypatch, desktop_backend._build_app())

    with client:
        missing = client.get('/metrics')
        invalid = client.get('/metrics', headers={'Authorization': 'Bearer wrong'})
        valid = client.get('/metrics', headers={'Authorization': 'Bearer test-metrics-token'})

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert 'omi_journey_accepted_total' in valid.text


def test_desktop_backend_mounts_authenticated_metrics(monkeypatch):
    monkeypatch.setenv('METRICS_SECRET', 'test-metrics-secret')
    from utils.metrics import OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL

    OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL.labels(
        journey='desktop_chat', client_kind='desktop_macos', app_build='unknown'
    ).inc()
    client = _test_client(monkeypatch, desktop_backend._build_app())

    with client:
        unauthorized = client.get('/metrics')
        response = client.get(
            '/metrics',
            headers={'Authorization': 'Bearer test-metrics-secret'},
        )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/plain')
    assert 'omi_client_journey_accepted_total' in response.text


def test_desktop_startup_and_retired_routes_need_no_v2_redis(monkeypatch):
    from unittest.mock import AsyncMock, Mock
    from database import proactivity_redis, redis_db

    for key in ('HOST', 'PORT', 'PASSWORD'):
        monkeypatch.delenv(f'PROACTIVITY_REDIS_{key}', raising=False)
    v2_client = Mock(side_effect=AssertionError('desktop must not acquire a v2 Redis client'))
    monkeypatch.setattr(proactivity_redis, 'get_client', v2_client)
    monkeypatch.setattr(desktop_backend, 'load_backend_env', lambda: None)
    monkeypatch.setattr(desktop_backend, 'prepare_google_credentials', lambda: None)
    monkeypatch.setattr(desktop_backend, '_initialize_firebase_admin', lambda: None)
    monkeypatch.setattr(desktop_backend, 'start_metrics_sidecar_server', lambda: None)
    monkeypatch.setattr(desktop_backend, 'stop_metrics_sidecar_server', lambda: None)
    monkeypatch.setattr(desktop_backend, 'shutdown_managed_spend_ledger', AsyncMock())
    monkeypatch.setattr(desktop_backend, 'close_all_clients', AsyncMock())
    monkeypatch.setattr(desktop_backend.reservation_state, 'aclose', AsyncMock())
    monkeypatch.setattr(desktop_backend, 'close_posthog_control_plane', lambda: None)
    monkeypatch.setattr(desktop_backend, 'close_free_tier_control_plane', lambda: None)
    # Readiness continues to probe the existing desktop Redis, independent of v2.
    monkeypatch.setenv('REDIS_DB_HOST', 'synthetic-desktop.example')
    normal_ping = Mock(return_value=True)
    monkeypatch.setattr(redis_db.r, 'ping', normal_ping)

    app = desktop_backend.create_app()
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/ready').status_code == 200
        assert client.post('/v1/desktop/proactivity/completions', content=b'not json').status_code == 429
        assert client.post('/v1/jit/proactivity/reservations', content=b'not json').status_code == 410
        assert client.post('/v1/jit/trigger-feedback', content=b'not json').status_code == 410
        assert client.get('/v1/proactivity/feed').status_code == 404
        assert client.post('/v1/proactivity/items/item/outcomes', json={}).status_code == 404
    normal_ping.assert_called_once()
    v2_client.assert_not_called()
