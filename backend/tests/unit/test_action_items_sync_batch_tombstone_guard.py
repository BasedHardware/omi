"""Tests for soft-deleted (tombstone) safety in action items batch sync and reminders sync."""

from unittest.mock import MagicMock, patch

from database.action_items import BatchMutationResult, get_pending_apple_reminders_sync
from routers.action_items import (
    SyncBatchItem,
    SyncBatchRequest,
    get_pending_sync_items,
    sync_batch_update,
)

UID = "test-user-sync-batch"
LIVE_TASK_ID = "task-live-1"
DELETED_TASK_ID = "task-deleted-1"
NONEXISTENT_TASK_ID = "task-nonexistent-1"


class TestSyncBatchUpdateTombstoneGuard:
    @patch("routers.action_items.sync_action_item_reminder")
    @patch("routers.action_items.upsert_action_item_vectors_batch")
    @patch("routers.action_items.action_items_db")
    def test_sync_batch_update_skips_deleted_item(self, mock_db, mock_vectors, mock_reminder):
        mock_db.get_action_item.return_value = {
            "id": DELETED_TASK_ID,
            "description": "Deleted task",
            "completed": False,
            "deleted": True,
            "is_locked": False,
        }
        mock_db.batch_sync_update_action_items.return_value = BatchMutationResult(
            updated_ids=[],
            missing_ids=[],
            noop_ids=[],
        )

        request = SyncBatchRequest(
            items=[
                SyncBatchItem(
                    id=DELETED_TASK_ID,
                    description="Updated text on deleted task",
                    completed=True,
                )
            ]
        )

        response = sync_batch_update(request=request, uid=UID)

        # batch_sync_update_action_items must not receive the deleted task
        if mock_db.batch_sync_update_action_items.called:
            called_updates = mock_db.batch_sync_update_action_items.call_args[0][1]
            updated_ids = [u["id"] for u in called_updates]
            assert DELETED_TASK_ID not in updated_ids

        # Vectors and reminders must not be triggered for the deleted task
        mock_vectors.assert_not_called()
        mock_reminder.assert_not_called()

        # The deleted task should be reported in missing_ids
        assert DELETED_TASK_ID in response.get("missing_ids", [])
        assert response["updated_count"] == 0

    @patch("routers.action_items.sync_action_item_reminder")
    @patch("routers.action_items.upsert_action_item_vectors_batch")
    @patch("routers.action_items.action_items_db")
    def test_sync_batch_update_handles_mixed_live_and_deleted(self, mock_db, mock_vectors, mock_reminder):
        def mock_get(uid, task_id):
            if task_id == LIVE_TASK_ID:
                return {
                    "id": LIVE_TASK_ID,
                    "description": "Live task",
                    "completed": False,
                    "deleted": False,
                    "is_locked": False,
                }
            if task_id == DELETED_TASK_ID:
                return {
                    "id": DELETED_TASK_ID,
                    "description": "Deleted task",
                    "completed": False,
                    "deleted": True,
                    "is_locked": False,
                }
            return None

        mock_db.get_action_item.side_effect = mock_get
        mock_db.batch_sync_update_action_items.return_value = BatchMutationResult(
            updated_ids=[LIVE_TASK_ID],
            missing_ids=[],
            noop_ids=[],
        )

        request = SyncBatchRequest(
            items=[
                SyncBatchItem(id=LIVE_TASK_ID, description="Live updated"),
                SyncBatchItem(id=DELETED_TASK_ID, description="Deleted updated"),
            ]
        )

        response = sync_batch_update(request=request, uid=UID)

        # Only live item must be passed to db.batch_sync_update_action_items
        called_updates = mock_db.batch_sync_update_action_items.call_args[0][1]
        passed_ids = [u["id"] for u in called_updates]
        assert passed_ids == [LIVE_TASK_ID]

        assert DELETED_TASK_ID in response.get("missing_ids", [])
        assert response["updated_count"] == 1

    @patch("routers.action_items.sync_action_item_reminder")
    @patch("routers.action_items.upsert_action_item_vectors_batch")
    @patch("routers.action_items.action_items_db")
    def test_sync_batch_update_skips_nonexistent_item(self, mock_db, mock_vectors, mock_reminder):
        mock_db.get_action_item.return_value = None
        mock_db.batch_sync_update_action_items.return_value = BatchMutationResult(
            updated_ids=[],
            missing_ids=[],
            noop_ids=[],
        )

        request = SyncBatchRequest(items=[SyncBatchItem(id=NONEXISTENT_TASK_ID, description="Nonexistent")])

        response = sync_batch_update(request=request, uid=UID)

        if mock_db.batch_sync_update_action_items.called:
            called_updates = mock_db.batch_sync_update_action_items.call_args[0][1]
            updated_ids = [u["id"] for u in called_updates]
            assert NONEXISTENT_TASK_ID not in updated_ids

        assert NONEXISTENT_TASK_ID in response.get("missing_ids", [])


class TestGetPendingSyncItemsTombstoneGuard:
    @patch("routers.action_items.action_items_db")
    def test_get_pending_sync_items_omits_deleted(self, mock_db):
        mock_db.get_pending_apple_reminders_sync.return_value = {
            "pending_export": [
                {
                    "id": LIVE_TASK_ID,
                    "description": "Live task",
                    "completed": False,
                    "deleted": False,
                    "is_locked": False,
                },
                {
                    "id": DELETED_TASK_ID,
                    "description": "Deleted task",
                    "completed": False,
                    "deleted": True,
                    "is_locked": False,
                },
            ],
            "synced_items": [
                {
                    "id": "synced-1",
                    "description": "Synced live",
                    "completed": False,
                    "deleted": False,
                    "is_locked": False,
                },
                {
                    "id": "synced-deleted",
                    "description": "Synced deleted",
                    "completed": False,
                    "deleted": True,
                    "is_locked": False,
                },
            ],
        }

        result = get_pending_sync_items(platform="apple_reminders", uid=UID)

        pending_ids = [item.id for item in result["pending_export"]]
        assert LIVE_TASK_ID in pending_ids
        assert DELETED_TASK_ID not in pending_ids

        synced_ids = [item.id for item in result["synced_items"]]
        assert "synced-1" in synced_ids
        assert "synced-deleted" not in synced_ids


class TestDatabasePendingSyncTombstoneGuard:
    def test_database_get_pending_apple_reminders_sync_omits_deleted(self, monkeypatch):
        import database.action_items as action_items_db

        mock_user = MagicMock()
        mock_coll = MagicMock()
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_user
        mock_user.collection.return_value = mock_coll
        monkeypatch.setattr(action_items_db, "db", mock_db)

        # pending query
        mock_pending_doc_live = MagicMock()
        mock_pending_doc_live.id = LIVE_TASK_ID
        mock_pending_doc_live.to_dict.return_value = {
            "description": "Live pending",
            "completed": False,
            "sync_requested": True,
            "exported": False,
            "deleted": False,
        }

        mock_pending_doc_deleted = MagicMock()
        mock_pending_doc_deleted.id = DELETED_TASK_ID
        mock_pending_doc_deleted.to_dict.return_value = {
            "description": "Deleted pending",
            "completed": False,
            "sync_requested": True,
            "exported": False,
            "deleted": True,
        }

        # synced query
        mock_synced_doc_live = MagicMock()
        mock_synced_doc_live.id = "synced-live"
        mock_synced_doc_live.to_dict.return_value = {
            "description": "Synced live",
            "completed": False,
            "export_platform": "apple_reminders",
            "exported": True,
            "deleted": False,
        }

        mock_synced_doc_deleted = MagicMock()
        mock_synced_doc_deleted.id = "synced-deleted"
        mock_synced_doc_deleted.to_dict.return_value = {
            "description": "Synced deleted",
            "completed": False,
            "export_platform": "apple_reminders",
            "exported": True,
            "deleted": True,
        }

        mock_pending_query = MagicMock()
        mock_pending_query.stream.return_value = [mock_pending_doc_live, mock_pending_doc_deleted]

        mock_synced_query = MagicMock()
        mock_synced_query.where.return_value = mock_synced_query
        mock_synced_query.limit.return_value = mock_synced_query
        mock_synced_query.stream.return_value = [mock_synced_doc_live, mock_synced_doc_deleted]

        def coll_where(*args, **kwargs):
            filter_arg = kwargs.get("filter")
            if hasattr(filter_arg, "field_path") and filter_arg.field_path == "sync_requested":
                return mock_pending_query
            # If FieldFilter has _field_path
            if getattr(filter_arg, "_field_path", None) == "sync_requested":
                return mock_pending_query
            return mock_synced_query

        mock_coll.where.side_effect = coll_where
        mock_pending_query.limit.return_value = mock_pending_query

        result = get_pending_apple_reminders_sync(uid=UID)

        pending_ids = [item["id"] for item in result["pending_export"]]
        assert LIVE_TASK_ID in pending_ids
        assert DELETED_TASK_ID not in pending_ids

        synced_ids = [item["id"] for item in result["synced_items"]]
        assert "synced-live" in synced_ids
        assert "synced-deleted" not in synced_ids
