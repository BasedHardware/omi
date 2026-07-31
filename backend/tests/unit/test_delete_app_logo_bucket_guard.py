"""Regression test: delete_app_logo must not act on a URL from another bucket.

utils.other.storage.delete_app_logo requires the URL to START WITH the app-logo bucket's public-URL
prefix (derived from the object-store port, not a hard-wired string). A URL for a different/legacy
bucket — or one that embeds the prefix later in the path — must not delete anything. Exercised through
the real port path with the in-memory ``FakeObjectStore`` (the store seam replaced the raw GCS client
when storage.py migrated to ``utils.object_store``, ADR-0032).
"""

import utils.other.storage as storage
from tests.object_store_fakes import FakeObjectStore


def _fake_store(monkeypatch) -> FakeObjectStore:
    # public_endpoint mimics the GCS public host so the legacy googleapis URLs below match the prefix
    # the guard derives via public_url(); the delete path itself runs against the fake unchanged.
    store = FakeObjectStore(public_endpoint="https://storage.googleapis.com")
    monkeypatch.setattr(storage, "_object_store", lambda: store)
    return store


def test_delete_app_logo_ignores_url_from_other_bucket(monkeypatch):
    store = _fake_store(monkeypatch)
    store.put("some-other-bucket", "x.png", b"logo")

    storage.delete_app_logo("https://storage.googleapis.com/some-other-bucket/x.png")  # must not raise

    assert store.exists("some-other-bucket", "x.png")  # untouched


def test_delete_app_logo_ignores_url_that_embeds_prefix_later(monkeypatch):
    store = _fake_store(monkeypatch)
    # A foreign-bucket URL that embeds the app-logo prefix later in the path must NOT delete: the
    # guard requires the URL to start with the prefix, not merely contain it.
    embedded = (
        f"https://storage.googleapis.com/other-bucket/https://storage.googleapis.com/{storage.omi_apps_bucket}/x.png"
    )

    storage.delete_app_logo(embedded)  # must not raise, must delete nothing

    assert store.list(storage.omi_apps_bucket, "") == []


def test_delete_app_logo_deletes_matching_url(monkeypatch):
    store = _fake_store(monkeypatch)
    store.put(storage.omi_apps_bucket, "app123.png", b"logo")
    url = f"https://storage.googleapis.com/{storage.omi_apps_bucket}/app123.png"

    storage.delete_app_logo(url)

    assert not store.exists(storage.omi_apps_bucket, "app123.png")  # deleted
