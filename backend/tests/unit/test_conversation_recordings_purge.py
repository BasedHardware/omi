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


class TestDeleteAllConversationRecordings:
    def test_unconfigured_bucket_is_a_no_op(self):
        """Before the fix this raised ValueError and blocked the whole account wipe."""
        with patch.object(storage_mod, "memories_recordings_bucket", None), patch.object(
            storage_mod, "_get_storage_client"
        ) as get_client:
            storage_mod.delete_all_conversation_recordings("uid1")
        get_client.assert_not_called()

    def test_configured_bucket_purges_the_uid_prefix(self):
        blob = MagicMock()
        bucket = MagicMock()
        bucket.list_blobs.return_value = [blob]
        client = MagicMock()
        client.bucket.return_value = bucket
        with patch.object(storage_mod, "memories_recordings_bucket", "memories-recordings"), patch.object(
            storage_mod, "_get_storage_client", return_value=client
        ):
            storage_mod.delete_all_conversation_recordings("uid1")
        client.bucket.assert_called_once_with("memories-recordings")
        bucket.list_blobs.assert_called_once_with(prefix="uid1/")
        blob.delete.assert_called_once()

    def test_real_gcs_failure_still_raises(self):
        """The purge is required: a genuine GCS error must keep blocking the irreversible wipe."""
        client = MagicMock()
        client.bucket.side_effect = RuntimeError("gcs down")
        with patch.object(storage_mod, "memories_recordings_bucket", "memories-recordings"), patch.object(
            storage_mod, "_get_storage_client", return_value=client
        ):
            with pytest.raises(RuntimeError):
                storage_mod.delete_all_conversation_recordings("uid1")
