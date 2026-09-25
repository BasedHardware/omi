"""Tests for utils/screen_frames/store.py — the composite (Firestore + GCS)
operations, in particular delete_conversation_screen_frames: contract §8
requires a delete to close the loop on the Firestore doc AND both GCS
objects for every frame, not just remove the Firestore record.
"""

from unittest.mock import MagicMock

from utils.screen_frames import store as store_mod

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
        monkeypatch.setattr(store_mod, "storage", fake_storage)

        assert store_mod.delete_conversation_screen_frames(UID, CONVERSATION_ID) == 0
        fake_storage.delete_screen_frame_blobs.assert_not_called()


class TestDeleteSingleScreenFrame:
    def test_deletes_firestore_doc_and_gcs_blobs(self, monkeypatch):
        fake_screen_frames_db = MagicMock()
        fake_screen_frames_db.delete_conversation_screen_frame_doc.return_value = True
        monkeypatch.setattr(store_mod, "screen_frames_db", fake_screen_frames_db)

        fake_storage = MagicMock()
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
        monkeypatch.setattr(store_mod, "screen_frames_db", fake_screen_frames_db)

        fake_storage = MagicMock()
        monkeypatch.setattr(store_mod, "storage", fake_storage)

        existed = store_mod.delete_screen_frame(UID, CONVERSATION_ID, "frame-a")

        assert existed is False
        fake_storage.delete_screen_frame_blobs.assert_called_once_with(UID, CONVERSATION_ID, "frame-a")
