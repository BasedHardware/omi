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
    def _run(self, swift_by_relative_path: dict[str, str]) -> tuple[int, list[str]]:
        """Write a disposable Swift tree, run the real checker.

        Returns the exit code and one `file:line: source` entry per reported
        violation, so every assertion can pin the exact set rather than probing
        for a substring and letting extra reports slip through.
        """
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
            reported = [
                line[2:].replace(f"{sources}/", "")
                for line in buffer.getvalue().splitlines()
                if line.startswith("- ")
            ]
            return code, reported

    def test_flags_the_screenshot_instance_from_11208(self):
        # Verbatim shape of RewindDatabase.insertScreenshot before #11208, where
        # every consumer read `if let id = inserted.id` and got nothing.
        code, reported = self._run(
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
        self.assertEqual(reported, ["Rewind/Core/RewindDatabase.swift:4: try record.insert(db)"])

    def test_flags_the_ai_user_profile_instance_from_11216(self):
        code, reported = self._run(
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
        self.assertEqual(
            reported,
            [
                "ProactiveAssistants/Services/AIUserProfileService.swift:4: "
                "try record.insert(database)"
            ],
        )

    def test_flags_the_conflict_resolution_overload(self):
        code, reported = self._run(
            {"Storage.swift": "try record.insert(db, onConflict: .replace)\n"}
        )

        self.assertEqual(code, 1)
        self.assertEqual(
            reported, ["Storage.swift:1: try record.insert(db, onConflict: .replace)"]
        )

    def test_flags_a_try_expression_split_across_lines(self):
        # swift-format can wrap a long call, so the `try` that proves this is a
        # throwing GRDB call may sit a line above the call itself. The report must
        # point at the call site, not at the `try`.
        code, reported = self._run(
            {
                "Storage.swift": """
                try
                  record.insert(db)
                """
            }
        )

        self.assertEqual(code, 1)
        self.assertEqual(reported, ["Storage.swift:2: record.insert(db)"])

    def test_accepts_the_inserted_idiom(self):
        code, reported = self._run(
            {
                "Storage.swift": """
                let saved = try record.inserted(db)
                _ = try other.inserted(database)
                """
            }
        )

        self.assertEqual(code, 0)
        self.assertEqual(reported, [])

    def test_does_not_flag_set_and_array_inserts(self):
        # These shapes are all live in Desktop/Sources; a bare `.insert(` rule
        # would flag every one of them.
        code, reported = self._run(
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
        self.assertEqual(reported, [])

    def test_does_not_flag_a_collection_element_that_happens_to_be_named_db(self):
        # cubic's case: the argument name alone cannot tell a GRDB handle from an
        # Int. `Set.insert` does not throw, so the absence of `try` settles it.
        code, reported = self._run(
            {
                "Collections.swift": """
                var values: Set<Int> = []
                let db = 123
                values.insert(db)
                let database = 456
                values.insert(database)
                """
            }
        )

        self.assertEqual(code, 0)
        self.assertEqual(reported, [])

    def test_ignores_line_comments(self):
        code, reported = self._run(
            {
                "Storage.swift": """
                // do not call record.insert(db)
                let x = 1  // and never try record.insert(database) either
                """
            }
        )

        self.assertEqual(code, 0)
        self.assertEqual(reported, [])

    def test_ignores_block_comments_including_nested_ones(self):
        code, reported = self._run(
            {
                "Storage.swift": """
                /* outer
                   /* nested: try record.insert(db) */
                   still commented: try record.insert(database)
                */
                try real.insert(db)
                """
            }
        )

        self.assertEqual(code, 1)
        self.assertEqual(reported, ["Storage.swift:5: try real.insert(db)"])

    def test_ignores_string_literals(self):
        code, reported = self._run(
            {
                "Storage.swift": """
                let message = "record.insert(database)"
                let escaped = "he said \\"try record.insert(db)\\" loudly"
                let url = "https://example.com/try record.insert(db)"
                """
            }
        )

        self.assertEqual(code, 0)
        self.assertEqual(reported, [])

    def test_ignores_multiline_and_raw_string_literals(self):
        code, reported = self._run(
            {
                "Storage.swift": '''
                let doc = """
                  Never write try record.insert(db) here.
                  """
                let raw = #"try record.insert(database)"#
                let rawer = ##"try record.insert(db)"##
                '''
            }
        )

        self.assertEqual(code, 0)
        self.assertEqual(reported, [])

    def test_flags_a_real_call_sharing_a_line_with_a_lookalike_comment(self):
        code, reported = self._run(
            {"Storage.swift": "try record.insert(db)  // not values.insert(db)\n"}
        )

        self.assertEqual(code, 1)
        self.assertEqual(
            reported, ["Storage.swift:1: try record.insert(db)  // not values.insert(db)"]
        )

    def test_reports_every_violation_not_just_the_first(self):
        code, reported = self._run(
            {
                "A.swift": "try one.insert(db)\n",
                "B.swift": "try two.insert(database)\ntry three.insert(db)\n",
            }
        )

        self.assertEqual(code, 1)
        self.assertEqual(
            sorted(reported),
            [
                "A.swift:1: try one.insert(db)",
                "B.swift:1: try two.insert(database)",
                "B.swift:2: try three.insert(db)",
            ],
        )

    def test_missing_sources_dir_is_a_usage_error(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = checker.main(["--sources-dir", "/nonexistent/omi/sources"])

        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
