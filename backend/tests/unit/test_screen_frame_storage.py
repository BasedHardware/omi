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


class TestSignedUrlReportsTheTrueExpiry:
    """Signed URLs are cached ~60 min; a cache hit must report the cached signature's
    remaining life, and a nearly dead cached URL must not be handed out at all."""

    def _blob(self):
        blob = MagicMock()
        blob.name = "u/c/f.jpg"
        blob.generate_signed_url.return_value = "https://fresh"
        return blob

    def test_cache_hit_reports_remaining_life(self, monkeypatch):
        import datetime as dt

        monkeypatch.setattr(storage_mod, "get_cached_signed_url", lambda path: "https://cached")
        monkeypatch.setattr(storage_mod, "get_cached_signed_url_ttl", lambda path: 20 * 60)
        blob = self._blob()
        before = dt.datetime.now(dt.timezone.utc)

        url, expires_at = storage_mod._screen_frame_signed_url(blob)

        assert url == "https://cached"
        assert dt.timedelta(minutes=19) < expires_at - before <= dt.timedelta(minutes=20, seconds=1)
        blob.generate_signed_url.assert_not_called()

    def test_nearly_expired_cache_entry_is_re_signed(self, monkeypatch):
        import datetime as dt

        cached: list = []
        monkeypatch.setattr(storage_mod, "get_cached_signed_url", lambda path: "https://cached")
        monkeypatch.setattr(storage_mod, "get_cached_signed_url_ttl", lambda path: 5 * 60)
        monkeypatch.setattr(storage_mod, "cache_signed_url", lambda *args: cached.append(args))
        monkeypatch.setattr(storage_mod, "iam_signing_kwargs", lambda client: {})
        before = dt.datetime.now(dt.timezone.utc)

        url, expires_at = storage_mod._screen_frame_signed_url(self._blob())

        assert url == "https://fresh"
        assert expires_at - before >= dt.timedelta(minutes=59)
        assert cached == [("u/c/f.jpg", "https://fresh", 3600)]


def test_frame_download_disables_the_library_retry_so_the_caller_budget_holds(monkeypatch):
    bucket = MagicMock()
    storage_mod.storage_client.bucket.return_value = bucket
    blob = bucket.blob.return_value
    blob.download_as_bytes.return_value = b"jpeg"

    assert storage_mod.download_screen_frame_bytes(UID, CONVERSATION_ID, FRAME_ID, timeout=2.5) == b"jpeg"
    blob.download_as_bytes.assert_called_once_with(timeout=2.5, retry=None)
