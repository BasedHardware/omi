"""GET and PATCH /v1/folders/{folder_id} must 404 a malformed folder doc, not 500.

Both routes returned the stored Firestore dict straight into `response_model=Folder`. A legacy
or malformed doc (missing `name` / `created_at`, or a required field stored as null) failed
response validation, so the client got HTTP 500. PATCH wrote to Firestore before that 500, so
the update landed on a folder the API could not return.

`GET /v1/folders` already skips such docs (`Folder.model_validate` + `ValidationError`). The
single-folder routes now apply the same check and answer 404 "Folder not found". PATCH makes it
on the folder as the update would leave it, before writing: an update that leaves the folder
malformed is rejected with no write, and one that supplies a valid value for the bad field still
repairs the folder and returns 200, as it did before.
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

# (stored doc, PATCH body) where the update leaves the folder malformed.
UNREPAIRED_PATCHES = {
    'other_field_on_null_name': (MALFORMED_FOLDERS['null_name'], {'description': 'new'}),
    'explicit_null_on_null_name': (MALFORMED_FOLDERS['null_name'], {'name': None}),
    'name_on_legacy_without_timestamps': (MALFORMED_FOLDERS['legacy_missing_name_and_timestamps'], {'name': 'Fixed'}),
}

# (damage to a valid stored doc, PATCH body that supplies a valid value for the damaged field).
REPAIRING_PATCHES = {
    'null_name': ({'name': None}, {'name': 'Fixed'}),
    'null_color': ({'color': None}, {'color': '#10B981'}),
    'null_order': ({'order': None}, {'order': 2}),
    'overlong_description': ({'description': 'x' * 501}, {'description': 'short'}),
}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(folders.router)
    app.dependency_overrides[folders.auth.get_current_user_uid] = lambda: 'uid'
    return TestClient(app, raise_server_exceptions=False)


def _fake_store(monkeypatch, doc):
    """Serve `doc` from folders_db and apply updates on top of it. Returns the stored versions."""
    versions = [dict(doc)]
    monkeypatch.setattr(folders.folders_db, 'get_folder', lambda uid, folder_id: dict(versions[-1]))
    monkeypatch.setattr(
        folders.folders_db, 'update_folder', lambda uid, folder_id, data: versions.append({**versions[-1], **data})
    )
    return versions


@pytest.mark.parametrize('doc', MALFORMED_FOLDERS.values(), ids=MALFORMED_FOLDERS.keys())
def test_get_malformed_folder_is_not_found(client, monkeypatch, doc):
    _fake_store(monkeypatch, doc)

    response = client.get('/v1/folders/f_bad')

    assert response.status_code == 404
    assert response.json() == {'detail': 'Folder not found'}


@pytest.mark.parametrize('doc, body', UNREPAIRED_PATCHES.values(), ids=UNREPAIRED_PATCHES.keys())
def test_patch_leaving_folder_malformed_is_not_found_and_not_written(client, monkeypatch, doc, body):
    versions = _fake_store(monkeypatch, doc)

    response = client.patch('/v1/folders/f_bad', json=body)

    assert response.status_code == 404
    assert response.json() == {'detail': 'Folder not found'}
    assert versions == [doc]


@pytest.mark.parametrize('damage, body', REPAIRING_PATCHES.values(), ids=REPAIRING_PATCHES.keys())
def test_patch_repairing_malformed_folder_is_saved(client, monkeypatch, damage, body):
    versions = _fake_store(monkeypatch, {**VALID_FOLDER, **damage})

    response = client.patch('/v1/folders/f_valid', json=body)

    assert response.status_code == 200
    assert {field: response.json()[field] for field in body} == body
    assert len(versions) == 2


def test_get_valid_folder_is_served(client, monkeypatch):
    _fake_store(monkeypatch, VALID_FOLDER)

    response = client.get('/v1/folders/f_valid')

    assert response.status_code == 200
    assert response.json()['name'] == 'Work'
