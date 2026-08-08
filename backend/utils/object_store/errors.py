"""Neutral object-store errors (ADR-0032).

The port raises these regardless of backend so callers never catch a GCS ``NotFound`` or a botocore
``ClientError``. Adapters translate their backend's not-found into ``ObjectNotFound``.
"""

from __future__ import annotations


class ObjectStoreError(RuntimeError):
    """Base class for object-store failures surfaced through the port."""


class ObjectNotFound(ObjectStoreError):
    """Raised by read paths (get_bytes/download_to) when the object does not exist."""

    def __init__(self, bucket: str, key: str):
        self.bucket = bucket
        self.key = key
        super().__init__(f"object not found: {bucket}/{key}")


__all__ = ["ObjectStoreError", "ObjectNotFound"]
