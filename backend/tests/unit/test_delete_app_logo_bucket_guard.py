"""Regression test: delete_app_logo must not IndexError on a URL from another bucket.

utils.other.storage.delete_app_logo did img_url.split(prefix)[1] where prefix is the app-logo
bucket URL. A googleapis URL for a DIFFERENT or legacy bucket makes split return a one-element
list, so [1] raised IndexError. Callers guard only with the looser
startswith('https://storage.googleapis.com/'), so such a URL reaches here. It now returns when
the app-logo bucket prefix is absent, and still deletes a matching URL.
"""

import utils.other.storage as storage


class _FakeBlob:
    def __init__(self, sink):
        self._sink = sink

    def delete(self):
        self._sink.append('deleted')


class _FakeBucket:
    def __init__(self, sink):
        self._sink = sink

    def blob(self, path):
        self._sink.append(('blob', path))
        return _FakeBlob(self._sink)


class _FakeClient:
    def __init__(self, sink):
        self._sink = sink

    def bucket(self, name):
        return _FakeBucket(self._sink)


def test_delete_app_logo_ignores_url_from_other_bucket(monkeypatch):
    sink = []
    monkeypatch.setattr(storage, '_get_storage_client', lambda: _FakeClient(sink))

    storage.delete_app_logo('https://storage.googleapis.com/some-other-bucket/x.png')  # must not raise

    assert sink == []  # nothing deleted


def test_delete_app_logo_ignores_url_that_embeds_prefix_later(monkeypatch):
    sink = []
    monkeypatch.setattr(storage, '_get_storage_client', lambda: _FakeClient(sink))
    # A foreign-bucket URL that embeds the app-logo prefix later in the path must NOT delete: the
    # guard requires the URL to start with the prefix, not merely contain it.
    embedded = (
        f'https://storage.googleapis.com/other-bucket/https://storage.googleapis.com/{storage.omi_apps_bucket}/x.png'
    )

    storage.delete_app_logo(embedded)

    assert sink == []  # nothing deleted


def test_delete_app_logo_deletes_matching_url(monkeypatch):
    sink = []
    monkeypatch.setattr(storage, '_get_storage_client', lambda: _FakeClient(sink))
    url = f'https://storage.googleapis.com/{storage.omi_apps_bucket}/app123.png'

    storage.delete_app_logo(url)

    assert ('blob', 'app123.png') in sink
    assert 'deleted' in sink
