"""Tests for the screen-frame GCS helpers in utils/other/storage.py
(contract §8): the object path convention, and — the specific property the
task calls out — that deleting a frame closes the loop on BOTH GCS objects
(content + thumbnail) and their cached signed URLs, not just one.
"""

from unittest.mock import MagicMock

import pytest

import utils.other.storage as storage_mod

UID = "user-1"
CONVERSATION_ID = "conv-1"
FRAME_ID = "frame-1"


@pytest.fixture(autouse=True)
def _stub_storage_client(monkeypatch):
    monkeypatch.setattr(storage_mod, "storage_client", MagicMock())
    monkeypatch.setattr(storage_mod, "screen_frames_bucket", "test-screen-frames-bucket")


class TestBlobPaths:
    def test_content_and_thumbnail_paths_are_distinct_and_scoped_by_uid(self):
        content_path = storage_mod._screen_frame_blob_path(UID, CONVERSATION_ID, FRAME_ID)
        thumb_path = storage_mod._screen_frame_thumbnail_blob_path(UID, CONVERSATION_ID, FRAME_ID)
        assert content_path == f"{UID}/{CONVERSATION_ID}/{FRAME_ID}.jpg"
        assert thumb_path == f"{UID}/{CONVERSATION_ID}/{FRAME_ID}_thumb.jpg"
        assert content_path != thumb_path


class TestUploadWritesBothBlobs:
    def test_upload_writes_content_and_thumbnail(self, monkeypatch):
        mock_bucket = MagicMock()
        storage_mod.storage_client.bucket.return_value = mock_bucket
        blobs_created = []

        def _blob(path):
            b = MagicMock()
            b.path = path
            blobs_created.append(b)
            return b

        mock_bucket.blob.side_effect = _blob

        storage_mod.upload_screen_frame_blobs(UID, CONVERSATION_ID, FRAME_ID, b"content-bytes", b"thumb-bytes")

        assert len(blobs_created) == 2
        blobs_created[0].upload_from_string.assert_called_once_with(b"content-bytes", content_type="image/jpeg")
        blobs_created[1].upload_from_string.assert_called_once_with(b"thumb-bytes", content_type="image/jpeg")


class TestDeleteClosesBothObjectsAndCache:
    def test_delete_removes_both_gcs_objects_and_both_cached_urls(self, monkeypatch):
        deleted_paths = []
        evicted_cache_paths = []

        monkeypatch.setattr(
            storage_mod, "delete_blob", lambda bucket, path: deleted_paths.append((bucket, path)) or True
        )
        monkeypatch.setattr(storage_mod, "delete_cached_signed_url", lambda path: evicted_cache_paths.append(path))

        storage_mod.delete_screen_frame_blobs(UID, CONVERSATION_ID, FRAME_ID)

        content_path = storage_mod._screen_frame_blob_path(UID, CONVERSATION_ID, FRAME_ID)
        thumb_path = storage_mod._screen_frame_thumbnail_blob_path(UID, CONVERSATION_ID, FRAME_ID)

        assert deleted_paths == [
            ("test-screen-frames-bucket", content_path),
            ("test-screen-frames-bucket", thumb_path),
        ]
        assert set(evicted_cache_paths) == {content_path, thumb_path}

    def test_delete_is_unconditional_even_if_one_object_was_already_missing(self, monkeypatch):
        # delete_blob returning False (NotFound) must not stop the thumbnail
        # delete or the cache eviction — a delete that leaves anything behind
        # is a bug, not a partial success.
        calls = []
        monkeypatch.setattr(storage_mod, "delete_blob", lambda bucket, path: calls.append(path) or False)
        evicted = []
        monkeypatch.setattr(storage_mod, "delete_cached_signed_url", lambda path: evicted.append(path))

        storage_mod.delete_screen_frame_blobs(UID, CONVERSATION_ID, FRAME_ID)

        assert len(calls) == 2
        assert len(evicted) == 2
