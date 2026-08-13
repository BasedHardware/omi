"""Unit tests for upload_audio_chunk data_protection_level caching.

Verifies that when data_protection_level is passed to upload_audio_chunk(),
the per-chunk Firestore read (users_db.get_data_protection_level) is skipped.
When not provided, falls back to the DB read for backward compatibility.
"""

import os
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_STORAGE_PY = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "utils", "other", "storage.py"))


@pytest.fixture(scope="module")
def storage_mod():
    """Load ``utils.other.storage`` cred-free.

    ``storage.py`` constructs ``storage.Client(...)`` at import time, which calls
    ``google.auth.default()`` and raises ``DefaultCredentialsError`` in cred-less
    environments (CI / local dev). Stubbing ``google.cloud.storage`` before the
    fresh load makes that construction a no-op MagicMock. The ``stub_modules``
    block self-restores on exit (the loaded module is evicted from ``sys.modules``
    so it cannot leak to other test files); this fixture hands the test a direct
    reference to the freshly loaded module.
    """
    fake_gcs = AutoMockModule("google.cloud.storage")
    with stub_modules({"google.cloud.storage": fake_gcs}):
        yield load_module_fresh("utils.other.storage", _STORAGE_PY)


class TestUploadAudioChunkDataProtectionCache:
    """Tests for the data_protection_level caching in upload_audio_chunk."""

    @pytest.fixture(autouse=True)
    def _stub_storage_seams(self, storage_mod, monkeypatch):
        monkeypatch.setattr(storage_mod, "encode_pcm_to_opus", lambda chunk_data: chunk_data)
        monkeypatch.setattr(storage_mod, "storage_client", MagicMock())

    def _setup_mock_bucket(self, storage_mod):
        """Set up mock bucket and blob for upload tests."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        storage_mod.storage_client.bucket.return_value = mock_bucket
        return mock_bucket, mock_blob

    def test_skips_db_read_when_level_provided(self, storage_mod, monkeypatch):
        """When data_protection_level is passed, should NOT call Firestore."""
        mock_users_db = MagicMock()
        monkeypatch.setattr(storage_mod, "users_db", mock_users_db)
        self._setup_mock_bucket(storage_mod)

        storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 100,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='standard',
        )

        mock_users_db.get_data_protection_level.assert_not_called()

    def test_falls_back_to_db_when_level_not_provided(self, storage_mod, monkeypatch):
        """When data_protection_level is None (default), should read from Firestore."""
        mock_users_db = MagicMock()
        mock_users_db.get_data_protection_level.return_value = 'standard'
        monkeypatch.setattr(storage_mod, "users_db", mock_users_db)
        self._setup_mock_bucket(storage_mod)

        storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 100,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
        )

        mock_users_db.get_data_protection_level.assert_called_once_with('test-uid')

    def test_standard_level_uploads_unencrypted(self, storage_mod, monkeypatch):
        """Standard protection level should upload unencrypted Opus audio."""
        mock_users_db = MagicMock()
        monkeypatch.setattr(storage_mod, "users_db", mock_users_db)
        _, mock_blob = self._setup_mock_bucket(storage_mod)

        path = storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 100,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='standard',
        )

        assert path.endswith('.opus')
        mock_blob.upload_from_string.assert_called_once()

    def test_enhanced_level_uploads_encrypted(self, storage_mod, monkeypatch):
        """Enhanced protection level should encrypt and upload .enc."""
        mock_users_db = MagicMock()
        monkeypatch.setattr(storage_mod, "users_db", mock_users_db)
        mock_encryption = MagicMock()
        mock_encryption.encrypt_audio_chunk.return_value = b'\x01' * 120
        monkeypatch.setattr(storage_mod, "encryption", mock_encryption)
        _, mock_blob = self._setup_mock_bucket(storage_mod)

        path = storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 100,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='enhanced',
        )

        assert path.endswith('.enc')
        mock_encryption.encrypt_audio_chunk.assert_called_once_with(b'\x00' * 100, 'test-uid')

    def test_explicit_none_falls_back_to_db(self, storage_mod, monkeypatch):
        """Explicitly passing None should still fall back to DB read."""
        mock_users_db = MagicMock()
        mock_users_db.get_data_protection_level.return_value = 'standard'
        monkeypatch.setattr(storage_mod, "users_db", mock_users_db)
        self._setup_mock_bucket(storage_mod)

        storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 100,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level=None,
        )

        mock_users_db.get_data_protection_level.assert_called_once_with('test-uid')
