"""App logo/thumbnail upload + public-URL paths go through the neutral object-store port (ADR-0032).

The spike slice that proved a real ``utils.other.storage`` caller works over the port: uploads land
in the store, and the returned URLs are the backend's ``public_url`` (no hard-wired
storage.googleapis.com string). Run against the in-memory ``FakeObjectStore`` so it is hermetic; the
adapters' parity is covered by ``tests/contract/test_object_store_contract.py``.
"""

import utils.other.storage as storage
from tests.object_store_fakes import FakeObjectStore


def _fake_store(monkeypatch) -> FakeObjectStore:
    store = FakeObjectStore(public_endpoint="https://cdn.example")
    monkeypatch.setattr(storage, "_object_store", lambda: store)
    return store


def test_upload_app_logo_stores_and_returns_public_url(monkeypatch, tmp_path):
    store = _fake_store(monkeypatch)
    src = tmp_path / "logo.png"
    src.write_bytes(b"PNGDATA")

    url = storage.upload_app_logo(str(src), "app42")

    assert store.get_bytes(storage.omi_apps_bucket, "app42.png") == b"PNGDATA"
    assert url == store.public_url(storage.omi_apps_bucket, "app42.png")
    assert url.endswith(f"{storage.omi_apps_bucket}/app42.png")  # public_url-derived, not hard-wired


def test_upload_app_thumbnail_stores_and_returns_public_url(monkeypatch, tmp_path):
    store = _fake_store(monkeypatch)
    src = tmp_path / "thumb.jpg"
    src.write_bytes(b"JPEGDATA")

    url = storage.upload_app_thumbnail(str(src), "th7")

    assert store.get_bytes(storage.app_thumbnails_bucket, "th7.jpg") == b"JPEGDATA"
    assert url == storage.get_app_thumbnail_url("th7")
    assert url.endswith(f"{storage.app_thumbnails_bucket}/th7.jpg")


def test_upload_then_delete_logo_roundtrip(monkeypatch, tmp_path):
    store = _fake_store(monkeypatch)
    src = tmp_path / "logo.png"
    src.write_bytes(b"x")

    url = storage.upload_app_logo(str(src), "app99")
    assert store.exists(storage.omi_apps_bucket, "app99.png")

    storage.delete_app_logo(url)
    assert not store.exists(storage.omi_apps_bucket, "app99.png")
