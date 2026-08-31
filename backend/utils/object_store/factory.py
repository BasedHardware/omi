"""Object-store backend selection (ADR-0032).

``get_object_store()`` returns the active adapter singleton, chosen by ``OBJECT_STORE_BACKEND``
(default ``gcs``). Adapters are imported lazily so a deployment only needs the SDK for its backend
(``google-cloud-storage`` for gcs, ``boto3`` for s3). GCS stays the first-class default.
"""

from __future__ import annotations

import os
import threading
from typing import Optional

from utils.object_store.ports import ObjectStore

_lock = threading.Lock()
_instance: Optional[ObjectStore] = None


def _build(backend: str) -> ObjectStore:
    if backend == "gcs":
        from utils.object_store.adapters.gcs import GCSObjectStore

        return GCSObjectStore()
    if backend == "s3":
        from utils.object_store.adapters.s3 import S3ObjectStore

        return S3ObjectStore()
    raise ValueError(f"unsupported OBJECT_STORE_BACKEND={backend!r} (expected 'gcs' or 's3')")


def get_object_store() -> ObjectStore:
    """Return the process-wide object-store adapter for the configured backend."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                # ``or "gcs"`` (not getenv's default arg) so an empty/whitespace value falls back to
                # the documented GCS default too, matching the store and vector factories (ADR-0032).
                _instance = _build((os.getenv("OBJECT_STORE_BACKEND") or "gcs").strip().lower() or "gcs")
    return _instance


def reset_object_store_for_tests() -> None:
    """Drop the cached singleton (tests that swap OBJECT_STORE_BACKEND / inject a fake)."""
    global _instance
    with _lock:
        _instance = None


__all__ = ["get_object_store", "reset_object_store_for_tests"]
