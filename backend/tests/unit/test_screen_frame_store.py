"""Tests for utils/screen_frames/store.py — the composite (Firestore + GCS)
operations, in particular delete_conversation_screen_frames: contract §8
requires a delete to close the loop on the Firestore doc AND both GCS
objects for every frame, not just remove the Firestore record.
"""

from unittest.mock import MagicMock

from utils.screen_frames import store as store_mod
from utils.screen_frames.environment import LEGACY_SCREEN_FRAMES_BUCKET

PROD_BUCKET = "based-hardware-prod-screen-frames"
UID = "user-1"
CONVERSATION_ID = "conv-1"


class TestDeleteConversationScreenFramesClosesTheLoop:
    def test_deletes_gcs_blobs_for_every_frame_then_the_firestore_docs(self, monkeypatch):
        fake_screen_frames_db = MagicMock()
        fake_screen_frames_db.get_conversation_screen_frames.return_value = [
            {"id": "frame-a"},
            {"id": "frame-b"},
        ]
        fake_screen_frames_db.delete_conversation_screen_frame_docs.return_value = 2
        monkeypatch.setattr(store_mod, "screen_frames_db", fake_screen_frames_db)

        fake_storage = MagicMock()
        fake_storage.configured_screen_frames_bucket.return_value = LEGACY_SCREEN_FRAMES_BUCKET
        monkeypatch.setattr(store_mod, "storage", fake_storage)

        deleted_count = store_mod.delete_conversation_screen_frames(UID, CONVERSATION_ID)

        assert deleted_count == 2
        assert fake_storage.delete_screen_frame_blobs.call_count == 2
        fake_storage.delete_screen_frame_blobs.assert_any_call(UID, CONVERSATION_ID, "frame-a")
        fake_storage.delete_screen_frame_blobs.assert_any_call(UID, CONVERSATION_ID, "frame-b")
        fake_screen_frames_db.delete_conversation_screen_frame_docs.assert_called_once_with(UID, CONVERSATION_ID)

    def test_no_frames_is_a_clean_no_op(self, monkeypatch):
        fake_screen_frames_db = MagicMock()
        fake_screen_frames_db.get_conversation_screen_frames.return_value = []
        fake_screen_frames_db.delete_conversation_screen_frame_docs.return_value = 0
        monkeypatch.setattr(store_mod, "screen_frames_db", fake_screen_frames_db)

        fake_storage = MagicMock()
        fake_storage.configured_screen_frames_bucket.return_value = LEGACY_SCREEN_FRAMES_BUCKET
        monkeypatch.setattr(store_mod, "storage", fake_storage)

        assert store_mod.delete_conversation_screen_frames(UID, CONVERSATION_ID) == 0
        fake_storage.delete_screen_frame_blobs.assert_not_called()


class TestDeleteSingleScreenFrame:
    def test_deletes_firestore_doc_and_gcs_blobs(self, monkeypatch):
        fake_screen_frames_db = MagicMock()
        fake_screen_frames_db.delete_conversation_screen_frame_doc.return_value = True
        fake_screen_frames_db.get_conversation_screen_frame_doc.return_value = {"id": "frame-a"}
        monkeypatch.setattr(store_mod, "screen_frames_db", fake_screen_frames_db)

        fake_storage = MagicMock()
        fake_storage.configured_screen_frames_bucket.return_value = LEGACY_SCREEN_FRAMES_BUCKET
        monkeypatch.setattr(store_mod, "storage", fake_storage)

        existed = store_mod.delete_screen_frame(UID, CONVERSATION_ID, "frame-a")

        assert existed is True
        fake_screen_frames_db.delete_conversation_screen_frame_doc.assert_called_once_with(
            UID, CONVERSATION_ID, "frame-a"
        )
        fake_storage.delete_screen_frame_blobs.assert_called_once_with(UID, CONVERSATION_ID, "frame-a")

    def test_gcs_delete_still_runs_even_if_firestore_doc_was_already_gone(self, monkeypatch):
        fake_screen_frames_db = MagicMock()
        fake_screen_frames_db.delete_conversation_screen_frame_doc.return_value = False
        fake_screen_frames_db.get_conversation_screen_frame_doc.return_value = None
        monkeypatch.setattr(store_mod, "screen_frames_db", fake_screen_frames_db)

        fake_storage = MagicMock()
        fake_storage.configured_screen_frames_bucket.return_value = LEGACY_SCREEN_FRAMES_BUCKET
        monkeypatch.setattr(store_mod, "storage", fake_storage)

        existed = store_mod.delete_screen_frame(UID, CONVERSATION_ID, "frame-a")

        assert existed is False
        fake_storage.delete_screen_frame_blobs.assert_called_once_with(UID, CONVERSATION_ID, "frame-a")


class TestFramesBelongToTheBucketThatHoldsTheirBytes:
    """Dev and prod share Firestore; each frame doc records its own bucket."""

    def _fakes(self, monkeypatch, *, configured, frames=(), doc=None):
        fake_db = MagicMock()
        fake_db.get_conversation_screen_frames.return_value = list(frames)
        fake_db.get_conversation_screen_frame_doc.return_value = doc
        fake_db.delete_conversation_screen_frame_docs.return_value = len(frames)
        monkeypatch.setattr(store_mod, "screen_frames_db", fake_db)
        fake_storage = MagicMock()
        fake_storage.configured_screen_frames_bucket.return_value = configured
        monkeypatch.setattr(store_mod, "storage", fake_storage)
        return fake_db, fake_storage

    def test_prod_refuses_to_delete_a_legacy_dev_frame(self, monkeypatch):
        fake_db, fake_storage = self._fakes(monkeypatch, configured=PROD_BUCKET, doc={"id": "frame-a"})

        assert store_mod.delete_screen_frame(UID, CONVERSATION_ID, "frame-a") is False
        fake_db.delete_conversation_screen_frame_doc.assert_not_called()
        fake_storage.delete_screen_frame_blobs.assert_not_called()

    def test_prod_deletes_its_own_frame(self, monkeypatch):
        fake_db, fake_storage = self._fakes(
            monkeypatch, configured=PROD_BUCKET, doc={"id": "frame-a", "storage_bucket": PROD_BUCKET}
        )
        fake_db.delete_conversation_screen_frame_doc.return_value = True

        assert store_mod.delete_screen_frame(UID, CONVERSATION_ID, "frame-a") is True
        fake_storage.delete_screen_frame_blobs.assert_called_once_with(UID, CONVERSATION_ID, "frame-a")

    def test_conversation_delete_reaches_foreign_bytes_best_effort(self, monkeypatch):
        frames = [{"id": "own", "storage_bucket": PROD_BUCKET}, {"id": "legacy"}]
        fake_db, fake_storage = self._fakes(monkeypatch, configured=PROD_BUCKET, frames=frames)

        def delete(uid, cid, fid, **kwargs):
            if kwargs.get("bucket"):
                raise PermissionError("no access to the dev bucket")

        fake_storage.delete_screen_frame_blobs.side_effect = delete

        assert store_mod.delete_conversation_screen_frames(UID, CONVERSATION_ID) == 2
        fake_storage.delete_screen_frame_blobs.assert_any_call(UID, CONVERSATION_ID, "own")
        fake_storage.delete_screen_frame_blobs.assert_any_call(
            UID, CONVERSATION_ID, "legacy", bucket=LEGACY_SCREEN_FRAMES_BUCKET
        )
        fake_db.delete_conversation_screen_frame_docs.assert_called_once_with(UID, CONVERSATION_ID)
