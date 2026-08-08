"""Google Cloud Storage adapter — the reference implementation of the object-store port (ADR-0032).

Encapsulates exactly the GCS logic that lived inline in ``utils/other/storage.py``: lazy client,
``blob.*`` ops, V4 signed URLs, ``make_public``. It is the contract of record; its behavior is what
the S3 adapter must match (dual-backend contract test). Redis caching of signed URLs stays in the
caller (``storage._signed_url``), not here — the adapter only mints.
"""

from __future__ import annotations

import datetime
import json
import os
import threading
from typing import IO, Any, Dict, List, Optional

from utils.object_store.errors import ObjectNotFound
from utils.object_store.ports import ObjectInfo

_client_lock = threading.Lock()
_client: Any = None


def _storage_client() -> Any:
    """Lazy GCS client (never probes ADC/GCE metadata at import), identical to the previous inline seam."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from google.cloud import storage  # lazy: only the gcs backend needs this SDK

                if os.environ.get("SERVICE_ACCOUNT_JSON"):
                    from google.oauth2 import service_account

                    info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
                    creds = service_account.Credentials.from_service_account_info(info)
                    _client = storage.Client(credentials=creds)
                else:
                    project = (
                        os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("FIREBASE_PROJECT_ID") or ""
                    ).strip()
                    _client = storage.Client(project=project) if project else storage.Client()
    return _client


class GCSObjectStore:
    """ObjectStore over Google Cloud Storage. ``bucket`` is the real GCS bucket name; ``key`` the blob path."""

    def _blob(self, bucket: str, key: str) -> Any:
        return _storage_client().bucket(bucket).blob(key)

    def _make_public(self, blob: Any) -> None:
        try:
            blob.make_public()
        except Exception:  # bucket-level IAM may already grant public read; best-effort as before
            pass

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
        blob = self._blob(bucket, key)
        if cache_control is not None:
            blob.cache_control = cache_control
        if metadata is not None:
            blob.metadata = dict(metadata)
        if isinstance(data, (bytes, bytearray)):
            blob.upload_from_string(bytes(data), content_type=content_type)
        else:
            blob.upload_from_file(data, content_type=content_type)
        if public:
            self._make_public(blob)

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
        blob = self._blob(bucket, key)
        if cache_control is not None:
            blob.cache_control = cache_control
        blob.upload_from_filename(src_path, content_type=content_type)
        if public:
            self._make_public(blob)

    def open_write(self, bucket: str, key: str, *, content_type: Optional[str] = None) -> IO[bytes]:
        return self._blob(bucket, key).open("wb", content_type=content_type)

    # --- reads ---
    def get_bytes(self, bucket: str, key: str) -> bytes:
        from google.api_core.exceptions import NotFound

        try:
            return self._blob(bucket, key).download_as_bytes()
        except NotFound:
            raise ObjectNotFound(bucket, key)

    def download_to(self, bucket: str, key: str, dst_path: str) -> None:
        from google.api_core.exceptions import NotFound

        try:
            self._blob(bucket, key).download_to_filename(dst_path)
        except NotFound:
            raise ObjectNotFound(bucket, key)

    def exists(self, bucket: str, key: str) -> bool:
        return bool(self._blob(bucket, key).exists())

    def list(self, bucket: str, prefix: str) -> List[ObjectInfo]:
        out: List[ObjectInfo] = []
        for blob in _storage_client().list_blobs(bucket, prefix=prefix):
            out.append(
                ObjectInfo(key=blob.name, size=int(blob.size or 0), updated_at=blob.updated, metadata=dict(blob.metadata or {}))
            )
        return out

    # --- mutations ---
    def delete(self, bucket: str, key: str) -> bool:
        from google.api_core.exceptions import NotFound

        try:
            self._blob(bucket, key).delete()
            return True
        except NotFound:
            return False

    def copy(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> None:
        client = _storage_client()
        source = client.bucket(src_bucket).blob(src_key)
        client.bucket(src_bucket).copy_blob(source, client.bucket(dst_bucket), dst_key)

    # --- metadata ---
    def get_metadata(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        blob = self._blob(bucket, key)
        try:
            blob.reload()
        except Exception:
            return None
        return dict(blob.metadata or {})

    def set_metadata(self, bucket: str, key: str, metadata: Dict[str, Any]) -> None:
        blob = self._blob(bucket, key)
        blob.metadata = dict(metadata)
        blob.patch()

    # --- URLs ---
    def presign_get(self, bucket: str, key: str, *, expires_seconds: int) -> str:
        return self._blob(bucket, key).generate_signed_url(
            version="v4", expiration=datetime.timedelta(seconds=expires_seconds), method="GET"
        )

    def public_url(self, bucket: str, key: str) -> str:
        # GCS public endpoint; the domain no longer hardcodes this — it derives from the adapter.
        return f"https://storage.googleapis.com/{bucket}/{key}"


__all__ = ["GCSObjectStore"]
