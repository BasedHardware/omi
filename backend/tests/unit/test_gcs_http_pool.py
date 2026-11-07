"""The shared GCS client's pool matches executor concurrency; the drain cap is bounded."""

import importlib

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import storage

from utils.other import local_storage


@pytest.mark.parametrize('raw,expected', [(None, 128), ('64', 64), ('3', 10), ('9999', 512), ('bad', 128)])
def test_pool_size_setting_is_bounded(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv('GCS_HTTP_POOL_MAXSIZE', raising=False)
    else:
        monkeypatch.setenv('GCS_HTTP_POOL_MAXSIZE', raw)
    assert local_storage.gcs_http_pool_maxsize() == expected


def test_client_session_uses_the_sized_https_adapter(monkeypatch):
    monkeypatch.setenv('GCS_HTTP_POOL_MAXSIZE', '96')
    client = local_storage._size_http_pool(storage.Client(project='synthetic', credentials=AnonymousCredentials()))
    adapter = client._http.get_adapter('https://storage.googleapis.com/')
    assert adapter._pool_maxsize == 96


def test_pool_sizing_failure_keeps_the_client(caplog):
    class Broken:
        @property
        def _http(self):
            raise RuntimeError('synthetic')

    client = Broken()
    assert local_storage._size_http_pool(client) is client
    assert 'event=gcs_http_pool outcome=default exception_type=RuntimeError' in caplog.text


def test_a_non_default_adapter_is_kept():
    import requests.adapters

    class MutualTls(requests.adapters.HTTPAdapter):
        pass

    client = storage.Client(project='synthetic', credentials=AnonymousCredentials())
    keep = MutualTls()
    client._http.mount('https://', keep)
    local_storage._size_http_pool(client)
    assert client._http.get_adapter('https://storage.googleapis.com/') is keep
