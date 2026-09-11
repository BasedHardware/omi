"""HTTP response/serialization coverage for the Asana chooser pagination contract."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def asana_client(monkeypatch):
    from routers import task_integrations as ti
    from utils import task_integrations_ops as ops

    integration = {'connected': True, 'access_token': 'fixture-token'}
    monkeypatch.setattr(ti, 'run_blocking', AsyncMock(return_value=integration))
    monkeypatch.setattr(ti, 'ensure_valid_oauth_token', AsyncMock(return_value=integration))
    get = AsyncMock()
    monkeypatch.setattr(ops, 'get_http_client', lambda: SimpleNamespace(get=get))
    app = FastAPI()
    app.include_router(ti.router)
    app.dependency_overrides[ti.auth.get_current_user_uid] = lambda: 'fixture-uid'
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, get


def response(status, body):
    return SimpleNamespace(status_code=status, json=lambda: body)


def test_chooser_http_returns_projects_from_both_pages(asana_client):
    client, get = asana_client
    get.side_effect = [
        response(200, {'data': [{'gid': '1', 'name': 'First'}], 'next_page': {'offset': 'next'}}),
        response(200, {'data': [{'gid': '2', 'name': 'Second'}], 'next_page': None}),
    ]
    result = client.get('/v1/task-integrations/asana/projects/workspace')
    assert result.status_code == 200
    assert [p['gid'] for p in result.json()['projects']] == ['1', '2']
    assert get.await_count == 2


def test_chooser_http_propagates_later_page_failure(asana_client):
    client, get = asana_client
    get.side_effect = [
        response(200, {'data': [{'gid': '1', 'name': 'First'}], 'next_page': {'offset': 'next'}}),
        response(503, {}),
    ]
    result = client.get('/v1/task-integrations/asana/projects/workspace')
    assert result.status_code == 503
    assert result.json() == {'detail': 'Failed to fetch Asana projects'}
