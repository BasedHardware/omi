#!/usr/bin/env python3
"""Behavioral tests for the desktop GRDB insert-idiom checker.

The checker is a static tripwire over Swift sources, so these tests are its
behavioral coverage: each case runs the real `main()` against a disposable source
tree and asserts the exit code and the reported sites.

The positive cases are the two real merged instances the checker exists to catch,
reproduced verbatim from their pre-fix source:

  * `Screenshot` in `RewindDatabase.insertScreenshot` (#11204 -> #11208)
  * `AIUserProfileRecord` in `AIUserProfileService` (#11204 -> #11216)

The negative cases are the Set/Array `insert` shapes that actually occur in
`Desktop/Sources`, which a naive `.insert(` rule would flag.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

CHECKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check-grdb-insert-idiom.py"

_spec = importlib.util.spec_from_file_location("check_grdb_insert_idiom", CHECKER_PATH)
assert _spec and _spec.loader, f"cannot load checker from {CHECKER_PATH}"
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


class GRDBInsertIdiomCheckerTests(unittest.TestCase):
    def _run(self, swift_by_relative_path: dict[str, str]) -> tuple[int, str]:
        """Write a disposable Swift tree, run the real checker, return (exit code, stdout)."""
        with TemporaryDirectory() as tmp:
            sources = Path(tmp) / "Sources"
            for relative_path, body in swift_by_relative_path.items():
                path = sources / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                # lstrip so a triple-quoted body's opening newline does not shift
                # every asserted line number by one.
                path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = checker.main(["--sources-dir", str(sources)])
            return code, buffer.getvalue()

    def test_flags_the_screenshot_instance_from_11208(self):
        # Verbatim shape of RewindDatabase.insertScreenshot before #11208, where
        # every consumer read `if let id = inserted.id` and got nothing.
        code, output = self._run(
            {
                "Rewind/Core/RewindDatabase.swift": """
                func insertScreenshot(_ screenshot: Screenshot) throws -> Screenshot {
                  return try dbQueue.write { db in
                    var record = screenshot
                    try record.insert(db)
                    return record
                  }
                }
                """
            }
        )

        self.assertEqual(code, 1)
        self.assertIn("Rewind/Core/RewindDatabase.swift:4", output)
        self.assertIn("try record.insert(db)", output)

    def test_flags_the_ai_user_profile_instance_from_11216(self):
        code, output = self._run(
            {
                "ProactiveAssistants/Services/AIUserProfileService.swift": """
                func generateProfile() async throws -> AIUserProfileRecord {
                  return try await db.write { database in
                    var record = built
                    try record.insert(database)
                    return record
                  }
                }
                """
            }
        )

        self.assertEqual(code, 1)
        self.assertIn("AIUserProfileService.swift:4", output)

    def test_flags_the_conflict_resolution_overload(self):
        code, output = self._run(
            {"Storage.swift": "try record.insert(db, onConflict: .replace)\n"}
        )

        self.assertEqual(code, 1)
        self.assertIn("Storage.swift:1", output)

    def test_accepts_the_inserted_idiom(self):
        code, output = self._run(
            {
                "Storage.swift": """
                let saved = try record.inserted(db)
                _ = try other.inserted(database)
                """
            }
        )

        self.assertEqual(code, 0)
        self.assertIn("ok:", output)

    def test_does_not_flag_set_and_array_inserts(self):
        # These shapes are all live in Desktop/Sources; a bare `.insert(` rule
        # would flag every one of them.
        code, _ = self._run(
            {
                "Collections.swift": """
                seen.insert(task.id)
                tasks.insert(task, at: 0)
                keys.insert(key)
                names.insert($0.lowercased())
                ids.insert(candidateID)
                """
            }
        )

        self.assertEqual(code, 0)

    def test_reports_every_violation_not_just_the_first(self):
        code, output = self._run(
            {
                "A.swift": "try one.insert(db)\n",
                "B.swift": "try two.insert(database)\n",
            }
        )

        self.assertEqual(code, 1)
        self.assertEqual(output.count("\n- "), 2)

    def test_missing_sources_dir_is_a_usage_error(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = checker.main(["--sources-dir", "/nonexistent/omi/sources"])

        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
