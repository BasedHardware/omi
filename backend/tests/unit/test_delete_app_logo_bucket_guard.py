"""Regression test: delete_app_logo must not IndexError on a URL from another bucket.

utils.other.storage.delete_app_logo did img_url.split(prefix)[1] where prefix is the app-logo
bucket URL. A googleapis URL for a DIFFERENT or legacy bucket makes split return a one-element
list, so [1] raised IndexError. Callers guard only with the looser
startswith('https://storage.googleapis.com/'), so such a URL reaches here. It now returns when
the app-logo bucket prefix is absent, and still deletes a matching URL.

Exercised through the neutral object-store port: delete_app_logo builds its prefix from
_object_store().public_url(omi_apps_bucket, '') and deletes via _object_store().delete(), so a fake
with a googleapis endpoint reproduces the exact URL-prefix guard (was a raw GCS _get_storage_client).
"""

import utils.other.storage as storage
from tests.object_store_fakes import FakeObjectStore


class _RecordingObjectStore(FakeObjectStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.deleted: list = []

    def delete(self, bucket, key):
        self.deleted.append((bucket, key))
        return super().delete(bucket, key)


def _install(monkeypatch):
    store = _RecordingObjectStore(public_endpoint="https://storage.googleapis.com")
    monkeypatch.setattr(storage, '_object_store', lambda: store)
    return store


def test_delete_app_logo_ignores_url_from_other_bucket(monkeypatch):
    store = _install(monkeypatch)

    storage.delete_app_logo('https://storage.googleapis.com/some-other-bucket/x.png')  # must not raise

    assert store.deleted == []  # nothing deleted


def test_delete_app_logo_ignores_url_that_embeds_prefix_later(monkeypatch):
    store = _install(monkeypatch)
    # A foreign-bucket URL that embeds the app-logo prefix later in the path must NOT delete: the
    # guard requires the URL to start with the prefix, not merely contain it.
    embedded = (
        f'https://storage.googleapis.com/other-bucket/https://storage.googleapis.com/{storage.omi_apps_bucket}/x.png'
    )

    storage.delete_app_logo(embedded)

    assert store.deleted == []  # nothing deleted


def test_delete_app_logo_deletes_matching_url(monkeypatch):
    store = _install(monkeypatch)
    store.put(storage.omi_apps_bucket, 'app123.png', b'x')
    url = f'https://storage.googleapis.com/{storage.omi_apps_bucket}/app123.png'

    storage.delete_app_logo(url)

    assert (storage.omi_apps_bucket, 'app123.png') in store.deleted
    assert not store.exists(storage.omi_apps_bucket, 'app123.png')
