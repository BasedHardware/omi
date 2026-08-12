"""GCS adapter: public_url must derive from the configured endpoint (self-hosted GCS-mode returns
reachable URLs), and get_metadata must only swallow NotFound — a storage outage must surface, not be
mistaken for missing cache metadata (cubic review PR 10887, backend/utils/object_store/adapters/gcs.py)."""

import pytest

import utils.object_store.adapters.gcs as gcs


def test_public_url_defaults_to_google(monkeypatch):
    monkeypatch.delenv("GCS_PUBLIC_ENDPOINT", raising=False)
    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    assert gcs.GCSObjectStore().public_url("b", "k/x") == "https://storage.googleapis.com/b/k/x"


def test_public_url_derives_from_emulator_host(monkeypatch):
    monkeypatch.delenv("GCS_PUBLIC_ENDPOINT", raising=False)
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://gcs:4443/")
    assert gcs.GCSObjectStore().public_url("b", "k/x") == "http://gcs:4443/b/k/x"


def test_get_metadata_returns_none_only_on_notfound(monkeypatch):
    from google.api_core.exceptions import NotFound

    class _Blob:
        metadata = {"a": "1"}

        def reload(self):
            raise NotFound("gone")

    monkeypatch.setattr(gcs.GCSObjectStore, "_blob", lambda self, b, k: _Blob())
    assert gcs.GCSObjectStore().get_metadata("b", "k") is None


def test_get_metadata_reraises_storage_outage(monkeypatch):
    from google.api_core.exceptions import ServiceUnavailable

    class _Blob:
        metadata = {}

        def reload(self):
            raise ServiceUnavailable("outage")

    monkeypatch.setattr(gcs.GCSObjectStore, "_blob", lambda self, b, k: _Blob())
    with pytest.raises(ServiceUnavailable):
        gcs.GCSObjectStore().get_metadata("b", "k")
