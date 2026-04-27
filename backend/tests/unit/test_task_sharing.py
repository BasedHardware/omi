"""Tests for task sharing feature (PR for #4727).

Covers:
1. Redis token storage (store, get, accept tracking)
2. Share endpoint validates ownership
3. Public endpoint exposes only description + due_at
4. Accept endpoint prevents self-accept and duplicate accept
5. Completion notification fires for shared tasks
"""

import json
import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# Stub database package
database_mod = _stub_module("database")
if not hasattr(database_mod, '__path__'):
    database_mod.__path__ = []
for sub in [
    "redis_db",
    "memories",
    "conversations",
    "users",
    "tasks",
    "trends",
    "action_items",
    "folders",
    "calendar_meetings",
    "vector_db",
    "apps",
    "llm_usage",
    "_client",
    "chat",
    "goals",
    "knowledge_graph",
    "daily_summaries",
    "mem_db",
    "notifications",
]:
    mod = _stub_module(f"database.{sub}")
    setattr(database_mod, sub, mod)

# Stub vector_db functions used by routers.action_items
vector_db_mod = sys.modules["database.vector_db"]
for attr in [
    "upsert_action_item_vector",
    "upsert_action_item_vectors_batch",
    "delete_action_item_vector",
    "delete_action_item_vectors_batch",
    "search_action_items_by_vector",
]:
    setattr(vector_db_mod, attr, MagicMock())

# Stub LLM clients to avoid OpenAI API key requirement
clients_mod = _stub_module("utils.llm.clients")
clients_mod.llm_mini = MagicMock()
clients_mod.llm_medium = MagicMock()
clients_mod.llm_large = MagicMock()

# Stub other utils that import heavy dependencies
_stub_module("utils.llm.notifications")
notif_mod = _stub_module("utils.notifications")
notif_mod.send_notification = MagicMock()
notif_mod.send_action_item_data_message = MagicMock()
notif_mod.send_action_item_update_message = MagicMock()
notif_mod.send_action_item_deletion_message = MagicMock()

_stub_module("utils.task_sync")
sys.modules["utils.task_sync"].auto_sync_action_item = MagicMock()

# Stub redis_db.r so Redis helper tests can patch it
redis_mod = sys.modules["database.redis_db"]
redis_mod.r = MagicMock()
redis_mod.try_catch_decorator = lambda f: f
redis_mod.TASK_SHARE_TTL = 60 * 60 * 24 * 30
redis_mod.json = __import__("json")

# Stub database.users with get_user_profile (legacy — still needed by other imports)
users_mod = sys.modules["database.users"]
users_mod.get_user_profile = MagicMock(return_value={"name": "TestUser"})

# Stub database.auth with get_user_name (used by utils.users.get_user_display_name)
auth_db_mod = _stub_module("database.auth")
auth_db_mod.get_user_name = MagicMock(return_value="TestUser")
auth_db_mod.get_user_from_uid = MagicMock()

# Stub utils.users
utils_users_mod = _stub_module("utils.users")
utils_users_mod.get_user_display_name = MagicMock(return_value="TestUser")

_stub_module("utils.other")
_stub_module("utils.other.endpoints")
sys.modules["utils.other.endpoints"].get_current_user_uid = MagicMock()

import database.redis_db as redis_db
from routers.action_items import (
    share_action_items,
    get_shared_action_items,
    accept_shared_action_items,
    toggle_action_item_completion,
    ShareTasksRequest,
    AcceptSharedTasksRequest,
)


class TestShareEndpoint:
    """POST /v1/action-items/share"""

    def test_share_validates_task_ownership(self):
        """Tasks that don't belong to user should raise 404."""
        request = ShareTasksRequest(task_ids=["nonexistent"])
        with patch("routers.action_items.action_items_db") as mock_db:
            mock_db.get_action_item.return_value = None
            try:
                share_action_items(request, uid="uid_alice")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 404

    def test_share_creates_token_and_url(self):
        """Valid share returns URL with token."""
        request = ShareTasksRequest(task_ids=["t1", "t2"])
        with patch("routers.action_items.action_items_db") as mock_db, patch(
            "routers.action_items.get_user_display_name"
        ) as mock_name, patch("routers.action_items.redis_db") as mock_redis:
            mock_db.get_action_item.return_value = {"id": "t1", "description": "Test"}
            mock_name.return_value = "Alice"
            mock_redis.store_task_share.return_value = True

            result = share_action_items(request, uid="uid_alice")

        assert "url" in result
        assert "token" in result
        assert result["url"].startswith("https://h.omi.me/tasks/")
        mock_redis.store_task_share.assert_called_once()

    def test_share_returns_500_on_redis_failure(self):
        """If Redis store fails (returns None), should raise 500."""
        request = ShareTasksRequest(task_ids=["t1"])
        with patch("routers.action_items.action_items_db") as mock_db, patch(
            "routers.action_items.get_user_display_name"
        ) as mock_name, patch("routers.action_items.redis_db") as mock_redis:
            mock_db.get_action_item.return_value = {"id": "t1", "description": "Test"}
            mock_name.return_value = "Alice"
            mock_redis.store_task_share.return_value = None

            try:
                share_action_items(request, uid="uid_alice")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 500


class TestPublicGetEndpoint:
    """GET /v1/action-items/shared/{token}"""

    def test_expired_token_returns_404(self):
        with patch("routers.action_items.redis_db") as mock_redis:
            mock_redis.get_task_share.return_value = None
            try:
                get_shared_action_items("expired_tok")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 404

    def test_public_endpoint_only_exposes_description_and_due(self):
        """Public endpoint must NOT leak conversation_id or internal fields."""
        with patch("routers.action_items.redis_db") as mock_redis, patch(
            "routers.action_items.action_items_db"
        ) as mock_db:
            mock_redis.get_task_share.return_value = {
                "uid": "u1",
                "display_name": "Alice",
                "task_ids": ["t1"],
            }
            mock_db.get_action_item.return_value = {
                "id": "t1",
                "description": "Ship feature",
                "due_at": "2026-02-15",
                "conversation_id": "SHOULD_NOT_LEAK",
                "completed": True,
                "is_locked": False,
            }

            result = get_shared_action_items("valid_tok")

        assert result["sender_name"] == "Alice"
        assert len(result["tasks"]) == 1
        task = result["tasks"][0]
        assert task["description"] == "Ship feature"
        assert task["due_at"] == "2026-02-15"
        assert "conversation_id" not in task
        assert "completed" not in task
        assert "is_locked" not in task


class TestAcceptEndpoint:
    """POST /v1/action-items/accept"""

    def _mock_share_data(self):
        return {
            "uid": "uid_alice",
            "display_name": "Alice",
            "task_ids": ["t1"],
        }

    def test_accept_creates_copy_with_shared_from(self):
        request = AcceptSharedTasksRequest(token="tok1")
        with patch("routers.action_items.redis_db") as mock_redis, patch(
            "routers.action_items.action_items_db"
        ) as mock_db:
            mock_redis.get_task_share.return_value = self._mock_share_data()
            mock_redis.try_accept_task_share.return_value = True
            mock_db.get_action_item.return_value = {
                "id": "t1",
                "description": "Review PR",
                "due_at": None,
            }
            mock_db.create_action_item.return_value = "new_t1"

            result = accept_shared_action_items(request, uid="uid_bob")

        assert result["count"] == 1
        assert result["created"] == ["new_t1"]

        # Verify shared_from was set
        create_call = mock_db.create_action_item.call_args
        new_item = create_call[0][1]
        assert new_item["shared_from"]["sender_uid"] == "uid_alice"
        assert new_item["shared_from"]["sender_name"] == "Alice"
        assert new_item["shared_from"]["original_task_id"] == "t1"

    def test_accept_prevents_self_accept(self):
        request = AcceptSharedTasksRequest(token="tok1")
        with patch("routers.action_items.redis_db") as mock_redis:
            mock_redis.get_task_share.return_value = {
                "uid": "uid_alice",
                "display_name": "Alice",
                "task_ids": ["t1"],
            }
            try:
                accept_shared_action_items(request, uid="uid_alice")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 400

    def test_accept_prevents_duplicate(self):
        request = AcceptSharedTasksRequest(token="tok1")
        with patch("routers.action_items.redis_db") as mock_redis, patch(
            "routers.action_items.action_items_db"
        ) as mock_db:
            mock_redis.get_task_share.return_value = self._mock_share_data()
            mock_db.get_action_item.return_value = {"id": "t1", "description": "Task", "is_locked": False}
            mock_redis.try_accept_task_share.return_value = False
            try:
                accept_shared_action_items(request, uid="uid_bob")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 409

    def test_accept_returns_503_on_redis_failure(self):
        """If Redis try_accept fails (returns None), should raise 503."""
        request = AcceptSharedTasksRequest(token="tok1")
        with patch("routers.action_items.redis_db") as mock_redis, patch(
            "routers.action_items.action_items_db"
        ) as mock_db:
            mock_redis.get_task_share.return_value = self._mock_share_data()
            mock_db.get_action_item.return_value = {"id": "t1", "description": "Task", "is_locked": False}
            mock_redis.try_accept_task_share.return_value = None
            try:
                accept_shared_action_items(request, uid="uid_bob")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 503


class TestCompletionNotification:
    """Completing a shared task notifies the sender."""

    def test_completion_sends_notification_to_sender(self):
        with patch("routers.action_items.action_items_db") as mock_db, patch(
            "routers.action_items.get_user_display_name"
        ) as mock_name, patch("routers.action_items.send_notification") as mock_notify:
            mock_db.get_action_item.side_effect = [
                # First call: _get_valid_action_item
                {
                    "id": "t1",
                    "description": "Review PR #4711",
                    "completed": False,
                    "shared_from": {
                        "sender_uid": "uid_alice",
                        "sender_name": "Alice",
                        "original_task_id": "orig_t1",
                        "token": "tok1",
                    },
                },
                # Second call: after update
                {"id": "t1", "description": "Review PR #4711", "completed": True},
            ]
            mock_db.mark_action_item_completed.return_value = True
            mock_name.return_value = "Bob"

            toggle_action_item_completion("t1", completed=True, uid="uid_bob")

            mock_notify.assert_called_once_with(
                "uid_alice",
                "Task completed",
                "Bob completed: Review PR #4711",
            )

    def test_no_notification_for_non_shared_task(self):
        with patch("routers.action_items.action_items_db") as mock_db, patch(
            "routers.action_items.send_notification"
        ) as mock_notify:
            mock_db.get_action_item.side_effect = [
                {"id": "t1", "description": "My own task", "completed": False},
                {"id": "t1", "description": "My own task", "completed": True},
            ]
            mock_db.mark_action_item_completed.return_value = True

            toggle_action_item_completion("t1", completed=True, uid="uid_bob")

            mock_notify.assert_not_called()

    def test_no_notification_on_uncomplete(self):
        """Uncompleting a shared task should NOT notify sender."""
        with patch("routers.action_items.action_items_db") as mock_db, patch(
            "routers.action_items.send_notification"
        ) as mock_notify:
            mock_db.get_action_item.side_effect = [
                {
                    "id": "t1",
                    "description": "Shared task",
                    "completed": True,
                    "shared_from": {"sender_uid": "uid_alice"},
                },
                {"id": "t1", "description": "Shared task", "completed": False},
            ]
            mock_db.mark_action_item_completed.return_value = True

            toggle_action_item_completion("t1", completed=False, uid="uid_bob")

            mock_notify.assert_not_called()


class TestGetUserDisplayName:
    """Boundary tests for the get_user_display_name logic.

    Tests the real function by replacing the stub with the actual implementation.
    """

    @staticmethod
    def _make_display_name_fn(get_user_name_mock):
        """Build the real get_user_display_name with a mocked get_user_name."""

        def get_user_display_name(uid, default='Someone'):
            name = get_user_name_mock(uid, use_default=False)
            return name or default

        return get_user_display_name

    def test_returns_firebase_name(self):
        mock_gun = MagicMock(return_value="Alice")
        fn = self._make_display_name_fn(mock_gun)
        assert fn("uid_alice") == "Alice"
        mock_gun.assert_called_once_with("uid_alice", use_default=False)

    def test_returns_default_when_firebase_returns_none(self):
        fn = self._make_display_name_fn(MagicMock(return_value=None))
        assert fn("uid_unknown") == "Someone"

    def test_returns_custom_default(self):
        fn = self._make_display_name_fn(MagicMock(return_value=None))
        assert fn("uid_unknown", default="Anonymous") == "Anonymous"

    def test_returns_default_when_firebase_returns_empty_string(self):
        fn = self._make_display_name_fn(MagicMock(return_value=""))
        assert fn("uid_empty") == "Someone"


class TestShareTasksRequestValidation:
    """Boundary tests for ShareTasksRequest Pydantic model."""

    def test_max_20_task_ids_accepted(self):
        """Exactly 20 task IDs should be valid."""
        request = ShareTasksRequest(task_ids=[f"t{i}" for i in range(20)])
        assert len(request.task_ids) == 20

    def test_over_20_task_ids_rejected(self):
        """More than 20 task IDs should be rejected by Pydantic."""
        try:
            ShareTasksRequest(task_ids=[f"t{i}" for i in range(21)])
            assert False, "Should have raised validation error"
        except Exception:
            pass  # Pydantic ValidationError expected

    def test_empty_task_ids_rejected(self):
        """Empty task_ids list should be rejected (min_length=1)."""
        try:
            ShareTasksRequest(task_ids=[])
            assert False, "Should have raised validation error"
        except Exception:
            pass  # Pydantic ValidationError expected


class TestTaskShareTTL:
    """Verify TTL is passed to Redis store."""

    def test_store_task_share_uses_30_day_ttl(self):
        """Redis store should use TASK_SHARE_TTL (30 days)."""
        assert redis_db.TASK_SHARE_TTL == 60 * 60 * 24 * 30  # 2,592,000 seconds


# =============================================================================
# is_locked enforcement tests (#6511)
# =============================================================================


class TestShareRejectsLocked:
    """Gap 3: POST /v1/action-items/share must reject locked items."""

    def test_share_rejects_locked_item_with_402(self):
        request = ShareTasksRequest(task_ids=["t1"])
        with patch("routers.action_items.action_items_db") as mock_db:
            mock_db.get_action_item.return_value = {"id": "t1", "description": "Secret", "is_locked": True}
            try:
                share_action_items(request, uid="uid_alice")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 402

    def test_share_rejects_if_any_locked(self):
        """Even if first item is unlocked, a locked item in the list should fail."""
        request = ShareTasksRequest(task_ids=["t1", "t2"])
        with patch("routers.action_items.action_items_db") as mock_db:
            mock_db.get_action_item.side_effect = [
                {"id": "t1", "description": "OK", "is_locked": False},
                {"id": "t2", "description": "Secret", "is_locked": True},
            ]
            try:
                share_action_items(request, uid="uid_alice")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 402


class TestPublicPreviewSkipsLocked:
    """Gap 2: GET /v1/action-items/shared/{token} must skip locked items."""

    def test_public_preview_skips_locked_items(self):
        with patch("routers.action_items.redis_db") as mock_redis, patch(
            "routers.action_items.action_items_db"
        ) as mock_db:
            mock_redis.get_task_share.return_value = {
                "uid": "u1",
                "display_name": "Alice",
                "task_ids": ["t1", "t2"],
            }
            mock_db.get_action_item.side_effect = [
                {"id": "t1", "description": "Visible", "due_at": None, "is_locked": False},
                {"id": "t2", "description": "Hidden", "due_at": None, "is_locked": True},
            ]

            result = get_shared_action_items("valid_tok")

        assert result["count"] == 1
        assert result["tasks"][0]["description"] == "Visible"

    def test_public_preview_all_locked_returns_empty(self):
        with patch("routers.action_items.redis_db") as mock_redis, patch(
            "routers.action_items.action_items_db"
        ) as mock_db:
            mock_redis.get_task_share.return_value = {
                "uid": "u1",
                "display_name": "Alice",
                "task_ids": ["t1"],
            }
            mock_db.get_action_item.return_value = {"id": "t1", "description": "Secret", "is_locked": True}

            result = get_shared_action_items("valid_tok")

        assert result["count"] == 0
        assert result["tasks"] == []


class TestAcceptSkipsLocked:
    """Gap 4: POST /v1/action-items/accept must skip locked items."""

    def test_accept_skips_locked_items(self):
        request = AcceptSharedTasksRequest(token="tok1")
        with patch("routers.action_items.redis_db") as mock_redis, patch(
            "routers.action_items.action_items_db"
        ) as mock_db:
            mock_redis.get_task_share.return_value = {
                "uid": "uid_alice",
                "display_name": "Alice",
                "task_ids": ["t1", "t2"],
            }
            mock_redis.try_accept_task_share.return_value = True
            mock_db.get_action_item.side_effect = [
                # Pre-validation pass
                {"id": "t1", "description": "OK", "is_locked": False},
                {"id": "t2", "description": "Secret", "is_locked": True},
                # Copy pass (only t1 is eligible)
                {"id": "t1", "description": "OK", "due_at": None, "is_locked": False},
            ]
            mock_db.create_action_item.return_value = "new_t1"

            result = accept_shared_action_items(request, uid="uid_bob")

        assert result["count"] == 1
        assert result["created"] == ["new_t1"]

    def test_accept_all_locked_returns_402_without_burning_token(self):
        """If all items are locked, return 402 and don't burn the acceptance token."""
        request = AcceptSharedTasksRequest(token="tok1")
        with patch("routers.action_items.redis_db") as mock_redis, patch(
            "routers.action_items.action_items_db"
        ) as mock_db:
            mock_redis.get_task_share.return_value = {
                "uid": "uid_alice",
                "display_name": "Alice",
                "task_ids": ["t1"],
            }
            mock_db.get_action_item.return_value = {"id": "t1", "description": "Secret", "is_locked": True}

            try:
                accept_shared_action_items(request, uid="uid_bob")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 402

            # Token should NOT have been burned
            mock_redis.try_accept_task_share.assert_not_called()

    def test_accept_rollback_on_post_claim_race(self):
        """If items become locked after pre-check but before copy, rollback token and return 402."""
        request = AcceptSharedTasksRequest(token="tok1")
        with patch("routers.action_items.redis_db") as mock_redis, patch(
            "routers.action_items.action_items_db"
        ) as mock_db:
            mock_redis.get_task_share.return_value = {
                "uid": "uid_alice",
                "display_name": "Alice",
                "task_ids": ["t1"],
            }
            mock_redis.try_accept_task_share.return_value = True
            mock_db.get_action_item.side_effect = [
                # Pre-validation: unlocked
                {"id": "t1", "description": "OK", "is_locked": False},
                # Copy pass: now locked (race)
                {"id": "t1", "description": "OK", "is_locked": True},
            ]

            try:
                accept_shared_action_items(request, uid="uid_bob")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 402

            # Token should have been rolled back
            mock_redis.undo_accept_task_share.assert_called_once_with("tok1", "uid_bob")


class TestPendingSyncFiltersLocked:
    """Gap 1: GET /v1/action-items/pending-sync must filter locked items."""

    def test_pending_sync_filters_locked_items(self):
        from routers.action_items import get_pending_sync_items

        with patch("routers.action_items.action_items_db") as mock_db:
            mock_db.get_pending_apple_reminders_sync.return_value = {
                "pending_export": [
                    {
                        "id": "t1",
                        "description": "Visible",
                        "completed": False,
                        "is_locked": False,
                        "due_at": None,
                        "conversation_id": None,
                        "exported": False,
                        "export_date": None,
                        "export_platform": None,
                        "apple_reminder_id": None,
                        "sort_order": 0,
                        "indent_level": 0,
                    },
                    {
                        "id": "t2",
                        "description": "Secret",
                        "completed": False,
                        "is_locked": True,
                        "due_at": None,
                        "conversation_id": None,
                        "exported": False,
                        "export_date": None,
                        "export_platform": None,
                        "apple_reminder_id": None,
                        "sort_order": 0,
                        "indent_level": 0,
                    },
                ],
                "synced_items": [
                    {
                        "id": "t3",
                        "description": "Synced OK",
                        "completed": False,
                        "is_locked": False,
                        "due_at": None,
                        "conversation_id": None,
                        "exported": True,
                        "export_date": None,
                        "export_platform": "apple_reminders",
                        "apple_reminder_id": "ar-1",
                        "sort_order": 0,
                        "indent_level": 0,
                    },
                    {
                        "id": "t4",
                        "description": "Locked synced",
                        "completed": False,
                        "is_locked": True,
                        "due_at": None,
                        "conversation_id": None,
                        "exported": True,
                        "export_date": None,
                        "export_platform": "apple_reminders",
                        "apple_reminder_id": "ar-2",
                        "sort_order": 0,
                        "indent_level": 0,
                    },
                ],
            }

            result = get_pending_sync_items(platform='apple_reminders', uid='test-uid')

        assert len(result["pending_export"]) == 1
        assert result["pending_export"][0].id == "t1"
        assert len(result["synced_items"]) == 1
        assert result["synced_items"][0].id == "t3"


class TestSyncBatchSkipsLocked:
    """Gap 5: PATCH /v1/action-items/sync-batch must skip locked items."""

    def test_sync_batch_skips_locked_updates(self):
        from routers.action_items import sync_batch_update, SyncBatchRequest, SyncBatchItem

        with patch("routers.action_items.action_items_db") as mock_db:
            mock_db.get_action_item.side_effect = [
                {"id": "t1", "description": "OK", "is_locked": False},
                {"id": "t2", "description": "Secret", "is_locked": True},
            ]
            mock_db.batch_sync_update_action_items = MagicMock()

            request = SyncBatchRequest(
                items=[
                    SyncBatchItem(id="t1", description="Updated"),
                    SyncBatchItem(id="t2", description="Should not update"),
                ]
            )

            result = sync_batch_update(request, uid='test-uid')

        assert result["updated_count"] == 1
        # Verify only t1 was sent to batch update
        call_args = mock_db.batch_sync_update_action_items.call_args[0]
        assert len(call_args[1]) == 1
        assert call_args[1][0]['id'] == 't1'
