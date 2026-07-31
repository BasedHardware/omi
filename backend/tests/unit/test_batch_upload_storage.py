"""Unit tests for upload_audio_chunks_batch (#5418 Phase 2).

Verifies:
1. Batch upload with multiple chunks — streams to the object store
2. Single chunk batch uses single timestamp filename
3. Encrypted batch upload (enhanced protection)
4. Empty batch returns empty list
5. DB lookup count — only one fetch per batch when level is None
6. Unsorted input produces correctly ordered upload

storage.py migrated to the neutral object-store port (ADR-0032); these run against an in-memory
FakeObjectStore at the port seam rather than a raw GCS MagicMock, so they exercise the real path.
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules
from utils.other import storage as storage_mod
from tests.object_store_fakes import FakeObjectStore

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def store(monkeypatch):
    """Point storage.py's object-store seam at a fresh in-memory FakeObjectStore per test."""
    fake = FakeObjectStore()
    monkeypatch.setattr(storage_mod, "_object_store", lambda: fake)
    return fake


def _bucket() -> str:
    return storage_mod.private_cloud_sync_bucket


@pytest.fixture(scope="module")
def merge():
    """Load a fresh ``utils.conversations.merge_conversations`` against stubbed
    database/models/memory/storage chains.

    Mirrors ``tests/unit/test_merge_validation.py``. The module is exec'd inside a
    ``stub_modules`` block so its heavy transitive imports are faked, and the
    freshly-loaded module is evicted from ``sys.modules`` on teardown — keeping the
    suite hermetic regardless of collection/test ordering. The yielded module object
    is the single stable identity that tests patch (via ``monkeypatch.setattr``) and
    read ``_copy_audio_chunks_for_merge`` from, so the function always closes over
    the same module its patches target.
    """
    database_pkg = ModuleType("database")
    database_pkg.__path__ = []  # type: ignore[attr-defined]

    client_stub = ModuleType("database._client")
    client_stub.db = MagicMock(name="db")

    conversations_stub = ModuleType("database.conversations")
    conversations_stub.get_conversation = MagicMock(return_value=None)

    vector_db_stub = ModuleType("database.vector_db")
    vector_db_stub.delete_vector = MagicMock()

    # utils.other.storage is stubbed (not imported real) so the merge module's
    # ``_object_store`` / ``list_audio_chunks`` / ``private_cloud_sync_bucket``
    # references resolve to fakes that tests then override via monkeypatch.
    storage_stub = ModuleType("utils.other.storage")
    for _name in [
        "compute_audio_files_fingerprint",
        "delete_conversation_audio_files",
        "enqueue_conversation_artifact_build",
        "list_audio_chunks",
        "_object_store",
        "private_cloud_sync_bucket",
        "_get_extension_for_path",
    ]:
        setattr(storage_stub, _name, MagicMock())

    cloud_tasks_stub = ModuleType("utils.cloud_tasks")
    cloud_tasks_stub.is_audio_merge_dispatch_enabled = MagicMock(return_value=False)

    models_pkg = ModuleType("models")
    models_pkg.__path__ = []  # type: ignore[attr-defined]
    model_submods = {
        "models.audio_file": ["AudioFile"],
        "models.conversation": ["Conversation"],
        "models.conversation_enums": ["ConversationStatus"],
        "models.structured": ["Structured"],
    }
    model_stubs: dict[str, ModuleType] = {}
    for _modname, _attrs in model_submods.items():
        _mod = ModuleType(_modname)
        for _attr in _attrs:
            setattr(_mod, _attr, MagicMock())
        model_stubs[_modname] = _mod

    memory_service_stub = ModuleType("utils.memory.memory_service")
    setattr(memory_service_stub, "MemoryService", MagicMock())

    class _MemorySystem:
        LEGACY = "legacy"
        CANONICAL = "canonical"

    memory_system_stub = ModuleType("utils.memory.memory_system")
    setattr(memory_system_stub, "MemorySystem", _MemorySystem)

    canonical_activation_stub = ModuleType("utils.memory.canonical_activation")
    setattr(canonical_activation_stub, "canonical_write_enabled", MagicMock(return_value=False))

    surface_routing_stub = ModuleType("utils.memory.surface_routing")
    setattr(surface_routing_stub, "pin_memory_system", MagicMock(return_value=_MemorySystem.LEGACY))

    # These tests exercise the merge module's audio-copy helper only. Stub the
    # lifecycle boundary so the fixture remains isolated from its unrelated
    # durable-finalization dependencies.
    lifecycle_stub = ModuleType("utils.conversations.lifecycle")

    fakes: dict[str, ModuleType] = {
        "database": database_pkg,
        "database._client": client_stub,
        "database.conversations": conversations_stub,
        "database.vector_db": vector_db_stub,
        "utils.cloud_tasks": cloud_tasks_stub,
        "utils.other.storage": storage_stub,
        "models": models_pkg,
        "utils.memory.memory_service": memory_service_stub,
        "utils.memory.memory_system": memory_system_stub,
        "utils.memory.canonical_activation": canonical_activation_stub,
        "utils.memory.surface_routing": surface_routing_stub,
        "utils.conversations.lifecycle": lifecycle_stub,
    }
    fakes.update(model_stubs)

    with stub_modules(fakes):
        module = load_module_fresh(
            "utils.conversations.merge_conversations",
            os.path.join(str(_BACKEND), "utils", "conversations", "merge_conversations.py"),
        )
        yield module


class TestBatchUpload:
    """Tests for upload_audio_chunks_batch streaming to the object store."""

    @patch.object(storage_mod, 'users_db')
    def test_batch_multiple_chunks_standard(self, mock_users_db, store):
        """Multiple chunks streamed as single .batch.bin object."""
        chunks = [
            {'data': b'\x01' * 100, 'timestamp': 1000.000},
            {'data': b'\x02' * 100, 'timestamp': 1005.000},
            {'data': b'\x03' * 100, 'timestamp': 1010.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks, uid='test-uid', conversation_id='conv-1', data_protection_level='standard'
        )

        assert len(paths) == 1
        assert paths[0].endswith('.batch.bin')
        assert '1000.000-1010.000' in paths[0]
        written = store.get_bytes(_bucket(), paths[0])
        assert len(written) == 300
        assert written[:100] == b'\x01' * 100
        assert written[100:200] == b'\x02' * 100
        assert written[200:] == b'\x03' * 100

    @patch.object(storage_mod, 'users_db')
    def test_single_chunk_batch(self, mock_users_db, store):
        """Single chunk batch uses single timestamp in filename."""
        paths = storage_mod.upload_audio_chunks_batch(
            chunks=[{'data': b'\x01' * 50, 'timestamp': 1000.000}],
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        assert len(paths) == 1
        assert '1000.000.batch.bin' in paths[0]
        assert store.exists(_bucket(), paths[0])

    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'users_db')
    def test_batch_encrypted(self, mock_users_db, mock_encryption, store):
        """Enhanced protection encrypts each chunk and streams to the object store."""
        mock_encryption.encrypt_audio_chunk.return_value = b'\xee' * 120

        chunks = [
            {'data': b'\x01' * 100, 'timestamp': 1000.000},
            {'data': b'\x02' * 100, 'timestamp': 1005.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks, uid='test-uid', conversation_id='conv-1', data_protection_level='enhanced'
        )

        assert len(paths) == 1
        assert paths[0].endswith('.batch.enc')
        assert mock_encryption.encrypt_audio_chunk.call_count == 2
        assert len(store.get_bytes(_bucket(), paths[0])) == 240

    @patch.object(storage_mod, 'users_db')
    def test_empty_batch_returns_empty(self, mock_users_db, store):
        """Empty chunk list returns empty list without any storage ops."""
        paths = storage_mod.upload_audio_chunks_batch(
            chunks=[], uid='test-uid', conversation_id='conv-1', data_protection_level='standard'
        )

        assert paths == []
        assert store.list(_bucket(), '') == []  # nothing written

    @patch.object(storage_mod, 'users_db')
    def test_db_lookup_once_per_batch(self, mock_users_db, store):
        """When data_protection_level is None, DB is queried exactly once per batch."""
        mock_users_db.get_data_protection_level.return_value = 'standard'

        chunks = [
            {'data': b'\x01' * 50, 'timestamp': 1000.000},
            {'data': b'\x02' * 50, 'timestamp': 1005.000},
            {'data': b'\x03' * 50, 'timestamp': 1010.000},
        ]

        storage_mod.upload_audio_chunks_batch(chunks=chunks, uid='test-uid', conversation_id='conv-1')

        mock_users_db.get_data_protection_level.assert_called_once_with('test-uid')

    @patch.object(storage_mod, 'users_db')
    def test_unsorted_input_produces_ordered_upload(self, mock_users_db, store):
        """Chunks provided out of order are sorted by timestamp before upload."""
        chunks = [
            {'data': b'\x03' * 50, 'timestamp': 1010.000},
            {'data': b'\x01' * 50, 'timestamp': 1000.000},
            {'data': b'\x02' * 50, 'timestamp': 1005.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks, uid='test-uid', conversation_id='conv-1', data_protection_level='standard'
        )

        assert '1000.000-1010.000' in paths[0]
        written = store.get_bytes(_bucket(), paths[0])
        assert written[:50] == b'\x01' * 50
        assert written[50:100] == b'\x02' * 50
        assert written[100:] == b'\x03' * 50

    @patch.object(storage_mod, 'users_db')
    def test_skips_db_when_level_provided(self, mock_users_db, store):
        """When data_protection_level is explicitly provided, no DB read."""
        storage_mod.upload_audio_chunks_batch(
            chunks=[{'data': b'\x01' * 50, 'timestamp': 1000.000}],
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        mock_users_db.get_data_protection_level.assert_not_called()

    @patch.object(storage_mod, 'users_db')
    def test_large_batch_streams_correctly(self, mock_users_db, store):
        """Large batch (50 chunks) streams without regression."""
        chunks = [{'data': b'\xaa' * 80_000, 'timestamp': 1000.000 + i * 5.0} for i in range(50)]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks, uid='test-uid', conversation_id='conv-1', data_protection_level='standard'
        )

        assert len(paths) == 1
        assert paths[0].endswith('.batch.bin')
        assert len(store.get_bytes(_bucket(), paths[0])) == 50 * 80_000  # every chunk streamed

    @patch.object(storage_mod, 'users_db')
    def test_identical_timestamps_filename_and_order(self, mock_users_db, store):
        """Chunks with identical timestamps produce valid filename and stable order."""
        chunks = [
            {'data': b'\x01' * 50, 'timestamp': 1000.000},
            {'data': b'\x02' * 50, 'timestamp': 1000.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks, uid='test-uid', conversation_id='conv-1', data_protection_level='standard'
        )

        assert len(paths) == 1
        assert '1000.000.batch.bin' in paths[0]

    @patch.object(storage_mod, 'users_db')
    def test_streaming_writes_full_payload(self, mock_users_db, store):
        """Batch mode streams the chunk bytes to a single object."""
        storage_mod.upload_audio_chunks_batch(
            chunks=[{'data': b'\x01' * 50, 'timestamp': 1000.000}],
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        objs = store.list(_bucket(), 'chunks/test-uid/conv-1/')
        assert len(objs) == 1
        assert store.get_bytes(_bucket(), objs[0].key) == b'\x01' * 50


class TestListAudioChunksBatchAware:
    """Tests for list_audio_chunks handling .batch.bin/.batch.enc files."""

    def _seed(self, store, blob_names):
        for name in blob_names:
            store.put(_bucket(), name, b'x')

    def test_list_per_chunk_files(self, store):
        """Standard per-chunk .bin files are listed correctly."""
        self._seed(store, ['chunks/uid/conv/1000.000.bin', 'chunks/uid/conv/1005.000.bin'])
        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 2
        assert result[0]['timestamp'] == 1000.000
        assert result[1]['timestamp'] == 1005.000

    def test_list_batch_bin_file(self, store):
        """Batch .batch.bin file is listed with first timestamp."""
        self._seed(store, ['chunks/uid/conv/1000.000-1010.000.batch.bin'])
        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 1
        assert result[0]['timestamp'] == 1000.000
        assert result[0]['is_batch'] is True

    def test_list_batch_enc_file(self, store):
        """Batch .batch.enc file is listed with first timestamp."""
        self._seed(store, ['chunks/uid/conv/1000.000-1010.000.batch.enc'])
        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 1
        assert result[0]['timestamp'] == 1000.000
        assert result[0]['is_batch'] is True

    def test_list_single_chunk_batch(self, store):
        """Single-chunk batch file (no range) is listed correctly."""
        self._seed(store, ['chunks/uid/conv/1000.000.batch.bin'])
        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 1
        assert result[0]['timestamp'] == 1000.000
        assert result[0]['is_batch'] is True

    def test_list_mixed_per_chunk_and_batch(self, store):
        """Mixed per-chunk and batch files are all listed and sorted."""
        self._seed(
            store,
            [
                'chunks/uid/conv/1010.000-1020.000.batch.bin',
                'chunks/uid/conv/1000.000.bin',
                'chunks/uid/conv/1005.000.bin',
            ],
        )
        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 3
        assert result[0]['timestamp'] == 1000.000
        assert result[0]['is_batch'] is False
        assert result[1]['timestamp'] == 1005.000
        assert result[2]['timestamp'] == 1010.000
        assert result[2]['is_batch'] is True

    def test_list_skips_meta_json(self, store):
        """Meta JSON files are not listed as chunks."""
        self._seed(store, ['chunks/uid/conv/1000.000.bin', 'chunks/uid/conv/1000.000.meta.json'])
        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 1

    def test_per_chunk_has_is_batch_false(self, store):
        """Per-chunk files have is_batch=False."""
        self._seed(store, ['chunks/uid/conv/1000.000.enc'])
        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert result[0]['is_batch'] is False


class TestDeleteAudioChunksBatchAware:
    """Tests for delete_audio_chunks handling batch files."""

    def test_delete_per_chunk_by_timestamp(self, store):
        """Per-chunk files are deleted by exact timestamp match."""
        path = 'chunks/uid/conv/1000.000.bin'
        store.put(_bucket(), path, b'x')
        storage_mod.delete_audio_chunks('uid', 'conv', [1000.000])
        assert not store.exists(_bucket(), path)

    def test_delete_batch_by_start_timestamp(self, store):
        """Batch files are deleted when start timestamp matches (found via scan)."""
        path = 'chunks/uid/conv/1000.000-1010.000.batch.bin'
        store.put(_bucket(), path, b'x')
        storage_mod.delete_audio_chunks('uid', 'conv', [1000.000])
        assert not store.exists(_bucket(), path)

    def test_delete_tries_batch_extensions(self, store):
        """Direct lookup tries .batch.enc / .batch.bin extensions."""
        path = 'chunks/uid/conv/1000.000.batch.enc'
        store.put(_bucket(), path, b'x')
        storage_mod.delete_audio_chunks('uid', 'conv', [1000.000])
        assert not store.exists(_bucket(), path)


class TestDownloadAudioChunksMergeBatchAware:
    """Tests for download_audio_chunks_and_merge handling batch blobs."""

    def test_download_batch_blob_found(self, store):
        """Batch blob is resolved via list_audio_chunks and downloaded."""
        batch_path = 'chunks/uid/conv/1000.000-1010.000.batch.bin'
        batch_data = b'\x01' * 100 + b'\x02' * 100
        store.put(_bucket(), batch_path, batch_data)

        result = storage_mod.download_audio_chunks_and_merge(
            uid='uid', conversation_id='conv', timestamps=[1000.000], fill_gaps=False
        )

        assert result == batch_data

    def test_download_per_chunk_still_works(self, store):
        """Per-chunk .bin files are still downloaded correctly."""
        store.put(_bucket(), 'chunks/uid/conv/1000.000.bin', b'\x01' * 100)
        store.put(_bucket(), 'chunks/uid/conv/1005.000.bin', b'\x02' * 100)

        result = storage_mod.download_audio_chunks_and_merge(
            uid='uid', conversation_id='conv', timestamps=[1000.000, 1005.000], fill_gaps=False
        )

        assert result == b'\x01' * 100 + b'\x02' * 100

    def test_download_batch_deduplicates(self, store):
        """Multiple timestamps pointing to same batch blob download it once."""
        batch_path = 'chunks/uid/conv/1000.000-1010.000.batch.bin'
        batch_data = b'\xaa' * 300
        store.put(_bucket(), batch_path, batch_data)

        downloads = []
        orig = store.get_bytes
        store.get_bytes = lambda b, k: (downloads.append(k), orig(b, k))[1]

        result = storage_mod.download_audio_chunks_and_merge(
            uid='uid', conversation_id='conv', timestamps=[1000.000], fill_gaps=False
        )

        assert result == batch_data
        assert len([p for p in downloads if 'batch' in p]) == 1

    @patch.object(storage_mod, 'encryption')
    def test_download_batch_encrypted_decrypts(self, mock_encryption, store):
        """Encrypted batch blob is decrypted via decrypt_audio_file."""
        batch_path = 'chunks/uid/conv/1000.000-1010.000.batch.enc'
        encrypted_data = b'\xee' * 200
        decrypted_data = b'\xdd' * 180
        mock_encryption.decrypt_audio_file.return_value = decrypted_data
        store.put(_bucket(), batch_path, encrypted_data)

        result = storage_mod.download_audio_chunks_and_merge(
            uid='uid', conversation_id='conv', timestamps=[1000.000], fill_gaps=False
        )

        mock_encryption.decrypt_audio_file.assert_called_once_with(encrypted_data, 'uid')
        assert result == decrypted_data


class TestCopyAudioChunksForMergeBatchAware:
    """Tests for _copy_audio_chunks_for_merge preserving batch blob filenames."""

    def _wire(self, merge, monkeypatch):
        store = FakeObjectStore()
        mock_conv_db = MagicMock()
        mock_conv_db.create_audio_files_from_chunks.return_value = []
        monkeypatch.setattr(merge, '_object_store', lambda: store)
        monkeypatch.setattr(merge, 'private_cloud_sync_bucket', 'omi-private-cloud-sync')
        monkeypatch.setattr(merge, 'conversations_db', mock_conv_db)
        return store

    def test_copy_preserves_batch_filename(self, merge, monkeypatch):
        """Batch blob filenames are preserved during copy (not renamed to single-timestamp)."""
        store = self._wire(merge, monkeypatch)
        src = 'chunks/uid/conv-old/1000.000-1060.000.batch.bin'
        store.put('omi-private-cloud-sync', src, b'audio')
        monkeypatch.setattr(
            merge, 'list_audio_chunks', lambda uid, cid: [{'timestamp': 1000.0, 'path': src, 'size': 9, 'is_batch': True}]
        )

        merge._copy_audio_chunks_for_merge('uid', [{'id': 'conv-old'}], 'conv-new')

        assert store.exists('omi-private-cloud-sync', 'chunks/uid/conv-new/1000.000-1060.000.batch.bin')

    def test_copy_preserves_single_chunk_filename(self, merge, monkeypatch):
        """Single-chunk filenames are also preserved during copy."""
        store = self._wire(merge, monkeypatch)
        src = 'chunks/uid/conv-old/1000.000.bin'
        store.put('omi-private-cloud-sync', src, b'audio')
        monkeypatch.setattr(
            merge, 'list_audio_chunks', lambda uid, cid: [{'timestamp': 1000.0, 'path': src, 'size': 5, 'is_batch': False}]
        )

        merge._copy_audio_chunks_for_merge('uid', [{'id': 'conv-old'}], 'conv-new')

        assert store.exists('omi-private-cloud-sync', 'chunks/uid/conv-new/1000.000.bin')

    def test_copy_mixed_single_and_batch(self, merge, monkeypatch):
        """Mixed single + batch blobs are all copied with original filenames."""
        store = self._wire(merge, monkeypatch)
        src_single = 'chunks/uid/conv-old/1000.000.enc'
        src_batch = 'chunks/uid/conv-old/1010.000-1070.000.batch.enc'
        store.put('omi-private-cloud-sync', src_single, b'a')
        store.put('omi-private-cloud-sync', src_batch, b'b')
        monkeypatch.setattr(
            merge,
            'list_audio_chunks',
            lambda uid, cid: [
                {'timestamp': 1000.0, 'path': src_single, 'size': 1, 'is_batch': False},
                {'timestamp': 1010.0, 'path': src_batch, 'size': 1, 'is_batch': True},
            ],
        )

        merge._copy_audio_chunks_for_merge('uid', [{'id': 'conv-old'}], 'conv-new')

        assert store.exists('omi-private-cloud-sync', 'chunks/uid/conv-new/1000.000.enc')
        assert store.exists('omi-private-cloud-sync', 'chunks/uid/conv-new/1010.000-1070.000.batch.enc')
