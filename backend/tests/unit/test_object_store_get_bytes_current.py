"""get_bytes_current reads the authoritative current object: GCS pins the read to the object's
current generation so a CDN-cached predecessor can't drive an Agent VM rollout; S3 delegates to the
already-current authenticated GET (cubic review PR 10887)."""

import utils.object_store.adapters.gcs as gcs
import utils.object_store.adapters.s3 as s3


def test_gcs_get_bytes_current_pins_generation(monkeypatch):
    seen = {}

    class _Blob:
        generation = 42

        def reload(self):
            seen["reloaded"] = True

        def download_as_bytes(self, if_generation_match=None):
            seen["pin"] = if_generation_match
            return b"current-release"

    monkeypatch.setattr(gcs.GCSObjectStore, "_blob", lambda self, b, k: _Blob())
    assert gcs.GCSObjectStore().get_bytes_current("b", "k") == b"current-release"
    assert seen == {"reloaded": True, "pin": 42}  # generation resolved, then pinned


def test_s3_get_bytes_current_delegates_to_authenticated_get(monkeypatch):
    class _Body:
        def read(self):
            return b"s3-current"

    class _Client:
        def __init__(self):
            self.gets = []

        def get_object(self, Bucket, Key):
            self.gets.append((Bucket, Key))
            return {"Body": _Body()}

    client = _Client()
    monkeypatch.setattr(s3, "_s3", lambda: client)
    assert s3.S3ObjectStore().get_bytes_current("b", "k") == b"s3-current"
    assert client.gets == [("b", "k")]
