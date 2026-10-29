"""A failed raw-archive listing is never mistaken for a complete capture."""

from types import SimpleNamespace

import pytest

from utils.other import storage


@pytest.fixture
def listing(monkeypatch):
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    legacy = SimpleNamespace(name='chunks/owner/conv/100.000.batch.bin', size=10, generation=1, metadata=None)
    bucket = SimpleNamespace(name=storage.private_cloud_sync_bucket, list_blobs=lambda **kwargs: iter([legacy]))
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(storage.audio_archive, 'admitted', lambda uid, mode: True)
    monkeypatch.setattr(storage, 'playback_on_demand', lambda: False)

    def slow(*args):
        raise TimeoutError('synthetic slow archive listing')

    monkeypatch.setattr(storage, 'list_packs', slow)


def test_default_listing_keeps_legacy_chunks_when_archive_listing_fails(listing):
    chunks = storage.list_audio_chunks('owner', 'conv')
    assert [chunk['path'] for chunk in chunks] == ['chunks/owner/conv/100.000.batch.bin']


def test_required_archive_listing_raises_instead_of_returning_a_short_capture(listing):
    with pytest.raises(TimeoutError):
        storage.list_audio_chunks('owner', 'conv', require_archive=True)
