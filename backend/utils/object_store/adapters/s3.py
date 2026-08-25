"""Generic S3-compatible adapter for the object-store port (ADR-0032).

One adapter for the whole S3 protocol — RustFS (the on-prem contract target), MinIO, SeaweedFS,
Ceph, AWS S3 — differing only by ``S3_ENDPOINT``/credentials (ADR-0004: the adapter is the protocol,
the product is deployment config). Path-style addressing + SigV4, which every self-hosted S3 needs.

Env: ``S3_ENDPOINT`` (e.g. http://rustfs:9000), ``S3_ACCESS_KEY``, ``S3_SECRET_KEY``,
``S3_REGION`` (default us-east-1), ``S3_PUBLIC_ENDPOINT`` (REQUIRED for ``public_url`` — an externally
reachable base; no fallback to the internal ``S3_ENDPOINT``), ``S3_PUBLIC_ACL`` (default ``public-read``;
set empty on AWS bucket-owner-enforced buckets and grant public access via a bucket policy).
"""

from __future__ import annotations

import logging
import tempfile
import os
import threading
from typing import IO, Any, Dict, List, Optional

from utils.object_store.errors import ObjectNotFound
from utils.object_store.ports import ObjectInfo
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

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


_public_client_lock = threading.Lock()
_public_client: Any = None


def _s3_public() -> Any:
    """A client bound to the EXTERNAL base, used only to sign URLs that leave the process.

    Not the same client as ``_s3()``: a SigV4 signature covers the Host header, so a signed URL cannot
    have its host rewritten afterwards — the signature would stop matching and the object would 403.
    Signing has to happen against the host the caller will actually use.

    Returns ``None`` when ``S3_PUBLIC_ENDPOINT`` is unset, so ``presign_get`` can fall back to the
    internal client (unchanged behaviour for a deployment that never configured it) while recording the
    loss instead of hiding it.
    """
    if not (os.getenv("S3_PUBLIC_ENDPOINT") or "").strip():
        return None
    global _public_client
    if _public_client is None:
        with _public_client_lock:
            if _public_client is None:
                import boto3  # lazy: only the s3 backend needs this SDK
                from botocore.config import Config

                _public_client = boto3.client(
                    "s3",
                    endpoint_url=_public_base(),
                    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                    region_name=(os.getenv("S3_REGION") or "us-east-1").strip(),
                    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
                )
    return _public_client


def _public_base() -> str:
    # An externally reachable base for public_url — REQUIRED, no fallback to S3_ENDPOINT. The client endpoint
    # is usually internal (the documented RustFS setup is http://rustfs:9000), so falling back to it handed
    # external clients an unreachable URL (cubic PR 10887 s3.py:48). The operator must set S3_PUBLIC_ENDPOINT
    # to a host reachable by end users (a public RustFS/CDN address).
    base = (os.getenv("S3_PUBLIC_ENDPOINT") or "").strip().rstrip("/")
    if not base:
        raise ValueError(
            "S3_PUBLIC_ENDPOINT is not set: refusing to expose the internal S3_ENDPOINT as a public URL. "
            "Configure S3_PUBLIC_ENDPOINT with an externally reachable base for public objects."
        )
    return base


def _public_acl() -> Optional[str]:
    # ACL to apply to public objects. Default 'public-read'.
    #
    # MEASURED, because the comment here used to claim "RustFS/MinIO honor ACLs" and that is FALSE for the
    # RustFS we deploy: an object uploaded with public-read answers HTTP 403 to an anonymous GET on both
    # 1.0.0-beta.12 (our pin) and 1.0.0-rc.3 (rustfs/rustfs#928, still open), and SeaweedFS 4.43 behaves the
    # same. The only mechanism that works on all three is a BUCKET POLICY, and a prefix-scoped one at that
    # (verified: `<bucket>/public/*` public, the rest private). So the ACL is accepted and ignored: an
    # upload with public=True succeeds and its URL is unreachable, which reads as "public and broken"
    # rather than "not public". Tracked as BACKLOG L6.
    #
    # It is kept because it is not dead everywhere: MinIO does honour it, and on AWS buckets with Object
    # Ownership = 'bucket owner enforced' (default since 2023) ACLs are DISABLED and public-read makes the
    # upload FAIL — set S3_PUBLIC_ACL='' (empty) there and grant public access via a bucket policy instead
    # (cubic PR 10887 s3.py:117). An empty value means "send no ACL".
    value = os.getenv("S3_PUBLIC_ACL")
    if value is None:
        return "public-read"
    value = value.strip()
    return value or None


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
                _acl = _public_acl()
                if _acl:
                    kwargs["ACL"] = _acl
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
            _acl = _public_acl()
            if _acl:
                extra["ACL"] = _acl
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
            _acl = _public_acl()
            if _acl:
                extra["ACL"] = _acl
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

    # Headers a REPLACE self-copy drops unless restated. The GCS twin uses blob.patch(), which touches
    # only the metadata, so without this the two adapters disagreed on what "set metadata" means: on S3
    # it also reset the content type, and an image served as application/octet-stream is a broken image.
    _PRESERVED_HEADERS = ("ContentType", "CacheControl", "ContentDisposition", "ContentEncoding")

    def set_metadata(self, bucket: str, key: str, metadata: Dict[str, Any]) -> None:
        client = _s3()
        head = client.head_object(Bucket=bucket, Key=key)
        preserved = {name: head[name] for name in self._PRESERVED_HEADERS if head.get(name)}
        client.copy_object(
            Bucket=bucket,
            Key=key,
            CopySource={"Bucket": bucket, "Key": key},
            Metadata={str(k): str(v) for k, v in metadata.items()},
            MetadataDirective="REPLACE",
            **preserved,
        )

    # --- URLs ---
    def presign_get(self, bucket: str, key: str, *, expires_seconds: int) -> str:
        # Sign against the EXTERNAL base: this URL is handed to clients outside the process (the app, a
        # prerecorded STT provider, a desktop updater), and the client endpoint is the internal one
        # (the documented on-prem value is http://rustfs:9000). public_url already refused to expose
        # that host; signing was still doing it.
        client = _s3_public()
        if client is None:
            record_fallback(
                component='object_store',
                from_mode='presign_public_endpoint',
                to_mode='presign_internal_endpoint',
                reason='config_incomplete',
                outcome='degraded',
                log=logger,
            )
            client = _s3()
        return client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_seconds
        )

    def public_url(self, bucket: str, key: str) -> str:
        return f"{_public_base()}/{bucket}/{key}"


__all__ = ["S3ObjectStore"]
