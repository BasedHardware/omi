"""Owner-scoped pixel storage for frame-request evidence.

The queue database stores only this opaque storage id.  Objects are never
addressed by a caller-provided path and are removed at both conversation and
account deletion boundaries.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from utils.other.storage import _get_storage_client, private_cloud_sync_bucket


def _bucket() -> Any:
    bucket_name = (os.getenv("BUCKET_FRAME_REQUESTS") or private_cloud_sync_bucket).strip()
    if not bucket_name:
        raise RuntimeError("frame-request storage bucket is not configured")
    return _get_storage_client().bucket(bucket_name)


def _object_name(uid: str, storage_id: str) -> str:
    owner = uid.strip()
    identifier = storage_id.strip()
    if not owner or "/" in owner or "\\" in owner or not identifier or "/" in identifier or "\\" in identifier:
        raise ValueError("invalid frame-request storage identity")
    # Keep the object path opaque even if a future caller accidentally passes
    # an identifier with punctuation that a storage backend interprets.
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"frame-requests/{owner}/{digest}"


def upload_frame_request_pixels(uid: str, storage_id: str, data: bytes, content_type: str) -> None:
    if not data:
        raise ValueError("frame upload is empty")
    blob = _bucket().blob(_object_name(uid, storage_id))
    blob.upload_from_string(data, content_type=content_type)


def delete_frame_request_pixels(uid: str, storage_id: str) -> None:
    try:
        _bucket().blob(_object_name(uid, storage_id)).delete()
    except Exception as exc:
        # GCS NotFound is safe during an idempotent cleanup, while all other
        # errors remain visible to the deletion fence.
        if exc.__class__.__name__ in {"NotFound", "NotFoundError"}:
            return
        raise


def download_frame_request_pixels(uid: str, storage_id: str) -> bytes:
    """Read conversation-attached pixels only after owner authorization."""

    return bytes(_bucket().blob(_object_name(uid, storage_id)).download_as_bytes())


def delete_frame_request_pixels_for_user(uid: str, storage_ids: list[str]) -> int:
    deleted = 0
    for storage_id in storage_ids:
        delete_frame_request_pixels(uid, storage_id)
        deleted += 1
    return deleted


__all__ = [
    "delete_frame_request_pixels",
    "delete_frame_request_pixels_for_user",
    "download_frame_request_pixels",
    "upload_frame_request_pixels",
]
