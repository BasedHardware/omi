"""GET and PATCH /v1/folders/{folder_id} must 404 a malformed folder doc, not 500.

Both routes returned the stored Firestore dict straight into `response_model=Folder`. A legacy
or malformed doc (missing `name` / `created_at`, or a required field stored as null) failed
response validation, so the client got HTTP 500. PATCH wrote to Firestore before that 500, so
the update landed on a folder the API could not return.

`GET /v1/folders` already skips such docs (`Folder.model_validate` + `ValidationError`). The
single-folder routes now apply the same check and answer 404 "Folder not found", and PATCH makes
it before writing.
"""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.folders as folders

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)

VALID_FOLDER = {
    'id': 'f_valid',
    'name': 'Work',
    'color': '#3B82F6',
    'icon': 'folder',
    'created_at': NOW,
    'updated_at': NOW,
    'order': 0,
}

MALFORMED_FOLDERS = {
    'legacy_missing_name_and_timestamps': {'id': 'f_bad', 'description': 'legacy folder'},
    'null_name': {**VALID_FOLDER, 'id': 'f_bad', 'name': None},
}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(folders.router)
    app.dependency_overrides[folders.auth.get_current_user_uid] = lambda: 'uid'
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize('doc', MALFORMED_FOLDERS.values(), ids=MALFORMED_FOLDERS.keys())
def test_get_malformed_folder_is_not_found(client, monkeypatch, doc):
    monkeypatch.setattr(folders.folders_db, 'get_folder', lambda uid, folder_id: dict(doc))

    response = client.get('/v1/folders/f_bad')

    assert response.status_code == 404
    assert response.json() == {'detail': 'Folder not found'}


def test_patch_malformed_folder_is_not_found_and_not_written(client, monkeypatch):
    writes = []
    monkeypatch.setattr(folders.folders_db, 'get_folder', lambda uid, folder_id: dict(MALFORMED_FOLDERS['null_name']))
    monkeypatch.setattr(folders.folders_db, 'update_folder', lambda uid, folder_id, data: writes.append(data))

    response = client.patch('/v1/folders/f_bad', json={'description': 'new'})

    assert response.status_code == 404
    assert response.json() == {'detail': 'Folder not found'}
    assert writes == []


def test_get_valid_folder_is_served(client, monkeypatch):
    monkeypatch.setattr(folders.folders_db, 'get_folder', lambda uid, folder_id: dict(VALID_FOLDER))

    response = client.get('/v1/folders/f_valid')

    assert response.status_code == 200
    assert response.json()['name'] == 'Work'
