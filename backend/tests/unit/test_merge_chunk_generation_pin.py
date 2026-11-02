"""Tests for Issue #24302: pin source generation during merge chunk copy and delete.

Race: a spanless (v1, update-in-place) writer overwrites a source chunk between
the listing and the copy or delete.
Fix:
- copy_blob pins source_generation=<listed generation>.
- delete_audio_chunks pins if_generation_match=<listed generation>.
- Overwritten chunks are not deleted, preserving newer bytes.
"""

from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from google.api_core.exceptions import PreconditionFailed

from utils.conversations import merge_conversations as merge
from utils.other import storage

UID = 'u_test'
PRIVATE = 'omi-private-cloud-sync'
DERIVED = 'omi-audio-derived-uc1'


class _MockBlob:
    def __init__(self, bucket, name, data=b'initial', generation=10, crc32c='crc-1'):
        self.bucket = bucket
        self.name = name
        self.data = data
        self.size = len(data)
        self.generation = generation
        self.crc32c = crc32c
        self.metadata = None

    def exists(self):
        return self.name in self.bucket.objects

    def delete(self, if_generation_match=None, **kwargs):
        if self.name not in self.bucket.objects:
            return
        current = self.bucket.objects[self.name]
        if if_generation_match is not None and current.generation != if_generation_match:
            raise PreconditionFailed(f"Generation mismatch on delete: current {current.generation} != expected {if_generation_match}")
        del self.bucket.objects[self.name]
        self.bucket.deleted.append((self.name, if_generation_match))


class _MockBucket:
    def __init__(self, name, objects=None):
        self.name = name
        self.objects = dict(objects or {})  # name -> _MockBlob
        self.copies = []  # (source_name, dest_name, source_generation, if_generation_match)
        self.deleted = []

    def blob(self, name):
        if name in self.objects:
            return self.objects[name]
        return _MockBlob(self, name, data=b'', generation=0)

    def list_blobs(self, prefix='', **kwargs):
        return [b for name, b in list(self.objects.items()) if name.startswith(prefix)]

    def get_blob(self, name, retry=None):
        return self.objects.get(name)

    def copy_blob(self, source_blob, dest_bucket, new_path, if_generation_match=None, source_generation=None, retry=None):
        src = self.objects.get(source_blob.name)
        if src is None:
            raise PreconditionFailed(f"Source not found: {source_blob.name}")
        if source_generation is not None and src.generation != source_generation:
            raise PreconditionFailed(f"Source generation mismatch: current {src.generation} != pinned {source_generation}")

        dest_curr = dest_bucket.objects.get(new_path)
        if if_generation_match is not None:
            curr_gen = dest_curr.generation if dest_curr else 0
            if curr_gen != if_generation_match:
                raise PreconditionFailed(f"Destination generation mismatch: current {curr_gen} != match {if_generation_match}")

        new_gen = (dest_curr.generation + 1) if dest_curr else 1
        new_blob = _MockBlob(dest_bucket, new_path, data=src.data, generation=new_gen, crc32c=src.crc32c)
        dest_bucket.objects[new_path] = new_blob
        self.copies.append((source_blob.name, new_path, source_generation, if_generation_match))


@pytest.fixture
def mock_storage(monkeypatch):
    buckets = {
        PRIVATE: _MockBucket(PRIVATE),
        DERIVED: _MockBucket(DERIVED),
    }
    client = SimpleNamespace(bucket=lambda name: buckets[name])
    monkeypatch.setattr(merge, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage, '_get_storage_client', lambda: client)
    monkeypatch.setattr(merge, 'owner_storage_write_gate', lambda uid, bucket=None: nullcontext())
    monkeypatch.setattr(storage, 'owner_storage_write_gate', lambda uid, bucket=None: nullcontext())
    monkeypatch.setattr(merge.conversations_db, 'create_audio_files_from_chunks', lambda uid, cid: ['audio'])
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', DERIVED)
    return buckets


@pytest.mark.parametrize('bucket_name', [PRIVATE, DERIVED])
def test_copy_audio_chunks_pins_source_generation(mock_storage, bucket_name, monkeypatch):
    """When chunks are listed at generation G, copy_blob must pin source_generation=G."""
    src_path = f"chunks/{UID}/conv_1/100.000.bin"
    bucket = mock_storage[bucket_name]
    bucket.objects[src_path] = _MockBlob(bucket, src_path, data=b"original", generation=42)

    chunks = [
        {'path': src_path, 'generation': 42, 'size': 8, 'crc32c': 'crc-1', 'bucket': bucket_name}
    ]
    monkeypatch.setattr(merge, 'list_audio_chunks', lambda uid, cid, **kwargs: chunks)

    conversations = [{'id': 'conv_1', 'started_at': '2026-11-01T00:00:00Z'}]
    merge._copy_audio_chunks_for_merge(UID, conversations, 'new_conv', skip_existing=False)

    dest_path = f"chunks/{UID}/new_conv/100.000.bin"
    assert (src_path, dest_path, 42, None) in bucket.copies


@pytest.mark.parametrize('bucket_name', [PRIVATE, DERIVED])
def test_copy_fails_if_source_chunk_overwritten_before_copy(mock_storage, bucket_name, monkeypatch):
    """If a spanless writer updates source chunk before copy, pinned copy_blob rejects the stale read."""
    src_path = f"chunks/{UID}/conv_1/100.000.bin"
    bucket = mock_storage[bucket_name]
    # Listed at gen 42, but overwritten to gen 43
    bucket.objects[src_path] = _MockBlob(bucket, src_path, data=b"new_bytes", generation=43)

    chunks = [
        {'path': src_path, 'generation': 42, 'size': 8, 'crc32c': 'crc-1', 'bucket': bucket_name}
    ]
    monkeypatch.setattr(merge, 'list_audio_chunks', lambda uid, cid, **kwargs: chunks)

    conversations = [{'id': 'conv_1', 'started_at': '2026-11-01T00:00:00Z'}]
    with pytest.raises(PreconditionFailed):
        merge._copy_audio_chunks_for_merge(UID, conversations, 'new_conv', skip_existing=False)


@pytest.mark.parametrize('bucket_name', [PRIVATE, DERIVED])
def test_delete_audio_chunks_pins_generation_and_preserves_overwritten_chunks(mock_storage, bucket_name):
    """If a chunk was overwritten to G2 after merge listed/copied G1, delete pins G1 and preserves G2."""
    src_path = f"chunks/{UID}/conv_1/100.000.bin"
    bucket = mock_storage[bucket_name]
    # Overwritten to generation 99
    bucket.objects[src_path] = _MockBlob(bucket, src_path, data=b"overwritten", generation=99)

    # Delete pins generation 42 (which was copied)
    storage.delete_audio_chunks(UID, 'conv_1', [100.0], generations_by_path={src_path: 42})

    # The newer generation 99 blob MUST NOT be deleted
    assert src_path in bucket.objects
    assert bucket.objects[src_path].generation == 99


@pytest.mark.parametrize('bucket_name', [PRIVATE, DERIVED])
def test_copy_audio_chunks_skip_existing_pins_source_and_dest_generation(mock_storage, bucket_name, monkeypatch):
    """Under skip_existing=True (used in production merge), copy_blob pins source and dest generations."""
    src_path = f"chunks/{UID}/conv_1/100.000.bin"
    bucket = mock_storage[bucket_name]
    bucket.objects[src_path] = _MockBlob(bucket, src_path, data=b"original", generation=55, crc32c='crc-55')

    chunks = [
        {'path': src_path, 'generation': 55, 'size': 8, 'crc32c': 'crc-55', 'bucket': bucket_name}
    ]
    monkeypatch.setattr(merge, 'list_audio_chunks', lambda uid, cid, **kwargs: chunks)

    out_gens = {}
    conversations = [{'id': 'conv_1', 'started_at': '2026-11-01T00:00:00Z'}]
    merge._copy_audio_chunks_for_merge(UID, conversations, 'new_conv', skip_existing=True, out_generations=out_gens)

    dest_path = f"chunks/{UID}/new_conv/100.000.bin"
    # Fresh destination: if_generation_match=0, source_generation=55
    assert (src_path, dest_path, 55, 0) in bucket.copies
    assert out_gens.get((bucket_name, src_path)) == 55
    assert out_gens.get(src_path) == 55


@pytest.mark.parametrize('bucket_name', [PRIVATE, DERIVED])
def test_delete_audio_chunks_fails_closed_when_path_unpinned_in_supplied_map(mock_storage, bucket_name):
    """When generations_by_path is provided, unpinned paths fail closed (are NOT deleted unconditionally)."""
    p1 = f"chunks/{UID}/conv_1/100.000.bin"
    p2 = f"chunks/{UID}/conv_1/101.000.bin"
    bucket = mock_storage[bucket_name]
    bucket.objects[p1] = _MockBlob(bucket, p1, data=b"chunk1", generation=10)
    bucket.objects[p2] = _MockBlob(bucket, p2, data=b"chunk2", generation=20)

    # Supply generation map pinning p1, but omitting p2
    gens = {(bucket_name, p1): 10}
    storage.delete_audio_chunks(UID, 'conv_1', [100.0, 101.0], generations_by_path=gens)

    # p1 deleted because pinned generation matched
    assert p1 not in bucket.objects
    # p2 preserved because map omitted it (failed closed rather than deleting unconditionally)
    assert p2 in bucket.objects


@pytest.mark.parametrize('bucket_name', [PRIVATE, DERIVED])
def test_delete_conversation_audio_files_pins_generations_and_preserves_overwritten(mock_storage, bucket_name):
    """delete_conversation_audio_files pins chunk generations and preserves unpinned/overwritten blobs."""
    p_pinned = f"chunks/{UID}/conv_1/100.000.bin"
    p_newer = f"chunks/{UID}/conv_1/101.000.bin"
    bucket = mock_storage[bucket_name]
    bucket.objects[p_pinned] = _MockBlob(bucket, p_pinned, data=b"p", generation=10)
    bucket.objects[p_newer] = _MockBlob(bucket, p_newer, data=b"newer", generation=99)

    # Pinned generation map only pins p_pinned at 10
    gens = {(bucket_name, p_pinned): 10}
    storage.delete_conversation_audio_files(UID, 'conv_1', generations_by_path=gens)

    # Pinned blob was deleted
    assert p_pinned not in bucket.objects
    # Newer/unpinned blob was preserved
    assert p_newer in bucket.objects
