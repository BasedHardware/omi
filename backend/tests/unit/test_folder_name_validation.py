"""Tests for CreateFolderRequest and UpdateFolderRequest name validation and normalization.

Validates that:
- Empty strings and whitespace-only names are rejected with ValidationError ('folder name cannot be empty or blank') on both create and update paths.
- Valid names with leading/trailing whitespace are automatically stripped and normalized.
- Update requests allow name=None (omitted field) when updating other folder attributes such as description, color, icon, or order.
- Default and valid payloads succeed as expected.
"""

import unittest
from pydantic import ValidationError

from models.folder import CreateFolderRequest, UpdateFolderRequest


class TestFolderNameValidation(unittest.TestCase):
    """Test suite verifying folder name validation and whitespace normalization."""

    def test_create_folder_request_rejects_empty_name(self):
        with self.assertRaises(ValidationError) as cm:
            CreateFolderRequest(name="")
        self.assertTrue(
            any("folder name cannot be empty or blank" in err["msg"] or "at least 1 character" in err["msg"] for err in cm.exception.errors())
        )

    def test_create_folder_request_rejects_whitespace_only_name(self):
        for whitespace in (" ", "   ", "\t", "\n", " \t \n "):
            with self.subTest(whitespace=whitespace):
                with self.assertRaises(ValidationError) as cm:
                    CreateFolderRequest(name=whitespace)
                self.assertTrue(
                    any("folder name cannot be empty or blank" in err["msg"] for err in cm.exception.errors())
                )

    def test_create_folder_request_strips_leading_trailing_whitespace(self):
        req = CreateFolderRequest(name="  Work & Projects  ")
        self.assertEqual(req.name, "Work & Projects")

    def test_create_folder_request_accepts_valid_name(self):
        req = CreateFolderRequest(name="Personal Knowledge")
        self.assertEqual(req.name, "Personal Knowledge")
        self.assertIsNone(req.description)

    def test_update_folder_request_rejects_empty_name(self):
        with self.assertRaises(ValidationError) as cm:
            UpdateFolderRequest(name="")
        self.assertTrue(
            any("folder name cannot be empty or blank" in err["msg"] or "at least 1 character" in err["msg"] for err in cm.exception.errors())
        )

    def test_update_folder_request_rejects_whitespace_only_name(self):
        for whitespace in (" ", "   ", "\t", "\n", " \t \n "):
            with self.subTest(whitespace=whitespace):
                with self.assertRaises(ValidationError) as cm:
                    UpdateFolderRequest(name=whitespace)
                self.assertTrue(
                    any("folder name cannot be empty or blank" in err["msg"] for err in cm.exception.errors())
                )

    def test_update_folder_request_allows_omitted_name(self):
        req = UpdateFolderRequest(description="New folder notes", color="#10B981")
        self.assertIsNone(req.name)
        self.assertEqual(req.description, "New folder notes")
        self.assertEqual(req.color, "#10B981")

    def test_update_folder_request_strips_leading_trailing_whitespace(self):
        req = UpdateFolderRequest(name="  Archived Items  ")
        self.assertEqual(req.name, "Archived Items")


if __name__ == "__main__":
    unittest.main()
