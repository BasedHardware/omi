"""Neutral object-storage port (ADR-0007/0032).

The domain speaks (logical bucket, object key) + bytes/streams + neutral metadata — never a GCS
``Blob`` or an S3 object. Adapters map the contract onto Google Cloud Storage (reference) or any
S3-compatible backend (RustFS/MinIO/SeaweedFS/Ceph/AWS). Selected by ``OBJECT_STORE_BACKEND`` via
``factory.get_object_store()``.

Only object operations live here — no lifecycle/CORS (those are backend provisioning, ADR-0032 §5).
Every write goes through the backend; there are no client-side presigned uploads, so ``presign_get``
is the only URL-signing primitive (all signed URLs in use are GET).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import IO, Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class ObjectInfo:
    """Neutral listing/stat record — the backend-agnostic shape of one stored object."""

    key: str
    size: int
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ObjectStore(Protocol):
    """The neutral object-storage contract. ``bucket`` is a logical name (each adapter maps it to a
    configured real bucket); ``key`` is the object path within it."""

    # --- writes ---
    def put(
        self,
        bucket: str,
        key: str,
        data: bytes | IO[bytes],
        *,
        content_type: Optional[str] = None,
        cache_control: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        public: bool = False,
    ) -> None:
        """``metadata`` is written atomically with the object (GCS blob.metadata / S3 Metadata=)."""
        ...

    def put_from_file(
        self,
        bucket: str,
        key: str,
        src_path: str,
        *,
        content_type: Optional[str] = None,
        cache_control: Optional[str] = None,
        public: bool = False,
    ) -> None:
        """``public=True`` makes the object world-readable (GCS make_public / S3 public-read) so
        ``public_url`` resolves without a signature — the logo/thumbnail/chat flow (ADR-0032 §4).
        When the bucket already grants public read (uniform access), leave ``public=False`` and rely
        on ``public_url``; ``cache_control`` sets the served Cache-Control header."""
        ...

    def open_write(self, bucket: str, key: str, *, content_type: Optional[str] = None) -> IO[bytes]:
        """Streaming writer context manager (replaces ``blob.open('wb')``); S3 maps to multipart."""
        ...

    # --- reads (get_bytes/download_to raise errors.ObjectNotFound on a missing key) ---
    def get_bytes(self, bucket: str, key: str) -> bytes: ...

    def download_to(self, bucket: str, key: str, dst_path: str) -> None: ...

    def exists(self, bucket: str, key: str) -> bool: ...

    def list(self, bucket: str, prefix: str) -> List[ObjectInfo]: ...

    # --- mutations ---
    def delete(self, bucket: str, key: str) -> bool: ...

    def copy(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> None: ...

    # --- metadata (S3 metadata is immutable post-write; the adapter re-puts/copies) ---
    def get_metadata(self, bucket: str, key: str) -> Optional[Dict[str, Any]]: ...

    def set_metadata(self, bucket: str, key: str, metadata: Dict[str, Any]) -> None: ...

    # --- URLs ---
    def presign_get(self, bucket: str, key: str, *, expires_seconds: int) -> str:
        """Server-minted download URL. GCS V4 / S3 SigV4 — the sole signing primitive (all GET)."""
        ...

    def public_url(self, bucket: str, key: str) -> str:
        """Backend-neutral public URL for a public object (logos/thumbnails/chat). Derived from the
        configured endpoint — never a hard-wired storage.googleapis.com string (ADR-0032 §4)."""
        ...


__all__ = ["ObjectInfo", "ObjectStore"]
