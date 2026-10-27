"""Exercise Scheduler admission and the real bounded shadow worker offline."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import dream_store
from routers import dream_sweep
from utils import cloud_tasks, dream_agent

UID = 'synthetic-owner'
AUDIENCE = 'https://synthetic-sync.example/v2/sync-jobs/run'
INVOKER = 'synthetic-scheduler@example.iam.gserviceaccount.com'
ROOT = Path(__file__).resolve().parents[3]


def load_yaml(path):
    return yaml.load(path.read_text(), Loader=yaml.CSafeLoader)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', AUDIENCE)
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', INVOKER)
    monkeypatch.setattr(cloud_tasks, '_get_auth_request', lambda: object())
    app = FastAPI()
    app.include_router(dream_sweep.router)
    return TestClient(app)


@pytest.mark.parametrize('token', [None, 'wrong-audience', 'wrong-identity', 'unverified'])
def test_oidc_rejection_never_reaches_drain(client, monkeypatch, token):
    def verify(value, request, *, audience):
        assert audience == AUDIENCE
        if value == 'wrong-audience':
            raise ValueError('invalid audience')
        return {'email': INVOKER if value != 'wrong-identity' else 'other', 'email_verified': value != 'unverified'}

    monkeypatch.setattr(cloud_tasks.id_token, 'verify_oauth2_token', verify)
    drain = AsyncMock()
    monkeypatch.setattr(dream_agent, 'drain', drain)
    headers = {} if token is None else {'Authorization': 'Bearer ' + token}
    assert client.post('/v2/dream-agent/sweep', headers=headers).status_code == 403
    drain.assert_not_called()


def test_authenticated_off_is_cheap_noop(client, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false')
    monkeypatch.setattr(
        cloud_tasks.id_token,
        'verify_oauth2_token',
        lambda *a, **k: {
            'email': INVOKER,
            'email_verified': True,
        },
    )
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: pytest.fail('off read Firestore'))
    monkeypatch.setattr(dream_agent, 'retry_sweep', AsyncMock())
    monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: pytest.fail('off attempted admission'))
    response = client.post('/v2/dream-agent/sweep', headers={'Authorization': 'Bearer valid'})
    assert response.status_code == 200
    assert response.json() == {'complete': 0, 'failed': 0, 'not_admitted': 0, 'deadline': 0, 'waiting': 0}


def test_route_returns_counts_only(client, monkeypatch, caplog):
    monkeypatch.setattr(
        cloud_tasks.id_token,
        'verify_oauth2_token',
        lambda *a, **k: {
            'email': INVOKER,
            'email_verified': True,
        },
    )
    monkeypatch.setattr(
        dream_agent,
        'drain',
        AsyncMock(
            return_value=[
                {'status': 'complete', 'proposed': {'private': 'synthetic private content'}, 'run_id': UID},
                {'status': 'failed', 'error_type': 'synthetic'},
                {'status': 'not_admitted'},
                {'status': 'deadline'},
            ]
        ),
    )
    with caplog.at_level('INFO', logger='routers.dream_sweep'):
        response = client.post('/v2/dream-agent/sweep', headers={'Authorization': 'Bearer valid'})
    assert response.json() == {'complete': 1, 'failed': 1, 'not_admitted': 1, 'deadline': 1, 'waiting': 0}
    assert UID not in response.text and 'private' not in response.text
    logged = caplog.text
    assert 'candidates=4 complete=1 failed=1 not_admitted=1 deadline=1 waiting=0 failure_types=synthetic:1' in logged
    assert UID not in logged and 'private' not in logged
