#!/usr/bin/env python3
"""Unit tests for check_product_invariants.py (stdlib unittest)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from check_product_invariants import (
    format_suggest_block,
    matched_invariants,
    parse_invariant,
    path_matches,
    pr_body_cites_id,
    load_locked_invariants,
)


SAMPLE = """# INV-CHAT-1: One shared transcript

**Status:** locked
**Statement:** Test.

## Path globs

- `desktop/macos/agent/src/runtime/**`
- `desktop/macos/Desktop/Sources/Chat/**`

## PR rule

Name `INV-CHAT-1` in the PR body if you touch the path globs above.
"""

SAMPLE_UI = """# INV-UI-1: No purple

**Status:** locked

## Path globs

- `web/**`

## PR rule

Do **not** require naming `INV-UI-1` in routine UI PRs.
"""


class PathMatchTests(unittest.TestCase):
    def test_globstar_prefix(self) -> None:
        self.assertTrue(path_matches("desktop/macos/agent/src/runtime/kernel.ts", "desktop/macos/agent/src/runtime/**"))
        self.assertFalse(path_matches("desktop/macos/agent/tests/x.ts", "desktop/macos/agent/src/runtime/**"))

    def test_globstar_zero_segments(self) -> None:
        self.assertTrue(
            path_matches(
                "desktop/macos/Desktop/Sources/MemoryExportService.swift",
                "desktop/macos/Desktop/Sources/**/MemoryExport*",
            )
        )
        self.assertTrue(
            path_matches(
                "desktop/macos/Desktop/Sources/Foo/MemoryExportService.swift",
                "desktop/macos/Desktop/Sources/**/MemoryExport*",
            )
        )

    def test_exact_file(self) -> None:
        self.assertTrue(
            path_matches(
                "desktop/macos/Desktop/Sources/Providers/ChatProvider.swift",
                "desktop/macos/Desktop/Sources/Providers/ChatProvider.swift",
            )
        )


class ParseTests(unittest.TestCase):
    def test_parse_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat.md"
            path.write_text(SAMPLE, encoding="utf-8")
            parsed = parse_invariant(path)
            assert parsed is not None
            self.assertEqual(parsed["id"], "INV-CHAT-1")
            self.assertEqual(parsed["status"], "locked")
            self.assertTrue(parsed["require_naming"])
            self.assertEqual(len(parsed["globs"]), 2)

    def test_skip_naming(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui.md"
            path.write_text(SAMPLE_UI, encoding="utf-8")
            parsed = parse_invariant(path)
            assert parsed is not None
            self.assertFalse(parsed["require_naming"])


class MatchTests(unittest.TestCase):
    def test_matched_requires_naming(self) -> None:
        inv = {
            "id": "INV-CHAT-1",
            "status": "locked",
            "globs": ["desktop/macos/agent/src/runtime/**"],
            "require_naming": True,
            "path": "x",
        }
        ui = {
            "id": "INV-UI-1",
            "status": "locked",
            "globs": ["web/**"],
            "require_naming": False,
            "path": "y",
        }
        hits = matched_invariants(
            ["desktop/macos/agent/src/runtime/kernel.ts", "web/app/x.ts"],
            [inv, ui],
        )
        self.assertEqual([h["id"] for h in hits], ["INV-CHAT-1"])


class CitationTokenTests(unittest.TestCase):
    """pr_body_cites_id must match distinct tokens, not substrings."""

    def test_exact_id_cited(self) -> None:
        self.assertTrue(pr_body_cites_id("INV-CHAT-1", "## Product invariants affected\nINV-CHAT-1"))

    def test_id_in_code_span(self) -> None:
        self.assertTrue(pr_body_cites_id("INV-CHAT-1", "Touches `INV-CHAT-1`."))

    def test_different_number_not_false_positive(self) -> None:
        # INV-CHAT-10 must NOT satisfy a check for INV-CHAT-1
        self.assertFalse(pr_body_cites_id("INV-CHAT-1", "INV-CHAT-10"))

    def test_different_number_not_false_positive_reverse(self) -> None:
        # INV-CHAT-1 must NOT satisfy a check for INV-CHAT-10
        self.assertFalse(pr_body_cites_id("INV-CHAT-10", "INV-CHAT-1"))

    def test_template_html_comment_ignored(self) -> None:
        # The PR template contains INV-CHAT-1 as an example inside HTML comments.
        # A body that is just untouched template text must NOT pass.
        template_body = (
            "## Product invariants affected\n\n"
            "<!-- Name locked invariant IDs this PR touches (e.g. INV-CHAT-1), or \"none\". -->\n"
            "none"
        )
        self.assertFalse(pr_body_cites_id("INV-CHAT-1", template_body))

    def test_real_citation_overrides_template(self) -> None:
        # Even if the template comment is present, a real citation passes.
        template_body = (
            "## Product invariants affected\n\n"
            "<!-- Name locked invariant IDs this PR touches (e.g. INV-CHAT-1), or \"none\". -->\n"
            "INV-CHAT-1"
        )
        self.assertTrue(pr_body_cites_id("INV-CHAT-1", template_body))


class SuggestTests(unittest.TestCase):
    def test_suggest_block_lists_ids(self) -> None:
        block = format_suggest_block(
            [
                {"id": "INV-AUTH-1"},
                {"id": "INV-CHAT-1"},
            ]
        )
        self.assertEqual(
            block,
            "## Product invariants affected\n\n- INV-AUTH-1\n- INV-CHAT-1\n",
        )

    def test_suggest_block_none_when_empty(self) -> None:
        self.assertEqual(format_suggest_block([]), "## Product invariants affected\n\nnone\n")

    def test_suggest_cli_prints_paste_ready_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "changed.txt"
            changed.write_text(
                "desktop/macos/Desktop/Sources/Providers/ChatProvider.swift\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    ".github/scripts/check_product_invariants.py",
                    "--changed-files",
                    str(changed),
                    "--suggest",
                ],
                cwd=Path(__file__).resolve().parents[1].parent,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("## Product invariants affected", result.stdout)
            self.assertIn("- INV-AUTH-1", result.stdout)
            self.assertIn("- INV-CHAT-1", result.stdout)

    def test_failure_includes_suggest_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "changed.txt"
            body = Path(tmp) / "body.md"
            changed.write_text(
                "desktop/macos/Desktop/Sources/Providers/ChatProvider.swift\n",
                encoding="utf-8",
            )
            body.write_text("## Product invariants affected\n\nnone\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    ".github/scripts/check_product_invariants.py",
                    "--changed-files",
                    str(changed),
                    "--pr-body-file",
                    str(body),
                ],
                cwd=Path(__file__).resolve().parents[1].parent,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("Paste this into the PR body", result.stdout)
            self.assertIn("- INV-AUTH-1", result.stdout)
            self.assertIn("- INV-CHAT-1", result.stdout)


class FailClosedTests(unittest.TestCase):
    """load_locked_invariants must fail-closed on malformed invariant docs."""

    def test_malformed_doc_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inv_dir = Path(tmp) / "docs" / "product" / "invariants"
            inv_dir.mkdir(parents=True)
            # Missing the '# INV-XXX-N: Title' header
            (inv_dir / "broken.md").write_text(
                "## Some random doc\n\nNo invariant ID here.\n", encoding="utf-8"
            )
            with self.assertRaises(SystemExit) as ctx:
                load_locked_invariants(Path(tmp))
            self.assertIn("could not parse", str(ctx.exception).lower())

    def test_valid_doc_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inv_dir = Path(tmp) / "docs" / "product" / "invariants"
            inv_dir.mkdir(parents=True)
            (inv_dir / "chat.md").write_text(SAMPLE, encoding="utf-8")
            result = load_locked_invariants(Path(tmp))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["id"], "INV-CHAT-1")


if __name__ == "__main__":
    unittest.main()
