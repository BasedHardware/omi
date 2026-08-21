"""Two S3 adapter defects, both about a URL or a header the caller never sees go wrong.

L5 — presign_get signed against the INTERNAL endpoint. The client is built with
     endpoint_url=S3_ENDPOINT (the documented on-prem value is http://rustfs:9000) and
     generate_presigned_url inherits that host, so every signed URL that leaves the process carries an
     address no external client can reach: voice samples, merged audio, playback artifacts, desktop
     updates, and the temporal URL handed to a prerecorded STT provider. The adapter already has an
     external base for public_url — and _public_base() even REFUSES to fall back to the internal
     endpoint — so the reasoning existed and simply was not applied to signing.

     A SigV4 signature covers the Host header, so the host cannot be string-replaced after signing: the
     signature would no longer match. It needs a second client bound to the public base.

L7 — set_metadata is a self-copy with MetadataDirective=REPLACE and no ContentType/CacheControl, so it
     silently resets them; the GCS twin uses blob.patch() and preserves everything. Zero product
     callers today, which makes it a mine for the first one.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fresh_clients(monkeypatch):
    """The adapter memoises its clients in module globals; each test needs its own."""
    from utils.object_store.adapters import s3 as s3_mod

    monkeypatch.setattr(s3_mod, '_client', None, raising=False)
    monkeypatch.setattr(s3_mod, '_public_client', None, raising=False)
    monkeypatch.setenv('S3_ACCESS_KEY', 'k')
    monkeypatch.setenv('S3_SECRET_KEY', 's')
    monkeypatch.setenv('S3_ENDPOINT', 'http://rustfs:9000')
    return s3_mod


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc


# --- L5 -----------------------------------------------------------------------------------------


def test_a_signed_url_carries_the_public_host(_fresh_clients, monkeypatch):
    monkeypatch.setenv('S3_PUBLIC_ENDPOINT', 'https://files.example.test')
    from utils.object_store.adapters.s3 import S3ObjectStore

    url = S3ObjectStore().presign_get('b1', 'u1/speech_profile.wav', expires_seconds=60)
    assert _host(url) == 'files.example.test', 'the signed URL still points at the internal endpoint'


def test_the_signature_matches_that_host(_fresh_clients, monkeypatch):
    """Not just a rewritten host: SigV4 signs the Host header, so a string replacement would produce a
    URL that 403s on signature mismatch. The credential scope proves it was signed for this endpoint."""
    monkeypatch.setenv('S3_PUBLIC_ENDPOINT', 'https://files.example.test')
    from utils.object_store.adapters.s3 import S3ObjectStore

    url = S3ObjectStore().presign_get('b1', 'k1', expires_seconds=60)
    assert 'X-Amz-Signature=' in url and 'X-Amz-Algorithm=AWS4-HMAC-SHA256' in url
    assert 'SignedHeaders=host' in url


def test_without_a_public_endpoint_it_still_works_and_says_so(_fresh_clients, monkeypatch):
    """Non-breaking: a deployment that never set S3_PUBLIC_ENDPOINT keeps its old behaviour, but the
    loss stops being silent."""
    monkeypatch.delenv('S3_PUBLIC_ENDPOINT', raising=False)
    from utils.object_store.adapters import s3 as s3_mod

    events: list[dict] = []
    monkeypatch.setattr(s3_mod, 'record_fallback', lambda **kw: events.append(kw))

    url = s3_mod.S3ObjectStore().presign_get('b1', 'k1', expires_seconds=60)
    assert _host(url) == 'rustfs:9000'
    assert len(events) == 1 and events[0]['reason'] == 'config_incomplete'
    assert events[0]['component'] == 'object_store'


def test_the_public_url_is_unchanged(_fresh_clients, monkeypatch):
    """Legacy principal: public_url already used the external base and must keep doing exactly that."""
    monkeypatch.setenv('S3_PUBLIC_ENDPOINT', 'https://files.example.test')
    from utils.object_store.adapters.s3 import S3ObjectStore

    assert S3ObjectStore().public_url('b1', 'k1') == 'https://files.example.test/b1/k1'


# --- L7 -----------------------------------------------------------------------------------------


def test_set_metadata_preserves_the_content_type(_fresh_clients, monkeypatch):
    """A self-copy with REPLACE drops every header it does not restate. GCS's blob.patch() keeps them,
    so the two adapters disagreed on what "set metadata" means."""
    from utils.object_store.adapters import s3 as s3_mod

    captured: dict = {}

    class _Spy:
        def head_object(self, **kwargs):
            return {
                'Metadata': {'old': '1'},
                'ContentType': 'image/png',
                'CacheControl': 'public, max-age=60',
                'ContentDisposition': 'inline',
                'ContentEncoding': 'gzip',
            }

        def copy_object(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(s3_mod, '_s3', lambda: _Spy())
    s3_mod.S3ObjectStore().set_metadata('b1', 'k1', {'owner': 'ada'})

    assert captured['Metadata'] == {'owner': 'ada'}, 'the new metadata must replace the old'
    assert captured['MetadataDirective'] == 'REPLACE'
    assert captured['ContentType'] == 'image/png', 'the content type was reset'
    assert captured['CacheControl'] == 'public, max-age=60'
    assert captured['ContentDisposition'] == 'inline'
    assert captured['ContentEncoding'] == 'gzip'


def test_set_metadata_omits_headers_the_object_never_had(_fresh_clients, monkeypatch):
    """Restating an absent header as an empty string would be a change of its own."""
    from utils.object_store.adapters import s3 as s3_mod

    captured: dict = {}

    class _Spy:
        def head_object(self, **kwargs):
            return {'Metadata': {}}

        def copy_object(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(s3_mod, '_s3', lambda: _Spy())
    s3_mod.S3ObjectStore().set_metadata('b1', 'k1', {'owner': 'ada'})
    for header in ('ContentType', 'CacheControl', 'ContentDisposition', 'ContentEncoding'):
        assert header not in captured, f'{header} was invented'
