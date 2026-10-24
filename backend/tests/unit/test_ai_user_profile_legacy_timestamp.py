"""The AI profile routes must serve a profile whose `generated_at` is a Firestore Timestamp, not 500.

The retired Rust desktop backend stored `users/{uid}.ai_user_profile.generated_at` as a
Firestore Timestamp (`timestampValue`); the Python PATCH route stores the client's ISO-8601
string. `AIUserProfileResponse.generated_at` is typed `Optional[str]`, so a profile last
written by the Rust backend reads back as a `datetime` and failed response validation
(HTTP 500): on every GET /v1/users/ai-profile, and on a PATCH that leaves `generated_at`
alone, after the write had landed.

The response model now serves such a Timestamp as its ISO-8601 string.
"""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.datetime_helpers import DatetimeWithNanoseconds

import database.users as users_db
from routers import users as users_router
from utils.other import endpoints as auth

RUST_GENERATED_AT = DatetimeWithNanoseconds(2026, 3, 1, 8, 15, 30, 123456, tzinfo=timezone.utc)


class _UserDoc:
    """`users/{uid}` as the Firestore client hands it back, recording writes."""

    def __init__(self, data):
        self.data = data
        self.exists = True
        self.updates = []

    def collection(self, _name):
        return self

    def document(self, _uid):
        return self

    def get(self, *_args, **_kwargs):
        return self

    def to_dict(self):
        return dict(self.data)

    def update(self, payload):
        self.updates.append(payload)


def _profile_doc(generated_at):
    return _UserDoc(
        {'ai_user_profile': {'profile_text': 'Enjoys hiking', 'generated_at': generated_at, 'data_sources_used': 42}}
    )


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(users_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'uid-1'
    return TestClient(app, raise_server_exceptions=False)


def test_get_serves_a_rust_era_timestamp_as_an_iso_string(client, monkeypatch):
    monkeypatch.setattr(users_db, 'db', _profile_doc(RUST_GENERATED_AT))

    response = client.get('/v1/users/ai-profile')

    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body['generated_at']) == RUST_GENERATED_AT
    assert body['profile_text'] == 'Enjoys hiking'
    assert body['data_sources_used'] == 42


def test_patch_that_keeps_a_rust_era_timestamp_returns_the_profile(client, monkeypatch):
    doc = _profile_doc(RUST_GENERATED_AT)
    monkeypatch.setattr(users_db, 'db', doc)

    response = client.patch('/v1/users/ai-profile', json={'profile_text': 'Enjoys climbing'})

    assert response.status_code == 200
    assert response.json()['profile_text'] == 'Enjoys climbing'
    assert datetime.fromisoformat(response.json()['generated_at']) == RUST_GENERATED_AT
    assert doc.updates[0]['ai_user_profile']['profile_text'] == 'Enjoys climbing'


def test_an_iso_string_generated_at_is_served_unchanged(client, monkeypatch):
    monkeypatch.setattr(users_db, 'db', _profile_doc('2026-03-01T08:15:30.123Z'))

    response = client.get('/v1/users/ai-profile')

    assert response.status_code == 200
    assert response.json()['generated_at'] == '2026-03-01T08:15:30.123Z'
