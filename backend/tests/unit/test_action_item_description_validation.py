"""Tests for CanonicalTaskCreate, ActionItemCreateRequest, CanonicalTaskUpdate, and ActionItemUpdateRequest description validation and normalization.

Validates that:
- Empty strings and whitespace-only descriptions are strictly rejected with ValidationError ('description cannot be blank') across both creation and update models.
- Valid descriptions with leading/trailing whitespace are automatically stripped and normalized.
- Update requests allow description=None (omitted field) when updating other attributes like completed status.
- Parity is maintained between create and update contracts.
"""

import unittest
from pydantic import ValidationError

from models.action_item import (
    ActionItemCreateRequest,
    ActionItemUpdateRequest,
    CanonicalTaskCreate,
    CanonicalTaskUpdate,
)


class TestActionItemDescriptionValidation(unittest.TestCase):
    """Test suite verifying description validation on task creation and update models."""

    def test_canonical_task_create_rejects_empty_description(self):
        with self.assertRaises(ValidationError) as cm:
            CanonicalTaskCreate(description="")
        self.assertTrue(
            any("description cannot be blank" in err["msg"] or "at least 1 character" in err["msg"] for err in cm.exception.errors())
        )

    def test_canonical_task_create_rejects_whitespace_only_description(self):
        for whitespace in (" ", "   ", "\t", "\n", " \t \n "):
            with self.subTest(whitespace=whitespace):
                with self.assertRaises(ValidationError) as cm:
                    CanonicalTaskCreate(description=whitespace)
                self.assertTrue(
                    any("description cannot be blank" in err["msg"] for err in cm.exception.errors())
                )

    def test_canonical_task_create_strips_leading_trailing_whitespace(self):
        task = CanonicalTaskCreate(description="  Review PR  ")
        self.assertEqual(task.description, "Review PR")

    def test_canonical_task_create_accepts_valid_description(self):
        task = CanonicalTaskCreate(description="Implement non-blank description check")
        self.assertEqual(task.description, "Implement non-blank description check")

    def test_action_item_create_request_rejects_whitespace_description(self):
        with self.assertRaises(ValidationError) as cm:
            ActionItemCreateRequest(description="   ")
        self.assertTrue(
            any("description cannot be blank" in err["msg"] for err in cm.exception.errors())
        )

    def test_action_item_create_request_strips_whitespace(self):
        req = ActionItemCreateRequest(description="  Draft release notes  ")
        self.assertEqual(req.description, "Draft release notes")

    def test_canonical_task_update_rejects_empty_description(self):
        with self.assertRaises(ValidationError) as cm:
            CanonicalTaskUpdate(description="")
        self.assertTrue(
            any("description cannot be blank" in err["msg"] or "at least 1 character" in err["msg"] for err in cm.exception.errors())
        )

    def test_canonical_task_update_rejects_whitespace_only_description(self):
        for whitespace in (" ", "   ", "\t", "\n", " \t \n "):
            with self.subTest(whitespace=whitespace):
                with self.assertRaises(ValidationError) as cm:
                    CanonicalTaskUpdate(description=whitespace)
                self.assertTrue(
                    any("description cannot be blank" in err["msg"] for err in cm.exception.errors())
                )

    def test_canonical_task_update_strips_leading_trailing_whitespace(self):
        update = CanonicalTaskUpdate(description="  Deploy to staging  ")
        self.assertEqual(update.description, "Deploy to staging")

    def test_canonical_task_update_omitted_description_with_other_fields(self):
        update = CanonicalTaskUpdate(completed=True)
        self.assertIsNone(update.description)
        self.assertTrue(update.completed)

    def test_canonical_task_update_rejects_explicit_null_description(self):
        with self.assertRaises(ValidationError) as cm:
            CanonicalTaskUpdate(description=None, completed=True)
        self.assertTrue(
            any("description cannot be null" in err["msg"] for err in cm.exception.errors())
        )

    def test_action_item_update_request_rejects_whitespace_description(self):
        with self.assertRaises(ValidationError) as cm:
            ActionItemUpdateRequest(description="   ")
        self.assertTrue(
            any("description cannot be blank" in err["msg"] for err in cm.exception.errors())
        )

    def test_action_item_update_request_strips_whitespace(self):
        req = ActionItemUpdateRequest(description="  Clean warehouse  ")
        self.assertEqual(req.description, "Clean warehouse")


if __name__ == "__main__":
    unittest.main()
