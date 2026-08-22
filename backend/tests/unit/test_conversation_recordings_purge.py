"""Regression test: an unconfigured recordings bucket must not deadlock the account-deletion wipe.

BUCKET_MEMORIES_RECORDINGS was never wired into the backend charts, so `memories_recordings_bucket`
resolved to None in prod and `.bucket(None)` raised ValueError("Cannot determine path without bucket
name"). delete_all_conversation_recordings is a *required* purge step, so that raise aborted
background_wipe_user_data before users_db.delete_user_data(): every account-deletion request failed,
was marked wipe_failed, and was re-enqueued forever with the user's data still in Firestore.

An unconfigured bucket now means "nothing to purge" — uploads resolve the same name, so a deployment
without it cannot have stored recordings. A *real* GCS failure must still block the irreversible
Firestore wipe (test_delete_account_purge_storage.py::test_gcs_failure_blocks_firestore_wipe).
"""

from unittest.mock import MagicMock, patch

import pytest

from utils.other import storage as storage_mod
from tests.object_store_fakes import FakeObjectStore


class TestDeleteAllConversationRecordings:
    def test_unconfigured_bucket_is_a_no_op(self):
        """Before the fix this raised ValueError and blocked the whole account wipe."""
        store = MagicMock()
        with patch.object(storage_mod, "memories_recordings_bucket", None), patch.object(
            storage_mod, "_object_store", return_value=store
        ):
            assert storage_mod.delete_all_conversation_recordings("uid1") == 0
        store.list.assert_not_called()  # returns before ever reaching the store

    def test_configured_bucket_purges_the_uid_prefix(self):
        store = FakeObjectStore()
        store.put("memories-recordings", "uid1/conv-a.wav", b"x")
        store.put("memories-recordings", "uid1/conv-b.wav", b"x")
        store.put("memories-recordings", "uid2/other.wav", b"x")  # different uid: must survive
        with patch.object(storage_mod, "memories_recordings_bucket", "memories-recordings"), patch.object(
            storage_mod, "_object_store", return_value=store
        ):
            assert storage_mod.delete_all_conversation_recordings("uid1") == 2
        assert store.list("memories-recordings", "uid1/") == []  # purged
        assert store.exists("memories-recordings", "uid2/other.wav")  # untouched

    def test_real_gcs_failure_still_raises(self):
        """The purge is required: a genuine storage error must keep blocking the irreversible wipe."""
        store = MagicMock()
        store.list.side_effect = RuntimeError("gcs down")
        with patch.object(storage_mod, "memories_recordings_bucket", "memories-recordings"), patch.object(
            storage_mod, "_object_store", return_value=store
        ):
            with pytest.raises(RuntimeError):
                storage_mod.delete_all_conversation_recordings("uid1")
