"""Dual-backend contract test for the neutral object-store port (WP-objstore, ADR-0032/0004).

The SAME assertions run against every adapter — the in-memory fake (always, hermetic), the GCS
reference adapter (against fake-gcs-server), and the generic S3 adapter (against RustFS). Parity here
is the proof that ``utils.object_store`` abstracts the backend rather than leaking one: a caller
written to the port behaves identically whichever ``OBJECT_STORE_BACKEND`` is configured.

Live services (each backend is skipped when its env is absent, so the file is safe to collect anywhere):
  * ``STORAGE_EMULATOR_HOST`` — a fake-gcs-server the google-cloud-storage SDK talks to.
  * ``S3_ENDPOINT`` (+ ``S3_ACCESS_KEY``/``S3_SECRET_KEY``) — a RustFS/S3 endpoint.
The fake backend needs nothing and always runs. This is NOT a hermetic-only file (gcs/s3 need live
services) and is not run by ``backend/test.sh``; the offline harness runs it with both services up.
"""

from __future__ import annotations

import os
import uuid

import pytest

from utils.object_store.errors import ObjectNotFound


def _new_bucket_name() -> str:
    return f"omi-contract-{uuid.uuid4().hex[:12]}"


@pytest.fixture(params=["fake", "gcs", "s3"])
def store_and_bucket(request):
    """Yield ``(store, bucket)`` for each configured backend, creating the bucket where the backend needs it."""
    backend = request.param
    bucket = _new_bucket_name()

    if backend == "fake":
        from tests.object_store_fakes import FakeObjectStore

        return FakeObjectStore(), bucket

    if backend == "gcs":
        if not os.environ.get("STORAGE_EMULATOR_HOST"):
            pytest.skip("STORAGE_EMULATOR_HOST not set")
        from utils.object_store.adapters import gcs as gcs_mod

        # fake-gcs-server accepts anonymous auth for object ops (the SDK auto-uses AnonymousCredentials
        # when STORAGE_EMULATOR_HOST is set). It has no signing key, so presign_get[gcs] is skipped and
        # covered instead by the hermetic delegation unit test below.
        gcs_mod._client = None  # reset the module singleton so the emulator env is picked up
        gcs_mod._storage_client().create_bucket(bucket)
        return gcs_mod.GCSObjectStore(), bucket

    if not os.environ.get("S3_ENDPOINT"):
        pytest.skip("S3_ENDPOINT not set")
    from utils.object_store.adapters import s3 as s3_mod

    s3_mod._client = None  # reset the module singleton so the endpoint env is picked up
    s3_mod._s3().create_bucket(Bucket=bucket)
    return s3_mod.S3ObjectStore(), bucket


# --- writes / reads ----------------------------------------------------------


def test_put_get_roundtrip(store_and_bucket):
    store, bucket = store_and_bucket
    store.put(bucket, "a/obj.bin", b"hello world", content_type="application/octet-stream")
    assert store.get_bytes(bucket, "a/obj.bin") == b"hello world"


def test_exists(store_and_bucket):
    store, bucket = store_and_bucket
    assert store.exists(bucket, "missing") is False
    store.put(bucket, "here", b"x")
    assert store.exists(bucket, "here") is True


def test_get_bytes_missing_raises_object_not_found(store_and_bucket):
    store, bucket = store_and_bucket
    with pytest.raises(ObjectNotFound):
        store.get_bytes(bucket, "does/not/exist")


def test_put_with_metadata_roundtrips(store_and_bucket):
    store, bucket = store_and_bucket
    store.put(bucket, "meta/obj", b"x", metadata={"expires_at": "2099-01-01", "id": "abc"})
    assert store.get_metadata(bucket, "meta/obj") == {"expires_at": "2099-01-01", "id": "abc"}


def test_put_from_file_and_download_to(store_and_bucket, tmp_path):
    store, bucket = store_and_bucket
    src = tmp_path / "src.txt"
    src.write_bytes(b"file-bytes")
    store.put_from_file(bucket, "f/src.txt", str(src), content_type="text/plain")
    dst = tmp_path / "dst.txt"
    store.download_to(bucket, "f/src.txt", str(dst))
    assert dst.read_bytes() == b"file-bytes"


def test_open_write_streams(store_and_bucket):
    store, bucket = store_and_bucket
    with store.open_write(bucket, "s/stream.bin", content_type="application/octet-stream") as w:
        w.write(b"chunk-1")
        w.write(b"chunk-2")
    assert store.get_bytes(bucket, "s/stream.bin") == b"chunk-1chunk-2"


# --- listing -----------------------------------------------------------------


def test_list_by_prefix(store_and_bucket):
    store, bucket = store_and_bucket
    store.put(bucket, "p/1", b"aa")
    store.put(bucket, "p/2", b"bbb")
    store.put(bucket, "other/3", b"c")
    listed = {o.key: o.size for o in store.list(bucket, "p/")}
    assert listed == {"p/1": 2, "p/2": 3}


# --- mutations ---------------------------------------------------------------


def test_delete_reports_found(store_and_bucket):
    store, bucket = store_and_bucket
    store.put(bucket, "d/obj", b"x")
    assert store.delete(bucket, "d/obj") is True
    assert store.exists(bucket, "d/obj") is False
    assert store.delete(bucket, "d/obj") is False


def test_copy(store_and_bucket):
    store, bucket = store_and_bucket
    store.put(bucket, "c/src", b"payload")
    store.copy(bucket, "c/src", bucket, "c/dst")
    assert store.get_bytes(bucket, "c/dst") == b"payload"
    assert store.get_bytes(bucket, "c/src") == b"payload"  # copy leaves the source intact


# --- metadata ----------------------------------------------------------------


def test_metadata_roundtrip(store_and_bucket):
    store, bucket = store_and_bucket
    store.put(bucket, "m/obj", b"x")
    assert store.get_metadata(bucket, "m/obj") == {}
    store.set_metadata(bucket, "m/obj", {"owner": "ada", "kind": "logo"})
    assert store.get_metadata(bucket, "m/obj") == {"owner": "ada", "kind": "logo"}


def test_get_metadata_missing_is_none(store_and_bucket):
    store, bucket = store_and_bucket
    assert store.get_metadata(bucket, "nope") is None


# --- URLs --------------------------------------------------------------------


def test_presign_get_returns_url_for_key(store_and_bucket, request):
    if request.node.callspec.params["store_and_bucket"] == "gcs":
        pytest.skip("fake-gcs-server has no signing key; GCS V4 signing covered by the delegation unit test")
    store, bucket = store_and_bucket
    store.put(bucket, "u/obj", b"x")
    url = store.presign_get(bucket, "u/obj", expires_seconds=300)
    assert isinstance(url, str) and url
    assert bucket in url and "u/obj" in url


def test_public_url_ends_with_path(store_and_bucket):
    store, bucket = store_and_bucket
    assert store.public_url(bucket, "logo/x.png").endswith(f"{bucket}/logo/x.png")


# --- GCS V4 signing delegation (hermetic; fake-gcs-server can't sign, so assert the SDK call) ------


def test_gcs_presign_delegates_v4_get(monkeypatch):
    """The GCS adapter must ask the blob for a V4, GET, time-boxed signed URL — no network needed."""
    import datetime as _dt

    from utils.object_store.adapters import gcs as gcs_mod

    captured = {}

    class _FakeBlob:
        def generate_signed_url(self, **kwargs):
            captured.update(kwargs)
            return "https://signed.example/obj"

    class _FakeStore(gcs_mod.GCSObjectStore):
        def _blob(self, bucket, key):
            return _FakeBlob()

    url = _FakeStore().presign_get("b", "k", expires_seconds=600)
    assert url == "https://signed.example/obj"
    assert captured["version"] == "v4"
    assert captured["method"] == "GET"
    assert captured["expiration"] == _dt.timedelta(seconds=600)
