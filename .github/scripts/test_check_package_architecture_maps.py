#!/usr/bin/env python3
"""Tests for the oversized-package architecture map ratchet."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from check_package_architecture_maps import (
    ISSUE_URL,
    baseline_change_findings,
    evaluate_packages,
    load_baseline,
    run,
    source_count,
)


class PackageArchitectureMapTests(unittest.TestCase):
    def make_package(self, root: Path, relative: str, count: int) -> Path:
        package = root / relative
        package.mkdir(parents=True)
        for index in range(count):
            (package / f"module_{index}.py").write_text("VALUE = 1\n", encoding="utf-8")
        return package

    def test_new_oversized_package_fails_with_issue_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_package(root, "backend/utils/new_package", 13)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({"version": 1, "packages": {}}), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                result = run(repo_root=root, baseline_path=baseline_path, threshold=12)
            self.assertEqual(result, 1)
            self.assertIn("backend/utils/new_package", output.getvalue())
            self.assertIn(ISSUE_URL, output.getvalue())

    def test_threshold_is_strictly_greater_than_twelve(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_package(root, "backend/utils/twelve", 12)
            self.assertEqual(evaluate_packages(root, {}, threshold=12), [])

    def test_package_root_architecture_or_readme_map_passes(self) -> None:
        for map_name in ("ARCHITECTURE.md", "README.md"):
            with self.subTest(map_name=map_name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                package = self.make_package(root, "backend/utils/mapped", 13)
                (package / map_name).write_text("# Map\n", encoding="utf-8")
                self.assertEqual(evaluate_packages(root, {}, threshold=12), [])

    def test_nested_map_does_not_satisfy_package_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root, "backend/utils/mapless", 13)
            nested = package / "nested"
            nested.mkdir()
            (nested / "ARCHITECTURE.md").write_text("# Nested\n", encoding="utf-8")
            self.assertEqual(evaluate_packages(root, {}, threshold=12)[0].level, "error")

    def test_unchanged_baseline_warns_and_growth_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root, "backend/utils/legacy", 13)
            baseline = {"backend/utils/legacy": 13}
            finding = evaluate_packages(root, baseline, threshold=12)[0]
            self.assertEqual(finding.level, "warning")
            (package / "growth.py").write_text("VALUE = 1\n", encoding="utf-8")
            finding = evaluate_packages(root, baseline, threshold=12)[0]
            self.assertEqual(finding.level, "error")
            self.assertIn("grew from", finding.message)

    def test_baseline_cannot_grandfather_a_new_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(
                json.dumps({"version": 1, "packages": {"backend/utils/new_package": 13}}),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                result = run(repo_root=root, baseline_path=baseline_path, previous_baseline={})
            self.assertEqual(result, 1)
            self.assertIn("must add ARCHITECTURE.md or README.md", output.getvalue())

    def test_baseline_cannot_be_raised_to_hide_growth(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(
                json.dumps({"version": 1, "packages": {"backend/utils/legacy": 14}}),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                result = run(
                    repo_root=root,
                    baseline_path=baseline_path,
                    previous_baseline={"backend/utils/legacy": 13},
                )
            self.assertEqual(result, 1)
            self.assertIn("baseline increased from 13 to 14", output.getvalue())

    def test_baseline_may_shrink_or_remove_entries(self) -> None:
        self.assertEqual(
            baseline_change_findings(
                {"backend/utils/legacy": 12},
                {"backend/utils/legacy": 13, "backend/utils/documented": 20},
            ),
            [],
        )

    def test_nested_sources_count_but_generated_and_build_files_do_not(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root, "backend/utils/counting", 10)
            nested = package / "nested"
            nested.mkdir()
            (nested / "one.py").write_text("VALUE = 1\n", encoding="utf-8")
            (nested / "two.ts").write_text("export const value = 1\n", encoding="utf-8")
            (nested / "ignored.g.dart").write_text("generated\n", encoding="utf-8")
            build = package / "build"
            build.mkdir()
            (build / "ignored.py").write_text("VALUE = 1\n", encoding="utf-8")
            self.assertEqual(source_count(package), 12)

    def test_baseline_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            baseline_path = Path(temp) / "baseline.json"
            baseline_path.write_text(json.dumps({"version": 2, "packages": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_baseline(baseline_path)


if __name__ == "__main__":
    unittest.main()
