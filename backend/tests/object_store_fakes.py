"""In-memory ``ObjectStore`` fake for hermetic unit tests of migrated callers (WP-objstore, ADR-0032).

Implements the neutral object-store port over a dict keyed by ``(bucket, key)``. The adapters have
their own live dual-backend contract test (``tests/contract/test_object_store_contract.py`` against
fake-gcs-server and RustFS); this fake exists so ``utils/other/storage.py`` and other callers migrated
to the port can be unit-tested without any backend. Semantics mirror the port contract.
"""

from __future__ import annotations

import copy
import io
from datetime import datetime, timezone
from typing import IO, Any, Dict, List, Optional, Tuple

from utils.object_store.errors import ObjectNotFound
from utils.object_store.ports import ObjectInfo


class _Obj:
    __slots__ = ("data", "content_type", "cache_control", "public", "metadata", "updated_at")

    def __init__(
        self,
        data: bytes,
        content_type: Optional[str],
        cache_control: Optional[str],
        public: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.data = data
        self.content_type = content_type
        self.cache_control = cache_control
        self.public = public
        self.metadata: Dict[str, Any] = dict(metadata) if metadata else {}
        self.updated_at = datetime.now(timezone.utc)


class _FakeWriter(io.BytesIO):
    """Streaming writer whose bytes land in the store on context exit (mirrors blob.open('wb'))."""

    def __init__(self, store: "FakeObjectStore", bucket: str, key: str, content_type: Optional[str]):
        super().__init__()
        self._store, self._bucket, self._key, self._content_type = store, bucket, key, content_type

    def __enter__(self) -> "_FakeWriter":
        return self

    def __exit__(self, *exc: Any) -> None:
        if exc[0] is None:
            self._store.put(self._bucket, self._key, self.getvalue(), content_type=self._content_type)
        super().close()


class FakeObjectStore:
    """In-memory ObjectStore. ``public_endpoint`` seeds ``public_url`` so callers can assert on it."""

    def __init__(self, public_endpoint: str = "memory://objstore"):
        self._objs: Dict[Tuple[str, str], _Obj] = {}
        self._public_endpoint = public_endpoint.rstrip("/")

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
        raw = bytes(data) if isinstance(data, (bytes, bytearray)) else data.read()
        self._objs[(bucket, key)] = _Obj(raw, content_type, cache_control, public, metadata)

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
        with open(src_path, "rb") as fh:
            self.put(bucket, key, fh.read(), content_type=content_type, cache_control=cache_control, public=public)

    def open_write(self, bucket: str, key: str, *, content_type: Optional[str] = None) -> IO[bytes]:
        return _FakeWriter(self, bucket, key, content_type)

    # --- reads ---
    def get_bytes(self, bucket: str, key: str) -> bytes:
        try:
            return self._objs[(bucket, key)].data
        except KeyError:
            raise ObjectNotFound(bucket, key)

    def download_to(self, bucket: str, key: str, dst_path: str) -> None:
        with open(dst_path, "wb") as fh:
            fh.write(self.get_bytes(bucket, key))

    def exists(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self._objs

    def list(self, bucket: str, prefix: str) -> List[ObjectInfo]:
        out: List[ObjectInfo] = []
        for (b, k), obj in sorted(self._objs.items()):
            if b == bucket and k.startswith(prefix):
                out.append(ObjectInfo(key=k, size=len(obj.data), updated_at=obj.updated_at, metadata=dict(obj.metadata)))
        return out

    # --- mutations ---
    def delete(self, bucket: str, key: str) -> bool:
        return self._objs.pop((bucket, key), None) is not None

    def copy(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> None:
        src = self._objs[(src_bucket, src_key)]
        self._objs[(dst_bucket, dst_key)] = copy.deepcopy(src)

    # --- metadata ---
    def get_metadata(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        obj = self._objs.get((bucket, key))
        return dict(obj.metadata) if obj is not None else None

    def set_metadata(self, bucket: str, key: str, metadata: Dict[str, Any]) -> None:
        self._objs[(bucket, key)].metadata = dict(metadata)

    # --- URLs ---
    def presign_get(self, bucket: str, key: str, *, expires_seconds: int) -> str:
        return f"{self._public_endpoint}/{bucket}/{key}?X-Expires={expires_seconds}"

    def public_url(self, bucket: str, key: str) -> str:
        return f"{self._public_endpoint}/{bucket}/{key}"


__all__ = ["FakeObjectStore"]
