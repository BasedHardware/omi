# pyright: reportPrivateUsage=false
"""Owner-scoped pixel storage for frame-request evidence.

The queue database stores only this opaque storage id.  Objects are never
addressed by a caller-provided path and are removed at both conversation and
account deletion boundaries.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from utils.other.storage import _get_storage_client

TEMPORARY_STORAGE_PREFIX = "temporary-"
PERMANENT_STORAGE_PREFIX = "permanent-"


def _bucket(*, permanent: bool) -> Any:
    # Temporary and conversation-lifetime objects deliberately use different
    # buckets. The temporary bucket is lifecycle-backed; the permanent bucket
    # must have no object-expiration rule.
    env_name = "BUCKET_FRAME_REQUESTS" if permanent else "BUCKET_FRAME_REQUESTS_TEMPORARY"
    bucket_name = (os.getenv(env_name) or "").strip()
    if not bucket_name:
        raise RuntimeError(f"{env_name} is not configured")
    return _get_storage_client().bucket(bucket_name)


def _is_permanent(storage_id: str) -> bool:
    if storage_id.startswith(PERMANENT_STORAGE_PREFIX):
        return True
    if storage_id.startswith(TEMPORARY_STORAGE_PREFIX):
        return False
    # Existing objects created before the split lived in the permanent binding.
    return True


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
    if not storage_id.startswith(TEMPORARY_STORAGE_PREFIX):
        raise ValueError("new frame uploads must use temporary storage")
    blob = _bucket(permanent=False).blob(_object_name(uid, storage_id))
    blob.upload_from_string(data, content_type=content_type)


def delete_frame_request_pixels(uid: str, storage_id: str) -> None:
    try:
        _bucket(permanent=_is_permanent(storage_id)).blob(_object_name(uid, storage_id)).delete()
    except Exception as exc:
        # GCS NotFound is safe during an idempotent cleanup, while all other
        # errors remain visible to the deletion fence.
        if exc.__class__.__name__ in {"NotFound", "NotFoundError"}:
            return
        raise


def download_frame_request_pixels(uid: str, storage_id: str) -> bytes:
    """Read owner-authorized pixels from their declared storage tier."""

    return bytes(_bucket(permanent=_is_permanent(storage_id)).blob(_object_name(uid, storage_id)).download_as_bytes())


def copy_frame_request_pixels_to_permanent(uid: str, temporary_storage_id: str, permanent_storage_id: str) -> None:
    """Idempotently copy one temporary object into conversation-lifetime storage."""

    if not permanent_storage_id.startswith(PERMANENT_STORAGE_PREFIX):
        raise ValueError("promotion destination must be permanent")
    source_bucket = _bucket(permanent=_is_permanent(temporary_storage_id))
    destination_bucket = _bucket(permanent=True)
    source = source_bucket.blob(_object_name(uid, temporary_storage_id))
    source_bucket.copy_blob(source, destination_bucket, new_name=_object_name(uid, permanent_storage_id))


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
    "copy_frame_request_pixels_to_permanent",
    "PERMANENT_STORAGE_PREFIX",
    "TEMPORARY_STORAGE_PREFIX",
    "upload_frame_request_pixels",
]
