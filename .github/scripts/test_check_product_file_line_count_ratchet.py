#!/usr/bin/env python3
"""Behavioral regression tests for the oversized product-file line ratchet."""

from __future__ import annotations

import importlib.util
import subprocess
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

    def git(self, *args: str) -> None:
        # Drop inherited git environment so subprocesses target this test's
        # temporary repository instead of the enclosing hook's GIT_DIR. This
        # matters when the suite runs under a pre-push/pre-receive context,
        # where git exports GIT_DIR/GIT_WORK_TREE for the parent repository.
        subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
            env=RATCHET._clean_git_env(),
        )

    def test_rejects_growth_of_an_oversized_file(self) -> None:
        relative = "backend/routers/large.py"
        self.write_source(relative, 1501)

        failures, downward = RATCHET.check_changed_sources(self.root, baseline({relative: 1500}), {relative})

        self.assertEqual(downward, {})
        self.assertEqual(len(failures), 1)
        self.assertIn("grew from baseline 1500 to 1501", failures[0])
        self.assertIn("backend-routers.json", failures[0])

    def test_rejects_a_smaller_file_that_crosses_the_threshold(self) -> None:
        relative = "desktop/macos/Desktop/Sources/NewCoordinator.swift"
        self.write_source(relative, RATCHET.THRESHOLD)

        failures, downward = RATCHET.check_changed_sources(self.root, baseline({}), {relative})

        self.assertEqual(downward, {})
        self.assertEqual(len(failures), 1)
        self.assertIn("has no baseline entry", failures[0])
        self.assertIn("desktop-swift-root.json", failures[0])

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

    def test_sharding_round_trips_and_rejects_misplaced_entries(self) -> None:
        router = "backend/routers/large.py"
        floating_control_bar = "desktop/macos/Desktop/Sources/FloatingControlBar/Large.swift"
        aggregate = baseline(
            {router: 1600, floating_control_bar: 1700},
            {router: "Router migration boundary."},
        )

        shards = RATCHET.shard_baseline(aggregate)

        self.assertEqual(RATCHET.aggregate_baseline_shards(shards), aggregate)
        self.assertEqual(
            set(shards),
            {
                RATCHET.baseline_shard_relative(router),
                RATCHET.baseline_shard_relative(floating_control_bar),
            },
        )
        with self.assertRaisesRegex(ValueError, "belongs in"):
            RATCHET.validate_baseline(
                baseline({router: 1600}), RATCHET.baseline_shard_relative(floating_control_bar)
            )
        with self.assertRaisesRegex(ValueError, "duplicate baseline entry"):
            RATCHET.aggregate_baseline_shards(
                {
                    RATCHET.LEGACY_BASELINE_RELATIVE: baseline({router: 1600}),
                    RATCHET.baseline_shard_relative(router): baseline({router: 1600}),
                }
            )

    def test_downward_update_writes_only_the_owning_shard(self) -> None:
        router = "backend/routers/large.py"
        desktop_root = "desktop/macos/Desktop/Sources/Large.swift"
        self.write_source(router, 1550)
        self.write_source(desktop_root, 1600)
        aggregate = baseline({router: 1600, desktop_root: 1600})
        shards = RATCHET.shard_baseline(aggregate)
        RATCHET.write_baseline_shards(self.root, shards, set(shards))
        untouched_path = self.root / RATCHET.baseline_shard_relative(desktop_root)
        untouched_before = untouched_path.read_bytes()

        updated, touched, failures = RATCHET.update_downward_shards(self.root, shards, {router})

        self.assertEqual(failures, [])
        self.assertEqual(touched, {RATCHET.baseline_shard_relative(router)})
        RATCHET.write_baseline_shards(self.root, updated, touched)
        self.assertEqual(untouched_path.read_bytes(), untouched_before)
        self.assertEqual(
            RATCHET.load_baseline(self.root)["files"][router],
            1550,
        )

    def test_baseline_at_ref_supports_legacy_then_sharded_migration(self) -> None:
        router = "backend/routers/large.py"
        desktop_root = "desktop/macos/Desktop/Sources/Large.swift"
        legacy = baseline({router: 1600, desktop_root: 1600}, {router: "Historic migration."})
        legacy_path = self.root / RATCHET.LEGACY_BASELINE_RELATIVE
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(RATCHET.serialize_baseline(legacy), encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.email", "ratchet-test@example.invalid")
        self.git("config", "user.name", "Ratchet Test")
        self.git("add", ".")
        self.git("commit", "-qm", "legacy baseline")
        legacy_ref = RATCHET.baseline_at_ref(self.root, "HEAD")

        legacy_path.unlink()
        shards = RATCHET.shard_baseline(legacy)
        RATCHET.write_baseline_shards(self.root, shards, set(shards))
        self.git("add", "-A")
        self.git("commit", "-qm", "sharded baseline")
        sharded_ref = RATCHET.baseline_at_ref(self.root, "HEAD")

        self.assertEqual(legacy_ref, legacy)
        self.assertEqual(sharded_ref, legacy)


if __name__ == "__main__":
    unittest.main()
