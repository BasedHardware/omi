"""Tests for WorkstreamCreate and WorkstreamUpdate non-blank field validation and normalization.

Validates that:
- Empty strings and whitespace-only title or objective are rejected with ValidationError ('title cannot be blank', 'objective cannot be blank') across create and update models.
- Valid titles and objectives with surrounding whitespace are automatically stripped and normalized.
- Update requests allow omitted fields (title=None or objective=None) when updating other workstream attributes.
- Default and valid payloads succeed as expected.
"""

import unittest
from pydantic import ValidationError

from models.workstream import WorkstreamCreate, WorkstreamStatus, WorkstreamUpdate


class TestWorkstreamValidation(unittest.TestCase):
    """Test suite verifying workstream title and objective validation."""

    def test_workstream_create_rejects_empty_or_whitespace_title(self):
        for blank in ("", "   ", "\t\n"):
            with self.subTest(blank=blank):
                with self.assertRaises(ValidationError) as cm:
                    WorkstreamCreate(title=blank, objective="Valid objective")
                self.assertTrue(
                    any("title cannot be blank" in err["msg"] or "at least 1 character" in err["msg"] for err in cm.exception.errors())
                )

    def test_workstream_create_rejects_empty_or_whitespace_objective(self):
        for blank in ("", "   ", "\t\n"):
            with self.subTest(blank=blank):
                with self.assertRaises(ValidationError) as cm:
                    WorkstreamCreate(title="Valid title", objective=blank)
                self.assertTrue(
                    any("objective cannot be blank" in err["msg"] or "at least 1 character" in err["msg"] for err in cm.exception.errors())
                )

    def test_workstream_create_strips_leading_trailing_whitespace(self):
        ws = WorkstreamCreate(title="  Autonomous Agent Pipeline  ", objective="  Build high-reliability agent runtime  ")
        self.assertEqual(ws.title, "Autonomous Agent Pipeline")
        self.assertEqual(ws.objective, "Build high-reliability agent runtime")

    def test_workstream_update_rejects_whitespace_title(self):
        for blank in ("", "   ", "\t\n"):
            with self.subTest(blank=blank):
                with self.assertRaises(ValidationError) as cm:
                    WorkstreamUpdate(title=blank)
                self.assertTrue(
                    any("title cannot be blank" in err["msg"] or "at least 1 character" in err["msg"] for err in cm.exception.errors())
                )

    def test_workstream_update_rejects_whitespace_objective(self):
        for blank in ("", "   ", "\t\n"):
            with self.subTest(blank=blank):
                with self.assertRaises(ValidationError) as cm:
                    WorkstreamUpdate(objective=blank)
                self.assertTrue(
                    any("objective cannot be blank" in err["msg"] or "at least 1 character" in err["msg"] for err in cm.exception.errors())
                )

    def test_workstream_update_allows_omitted_fields(self):
        up = WorkstreamUpdate(status=WorkstreamStatus.completed)
        self.assertIsNone(up.title)
        self.assertIsNone(up.objective)
        self.assertEqual(up.status, WorkstreamStatus.completed)

    def test_workstream_update_strips_whitespace(self):
        up = WorkstreamUpdate(title="  Refined Target  ", objective="  Updated objective  ")
        self.assertEqual(up.title, "Refined Target")
        self.assertEqual(up.objective, "Updated objective")


if __name__ == "__main__":
    unittest.main()
