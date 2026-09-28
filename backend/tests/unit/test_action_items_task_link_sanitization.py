"""Hermetic unit tests for TaskLink error sanitization in the action items router.

Verifies that:
1. Internal TaskLinkResolverUnavailableError (e.g. 'Ticket 04 ... resolver is not registered')
   routes through _sanitize_task_link_error and returns a sanitized HTTP 409 response.
2. Domain validation messages on TaskLinkValidationError remain client-facing for UX compatibility.
3. All three router sites (create_action_item, update_action_item, create_action_items_batch)
   consistently sanitize resolver errors and preserve domain errors.
4. Source scan confirms zero unhandled TaskLinkResolverUnavailableError leaks across action_items.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[2]
ACTION_ITEMS_ROUTER_FILE = BACKEND_DIR / "routers" / "action_items.py"


class ActionItemsTaskLinkSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}
    _modified_parent_attrs: list = []
    _sanitize_fn = None
    _router_mod = None

    @classmethod
    def setUpClass(cls):
        cls._stubbed_modules = {}
        cls._modified_parent_attrs = []

        class StubTaskLinkValidationError(ValueError):
            pass

        class StubTaskLinkResolverUnavailableError(StubTaskLinkValidationError):
            pass

        class StubTaskRelationshipConflictError(ValueError):
            pass

        class StubFirestoreContentionExhausted(Exception):
            pass

        class StubModel(BaseModel):
            def storage_payload(self):
                return {}

        class StubCreateRequest(StubModel):
            goal_id: str | None = None
            workstream_id: str | None = None

        class StubUpdateRequest(StubModel):
            goal_id: str | None = None
            workstream_id: str | None = None
            completed: bool | None = None
            status: str | None = None
            description: str | None = None

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
            "utils.product_metrics",
            "utils.notifications",
            "utils.task_sync",
            "utils.task_intelligence",
            "utils.task_intelligence.proactive_engine",
            "utils.task_intelligence.task_links",
            "utils.product_telemetry",
        ]

        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                mock_mod.__path__ = []
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        for mod in stub_names:
            if "." in mod:
                parent, child = mod.rsplit(".", 1)
                if parent in sys.modules:
                    parent_mod = sys.modules[parent]
                    had_attr = hasattr(parent_mod, child)
                    old_val = getattr(parent_mod, child, None) if had_attr else None
                    cls._modified_parent_attrs.append((parent_mod, child, had_attr, old_val))
                    setattr(parent_mod, child, sys.modules[mod])

        # Inject classes
        sys.modules["utils.task_intelligence.task_links"].TaskLinkValidationError = StubTaskLinkValidationError
        sys.modules["utils.task_intelligence.task_links"].TaskLinkResolverUnavailableError = (
            StubTaskLinkResolverUnavailableError
        )
        sys.modules["database.action_items"].TaskRelationshipConflictError = StubTaskRelationshipConflictError
        sys.modules["database.firestore_transaction_retry"].FirestoreContentionExhausted = (
            StubFirestoreContentionExhausted
        )

        sys.modules["models.action_item"].ActionItem = StubModel
        sys.modules["models.action_item"].ActionItemCreateRequest = StubCreateRequest
        sys.modules["models.action_item"].ActionItemUpdateRequest = StubUpdateRequest
        sys.modules["models.action_item"].ActionItemResponse = StubModel
        sys.modules["models.action_item"].ActionItemsResponse = StubModel
        sys.modules["models.action_item"].ActionItemsSearchResponse = StubModel
        sys.modules["models.action_item"].ConversationActionItemsResponse = StubModel
        sys.modules["models.action_item"].ActionItemSummaryResponse = StubModel
        sys.modules["models.action_item"].PendingSyncResponse = StubModel

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        try:
            from routers.action_items import (
                _sanitize_task_link_error,
                create_action_item,
                update_action_item,
                create_action_items_batch,
            )
            import routers.action_items as action_items_mod
        except ImportError:
            # Local fallback for direct scratch testing
            import action_items_modified as action_items_mod
            from action_items_modified import (
                _sanitize_task_link_error,
                create_action_item,
                update_action_item,
                create_action_items_batch,
            )

        cls._sanitize_fn = staticmethod(_sanitize_task_link_error)
        cls._router_mod = action_items_mod
        cls._StubTaskLinkValidationError = StubTaskLinkValidationError
        cls._StubTaskLinkResolverUnavailableError = StubTaskLinkResolverUnavailableError
        cls._StubCreateRequest = StubCreateRequest
        cls._StubUpdateRequest = StubUpdateRequest

    @classmethod
    def tearDownClass(cls):
        for parent_mod, child, had_attr, old_val in reversed(cls._modified_parent_attrs):
            if had_attr:
                setattr(parent_mod, child, old_val)
            else:
                try:
                    delattr(parent_mod, child)
                except AttributeError:
                    pass
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def test_sanitize_task_link_error_returns_clean_message(self):
        sanitize = self._sanitize_fn
        exc = self._StubTaskLinkResolverUnavailableError("Ticket 04 workstream goal resolver is not registered")
        res = sanitize(exc)
        self.assertEqual(res, "Task link resolver is temporarily unavailable")

    def test_create_action_item_sanitizes_resolver_unavailable(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        create_fn = router_mod.create_action_item
        req = self._StubCreateRequest(goal_id="g-1", workstream_id="w-1")

        with patch.object(
            router_mod.task_links,
            "validate_task_links",
            side_effect=self._StubTaskLinkResolverUnavailableError(
                "Ticket 04 workstream goal resolver is not registered"
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_fn(request=req, uid="u-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "Task link resolver is temporarily unavailable")

    def test_create_action_item_preserves_domain_validation_message(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        create_fn = router_mod.create_action_item
        req = self._StubCreateRequest(goal_id="g-1", workstream_id="w-1")

        with patch.object(
            router_mod.task_links,
            "validate_task_links",
            side_effect=self._StubTaskLinkValidationError("goal does not exist"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_fn(request=req, uid="u-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "goal does not exist")

    def test_update_action_item_sanitizes_resolver_unavailable(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        update_fn = router_mod.update_action_item
        req = self._StubUpdateRequest(goal_id="g-1")

        with patch.object(router_mod, "_get_valid_action_item", return_value={"id": "ai-1"}), patch.object(
            router_mod.task_links,
            "validate_task_links",
            side_effect=self._StubTaskLinkResolverUnavailableError("Ticket 04 goal resolver is not registered"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                update_fn(action_item_id="ai-1", request=req, uid="u-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "Task link resolver is temporarily unavailable")

    def test_update_action_item_preserves_domain_validation_message(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        update_fn = router_mod.update_action_item
        req = self._StubUpdateRequest(goal_id="g-1")

        with patch.object(router_mod, "_get_valid_action_item", return_value={"id": "ai-1"}), patch.object(
            router_mod.task_links,
            "validate_task_links",
            side_effect=self._StubTaskLinkValidationError("task goal_id must match workstream goal_id"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                update_fn(action_item_id="ai-1", request=req, uid="u-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "task goal_id must match workstream goal_id")

    def test_create_action_items_batch_sanitizes_resolver_unavailable(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        batch_fn = router_mod.create_action_items_batch
        items = [self._StubCreateRequest(goal_id="g-1", workstream_id="w-1")]

        with patch.object(
            router_mod.task_links,
            "validate_task_links",
            side_effect=self._StubTaskLinkResolverUnavailableError(
                "Ticket 04 workstream goal resolver is not registered"
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                batch_fn(action_items=items, uid="u-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "Task link resolver is temporarily unavailable")

    def test_create_action_items_batch_preserves_domain_validation_message(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        batch_fn = router_mod.create_action_items_batch
        items = [self._StubCreateRequest(goal_id="g-1", workstream_id="w-1")]

        with patch.object(
            router_mod.task_links,
            "validate_task_links",
            side_effect=self._StubTaskLinkValidationError("workstream does not exist"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                batch_fn(action_items=items, uid="u-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "workstream does not exist")

    def test_no_raw_resolver_exception_leak_in_action_items(self):
        target_path = ACTION_ITEMS_ROUTER_FILE
        if not target_path.exists():
            target_path = Path(__file__).parent / "action_items_modified.py"
        source = target_path.read_text(encoding="utf-8")

        self.assertIn("_sanitize_task_link_error", source)
        self.assertIn("TaskLinkResolverUnavailableError", source)

        # Scans the file for TaskLinkValidationError handling
        lines = source.splitlines()
        found_count = 0
        for i, line in enumerate(lines):
            if "except TaskLinkValidationError" in line:
                found_count += 1
                # Next few lines must check for TaskLinkResolverUnavailableError
                block = "\n".join(lines[i : i + 6])
                self.assertIn("isinstance(exc, TaskLinkResolverUnavailableError)", block)
                self.assertIn("_sanitize_task_link_error", block)
        self.assertEqual(found_count, 3)


if __name__ == "__main__":
    unittest.main()
