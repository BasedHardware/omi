"""S3 public URLs must not leak the internal endpoint, and the public-object ACL must be configurable so
uploads work on AWS bucket-owner-enforced buckets (cubic PR 10887 s3.py:48 / s3.py:117)."""

import pytest

import utils.object_store.adapters.s3 as s3


class _FakeS3:
    def __init__(self):
        self.put_object_calls: list = []

    def put_object(self, **kwargs):
        self.put_object_calls.append(kwargs)

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):  # unused here
        pass


def _patch(monkeypatch) -> _FakeS3:
    fake = _FakeS3()
    monkeypatch.setattr(s3, "_s3", lambda: fake)
    return fake


def test_public_url_requires_public_endpoint_no_fallback(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setenv("S3_ENDPOINT", "http://rustfs:9000")  # internal
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT", raising=False)
    # Must NOT hand out the internal rustfs:9000 as a public URL.
    with pytest.raises(ValueError):
        s3.S3ObjectStore().public_url("bkt", "logo.png")


def test_public_url_uses_public_endpoint(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setenv("S3_ENDPOINT", "http://rustfs:9000")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT", "https://files.example/")  # trailing slash normalized
    assert s3.S3ObjectStore().public_url("bkt", "logo.png") == "https://files.example/bkt/logo.png"


def test_public_acl_defaults_to_public_read(monkeypatch):
    fake = _patch(monkeypatch)
    monkeypatch.delenv("S3_PUBLIC_ACL", raising=False)
    s3.S3ObjectStore().put("bkt", "k", b"x", public=True)
    assert fake.put_object_calls[-1].get("ACL") == "public-read"


def test_public_acl_empty_sends_no_acl(monkeypatch):
    # AWS bucket-owner-enforced: ACLs disabled — an empty S3_PUBLIC_ACL must omit ACL (bucket policy instead).
    fake = _patch(monkeypatch)
    monkeypatch.setenv("S3_PUBLIC_ACL", "")
    s3.S3ObjectStore().put("bkt", "k", b"x", public=True)
    assert "ACL" not in fake.put_object_calls[-1]
