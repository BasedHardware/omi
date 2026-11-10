"""Episode member wire retains existing Home classification and composed gist."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.episode import Episode
from routers import episodes as routes
from utils.episodes import home_read

NOW = datetime(2026, 11, 9, 9, tzinfo=timezone.utc)


def episode():
    return {
        'id': 'episode-1',
        'status': 'closed',
        'started_at': NOW,
        'last_activity_at': NOW,
        'conversation_ids': ['conversation-1'],
    }


@pytest.mark.parametrize(
    ('changes', 'step'),
    [
        ({}, 'ready'),
        ({'structured': {'title': 'Recording', 'title_provenance': 'server_minimum'}}, 'noise'),
        ({'summary_blocked_reason': 'content_below_floor'}, 'noise'),
        ({'summary_blocked_reason': 'content_below_floor', 'starred': True}, 'ready'),
        ({'summary_retryable': True}, 'failed'),
    ],
)
def test_projection_reuses_classifier_and_preserves_gist(monkeypatch, changes, step):
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'true')
    monkeypatch.setattr(home_read, 'user_zone_provider', lambda uid: lambda: 'UTC')
    row = {
        'id': 'conversation-1',
        'status': 'completed',
        'started_at': NOW,
        'finished_at': NOW,
        'structured': {'title': 'Workshop plans', 'overview': 'Reuse trays.\nKeep a clear path.'},
        **changes,
    }
    original = deepcopy(row)
    wire = home_read.project_episode('synthetic-user', episode(), members={'conversation-1': row})
    member = Episode.model_validate(wire).members[0]
    assert member.home_step == step
    assert member.overview == row['structured'].get('overview', '')
    assert member.title_provenance == row['structured'].get('title_provenance')
    assert row == original


def test_detail_endpoint_keeps_noise_that_home_omits_and_serializes_metadata(monkeypatch):
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'true')
    monkeypatch.setattr(routes, '_require', lambda uid, channel: None)
    monkeypatch.setattr(routes.service, 'episode_by_id', lambda uid, eid: episode())
    monkeypatch.setattr(home_read, 'user_zone_provider', lambda uid: lambda: 'UTC')
    row = {
        'status': 'completed',
        'started_at': NOW,
        'summary_blocked_reason': 'content_below_floor',
        'structured': {'title': 'A short clip', 'overview': 'A retained clip.'},
    }
    monkeypatch.setattr(home_read, '_read_members', lambda uid, episodes, **kw: {'conversation-1': row})
    monkeypatch.setattr(home_read, '_too_short_for_a_home_row', lambda row: True)
    assert home_read.project_episode('synthetic-user', episode(), list_row=True) is None
    app = FastAPI()
    app.include_router(routes.router)
    for route in app.routes:
        for dep in getattr(getattr(route, 'dependant', None), 'dependencies', []):
            app.dependency_overrides[dep.call] = lambda: 'synthetic-user'
    response = TestClient(app).get('/v1/episodes/episode-1')
    assert response.status_code == 200
    assert response.json()['members'][0]['home_step'] == 'noise'
    assert response.json()['members'][0]['overview'] == 'A retained clip.'


def test_projection_disabled_and_old_members_remain_decodable(monkeypatch):
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'false')
    monkeypatch.setattr(home_read, 'user_zone_provider', lambda uid: lambda: 'UTC')
    wire = home_read.project_episode(
        'synthetic-user',
        episode(),
        members={'conversation-1': {'status': 'completed', 'started_at': NOW, 'structured': {'title': 'Legacy title'}}},
    )
    member = Episode.model_validate(wire).members[0]
    assert member.home_step is None
    assert member.overview == ''
    assert (
        Episode.model_validate({**episode(), 'members': [{'id': 'old', 'started_at': NOW}]}).members[0].overview == ''
    )
