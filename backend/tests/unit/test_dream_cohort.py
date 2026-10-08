"""Exercise the production release-channel route locally with synthetic auth."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import dream_cohort


def test_authenticated_channel_contract_and_store_exit(monkeypatch):
    writes = []
    database = SimpleNamespace(
        collection=lambda name: SimpleNamespace(
            document=lambda uid: SimpleNamespace(set=lambda data, **kw: writes.append((name, uid, data)))
        )
    )
    monkeypatch.setattr(dream_cohort, 'get_firestore_client', lambda: database)
    app = FastAPI()
    app.include_router(dream_cohort.router)
    app.dependency_overrides[dream_cohort.auth.get_current_user_uid] = lambda: 'synthetic-authed-user'
    client = TestClient(app)
    monkeypatch.setenv('DREAM_AGENT_MODE', 'off')
    assert client.put('/v1/users/release-channel', json={'release_channel': 'testflight'}).status_code == 404
    assert not writes
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    for channel in ('testflight', 'app_store', 'dev'):
        response = client.put('/v1/users/release-channel', json={'release_channel': channel, 'app_build': 300})
        assert response.status_code == 204
        assert writes[-1] == (
            'users',
            'synthetic-authed-user',
            {'dream_release_channel': channel, 'dream_app_build': 300},
        )
    response = client.put('/v1/users/release-channel', json={'release_channel': 'testflight'})
    assert response.status_code == 204
    assert writes[-1] == (
        'users',
        'synthetic-authed-user',
        {'dream_release_channel': 'testflight', 'dream_app_build': None},
    )
    assert client.put('/v1/users/release-channel', json={'release_channel': 'production'}).status_code == 422
    assert len(writes) == 4


def test_plain_testflight_assertion_without_qualifying_build_cannot_enroll(monkeypatch):
    from config.dream_agent import eligible

    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_TESTFLIGHT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', '')
    monkeypatch.delenv('DREAM_AGENT_TESTFLIGHT_MIN_BUILD', raising=False)
    writes = []
    database = SimpleNamespace(
        collection=lambda name: SimpleNamespace(
            document=lambda uid: SimpleNamespace(set=lambda data, **kw: writes.append((name, uid, data)))
        )
    )
    monkeypatch.setattr(dream_cohort, 'get_firestore_client', lambda: database)
    app = FastAPI()
    app.include_router(dream_cohort.router)
    app.dependency_overrides[dream_cohort.auth.get_current_user_uid] = lambda: 'synthetic-authed-user'
    client = TestClient(app)
    response = client.put('/v1/users/release-channel', json={'release_channel': 'testflight'})
    assert response.status_code == 204
    user = writes[-1][2]
    assert not eligible('synthetic-authed-user', user)
    monkeypatch.setenv('DREAM_AGENT_TESTFLIGHT_MIN_BUILD', '300')
    assert not eligible('synthetic-authed-user', user)
