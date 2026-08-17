#!/usr/bin/env python3
"""Unit tests for the version-prefixed filename lint."""

from __future__ import annotations

import io
import unittest
from unittest.mock import patch

import check_version_prefixed_filenames as lint


class VersionPrefixedFilenameTests(unittest.TestCase):
    def test_detects_each_supported_source_suffix(self) -> None:
        for suffix in (".py", ".swift", ".ts", ".rs"):
            self.assertTrue(lint.is_versioned_filename(f"src/v4_reader{suffix}"))

    def test_ignores_nonmatching_names_and_suffixes(self) -> None:
        self.assertFalse(lint.is_versioned_filename("src/reader_v4.py"))
        self.assertFalse(lint.is_versioned_filename("src/v4_reader.dart"))
        self.assertFalse(lint.is_versioned_filename("src/v4_.py"))

    def test_allows_versioned_filenames_inside_version_packages(self) -> None:
        self.assertTrue(lint.is_in_versioned_package("backend/utils/memory/v4/v4_reader.py"))
        self.assertEqual(lint.violations(["backend/utils/memory/v4/v4_reader.py"]), [])

    def test_rejects_new_version_prefixed_filename_outside_package(self) -> None:
        self.assertEqual(lint.violations(["backend/utils/memory/v4_reader.py"]), ["backend/utils/memory/v4_reader.py"])

    def test_rejects_filename_in_a_different_version_package(self) -> None:
        self.assertEqual(
            lint.violations(["backend/utils/memory/v3/v4_reader.py"]), ["backend/utils/memory/v3/v4_reader.py"]
        )

    def test_allows_grandfathered_legacy_path(self) -> None:
        self.assertEqual(lint.violations(["backend/scripts/v3_dev_cloud_proof.py"]), [])

    def test_main_reports_issue_for_new_violation(self) -> None:
        output = io.StringIO()
        with patch.object(lint, "tracked_paths", return_value=["backend/utils/memory/v4_reader.py"]), patch(
            "sys.stdout", output
        ):
            self.assertEqual(lint.main(), 1)

        self.assertIn("version goes in the package path, not the filename", output.getvalue())
        self.assertIn(lint.ISSUE_URL, output.getvalue())


if __name__ == "__main__":
    unittest.main()
