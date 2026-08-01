"""Private storage references and local paths for projection images."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from google.cloud.exceptions import NotFound as BlobNotFound

from utils.other import storage as gcs_storage


def uses_gcs() -> bool:
    """Return whether projection image storage is configured for GCS."""
    return projection_images_bucket_name() is not None


def projection_images_bucket_name() -> str | None:
    """Read the private projection bucket at the call boundary."""
    return (os.getenv('BUCKET_PROJECTION_IMAGES') or '').strip() or None


def _local_projection_root() -> Path:
    return Path(os.getenv('PROJECTION_LOCAL_IMAGE_DIR') or Path(tempfile.gettempdir()) / 'omi-projection-images')


def _local_owner_root(uid: str) -> Path:
    owner_scope = hashlib.sha256(uid.encode('utf-8')).hexdigest()
    return _local_projection_root() / owner_scope


def projection_image_path(uid: str, projection_id: str, attempt_token: str | None = None) -> str:
    """Return the owner-scoped object name persisted with a projection."""
    if attempt_token:
        return f'{uid}/{projection_id}/{attempt_token}.png'
    return f'{uid}/{projection_id}.png'


def validate_projection_image_path(uid: str, projection_id: str, persisted_path: object) -> str:
    """Validate one persisted object path against its owner and projection."""
    if not isinstance(persisted_path, str):
        raise ValueError('projection image path is missing')
    legacy_path = projection_image_path(uid, projection_id)
    if persisted_path == legacy_path:
        return persisted_path

    prefix = f'{uid}/{projection_id}/'
    if not persisted_path.startswith(prefix) or not persisted_path.endswith('.png'):
        raise ValueError('projection image path does not match its owner and projection')
    raw_attempt_token = persisted_path[len(prefix) : -4]
    try:
        parsed_attempt_token = uuid.UUID(raw_attempt_token)
    except ValueError as error:
        raise ValueError('projection image path has an invalid attempt token') from error
    if str(parsed_attempt_token) != raw_attempt_token:
        raise ValueError('projection image path has a non-canonical attempt token')
    return persisted_path


def local_projection_image_path(
    uid: str,
    projection_id: str,
    attempt_token: str | None = None,
    *,
    persisted_path: str | None = None,
) -> Path:
    """Return the private local file corresponding to a validated persisted path."""
    image_path = validate_projection_image_path(
        uid,
        projection_id,
        persisted_path or projection_image_path(uid, projection_id, attempt_token),
    )
    owner_root = _local_owner_root(uid)
    owner_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    relative_path = image_path.removeprefix(f'{uid}/')
    local_path = owner_root.joinpath(*relative_path.split('/'))
    local_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return local_path


def upload_projection_image(
    file_path: str,
    uid: str,
    projection_id: str,
    attempt_token: str | None = None,
) -> str:
    """Upload an owner-scoped image without granting a public object ACL."""
    bucket_name = projection_images_bucket_name()
    if not bucket_name:
        raise RuntimeError('Projection image storage is not configured')
    path = projection_image_path(uid, projection_id, attempt_token)
    blob = gcs_storage.get_storage_bucket(bucket_name).blob(path)
    blob.cache_control = 'private, no-store'
    blob.upload_from_filename(file_path)
    return path


def download_projection_image(uid: str, projection_id: str, persisted_path: object) -> bytes:
    """Download exactly the validated path persisted for this owner and projection."""
    bucket_name = projection_images_bucket_name()
    if not bucket_name:
        raise BlobNotFound('Projection image storage is not configured')
    image_path = validate_projection_image_path(uid, projection_id, persisted_path)
    return gcs_storage.download_blob_bytes(bucket_name, image_path)


def delete_all_projection_images(uid: str) -> int:
    """Delete every projection image for one account from the active storage backend."""
    if not uid:
        return 0

    bucket_name = projection_images_bucket_name()
    if bucket_name:
        bucket = gcs_storage.get_storage_bucket(bucket_name)
        deleted = 0
        for blob in bucket.list_blobs(prefix=f'{uid}/'):
            blob.delete()
            deleted += 1
        return deleted

    owner_root = _local_owner_root(uid)
    if not owner_root.exists():
        return 0
    deleted = sum(1 for path in owner_root.rglob('*') if path.is_file())
    shutil.rmtree(owner_root)
    return deleted
