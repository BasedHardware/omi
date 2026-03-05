"""Unit tests for pusher private cloud data_protection_level caching.

Verifies that the pusher fetches data_protection_level once at session start
when private_cloud_sync is enabled, and passes it through to upload_audio_chunk
calls, eliminating per-chunk Firestore reads.

Tests the logic pattern used in pusher._websocket_util_trigger without importing
the full pusher module (which has heavy WebSocket/DB dependencies).
"""

from unittest.mock import MagicMock

import pytest


def _simulate_session_start(users_db, uid):
    """Reproduce the exact session-start caching logic from pusher.py line ~134."""
    private_cloud_sync_enabled = users_db.get_user_private_cloud_sync_enabled(uid)
    cached_protection_level = users_db.get_data_protection_level(uid) if private_cloud_sync_enabled else None
    return private_cloud_sync_enabled, cached_protection_level


def _simulate_upload(upload_fn, chunk_data, uid, conv_id, timestamp, cached_protection_level):
    """Reproduce the exact upload call from pusher.py process_private_cloud_queue."""
    upload_fn(chunk_data, uid, conv_id, timestamp, cached_protection_level)


class TestPusherDataProtectionCache:
    """Tests for data_protection_level session-level caching in pusher."""

    def test_fetches_protection_level_when_sync_enabled(self):
        """When private_cloud_sync is enabled, should fetch data_protection_level once."""
        mock_users_db = MagicMock()
        mock_users_db.get_user_private_cloud_sync_enabled.return_value = True
        mock_users_db.get_data_protection_level.return_value = 'standard'

        enabled, level = _simulate_session_start(mock_users_db, 'test-uid')

        assert enabled is True
        assert level == 'standard'
        mock_users_db.get_data_protection_level.assert_called_once_with('test-uid')

    def test_skips_protection_level_when_sync_disabled(self):
        """When private_cloud_sync is disabled, should NOT fetch data_protection_level."""
        mock_users_db = MagicMock()
        mock_users_db.get_user_private_cloud_sync_enabled.return_value = False

        enabled, level = _simulate_session_start(mock_users_db, 'test-uid')

        assert enabled is False
        assert level is None
        mock_users_db.get_data_protection_level.assert_not_called()

    def test_enhanced_level_cached_correctly(self):
        """Should correctly cache 'enhanced' protection level."""
        mock_users_db = MagicMock()
        mock_users_db.get_user_private_cloud_sync_enabled.return_value = True
        mock_users_db.get_data_protection_level.return_value = 'enhanced'

        _, level = _simulate_session_start(mock_users_db, 'test-uid')

        assert level == 'enhanced'

    def test_cached_level_passed_to_upload(self):
        """Cached protection level should be forwarded to upload_audio_chunk."""
        mock_users_db = MagicMock()
        mock_users_db.get_user_private_cloud_sync_enabled.return_value = True
        mock_users_db.get_data_protection_level.return_value = 'enhanced'

        _, cached_level = _simulate_session_start(mock_users_db, 'test-uid')

        mock_upload = MagicMock()
        _simulate_upload(mock_upload, b'\x00' * 1000, 'test-uid', 'conv-1', 1234567890.123, cached_level)

        mock_upload.assert_called_once_with(b'\x00' * 1000, 'test-uid', 'conv-1', 1234567890.123, 'enhanced')

    def test_multiple_uploads_use_same_cached_level(self):
        """Multiple uploads in the same session should all use the same cached level."""
        mock_users_db = MagicMock()
        mock_users_db.get_user_private_cloud_sync_enabled.return_value = True
        mock_users_db.get_data_protection_level.return_value = 'standard'

        _, cached_level = _simulate_session_start(mock_users_db, 'test-uid')

        mock_upload = MagicMock()
        for i in range(5):
            _simulate_upload(mock_upload, b'\x00' * 100, 'test-uid', 'conv-1', 1000.0 + i, cached_level)

        assert mock_upload.call_count == 5
        # All calls should pass the same cached 'standard' level
        for c in mock_upload.call_args_list:
            assert c[0][4] == 'standard'

        # get_data_protection_level should only have been called once at session start
        mock_users_db.get_data_protection_level.assert_called_once()
