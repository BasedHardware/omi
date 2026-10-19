"""A custom vocabulary over the 100-term limit is refused, not cut short and reported as saved."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import users


@pytest.fixture
def endpoint(monkeypatch):
    saved = []
    monkeypatch.setattr(users, 'set_user_transcription_preferences', lambda uid, **prefs: saved.append((uid, prefs)))
    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[users.auth.get_current_user_uid] = lambda: 'user-1'
    return TestClient(app), saved


def test_vocabulary_over_the_limit_is_refused_and_nothing_is_saved(endpoint):
    client, saved = endpoint

    response = client.patch(
        '/v1/users/transcription-preferences',
        json={'single_language_mode': True, 'vocabulary': [f'term{i}' for i in range(101)]},
    )

    # The apps keep the list they sent when the answer is ok, so an ok here made term 101 look saved.
    assert response.status_code == 400
    assert response.json() == {'detail': 'Custom vocabulary is limited to 100 terms'}
    assert saved == []


def test_vocabulary_at_the_limit_is_saved_whole(endpoint):
    client, saved = endpoint
    terms = [f'term{i}' for i in range(100)]

    response = client.patch('/v1/users/transcription-preferences', json={'vocabulary': terms})

    assert response.status_code == 200
    # UserStatusResponse also serializes its optional message (None) for released clients.
    assert response.json()['status'] == 'ok'
    assert saved == [('user-1', {'single_language_mode': None, 'vocabulary': terms})]
