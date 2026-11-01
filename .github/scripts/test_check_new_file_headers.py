#!/usr/bin/env python3
"""Behavioral tests for the new-file purpose-header check."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "check_new_file_headers",
    SCRIPT_DIR / "check_new_file_headers.py",
)
assert SPEC and SPEC.loader
CHECK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECK
SPEC.loader.exec_module(CHECK)

# Code-shaped filler (never comments: a comment filler would itself satisfy the
# header rule, and the line count must clear the small-file exemption).
PAD = "\n".join(f"var pad{i} = {i};" for i in range(50))
PY_PAD = "\n".join(f"pad_{i} = {i}" for i in range(50))


class NewFileHeaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "header-test@example.invalid")
        self.git("config", "user.name", "Header Test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
            env=CHECK.clean_git_env(),
        )

    def commit_base(self) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "base")
        return self.git("rev-parse", "HEAD").stdout.strip()

    def evaluate(self, base: str, changed: list[str]) -> list[str]:
        return CHECK.validate(self.root, changed, base)

    def write(self, relative: str, body: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_new_python_file_requires_docstring(self) -> None:
        base = self.commit_base()
        self.write("backend/utils/new_module.py", "x = 1\n" + PY_PAD + "\n")
        failures = self.evaluate(base, ["backend/utils/new_module.py"])
        self.assertEqual(len(failures), 1)
        self.assertIn("module docstring", failures[0])

    def test_new_python_file_with_docstring_passes(self) -> None:
        base = self.commit_base()
        self.write("backend/utils/documented.py", '"""Owns the frob pipeline."""\nx = 1\n' + PY_PAD + "\n")
        self.assertEqual(self.evaluate(base, ["backend/utils/documented.py"]), [])

    def test_new_python_file_that_does_not_parse_fails_closed(self) -> None:
        base = self.commit_base()
        self.write("backend/utils/broken.py", "def broken(:\n" + PY_PAD + "\n")
        failures = self.evaluate(base, ["backend/utils/broken.py"])
        self.assertEqual(len(failures), 1)
        self.assertIn("cannot parse", failures[0])

    def test_future_import_after_docstring_still_counts(self) -> None:
        base = self.commit_base()
        self.write(
            "backend/utils/ordered.py",
            '"""Docstring first."""\nfrom __future__ import annotations\n' + PY_PAD + "\n",
        )
        self.assertEqual(self.evaluate(base, ["backend/utils/ordered.py"]), [])

    def test_new_dart_file_requires_comment_block(self) -> None:
        base = self.commit_base()
        self.write("app/lib/services/new_service.dart", "import 'dart:async';\n" + PAD + "\nvoid main() {}\n")
        failures = self.evaluate(base, ["app/lib/services/new_service.dart"])
        self.assertEqual(len(failures), 1)
        self.assertIn("purpose header", failures[0])

    def test_leading_comment_block_passes(self) -> None:
        base = self.commit_base()
        self.write(
            "app/lib/services/documented.dart",
            "// Owns the wal drain.\n// One ledger, one uploader.\nimport 'dart:async';\n" + PAD + "\n",
        )
        self.assertEqual(self.evaluate(base, ["app/lib/services/documented.dart"]), [])

    def test_after_import_swift_doc_comment_passes(self) -> None:
        base = self.commit_base()
        self.write(
            "desktop/macos/Desktop/Sources/Chat/Documented.swift",
            "import Foundation\n\n/// Owns video sampling on device.\n/// The whole file never leaves the Mac.\n" + PAD + "\nstruct Sample {}\n",
        )
        self.assertEqual(self.evaluate(base, ["desktop/macos/Desktop/Sources/Chat/Documented.swift"]), [])

    def test_block_comment_header_passes_for_typescript(self) -> None:
        base = self.commit_base()
        self.write(
            "desktop/macos/agent/src/sender.ts",
            "/**\n * Backpressure-aware line sender.\n * Waits for drain instead of stalling.\n */\n" + PAD + "\nexport const x = 1;\n",
        )
        self.assertEqual(self.evaluate(base, ["desktop/macos/agent/src/sender.ts"]), [])

    def test_single_marker_comment_is_not_a_header(self) -> None:
        base = self.commit_base()
        self.write("app/lib/pages/one_line.dart", "// TODO: tidy\nimport 'dart:async';\n" + PAD + "\n")
        failures = self.evaluate(base, ["app/lib/pages/one_line.dart"])
        self.assertEqual(len(failures), 1)

    def test_comment_after_real_code_does_not_count(self) -> None:
        base = self.commit_base()
        self.write(
            "app/lib/pages/late_comment.dart",
            "const chunkSize = 60;\n// Owns chunking.\n// Second line.\n" + PAD + "\n",
        )
        self.assertEqual(len(self.evaluate(base, ["app/lib/pages/late_comment.dart"])), 1)

    def test_modified_file_is_ignored(self) -> None:
        self.write("backend/utils/existing.py", "x = 1\n" + "y = 2\n" * 30)
        base = self.commit_base()
        self.write("backend/utils/existing.py", "x = 2\n" + "y = 2\n" * 30)
        self.assertEqual(self.evaluate(base, ["backend/utils/existing.py"]), [])

    def test_small_files_are_exempt(self) -> None:
        base = self.commit_base()
        self.write("backend/utils/tiny.py", "x = 1\n")
        self.write("app/lib/tiny.dart", "import 'dart:async';\nvoid main() {}\n")
        self.assertEqual(
            self.evaluate(base, ["backend/utils/tiny.py", "app/lib/tiny.dart"]),
            [],
        )

    def test_init_test_and_generated_files_are_exempt(self) -> None:
        base = self.commit_base()
        self.write("backend/newpkg/__init__.py", "x = 1\n")
        self.write("app/test/widgets/new_page_test.dart", PAD + "\n")
        self.write("backend/tests/unit/test_new_thing.py", "def test_x():\n    assert 1\n" * 15)
        self.write("app/lib/gen/pigeon_stuff.g.dart", PAD + "\n")
        self.write("desktop/macos/Desktop/Sources/Generated/Tool.swift", PAD + "\n")
        self.assertEqual(
            self.evaluate(
                base,
                [
                    "backend/newpkg/__init__.py",
                    "app/test/widgets/new_page_test.dart",
                    "backend/tests/unit/test_new_thing.py",
                    "app/lib/gen/pigeon_stuff.g.dart",
                    "desktop/macos/Desktop/Sources/Generated/Tool.swift",
                ],
            ),
            [],
        )

    def test_out_of_scope_paths_and_extensions_are_ignored(self) -> None:
        base = self.commit_base()
        self.write("web/frontend/src/new_page.tsx", PAD + "\n")
        self.write("desktop/macos/scripts/new_tool.py", "x = 1\n" * 50)
        self.write("desktop/macos/agent/src/patched-acp-entry.mjs", PAD + "\n")
        self.assertEqual(
            self.evaluate(
                base,
                ["web/frontend/src/new_page.tsx", "desktop/macos/scripts/new_tool.py", "desktop/macos/agent/src/patched-acp-entry.mjs"],
            ),
            [],
        )

    def test_real_incident_shape_fails(self) -> None:
        # PR #14527 added the 231-line headerless app/lib/backend/http/api_result.dart:
        # imports straight into declarations, no comment block anywhere before code.
        base = self.commit_base()
        self.write("app/lib/backend/http/api_result.dart", "import 'dart:async';\n" + PAD + "\n")
        failures = self.evaluate(base, ["app/lib/backend/http/api_result.dart"])
        self.assertEqual(len(failures), 1)
        self.assertIn("api_result.dart", failures[0])


if __name__ == "__main__":
    unittest.main()
