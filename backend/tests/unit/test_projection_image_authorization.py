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
    downloaded: list[tuple[str, str, object]] = []
    monkeypatch.setenv('BUCKET_PROJECTION_IMAGES', 'private-projections')
    monkeypatch.setattr(
        projections.projections_db,
        'get_projection',
        lambda uid, projection_id: (
            {'id': projection_id, 'image_path': f'{uid}/{projection_id}.png'} if uid == 'owner-a' else None
        ),
    )
    monkeypatch.setattr(
        projection_storage,
        'download_projection_image',
        lambda uid, projection_id, persisted_path: downloaded.append((uid, projection_id, persisted_path))
        or b'private-image',
    )

    response = _client_for('owner-b').get('/v1/projection-images/00000000-0000-0000-0000-000000000001.png')

    assert response.status_code == 404
    assert downloaded == []


def test_projection_image_serves_valid_owner_without_public_caching(monkeypatch):
    projection_id = '00000000-0000-0000-0000-000000000001'
    attempt_token = '00000000-0000-0000-0000-0000000000a1'
    persisted_path = f'owner-a/{projection_id}/{attempt_token}.png'
    monkeypatch.setenv('BUCKET_PROJECTION_IMAGES', 'private-projections')
    monkeypatch.setattr(
        projections.projections_db,
        'get_projection',
        lambda uid, requested_id: (
            {'id': requested_id, 'image_path': persisted_path}
            if (uid, requested_id) == ('owner-a', projection_id)
            else None
        ),
    )
    downloaded: list[tuple[str, str, object]] = []
    monkeypatch.setattr(
        projection_storage,
        'download_projection_image',
        lambda uid, requested_id, image_path: downloaded.append((uid, requested_id, image_path)) or b'\x89PNG-private',
    )

    response = _client_for('owner-a').get(f'/v1/projection-images/{projection_id}.png')

    assert response.status_code == 200
    assert response.content == b'\x89PNG-private'
    assert response.headers['content-type'] == 'image/png'
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert downloaded == [('owner-a', projection_id, persisted_path)]


def test_projection_image_rejects_a_persisted_path_outside_the_owner_projection(monkeypatch):
    projection_id = '00000000-0000-0000-0000-000000000001'
    monkeypatch.setenv('BUCKET_PROJECTION_IMAGES', 'private-projections')
    monkeypatch.setattr(
        projections.projections_db,
        'get_projection',
        lambda uid, requested_id: {
            'id': requested_id,
            'image_path': f'owner-b/{requested_id}/00000000-0000-0000-0000-0000000000a1.png',
        },
    )
    downloaded: list[str] = []
    monkeypatch.setattr(
        gcs_storage,
        'download_blob_bytes',
        lambda _bucket, path: downloaded.append(path) or b'private-image',
    )

    response = _client_for('owner-a').get(f'/v1/projection-images/{projection_id}.png')

    assert response.status_code == 404
    assert downloaded == []


def test_projection_image_requires_a_persisted_path(monkeypatch):
    projection_id = '00000000-0000-0000-0000-000000000001'
    monkeypatch.setenv('BUCKET_PROJECTION_IMAGES', 'private-projections')
    monkeypatch.setattr(
        projections.projections_db,
        'get_projection',
        lambda uid, requested_id: {'id': requested_id},
    )
    downloaded: list[str] = []
    monkeypatch.setattr(
        gcs_storage,
        'download_blob_bytes',
        lambda _bucket, path: downloaded.append(path) or b'private-image',
    )

    response = _client_for('owner-a').get(f'/v1/projection-images/{projection_id}.png')

    assert response.status_code == 404
    assert downloaded == []


class _Blob:
    def __init__(self, name: str):
        self.name = name
        self.cache_control: str | None = None
        self.uploaded_from: str | None = None
        self.deleted = False

    def upload_from_filename(self, file_path: str) -> None:
        self.uploaded_from = file_path

    def delete(self) -> None:
        self.deleted = True


class _Bucket:
    def __init__(self):
        self.created: list[_Blob] = []

    def blob(self, name: str) -> _Blob:
        blob = _Blob(name)
        self.created.append(blob)
        return blob

    def list_blobs(self, *, prefix: str):
        return [blob for blob in self.created if blob.name.startswith(prefix)]


def test_gcs_upload_is_owner_scoped_and_never_public(monkeypatch, tmp_path: Path):
    bucket = _Bucket()
    source = tmp_path / 'projection.png'
    source.write_bytes(b'png')
    attempt_token = '00000000-0000-0000-0000-0000000000a1'
    monkeypatch.setenv('BUCKET_PROJECTION_IMAGES', 'private-projections')
    monkeypatch.setattr(gcs_storage, 'get_storage_bucket', lambda _name: bucket)

    stored_path = projection_storage.upload_projection_image(
        str(source),
        'owner-a',
        'projection-1',
        attempt_token,
    )

    assert stored_path == f'owner-a/projection-1/{attempt_token}.png'
    assert len(bucket.created) == 1
    assert bucket.created[0].name == stored_path
    assert bucket.created[0].cache_control == 'private, no-store'
    assert bucket.created[0].uploaded_from == str(source)


def test_scheduled_attempts_never_share_an_image_path():
    first = projection_storage.projection_image_path(
        'owner-a',
        'projection-1',
        '00000000-0000-0000-0000-0000000000a1',
    )
    second = projection_storage.projection_image_path(
        'owner-a',
        'projection-1',
        '00000000-0000-0000-0000-0000000000b2',
    )

    assert first != second


def test_account_purge_deletes_only_the_owner_gcs_prefix(monkeypatch):
    bucket = _Bucket()
    owner_blobs = [
        bucket.blob('owner-a/projection-1/00000000-0000-0000-0000-0000000000a1.png'),
        bucket.blob('owner-a/projection-2/00000000-0000-0000-0000-0000000000b2.png'),
    ]
    other_blob = bucket.blob('owner-ab/projection-1/00000000-0000-0000-0000-0000000000c3.png')
    monkeypatch.setenv('BUCKET_PROJECTION_IMAGES', 'private-projections')
    monkeypatch.setattr(gcs_storage, 'get_storage_bucket', lambda _name: bucket)

    assert projection_storage.delete_all_projection_images('owner-a') == 2
    assert all(blob.deleted for blob in owner_blobs)
    assert other_blob.deleted is False


def test_local_storage_is_owner_scoped_and_private(monkeypatch, tmp_path: Path):
    monkeypatch.setenv('PROJECTION_LOCAL_IMAGE_DIR', str(tmp_path))
    monkeypatch.delenv('BUCKET_PROJECTION_IMAGES', raising=False)
    fallback_events: list[dict] = []
    monkeypatch.setattr(generation, 'record_fallback', lambda **kwargs: fallback_events.append(kwargs))

    stored_path = generation._store_image(b'owner-a-image', 'owner-a', 'projection-1')
    owner_a_path = generation.local_projection_image_path('owner-a', 'projection-1')
    owner_b_path = generation.local_projection_image_path('owner-b', 'projection-1')

    assert stored_path == 'owner-a/projection-1.png'
    assert owner_a_path.read_bytes() == b'owner-a-image'
    assert owner_a_path != owner_b_path
    assert owner_a_path.stat().st_mode & 0o777 == 0o600
    assert {key: fallback_events[0][key] for key in ('component', 'from_mode', 'to_mode', 'reason', 'outcome')} == {
        'component': 'projections',
        'from_mode': 'gcs',
        'to_mode': 'local_disk',
        'reason': 'config_incomplete',
        'outcome': 'degraded',
    }


def test_account_purge_removes_only_the_hashed_local_owner_directory(monkeypatch, tmp_path: Path):
    monkeypatch.setenv('PROJECTION_LOCAL_IMAGE_DIR', str(tmp_path))
    monkeypatch.delenv('BUCKET_PROJECTION_IMAGES', raising=False)
    owner_path = projection_storage.local_projection_image_path('owner-a', 'projection-1')
    other_path = projection_storage.local_projection_image_path('owner-b', 'projection-1')
    owner_path.write_bytes(b'owner-a')
    other_path.write_bytes(b'owner-b')

    assert projection_storage.delete_all_projection_images('owner-a') == 1
    assert owner_path.exists() is False
    assert other_path.read_bytes() == b'owner-b'
