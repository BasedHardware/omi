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

from utils.object_store.errors import ObjectNotFound
from utils.other import storage as _storage
from utils.other.storage import owner_storage_write_gate


def _object_store():
    """The active object store, read through ``utils.other.storage`` rather than bound by import.

    One seam, one patch point: ``owner_storage_write_gate`` decides whether to fence by asking
    ``utils.other.storage._object_store()`` what is active. If this module bound that function at
    import time, a test that injects a fake there would move the writes but not the gate, and the
    fence would try to reach a real provider from a hermetic test.
    """

    return _storage._object_store()

TEMPORARY_STORAGE_PREFIX = "temporary-"
PERMANENT_STORAGE_PREFIX = "permanent-"


def _bucket(*, permanent: bool) -> str:
    # Temporary and conversation-lifetime objects deliberately use different
    # buckets. The temporary bucket is lifecycle-backed; the permanent bucket
    # must have no object-expiration rule.
    #
    # Returns the bucket NAME: every access below goes through the object-store port (ADR-0032), so
    # these two tiers work on GCS or on any S3-compatible backend a self-host configures.
    env_name = "BUCKET_FRAME_REQUESTS" if permanent else "BUCKET_FRAME_REQUESTS_TEMPORARY"
    bucket_name = (os.getenv(env_name) or "").strip()
    if not bucket_name:
        raise RuntimeError(f"{env_name} is not configured")
    return bucket_name


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
    bucket = _bucket(permanent=False)
    with owner_storage_write_gate(uid):
        _object_store().put(bucket, _object_name(uid, storage_id), data, content_type=content_type)


def delete_frame_request_pixels(uid: str, storage_id: str) -> None:
    try:
        _object_store().delete(_bucket(permanent=_is_permanent(storage_id)), _object_name(uid, storage_id))
    except ObjectNotFound:
        # A missing object is safe during an idempotent cleanup, while all other
        # errors remain visible to the deletion fence. Upstream matched the GCS
        # exception by class NAME because it had one backend; the port raises one
        # neutral type, so the intent survives a change of backend.
        return


def download_frame_request_pixels(uid: str, storage_id: str) -> bytes:
    """Read owner-authorized pixels from their declared storage tier."""

    return bytes(
        _object_store().get_bytes(_bucket(permanent=_is_permanent(storage_id)), _object_name(uid, storage_id))
    )


def copy_frame_request_pixels_to_permanent(uid: str, temporary_storage_id: str, permanent_storage_id: str) -> None:
    """Idempotently copy one temporary object into conversation-lifetime storage."""

    if not permanent_storage_id.startswith(PERMANENT_STORAGE_PREFIX):
        raise ValueError("promotion destination must be permanent")
    source_bucket = _bucket(permanent=_is_permanent(temporary_storage_id))
    destination_bucket = _bucket(permanent=True)
    with owner_storage_write_gate(uid):
        _object_store().copy(
            source_bucket,
            _object_name(uid, temporary_storage_id),
            destination_bucket,
            _object_name(uid, permanent_storage_id),
        )


def delete_frame_request_pixels_for_user(uid: str, storage_ids: list[str]) -> int:
    deleted = 0
    for storage_id in storage_ids:
        delete_frame_request_pixels(uid, storage_id)
        deleted += 1
    return deleted


def delete_all_frame_request_pixels_for_user(uid: str) -> int:
    """Enumerate both frame-request tiers so orphaned IDs cannot survive a wipe."""

    if not uid:
        return 0
    deleted = 0
    for permanent in (False, True):
        env_name = "BUCKET_FRAME_REQUESTS" if permanent else "BUCKET_FRAME_REQUESTS_TEMPORARY"
        if not (os.getenv(env_name) or '').strip():
            # A tier that is not configured cannot contain uploads from this
            # deployment; preserve the existing local/offline no-op behavior.
            continue
        bucket = _bucket(permanent=permanent)
        prefix = f'frame-requests/{uid}/'
        store = _object_store()
        for info in store.list(bucket, prefix):
            store.delete(bucket, info.key)
            deleted += 1
        remaining = store.list(bucket, prefix)
        if remaining:
            raise RuntimeError(f'frame-request purge left {len(remaining)} objects under {prefix}')
    return deleted


__all__ = [
    "delete_frame_request_pixels",
    "delete_frame_request_pixels_for_user",
    "delete_all_frame_request_pixels_for_user",
    "download_frame_request_pixels",
    "copy_frame_request_pixels_to_permanent",
    "PERMANENT_STORAGE_PREFIX",
    "TEMPORARY_STORAGE_PREFIX",
    "upload_frame_request_pixels",
]
