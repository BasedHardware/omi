#!/usr/bin/env python3
"""Fixture coverage for the fast @MainActor XCTest lifecycle guard."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = REPO_ROOT / "desktop/macos/scripts/check-main-actor-xctest-hooks.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("main_actor_xctest_hooks", GUARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MainActorXCTestHooksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = _load_guard()

    def test_rejects_async_super_hook_in_main_actor_xctest_case(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "UnsafeTests.swift"
            path.write_text(
                "import XCTest\n\n@MainActor\nfinal class UnsafeTests: XCTestCase {\n"
                "  override func setUp() async throws {\n    try await super.setUp()\n  }\n}\n",
                encoding="utf-8",
            )

            findings = self.guard.find_unsafe_hooks(path)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].class_name, "UnsafeTests")
            self.assertEqual(findings[0].hook, "setUp")

    def test_rejects_inline_main_actor_annotation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "UnsafeTests.swift"
            path.write_text(
                "import XCTest\n\n@MainActor final class UnsafeTests: XCTestCase {\n"
                "  override func tearDown() async throws {\n    try await super.tearDown()\n  }\n}\n",
                encoding="utf-8",
            )

            findings = self.guard.find_unsafe_hooks(path)

            self.assertEqual(
                [(finding.class_name, finding.hook) for finding in findings], [("UnsafeTests", "tearDown")]
            )

    def test_allows_nonisolated_or_safe_main_actor_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "SafeMainActorTests.swift").write_text(
                "import XCTest\n\n@MainActor\nfinal class SafeMainActorTests: XCTestCase {\n"
                "  override func setUp() async throws { }\n}\n",
                encoding="utf-8",
            )
            (root / "NonisolatedTests.swift").write_text(
                "import XCTest\n\nfinal class NonisolatedTests: XCTestCase {\n"
                "  override func setUp() async throws {\n    try await super.setUp()\n  }\n}\n",
                encoding="utf-8",
            )

            self.assertEqual(self.guard.find_all_unsafe_hooks(root), [])


if __name__ == "__main__":
    unittest.main()
