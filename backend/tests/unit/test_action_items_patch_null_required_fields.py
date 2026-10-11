"""Tests ensuring that PATCH/updates to action items do not write explicit nulls over non-nullable fields.

CanonicalTaskUpdate and ActionItemUpdateRequest must reject explicit nulls for non-nullable
fields ('description', 'status', 'completed', 'owner', 'source', 'provenance', 'sort_order',
'indent_level', 'exported'), and reject blank/empty descriptions.
Furthermore, ActionItemResponse must heal legacy or corrupt documents that carry explicit null
for those fields instead of raising ValidationError, and database updates with partial=True
must drop explicit nulls on non-nullable fields to prevent Firestore database poisoning.
"""

from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _load_action_items_db():
    if "database.action_items" in sys.modules and hasattr(
        sys.modules["database.action_items"], "_prepare_action_item_for_write"
    ):
        return sys.modules["database.action_items"]

    for p in ("google", "google.cloud", "google.api_core"):
        _pkg(p)

    for m in (
        "google.cloud.firestore",
        "google.cloud.firestore_v1",
        "google.cloud.firestore_v1.base_query",
        "google.api_core.exceptions",
        "firebase_admin",
        "redis",
        "prometheus_client",
        "fastapi",
        "utils.observability.fallback",
        "utils.observability",
        "utils.metrics",
    ):
        _mod(m)

    prom_mod = sys.modules["prometheus_client"]
    prom_mod.Counter = lambda *a, **kw: MagicMock()
    prom_mod.Histogram = lambda *a, **kw: MagicMock()

    sys.modules["utils.observability.fallback"].record_fallback = lambda *a, **kw: None
    sys.modules["utils.metrics"].OMI_FALLBACK_TOTAL = MagicMock()

    firestore_mod = sys.modules["google.cloud.firestore"]
    firestore_mod.ArrayUnion = lambda *a: a
    firestore_mod.ArrayRemove = lambda *a: a

    firestore_v1_mod = sys.modules["google.cloud.firestore_v1"]
    firestore_v1_mod.FieldFilter = object
    firestore_v1_mod.BaseCompositeFilter = object

    base_query_mod = sys.modules["google.cloud.firestore_v1.base_query"]
    base_query_mod.BaseCompositeFilter = object
    base_query_mod.FieldFilter = object

    api_exceptions_mod = sys.modules["google.api_core.exceptions"]
    for exc in (
        "DeadlineExceeded",
        "GoogleAPICallError",
        "NotFound",
        "InvalidArgument",
    ):
        setattr(api_exceptions_mod, exc, type(exc, (Exception,), {}))

    redis_mod = sys.modules["redis"]
    redis_mod.Redis = MagicMock()

    spec = importlib.util.spec_from_file_location(
        "database._action_items_null_patch_test",
        str(BACKEND_DIR / "database" / "action_items.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


action_items_db = _load_action_items_db()
from models.action_item import (
    ActionItemResponse,
    ActionItemUpdateRequest,
    CanonicalTaskUpdate,
    TaskOwner,
    TaskStatus,
)


class ActionItemsPatchNullRequiredFieldsTest(unittest.TestCase):
    def test_canonical_task_update_rejects_explicit_null_description(self):
        with self.assertRaises(ValueError) as ctx:
            CanonicalTaskUpdate(description=None)
        self.assertIn("description cannot be null", str(ctx.exception))

    def test_canonical_task_update_rejects_blank_description(self):
        with self.assertRaises(ValueError) as ctx:
            CanonicalTaskUpdate(description="   ")
        self.assertIn("description cannot be blank", str(ctx.exception))

    def test_canonical_task_update_rejects_explicit_null_required_fields(self):
        required_fields = (
            "status",
            "completed",
            "owner",
            "source",
            "provenance",
            "sort_order",
            "indent_level",
            "exported",
        )
        for field in required_fields:
            with self.subTest(field=field):
                with self.assertRaises(ValueError) as ctx:
                    CanonicalTaskUpdate(**{field: None})
                self.assertIn(f"{field} cannot be null", str(ctx.exception))

    def test_action_item_update_request_accepts_valid_updates(self):
        update = ActionItemUpdateRequest(
            description="Updated task description",
            completed=True,
            owner=TaskOwner.user,
        )
        payload = update.storage_payload()
        self.assertEqual(payload["description"], "Updated task description")
        self.assertEqual(payload["completed"], True)
        self.assertEqual(payload["status"], TaskStatus.completed)
        self.assertEqual(payload["owner"], TaskOwner.user)

    def test_action_item_response_heals_corrupt_legacy_null_fields(self):
        corrupt_doc = {
            "id": "task_corrupt_123",
            "description": "Legacy task with null properties",
            "completed": False,
            "owner": None,
            "source": None,
            "provenance": None,
            "sort_order": None,
            "indent_level": None,
            "exported": None,
        }
        res = ActionItemResponse.model_validate(corrupt_doc)
        self.assertEqual(res.id, "task_corrupt_123")
        self.assertEqual(res.description, "Legacy task with null properties")
        self.assertEqual(res.owner, TaskOwner.unknown)
        self.assertEqual(res.source, "legacy")
        self.assertEqual(res.provenance, [])
        self.assertEqual(res.sort_order, 0)
        self.assertEqual(res.indent_level, 0)
        self.assertEqual(res.exported, False)

    def test_prepare_action_item_for_write_drops_explicit_nulls_on_partial(self):
        partial_data = {
            "description": None,
            "owner": None,
            "source": None,
            "provenance": None,
            "sort_order": None,
            "indent_level": None,
            "exported": None,
            "due_at": None,
            "completed_at": None,
        }
        sanitized = action_items_db._prepare_action_item_for_write(partial_data, partial=True)
        for field in (
            "description",
            "owner",
            "source",
            "provenance",
            "sort_order",
            "indent_level",
            "exported",
        ):
            self.assertNotIn(field, sanitized)
        # Genuinely nullable fields are preserved
        self.assertIn("due_at", sanitized)
        self.assertIsNone(sanitized["due_at"])
        self.assertIn("completed_at", sanitized)
        self.assertIsNone(sanitized["completed_at"])


if __name__ == "__main__":
    unittest.main()
