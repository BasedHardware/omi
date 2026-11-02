"""Tests ensuring that PATCH/updates to action items do not write explicit nulls over non-nullable fields.

CanonicalTaskUpdate and ActionItemUpdateRequest must reject explicit nulls for non-nullable
fields ('description', 'status', 'completed', 'owner', 'source', 'provenance', 'sort_order',
'indent_level', 'exported'), and reject blank/empty descriptions.
Furthermore, ActionItemResponse must heal legacy or corrupt documents that carry explicit null
for those fields instead of raising ValidationError, and database updates with partial=True
must drop explicit nulls on non-nullable fields to prevent Firestore database poisoning.
"""

import unittest

from database.action_item_codec import prepare_action_item_for_write
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
        sanitized = prepare_action_item_for_write(partial_data, partial=True)
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
