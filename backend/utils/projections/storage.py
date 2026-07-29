"""Private storage references and local paths for projection images."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from google.cloud.exceptions import NotFound as BlobNotFound

from utils.other import storage as gcs_storage


def uses_gcs() -> bool:
    """Return whether projection image storage is configured for GCS."""
    return bool(gcs_storage.projection_images_bucket)


def projection_image_path(uid: str, projection_id: str) -> str:
    """Return the owner-scoped object name persisted with a projection."""
    return f'{uid}/{projection_id}.png'


def local_projection_image_path(uid: str, projection_id: str) -> Path:
    """Return the owner-scoped path used when no GCS bucket is configured."""
    root = Path(os.getenv('PROJECTION_LOCAL_IMAGE_DIR') or Path(tempfile.gettempdir()) / 'omi-projection-images')
    owner_scope = hashlib.sha256(uid.encode('utf-8')).hexdigest()
    owner_root = root / owner_scope
    owner_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return owner_root / f'{projection_id}.png'


def upload_projection_image(file_path: str, uid: str, projection_id: str) -> str:
    """Upload an owner-scoped image without granting a public object ACL."""
    bucket_name = gcs_storage.projection_images_bucket
    if not bucket_name:
        raise RuntimeError('Projection image storage is not configured')
    path = projection_image_path(uid, projection_id)
    blob = gcs_storage.get_storage_client().bucket(bucket_name).blob(path)
    blob.cache_control = 'private, no-store'
    blob.upload_from_filename(file_path)
    return path


def download_projection_image(uid: str, projection_id: str) -> bytes:
    """Download an owner-scoped image from the private projection bucket."""
    bucket_name = gcs_storage.projection_images_bucket
    if not bucket_name:
        raise BlobNotFound('Projection image storage is not configured')
    return gcs_storage.download_blob_bytes(bucket_name, projection_image_path(uid, projection_id))
