#!/usr/bin/env python3
"""Fixture and sabotage coverage for the desktop compiler-gate tripwire.

The #12867 class: `#if compiler(>=6.2)` wrapped Liquid Glass APIs so the
Xcode 16.4 ship/CI toolchain never typechecked them and the shipped app fell
back to the icon-less system Picker (#13548 reverted the tab bar). A planted
glass-style gate must fail the checker; removing it must pass. The allowlist
is asserted by exact contents so it cannot silently grow.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = REPO_ROOT / "desktop/macos/scripts/check-desktop-compiler-gates.py"
REAL_DESKTOP_ROOT = REPO_ROOT / "desktop/macos/Desktop"

GLASS_GATE_SABOTAGE = """\
import SwiftUI

#if compiler(>=6.2)
struct GlassTabBar: View {
  var body: some View {
    HStack { Text("omi") }.glassEffect()
  }
}
#else
struct GlassTabBar: View {
  var body: some View {
    HStack { Text("omi") }
  }
}
#endif
"""

GATE_REMOVED = """\
import SwiftUI

struct GlassTabBar: View {
  var body: some View {
    HStack { Text("omi") }
  }
}
"""

RUNTIME_AVAILABLE_ONLY = """\
import SwiftUI

struct GlassTabBar: View {
  var body: some View {
    if #available(macOS 26, *) {
      HStack { Text("omi") }.glassEffect()
    } else {
      HStack { Text("omi") }
    }
  }
}
"""

ELSEIF_GATE = """\
#if os(macOS)
let bar = 1
#elseif compiler(>=6.2)
let bar = 2
#endif
"""


def _load_guard():
    spec = importlib.util.spec_from_file_location("desktop_compiler_gates", GUARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DesktopCompilerGatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = _load_guard()

    def _write(self, root: Path, relative: str, source: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    def test_glass_style_compiler_gate_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self._write(root, "Sources/MainWindow/GlassTabBar.swift", GLASS_GATE_SABOTAGE)

            violations, allowed = self.guard.find_all_compiler_gates(root)

            self.assertEqual(allowed, [])
            self.assertEqual(len(violations), 1)
            self.assertEqual(violations[0].path, path)
            self.assertEqual(violations[0].line_number, 3)

    def test_removing_the_gate_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write(root, "Sources/MainWindow/GlassTabBar.swift", GATE_REMOVED)

            violations, _ = self.guard.find_all_compiler_gates(root)

            self.assertEqual(violations, [])

    def test_runtime_availability_without_compiler_gate_passes(self):
        """`#available` runtime gates are the sanctioned pattern, not a violation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write(root, "Sources/MainWindow/GlassTabBar.swift", RUNTIME_AVAILABLE_ONLY)

            violations, _ = self.guard.find_all_compiler_gates(root)

            self.assertEqual(violations, [])

    def test_elseif_compiler_branch_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self._write(root, "Tests/GlassTabBarTests.swift", ELSEIF_GATE)

            violations, _ = self.guard.find_all_compiler_gates(root)

            self.assertEqual([finding.path for finding in violations], [path])

    def test_commented_out_directive_is_inactive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write(
                root,
                "Sources/MainWindow/Legacy.swift",
                "// #if compiler(>=6.2)\nlet legacy = 1\n// #endif\n",
            )

            violations, _ = self.guard.find_all_compiler_gates(root)

            self.assertEqual(violations, [])

    def test_allowlist_is_empty_and_cannot_silently_grow(self):
        """Exact-contents assertion: adding an entry without this test's review fails."""
        self.assertEqual(self.guard.ALLOWED_COMPILER_GATES, ())

    def test_allowlist_entry_must_match_path_and_line_to_suppress(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write(root, "Sources/MainWindow/GlassTabBar.swift", GLASS_GATE_SABOTAGE)

            narrow = (
                self.guard.AllowlistEntry(
                    relative_path="Sources/MainWindow/GlassTabBar.swift",
                    line_contains="#if compiler(>=6.2)",
                    reason="test-only documented exception",
                ),
            )
            violations, allowed = self.guard.find_all_compiler_gates(root, allowlist=narrow)
            self.assertEqual(violations, [])
            self.assertEqual(len(allowed), 1)

            wrong_path = (dataclasses.replace(narrow[0], relative_path="Sources/Other.swift"),)
            violations, _ = self.guard.find_all_compiler_gates(root, allowlist=wrong_path)
            self.assertEqual(len(violations), 1)

    def test_sabotage_fixture_fails_the_cli_and_removal_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write(root, "Sources/MainWindow/GlassTabBar.swift", GLASS_GATE_SABOTAGE)

            planted = subprocess.run(
                [sys.executable, str(GUARD_PATH), "--root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(planted.returncode, 1, planted.stderr)
            self.assertIn("GlassTabBar.swift:3", planted.stderr)
            self.assertIn("#12867", planted.stderr)

            (root / "Sources/MainWindow/GlassTabBar.swift").write_text(GATE_REMOVED, encoding="utf-8")
            removed = subprocess.run(
                [sys.executable, str(GUARD_PATH), "--root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(removed.returncode, 0, removed.stderr + removed.stdout)

    def test_combined_predicate_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self._write(
                root,
                "Sources/MainWindow/GlassTabBar.swift",
                "#if os(macOS) && compiler(>=6.2)\nlet bar = 1\n#endif\n",
            )

            violations, _ = self.guard.find_all_compiler_gates(root)

            self.assertEqual([finding.path for finding in violations], [path])
            self.assertIn("compiler(>=6.2)", violations[0].line)

    def test_block_commented_directive_is_inactive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write(
                root,
                "Sources/MainWindow/Legacy.swift",
                "/*\n#if compiler(>=6.2)\nlet hidden = 1\n#endif\n*/\nlet visible = 1\n",
            )

            violations, _ = self.guard.find_all_compiler_gates(root)

            self.assertEqual(violations, [])

    def test_cli_fails_closed_when_scan_root_is_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            empty = subprocess.run(
                [sys.executable, str(GUARD_PATH), "--root", temp_dir],
                capture_output=True,
                text=True,
            )
            self.assertEqual(empty.returncode, 1, empty.stderr)
            self.assertIn("scanned nothing", empty.stderr)

    def test_real_desktop_tree_has_no_compiler_gates(self):
        violations, _ = self.guard.find_all_compiler_gates(REAL_DESKTOP_ROOT)

        self.assertEqual(
            violations,
            [],
            "the shipped Desktop tree must typecheck every Apple SDK API on the pinned toolchain",
        )


if __name__ == "__main__":
    unittest.main()
