"""The real HTTP route contracts for the shadow read adapter, using synthetic state."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import episodes as api
from utils.episodes.log import reads, worker
from utils.other import endpoints

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def setup(monkeypatch):
    monkeypatch.setattr(api, '_admitted', lambda uid, channel: True)
    monkeypatch.setattr(reads, 'ready', lambda uid: {'home_version': 7})
    monkeypatch.setattr(worker, 'sample_read', lambda *args: None)
    query = Mock(return_value=([], [], None))
    monkeypatch.setattr(reads, 'list_window', query)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[endpoints.get_current_user_uid] = lambda: 'test'
    return TestClient(app), query


def test_real_route_returns_304_before_home_page_or_member_reads(monkeypatch):
    http, query = setup(monkeypatch)
    params = {'from': NOW.isoformat(), 'to': (NOW + timedelta(days=1)).isoformat()}
    response = http.get('/v1/episodes', params=params)
    assert response.status_code == 200 and response.headers['x-omi-home-version'] == '7'
    etag = response.headers['etag']
    query.reset_mock()
    response = http.get('/v1/episodes', params=params, headers={'If-None-Match': etag})
    assert response.status_code == 304 and response.content == b''
    assert not query.called
    assert response.headers['cache-control'] == 'private, no-cache'
    changed = dict(params, to=(NOW + timedelta(days=2)).isoformat())
    assert http.get('/v1/episodes', params=changed, headers={'If-None-Match': etag}).status_code == 200
    assert query.called


def test_not_ready_and_policy_changed_use_legacy_projection(monkeypatch):
    http, query = setup(monkeypatch)
    legacy = Mock(return_value=([], None))
    project = Mock(return_value=[])
    monkeypatch.setattr(api.home_read, 'list_episode_window', legacy)
    monkeypatch.setattr(api.home_read, 'project_episodes', project)
    params = {'from': NOW.isoformat(), 'to': NOW.isoformat()}
    query.side_effect = ValueError('episode_home_policy_changed')
    response = http.get('/v1/episodes', params=params)
    assert response.status_code == 200
    assert response.json() == {'enabled': True, 'episodes': [], 'next_cursor': None}
    assert legacy.called and project.called
    monkeypatch.setattr(reads, 'ready', lambda uid: None)
    query.reset_mock()
    assert http.get('/v1/episodes', params=params).status_code == 200
    assert not query.called
