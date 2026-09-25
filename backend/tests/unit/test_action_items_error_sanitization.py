import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[2]
ACTION_ITEMS_ROUTER_FILE = BACKEND_DIR / "routers" / "action_items.py"


class ActionItemsErrorSanitizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._stubbed_modules = {}

        class StubModel(BaseModel):
            model_config = {"extra": "allow"}

            def storage_payload(self):
                return {}

        class StubTaskRelationshipConflictError(ValueError):
            pass

        class StubTaskLinkValidationError(ValueError):
            pass

        class StubFirestoreContentionExhausted(Exception):
            pass

        stub_names = [
            "database",
            "database.action_items",
            "database.conversations",
            "database.redis_db",
            "database.firestore_transaction_retry",
            "database.vector_db",
            "database.action_items_cache",
            "models",
            "models.action_item",
            "utils",
            "utils.executors",
            "utils.action_items_list_guard",
            "utils.metrics",
            "utils.users",
            "utils.share_links",
            "utils.other",
            "utils.other.endpoints",
            "utils.other.list_budget",
            "utils.notifications",
            "utils.task_sync",
            "utils.task_intelligence",
            "utils.task_intelligence.proactive_engine",
            "utils.task_intelligence.task_links",
            "utils.product_metrics",
            "utils.product_telemetry",
        ]
        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        for mod in stub_names:
            if "." in mod:
                parent, child = mod.rsplit(".", 1)
                if parent in sys.modules:
                    setattr(sys.modules[parent], child, sys.modules[mod])

        sys.modules["database.action_items"].TaskRelationshipConflictError = StubTaskRelationshipConflictError
        sys.modules["database.firestore_transaction_retry"].FirestoreContentionExhausted = (
            StubFirestoreContentionExhausted
        )
        sys.modules["utils.task_intelligence.task_links"].TaskLinkValidationError = StubTaskLinkValidationError

        # Link model attributes with StubModel
        models_mod = sys.modules["models.action_item"]
        models_mod.ActionItemCreateRequest = StubModel
        models_mod.ActionItemResponse = StubModel
        models_mod.ActionItemUpdateRequest = StubModel
        models_mod.ActionItemsResponse = StubModel
        models_mod.ActionItemsSearchResponse = StubModel
        models_mod.ConversationActionItemsResponse = StubModel
        models_mod.PendingSyncResponse = StubModel

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        try:
            from routers.action_items import _sanitize_task_relationship_error
            import routers.action_items as action_items_mod
        except ImportError:
            import action_items as action_items_mod
            from action_items import _sanitize_task_relationship_error

        cls._sanitize_fn = staticmethod(_sanitize_task_relationship_error)
        cls._router_mod = action_items_mod
        cls._StubConflictError = StubTaskRelationshipConflictError

    @classmethod
    def tearDownClass(cls):
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def test_sanitize_task_relationship_error_safe_messages(self):
        sanitize = self._sanitize_fn
        fallback = "Task relationship conflict"

        safe_cases = [
            "goal does not exist",
            "goal account generation mismatch",
            "ended goal cannot receive new task links",
            "workstream does not exist",
            "workstream account generation mismatch",
            "task goal_id must match workstream goal_id",
            "document id belongs to another account generation",
        ]

        for safe in safe_cases:
            err = self._StubConflictError(safe)
            self.assertEqual(sanitize(err, fallback), safe)

    def test_sanitize_task_relationship_error_filters_sensitive_internals(self):
        sanitize = self._sanitize_fn
        fallback = "Task relationship conflict"

        sensitive_cases = [
            "internal firestore transaction contention: /databases/(default)/documents/users/u1/action_items/x",
            "Traceback (most recent call last):\n  File 'db.py', line 12\nKeyError: 'workstream_id'",
            "PostgresDeadlockDetected: process 9218 waiting for ShareLock on transaction 88129",
            "",
            "   ",
        ]

        for leak in sensitive_cases:
            err = self._StubConflictError(leak)
            self.assertEqual(sanitize(err, fallback), fallback)

    def test_no_raw_str_exc_in_task_relationship_handlers(self):
        target_path = ACTION_ITEMS_ROUTER_FILE
        if not target_path.exists():
            target_path = Path(__file__).resolve().parents[1] / "routers" / "action_items.py"
        if not target_path.exists():
            target_path = Path(__file__).resolve().parents[0] / "action_items.py"
        if not target_path.exists():
            target_path = Path.cwd() / "backend" / "routers" / "action_items.py"
        if not target_path.exists():
            target_path = Path.cwd() / "action_items.py"
        source = target_path.read_text(encoding="utf-8")

        self.assertIn("_sanitize_task_relationship_error", source)
        for chunk in source.split("TaskRelationshipConflictError as exc:")[1:]:
            handler_block = chunk[:200]
            self.assertNotIn("detail=str(exc)", handler_block)
            self.assertIn("_sanitize_task_relationship_error", handler_block)

    def test_create_action_item_sanitizes_conflict(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        create_action_item = router_mod.create_action_item

        req_mock = MagicMock()
        req_mock.goal_id = "g-1"
        req_mock.workstream_id = "w-1"
        req_mock.storage_payload.return_value = {"description": "test"}

        # 1. Known safe message propagates cleanly
        with patch.object(router_mod.task_links, "validate_task_links"), patch.object(
            router_mod.action_items_db,
            "create_action_item",
            side_effect=self._StubConflictError("goal does not exist"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_action_item(req_mock, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "goal does not exist")

        # 2. Raw internal exception details are sanitized
        with patch.object(router_mod.task_links, "validate_task_links"), patch.object(
            router_mod.action_items_db,
            "create_action_item",
            side_effect=self._StubConflictError("firestore document internal lock failure"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_action_item(req_mock, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "Task relationship conflict")


if __name__ == "__main__":
    unittest.main()
