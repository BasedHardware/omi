"""In-memory GCS client for exercising the real audio producer and reader."""

import io
from types import SimpleNamespace

import numpy as np
import pytest

from utils import encryption
from utils.other import storage


@pytest.fixture
def memory_bucket(monkeypatch):
    """Only the storage client is fake; uploader, encryption, listing and decoding are real."""
    objects, reads, listings = {}, [], []

    class Blob:
        def __init__(self, name):
            self.name, self.metadata, self.data = name, None, b''

        @property
        def size(self):
            return len(self.data)

        def exists(self):
            return self.name in objects

        def open(self, mode, **kwargs):
            blob = self

            class Writer(io.BytesIO):
                def close(self):
                    blob.data = self.getvalue()
                    objects[blob.name] = blob
                    super().close()

            return Writer()

        def download_as_bytes(self, **kwargs):
            reads.append(self.name)
            if self.name not in objects:
                raise storage.NotFound('synthetic missing blob')
            data = self.data
            return data[kwargs.get('start', 0) : kwargs.get('end', len(data) - 1) + 1]

    class Bucket:
        def blob(self, name):
            return objects.get(name) or Blob(name)

        def list_blobs(self, prefix, **kwargs):
            listings.append(prefix)
            return [blob for name, blob in objects.items() if name.startswith(prefix)]

    bucket = Bucket()
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))

    def add(start, seconds, *, enhanced=False, span=False, uid='synthetic-user', conversation_id='synthetic'):
        data = (np.arange(round(seconds * 16000)) % 997 + 1).astype(np.int16).tobytes()
        name = f'chunks/{uid}/{conversation_id}/{start:.3f}.{"enc" if enhanced else "bin"}'
        blob = bucket.blob(name)
        blob.data = encryption.encrypt_audio_chunk(data, uid) if enhanced else data
        if span:
            blob.metadata = storage.span_blob_metadata(
                {'start': start, 'samples': len(data) // 2, 'sample_rate': 16000}
            )
        objects[name] = blob
        return data

    return SimpleNamespace(bucket=bucket, add=add, reads=reads, listings=listings, objects=objects)
