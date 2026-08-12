"""Generic S3-compatible adapter for the object-store port (ADR-0032).

One adapter for the whole S3 protocol — RustFS (the on-prem contract target), MinIO, SeaweedFS,
Ceph, AWS S3 — differing only by ``S3_ENDPOINT``/credentials (ADR-0004: the adapter is the protocol,
the product is deployment config). Path-style addressing + SigV4, which every self-hosted S3 needs.

Env: ``S3_ENDPOINT`` (e.g. http://rustfs:9000), ``S3_ACCESS_KEY``, ``S3_SECRET_KEY``,
``S3_REGION`` (default us-east-1), ``S3_PUBLIC_ENDPOINT`` (optional; base for ``public_url``, default = endpoint).
"""

from __future__ import annotations

import io
import tempfile
import os
import threading
from typing import IO, Any, Dict, List, Optional

from utils.object_store.errors import ObjectNotFound
from utils.object_store.ports import ObjectInfo

_NOT_FOUND_CODES = ("404", "NoSuchKey", "NotFound")

_client_lock = threading.Lock()
_client: Any = None


def _s3():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                import boto3  # lazy: only the s3 backend needs this SDK
                from botocore.config import Config

                _client = boto3.client(
                    "s3",
                    endpoint_url=(os.getenv("S3_ENDPOINT") or "").strip() or None,
                    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                    region_name=(os.getenv("S3_REGION") or "us-east-1").strip(),
                    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
                )
    return _client


def _public_base() -> str:
    return ((os.getenv("S3_PUBLIC_ENDPOINT") or os.getenv("S3_ENDPOINT") or "").strip()).rstrip("/")


# Bytes buffered by the streaming writer spill to disk past this size, so a large audio batch is
# never held entirely in process memory before the upload starts (upload_fileobj streams it in
# multipart chunks from the spooled file).
_SPOOL_MAX_BYTES = 16 * 1024 * 1024


class _S3Writer(tempfile.SpooledTemporaryFile):
    """Buffered streaming writer (S3 has no blob.open): bytes spill to disk past _SPOOL_MAX_BYTES and
    upload via multipart-capable upload_fileobj on context exit, keeping memory bounded."""

    def __init__(self, bucket: str, key: str, content_type: Optional[str]):
        super().__init__(max_size=_SPOOL_MAX_BYTES, mode="w+b")
        self._bucket, self._key, self._content_type = bucket, key, content_type

    def __enter__(self) -> "_S3Writer":
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            if exc[0] is None:
                extra: Dict[str, Any] = {}
                if self._content_type:
                    extra["ContentType"] = self._content_type
                self.seek(0)
                _s3().upload_fileobj(self, self._bucket, self._key, ExtraArgs=extra or None)
        finally:
            super().close()


class S3ObjectStore:
    """ObjectStore over any S3-compatible backend. ``bucket``/``key`` map to S3 Bucket/Key."""

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
        if isinstance(data, (bytes, bytearray)):
            kwargs: Dict[str, Any] = {"Bucket": bucket, "Key": key, "Body": bytes(data)}
            if content_type:
                kwargs["ContentType"] = content_type
            if cache_control:
                kwargs["CacheControl"] = cache_control
            if metadata is not None:
                kwargs["Metadata"] = {str(k): str(v) for k, v in metadata.items()}
            if public:
                kwargs["ACL"] = "public-read"
            _s3().put_object(**kwargs)
            return
        # A stream: upload_fileobj streams it in multipart chunks (bounded memory) instead of
        # reading the whole object into RAM (data.read()) before the request even starts.
        extra: Dict[str, Any] = {}
        if content_type:
            extra["ContentType"] = content_type
        if cache_control:
            extra["CacheControl"] = cache_control
        if metadata is not None:
            extra["Metadata"] = {str(k): str(v) for k, v in metadata.items()}
        if public:
            extra["ACL"] = "public-read"
        _s3().upload_fileobj(data, bucket, key, ExtraArgs=extra or None)

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
        extra: Dict[str, Any] = {}
        if content_type:
            extra["ContentType"] = content_type
        if cache_control:
            extra["CacheControl"] = cache_control
        if public:
            extra["ACL"] = "public-read"
        _s3().upload_file(src_path, bucket, key, ExtraArgs=extra or None)

    def open_write(self, bucket: str, key: str, *, content_type: Optional[str] = None) -> IO[bytes]:
        return _S3Writer(bucket, key, content_type)

    # --- reads ---
    def get_bytes_current(self, bucket: str, key: str) -> bytes:
        # An authenticated S3 GetObject is strongly consistent and always the current object (no CDN
        # edge in the read path), so there is no stale-generation to defeat: the current read is the
        # plain GET.
        return self.get_bytes(bucket, key)

    def get_bytes(self, bucket: str, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            return _s3().get_object(Bucket=bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND_CODES:
                raise ObjectNotFound(bucket, key)
            raise

    def download_to(self, bucket: str, key: str, dst_path: str) -> None:
        from botocore.exceptions import ClientError

        try:
            _s3().download_file(bucket, key, dst_path)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND_CODES:
                raise ObjectNotFound(bucket, key)
            raise

    def exists(self, bucket: str, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            _s3().head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def list(self, bucket: str, prefix: str) -> List[ObjectInfo]:
        out: List[ObjectInfo] = []
        paginator = _s3().get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                out.append(ObjectInfo(key=obj["Key"], size=int(obj.get("Size", 0)), updated_at=obj.get("LastModified")))
        return out

    # --- mutations ---
    def delete(self, bucket: str, key: str) -> bool:
        existed = self.exists(bucket, key)  # S3 delete is idempotent; mirror GCS's found/not-found return
        _s3().delete_object(Bucket=bucket, Key=key)
        return existed

    def copy(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> None:
        _s3().copy_object(Bucket=dst_bucket, Key=dst_key, CopySource={"Bucket": src_bucket, "Key": src_key})

    # --- metadata (immutable post-write on S3 → REPLACE via self-copy) ---
    def get_metadata(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        from botocore.exceptions import ClientError

        try:
            return dict(_s3().head_object(Bucket=bucket, Key=key).get("Metadata", {}))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def set_metadata(self, bucket: str, key: str, metadata: Dict[str, Any]) -> None:
        _s3().copy_object(
            Bucket=bucket,
            Key=key,
            CopySource={"Bucket": bucket, "Key": key},
            Metadata={str(k): str(v) for k, v in metadata.items()},
            MetadataDirective="REPLACE",
        )

    # --- URLs ---
    def presign_get(self, bucket: str, key: str, *, expires_seconds: int) -> str:
        return _s3().generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_seconds)

    def public_url(self, bucket: str, key: str) -> str:
        return f"{_public_base()}/{bucket}/{key}"


__all__ = ["S3ObjectStore"]
