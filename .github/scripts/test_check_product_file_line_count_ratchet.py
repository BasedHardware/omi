#!/usr/bin/env python3
"""Behavioral regression tests for the oversized product-file line ratchet."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "product_file_line_count_ratchet", SCRIPT_DIR / "check_product_file_line_count_ratchet.py"
)
assert SPEC and SPEC.loader
RATCHET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RATCHET)


def baseline(files: dict[str, int], justifications: dict[str, str] | None = None) -> dict:
    return {
        "threshold": RATCHET.THRESHOLD,
        "files": files,
        "raise_justifications": justifications or {},
    }


class ProductFileLineCountRatchetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_source(self, relative: str, lines: int) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("line\n" * lines, encoding="utf-8")

    def test_rejects_growth_of_an_oversized_file(self) -> None:
        relative = "backend/routers/large.py"
        self.write_source(relative, 1501)

        failures, downward = RATCHET.check_changed_sources(self.root, baseline({relative: 1500}), {relative})

        self.assertEqual(downward, {})
        self.assertEqual(len(failures), 1)
        self.assertIn("grew from baseline 1500 to 1501", failures[0])

    def test_rejects_a_smaller_file_that_crosses_the_threshold(self) -> None:
        relative = "desktop/macos/Desktop/Sources/NewCoordinator.swift"
        self.write_source(relative, RATCHET.THRESHOLD)

        failures, downward = RATCHET.check_changed_sources(self.root, baseline({}), {relative})

        self.assertEqual(downward, {})
        self.assertEqual(len(failures), 1)
        self.assertIn("has no baseline entry", failures[0])

    def test_update_mode_automatically_removes_baseline_after_a_split(self) -> None:
        relative = "desktop/macos/Desktop/Sources/OldCoordinator.swift"
        self.write_source(relative, 1499)
        original = baseline({relative: 1800}, {relative: "Historic exception."})

        updated, failures = RATCHET.update_downward(self.root, original, {relative})

        self.assertEqual(failures, [])
        self.assertNotIn(relative, updated["files"])
        self.assertNotIn(relative, updated["raise_justifications"])
        self.assertEqual(RATCHET.check_changed_sources(self.root, updated, {relative}), ([], {}))

    def test_explicit_raise_requires_changed_source_and_one_line_justification(self) -> None:
        relative = "backend/routers/large.py"
        self.write_source(relative, 1501)
        previous = baseline({relative: 1500})
        raised = baseline({relative: 1501})

        failures = RATCHET.baseline_transition_errors(self.root, previous, raised, {relative})

        self.assertEqual(failures, [f"{relative}: a baseline raise requires a one-line raise_justifications entry"])
        justified = baseline({relative: 1501}, {relative: "#9999 temporary migration boundary."})
        self.assertEqual(RATCHET.baseline_transition_errors(self.root, previous, justified, {relative}), [])

    def test_excludes_tests_generated_and_vendored_paths(self) -> None:
        excluded = [
            "backend/tests/test_big.py",
            "backend/routers/generated.gen.py",
            "desktop/macos/Desktop/Generated/Big.swift",
            "desktop/macos/Backend-Rust/vendor/big.rs",
        ]

        for relative in excluded:
            self.write_source(relative, 2000)
            self.assertFalse(RATCHET.is_product_source(relative), relative)
        self.assertEqual(RATCHET.changed_product_sources(set(excluded)), [])


if __name__ == "__main__":
    unittest.main()
