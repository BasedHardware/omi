"""Projection images stay private across storage and HTTP delivery."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import projections
from utils.other import storage as gcs_storage
from utils.projections import generation
from utils.projections import storage as projection_storage


def _client_for(uid: str | None) -> TestClient:
    app = FastAPI()
    app.include_router(projections.router)
    if uid is not None:
        app.dependency_overrides[projections.auth.get_current_user_uid] = lambda: uid
    return TestClient(app)


def test_projection_image_rejects_unauthenticated_access(monkeypatch):
    looked_up: list[tuple[str, str]] = []
    monkeypatch.setattr(
        projections.projections_db,
        'get_projection',
        lambda uid, projection_id: looked_up.append((uid, projection_id)),
    )

    response = _client_for(None).get('/v1/projection-images/00000000-0000-0000-0000-000000000001.png')

    assert response.status_code == 401
    assert looked_up == []


def test_projection_image_does_not_cross_owner_boundary(monkeypatch):
    downloaded: list[tuple[str, str]] = []
    monkeypatch.setattr(gcs_storage, 'projection_images_bucket', 'private-projections')
    monkeypatch.setattr(
        projections.projections_db,
        'get_projection',
        lambda uid, projection_id: {'id': projection_id} if uid == 'owner-a' else None,
    )
    monkeypatch.setattr(
        projection_storage,
        'download_projection_image',
        lambda uid, projection_id: downloaded.append((uid, projection_id)) or b'private-image',
    )

    response = _client_for('owner-b').get('/v1/projection-images/00000000-0000-0000-0000-000000000001.png')

    assert response.status_code == 404
    assert downloaded == []


def test_projection_image_serves_valid_owner_without_public_caching(monkeypatch):
    projection_id = '00000000-0000-0000-0000-000000000001'
    monkeypatch.setattr(gcs_storage, 'projection_images_bucket', 'private-projections')
    monkeypatch.setattr(
        projections.projections_db,
        'get_projection',
        lambda uid, requested_id: {'id': requested_id} if (uid, requested_id) == ('owner-a', projection_id) else None,
    )
    monkeypatch.setattr(
        projection_storage,
        'download_projection_image',
        lambda uid, requested_id: b'\x89PNG-private',
    )

    response = _client_for('owner-a').get(f'/v1/projection-images/{projection_id}.png')

    assert response.status_code == 200
    assert response.content == b'\x89PNG-private'
    assert response.headers['content-type'] == 'image/png'
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'


class _Blob:
    def __init__(self, name: str):
        self.name = name
        self.cache_control: str | None = None
        self.uploaded_from: str | None = None

    def upload_from_filename(self, file_path: str) -> None:
        self.uploaded_from = file_path


class _Bucket:
    def __init__(self):
        self.created: list[_Blob] = []

    def blob(self, name: str) -> _Blob:
        blob = _Blob(name)
        self.created.append(blob)
        return blob


class _StorageClient:
    def __init__(self, bucket: _Bucket):
        self._bucket = bucket

    def bucket(self, _name: str) -> _Bucket:
        return self._bucket


def test_gcs_upload_is_owner_scoped_and_never_public(monkeypatch, tmp_path: Path):
    bucket = _Bucket()
    source = tmp_path / 'projection.png'
    source.write_bytes(b'png')
    monkeypatch.setattr(gcs_storage, 'projection_images_bucket', 'private-projections')
    monkeypatch.setattr(gcs_storage, 'get_storage_client', lambda: _StorageClient(bucket))

    stored_path = projection_storage.upload_projection_image(str(source), 'owner-a', 'projection-1')

    assert stored_path == 'owner-a/projection-1.png'
    assert len(bucket.created) == 1
    assert bucket.created[0].name == stored_path
    assert bucket.created[0].cache_control == 'private, no-store'
    assert bucket.created[0].uploaded_from == str(source)


def test_local_storage_is_owner_scoped_and_private(monkeypatch, tmp_path: Path):
    monkeypatch.setenv('PROJECTION_LOCAL_IMAGE_DIR', str(tmp_path))
    monkeypatch.setattr(gcs_storage, 'projection_images_bucket', None)
    monkeypatch.setattr(generation, 'record_fallback', lambda **_kwargs: None)

    stored_path = generation._store_image(b'owner-a-image', 'owner-a', 'projection-1')
    owner_a_path = generation.local_projection_image_path('owner-a', 'projection-1')
    owner_b_path = generation.local_projection_image_path('owner-b', 'projection-1')

    assert stored_path == 'owner-a/projection-1.png'
    assert owner_a_path.read_bytes() == b'owner-a-image'
    assert owner_a_path != owner_b_path
    assert owner_a_path.stat().st_mode & 0o777 == 0o600
