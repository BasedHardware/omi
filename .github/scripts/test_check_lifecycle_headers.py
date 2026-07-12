#!/usr/bin/env python3
"""Unit tests for check_lifecycle_headers.py (stdlib unittest)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from check_lifecycle_headers import is_designated_path, parse_lifecycle_header, validate

PERMANENT = "# LIFECYCLE: permanent\n\nprint('ok')\n"
ONE_TIME = "# LIFECYCLE: one-time\n# DELETE-AFTER: INV-MEM-3\n\nprint('ok')\n"


def write(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class DesignatedPathTests(unittest.TestCase):
    def test_designated_paths_match_initial_policy(self) -> None:
        self.assertTrue(is_designated_path("backend/scripts/example_readiness.py"))
        self.assertTrue(is_designated_path("backend/scripts/rollout-proof.sh"))
        self.assertTrue(is_designated_path("backend/utils/memory/compatibility.py"))
        self.assertTrue(is_designated_path("backend/utils/memory/rollout/config.py"))
        self.assertFalse(is_designated_path("backend/scripts/deploy.py"))
        self.assertFalse(is_designated_path("backend/routers/rollout.py"))


class HeaderTests(unittest.TestCase):
    def test_accepts_permanent_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "permanent.py", PERMANENT)
            self.assertEqual(parse_lifecycle_header(path), ("permanent", None))

    def test_accepts_one_time_header_with_issue_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(
                Path(tmp),
                "one_time.py",
                "# LIFECYCLE: one-time\n# DELETE-AFTER: https://github.com/BasedHardware/omi/issues/123\n",
            )
            self.assertEqual(parse_lifecycle_header(path), ("one-time", None))

    def test_rejects_one_time_header_without_delete_after(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "one_time.py", "# LIFECYCLE: one-time\n")
            lifecycle, error = parse_lifecycle_header(path)
            self.assertIsNone(lifecycle)
            self.assertIn("DELETE-AFTER", error or "")

    def test_rejects_permanent_header_with_delete_after(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "permanent.py", PERMANENT.replace("\n\n", "\n# DELETE-AFTER: INV-MEM-3\n\n"))
            lifecycle, error = parse_lifecycle_header(path)
            self.assertIsNone(lifecycle)
            self.assertIn("must not", error or "")


class ValidationTests(unittest.TestCase):
    def test_new_unlabeled_designated_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = "backend/scripts/new_readiness.py"
            write(root, path, "print('missing header')\n")
            baseline = write(root, ".github/lifecycle-header-baseline.txt", "")
            errors = validate(root, [path], baseline)
            self.assertTrue(any("require a valid lifecycle header" in error for error in errors))

    def test_changed_baseline_file_requires_a_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = "backend/scripts/legacy_readiness.py"
            write(root, path, "print('legacy')\n")
            baseline = write(root, ".github/lifecycle-header-baseline.txt", f"{path}\n")
            errors = validate(root, [path], baseline)
            self.assertTrue(any("require a valid lifecycle header" in error for error in errors))

    def test_frozen_baseline_allows_unchanged_legacy_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = "backend/scripts/legacy_readiness.py"
            write(root, path, "print('legacy')\n")
            baseline = write(root, ".github/lifecycle-header-baseline.txt", f"{path}\n")
            self.assertEqual(validate(root, [], baseline), [])

    def test_unbaselined_legacy_file_fails_the_debt_census(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "backend/scripts/legacy_readiness.py", "print('legacy')\n")
            baseline = write(root, ".github/lifecycle-header-baseline.txt", "")
            errors = validate(root, [], baseline)
            self.assertTrue(any("baseline must exactly match" in error for error in errors))

    def test_valid_headers_are_not_baselined(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            permanent = "backend/scripts/permanent_gauntlet.py"
            one_time = "backend/utils/memory/one_time_rollout.py"
            write(root, permanent, PERMANENT)
            write(root, one_time, ONE_TIME)
            baseline = write(root, ".github/lifecycle-header-baseline.txt", "")
            self.assertEqual(validate(root, [permanent, one_time], baseline), [])


if __name__ == "__main__":
    unittest.main()
