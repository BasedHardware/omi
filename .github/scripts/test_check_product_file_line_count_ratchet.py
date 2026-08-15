#!/usr/bin/env python3
"""Behavioral tests for the base-derived oversized product-file ratchet."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "product_file_line_count_ratchet",
    SCRIPT_DIR / "check_product_file_line_count_ratchet.py",
)
assert SPEC and SPEC.loader
RATCHET = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RATCHET
SPEC.loader.exec_module(RATCHET)


class ProductFileLineCountRatchetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "ratchet-test@example.invalid")
        self.git("config", "user.name", "Ratchet Test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
            env=RATCHET.clean_git_env(),
        )

    def write_source(self, relative: str, lines: int) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("line\n" * lines, encoding="utf-8")

    def commit_base(self) -> str:
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        return self.git("rev-parse", "HEAD").stdout.strip()

    def evaluate(self, base: str, changed: set[str], body: str = "") -> list[str]:
        exceptions, parse_failures = RATCHET.parse_exceptions(body)
        return parse_failures + RATCHET.evaluate_changes(self.root, base, changed, exceptions)

    def test_rejects_oversized_growth_with_exact_suggestion(self) -> None:
        relative = "backend/routers/large.py"
        self.write_source(relative, 1500)
        base = self.commit_base()
        self.write_source(relative, 1501)

        failures = self.evaluate(base, {relative})

        self.assertEqual(len(failures), 1)
        self.assertIn("grew from 1500 to 1501", failures[0])
        self.assertIn(f"Line-Count-Exception: {relative} | 1500 -> 1501", failures[0])

    def test_exact_exception_approves_growth_without_repository_metadata(self) -> None:
        relative = "desktop/macos/Desktop/Sources/MainWindow/Large.swift"
        self.write_source(relative, 1600)
        base = self.commit_base()
        self.write_source(relative, 1625)
        body = f"Line-Count-Exception: {relative} | 1600 -> 1625 | Citation layout remains at its owner."

        self.assertEqual(self.evaluate(base, {relative}, body), [])
        self.assertFalse((self.root / ".github").exists())

    def test_threshold_crossing_requires_exception(self) -> None:
        relative = "desktop/macos/Desktop/Sources/NewCoordinator.swift"
        self.write_source(relative, 1499)
        base = self.commit_base()
        self.write_source(relative, 1500)

        failures = self.evaluate(base, {relative})

        self.assertEqual(len(failures), 1)
        self.assertIn("1499 to 1500", failures[0])

    def test_new_oversized_file_uses_zero_as_base(self) -> None:
        placeholder = "backend/routers/existing.py"
        self.write_source(placeholder, 1)
        base = self.commit_base()
        relative = "backend/routers/new_large.py"
        self.write_source(relative, 1500)
        body = f"Line-Count-Exception: {relative} | 0 -> 1500 | New generated-free router boundary."

        self.assertEqual(self.evaluate(base, {relative}, body), [])

    def test_reduction_and_split_ratchet_down_automatically(self) -> None:
        reduced = "backend/routers/reduced.py"
        split = "desktop/macos/Desktop/Sources/Split.swift"
        self.write_source(reduced, 1800)
        self.write_source(split, 1700)
        base = self.commit_base()
        self.write_source(reduced, 1600)
        self.write_source(split, 1499)

        self.assertEqual(self.evaluate(base, {reduced, split}), [])

    def test_synthetic_merge_honors_a_concurrent_target_branch_reduction(self) -> None:
        relative = "backend/routers/concurrent.py"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"base-{index}\n" for index in range(1600)), encoding="utf-8")
        common = self.commit_base()

        self.git("checkout", "-qb", "candidate")
        with path.open("a", encoding="utf-8") as source:
            source.write("".join(f"candidate-{index}\n" for index in range(10)))
        self.git("add", relative)
        self.git("commit", "-qm", "candidate growth")
        head = self.git("rev-parse", "HEAD").stdout.strip()

        self.git("checkout", "-qb", "target", common)
        path.write_text("".join(f"base-{index}\n" for index in range(100, 1600)), encoding="utf-8")
        self.git("add", relative)
        self.git("commit", "-qm", "target reduction")
        base = self.git("rev-parse", "HEAD").stdout.strip()

        candidate_tree = RATCHET.synthetic_merge_tree(self.root, base, head)
        failures = RATCHET.evaluate_changes(
            self.root,
            base,
            {relative},
            {},
            candidate_ref=candidate_tree,
        )

        self.assertEqual(RATCHET.source_count_at_ref(self.root, base, relative), 1500)
        self.assertEqual(RATCHET.source_count_at_ref(self.root, candidate_tree, relative), 1510)
        self.assertEqual(len(failures), 1)
        self.assertIn("grew from 1500 to 1510", failures[0])

    def test_rejects_malformed_duplicate_mismatched_and_unused_exceptions(self) -> None:
        growing = "backend/routers/growing.py"
        unchanged = "backend/routers/unchanged.py"
        self.write_source(growing, 1500)
        self.write_source(unchanged, 1600)
        base = self.commit_base()
        self.write_source(growing, 1510)
        body = "\n".join(
            [
                "Line-Count-Exception: malformed",
                f"Line-Count-Exception: {growing} | 1499 -> 1510 | Wrong base count is rejected.",
                f"Line-Count-Exception: {growing} | 1500 -> 1510 | Duplicate declaration is rejected.",
                f"Line-Count-Exception: {unchanged} | 1600 -> 1601 | Copied stale approval is rejected.",
            ]
        )

        failures = self.evaluate(base, {growing}, body)

        self.assertTrue(any("malformed" in failure for failure in failures))
        self.assertTrue(any("duplicate" in failure for failure in failures))
        self.assertTrue(any("diff is 1500 -> 1510" in failure for failure in failures))
        self.assertTrue(any("unchanged source" in failure for failure in failures))

    def test_excludes_tests_generated_and_vendored_paths(self) -> None:
        excluded = [
            "backend/tests/test_big.py",
            "backend/routers/generated.gen.py",
            "backend/routers/../escaped.py",
            "desktop/macos/Desktop/Generated/Big.swift",
            "desktop/macos/Desktop/.build/checkouts/Vendor.swift",
        ]

        for relative in excluded:
            self.assertFalse(RATCHET.is_product_source(relative), relative)

    def test_parser_rejects_short_reason_and_unsupported_path(self) -> None:
        _, failures = RATCHET.parse_exceptions(
            "\n".join(
                [
                    "Line-Count-Exception: README.md | 0 -> 1500 | Long enough reason.",
                    "Line-Count-Exception: backend/routers/large.py | 1500 -> 1501 | short",
                ]
            )
        )

        self.assertEqual(len(failures), 2)

    def test_repository_has_no_mutable_baseline_ledger(self) -> None:
        ledger = SCRIPT_DIR / "product_file_line_count_ratchet_baseline"
        self.assertEqual(list(ledger.glob("*.json")), [])

    def test_git_subprocess_environment_drops_hook_redirects(self) -> None:
        original = RATCHET.os.environ.copy()
        try:
            RATCHET.os.environ["GIT_DIR"] = "/wrong/repository"
            RATCHET.os.environ["GIT_WORK_TREE"] = "/wrong/worktree"
            RATCHET.os.environ["GIT_COMMON_DIR"] = "/wrong/common-directory"
            RATCHET.os.environ["GIT_INDEX_FILE"] = "/wrong/index"
            cleaned = RATCHET.clean_git_env()
        finally:
            RATCHET.os.environ.clear()
            RATCHET.os.environ.update(original)

        self.assertNotIn("GIT_DIR", cleaned)
        self.assertNotIn("GIT_WORK_TREE", cleaned)
        self.assertNotIn("GIT_COMMON_DIR", cleaned)
        self.assertNotIn("GIT_INDEX_FILE", cleaned)


if __name__ == "__main__":
    unittest.main()
