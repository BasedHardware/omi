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
        without_origin = client.get('/')

    assert allowed.status_code == 200
    assert allowed.headers['access-control-allow-origin'] == 'https://app.example'
    assert denied.status_code == 400
    assert 'access-control-allow-origin' not in denied.headers
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
