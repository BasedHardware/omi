from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import NotFound

from routers import users as users_router

PATH = '/v1/users/pendant-stop-feedback'
PAYLOAD = {'reason': 'charging_is_a_hassle', 'details': '  I forget the cable.  ', 'days_without_connection': 4}


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(users_router.router)
    return app


@pytest.fixture
def document(app, monkeypatch):
    app.dependency_overrides[users_router.auth.get_current_user_uid] = lambda: 'authenticated-user'
    firestore = MagicMock()
    monkeypatch.setattr(users_router.users_db, 'db', firestore)
    return firestore.collection.return_value.document.return_value, firestore


def test_requires_authentication(app):
    assert TestClient(app).post(PATH, json=PAYLOAD).status_code == 401


def test_writes_note_only_to_authenticated_users_existing_profile(app, document):
    user, firestore = document
    response = TestClient(app).post(PATH, json=PAYLOAD)
    assert response.status_code == 204
    assert response.content == b''
    firestore.collection.assert_called_once_with('users')
    firestore.collection.return_value.document.assert_called_once_with('authenticated-user')
    user.update.assert_called_once()
    assert not user.set.called
    note = user.update.call_args.args[0]['pendant_stop_feedback']
    assert note['timestamp'].utcoffset() == timedelta(0)
    assert note == {**PAYLOAD, 'details': 'I forget the cable.', 'timestamp': note['timestamp']}


@pytest.mark.parametrize(
    'invalid',
    [
        {'reason': 'unknown'},
        {'details': '   '},
        {'details': 'x' * 4001},
        {'days_without_connection': 2},
        {'days_without_connection': '4'},
        {'uid': 'another-user'},
    ],
)
def test_rejects_invalid_notes_without_writing(app, document, invalid):
    user, _ = document
    assert TestClient(app).post(PATH, json={**PAYLOAD, **invalid}).status_code == 422
    user.update.assert_not_called()


def test_does_not_recreate_missing_profile(app, document):
    user, _ = document
    user.update.side_effect = NotFound('missing')
    assert TestClient(app).post(PATH, json=PAYLOAD).status_code == 404
    user.set.assert_not_called()
