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

# Stub database.users with get_user_profile
users_mod = sys.modules["database.users"]
users_mod.get_user_profile = MagicMock(return_value={"name": "TestUser"})

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
            "routers.action_items.get_user_profile"
        ) as mock_profile, patch("routers.action_items.redis_db") as mock_redis:
            mock_db.get_action_item.return_value = {"id": "t1", "description": "Test"}
            mock_profile.return_value = {"name": "Alice"}
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
            "routers.action_items.get_user_profile"
        ) as mock_profile, patch("routers.action_items.redis_db") as mock_redis:
            mock_db.get_action_item.return_value = {"id": "t1", "description": "Test"}
            mock_profile.return_value = {"name": "Alice"}
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
            mock_redis.has_accepted_task_share.return_value = False
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
        with patch("routers.action_items.redis_db") as mock_redis:
            mock_redis.get_task_share.return_value = self._mock_share_data()
            mock_redis.has_accepted_task_share.return_value = True
            try:
                accept_shared_action_items(request, uid="uid_bob")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 409

    def test_accept_returns_503_on_redis_failure(self):
        """If Redis has_accepted check fails (returns None), should raise 503."""
        request = AcceptSharedTasksRequest(token="tok1")
        with patch("routers.action_items.redis_db") as mock_redis:
            mock_redis.get_task_share.return_value = self._mock_share_data()
            mock_redis.has_accepted_task_share.return_value = None
            try:
                accept_shared_action_items(request, uid="uid_bob")
                assert False, "Should have raised HTTPException"
            except Exception as e:
                assert e.status_code == 503


class TestCompletionNotification:
    """Completing a shared task notifies the sender."""

    def test_completion_sends_notification_to_sender(self):
        with patch("routers.action_items.action_items_db") as mock_db, patch(
            "routers.action_items.get_user_profile"
        ) as mock_profile, patch("routers.action_items.send_notification") as mock_notify:
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
            mock_profile.return_value = {"name": "Bob"}

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
