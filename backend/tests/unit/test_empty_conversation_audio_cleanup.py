"""Automatic empty-generation teardown retains audio independently of the row."""

import logging
from unittest.mock import Mock, call

import pytest

from utils.conversations import lifecycle
from utils.other import storage


@pytest.fixture
def storage_boundaries(monkeypatch):
    bucket = Mock()
    client = Mock()
    client.bucket.return_value = bucket
    monkeypatch.setattr(storage, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'private-sync')
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    photos = Mock()
    monkeypatch.setattr(lifecycle.conversations_db, 'delete_conversation_photos', photos)
    return bucket, photos


def test_committed_empty_generation_only_lists_raw_prefixes(monkeypatch, storage_boundaries, caplog):
    bucket, photos = storage_boundaries
    delete = Mock(return_value=True)
    monkeypatch.setattr(lifecycle.recording_sessions_db, 'tombstone_and_delete_empty_conversation', delete)
    objects = [Mock(), Mock(), Mock()]
    bucket.list_blobs.side_effect = [[objects[0], objects[1]], [], [objects[2]]]

    with caplog.at_level(logging.INFO, logger=lifecycle.__name__):
        assert lifecycle.delete_empty_recording_conversation('uid', 'conversation', 'recording') is True

    delete.assert_called_once_with('uid', 'conversation', 'recording')
    photos.assert_called_once_with('uid', 'conversation')
    # Inventory is conversation-scoped and never accesses derived or owner-wide prefixes.
    assert bucket.mock_calls == [
        call.list_blobs(prefix=f'{prefix}/uid/conversation/') for prefix in ('chunks', 'audio', 'raw-live')
    ]
    for blob in objects:
        blob.delete.assert_not_called()
    records = [record for record in caplog.records if record.message.startswith('Retained audio for empty')]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert 'retained_raw_objects=3 count_error=none' in records[0].message


def test_refused_delete_never_touches_audio(monkeypatch, storage_boundaries):
    bucket, photos = storage_boundaries
    monkeypatch.setattr(
        lifecycle.recording_sessions_db, 'tombstone_and_delete_empty_conversation', Mock(return_value=False)
    )

    assert lifecycle.delete_empty_recording_conversation('uid', 'conversation', 'recording') is False

    assert bucket.mock_calls == []
    photos.assert_not_called()


def test_failed_inventory_preserves_success_after_row_is_gone(monkeypatch, storage_boundaries, caplog):
    bucket, photos = storage_boundaries
    monkeypatch.setattr(
        lifecycle.recording_sessions_db, 'tombstone_and_delete_empty_conversation', Mock(return_value=True)
    )
    bucket.list_blobs.side_effect = RuntimeError('storage unavailable')

    with caplog.at_level(logging.INFO, logger=lifecycle.__name__):
        assert lifecycle.delete_empty_recording_conversation('uid', 'conversation', 'recording') is True

    photos.assert_called_once_with('uid', 'conversation')
    records = [record for record in caplog.records if record.message.startswith('Retained audio for empty')]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert records[0].exc_info is None
    assert 'retained_raw_objects=unknown count_error=RuntimeError' in records[0].message
