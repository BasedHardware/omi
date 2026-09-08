#!/usr/bin/env python3
"""Unit tests for check_product_invariants.py (stdlib unittest)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from check_product_invariants import (
    audit_registry,
    format_invariant_briefing,
    format_suggest_block,
    matched_invariants,
    missing_invariant_hits,
    parse_invariant,
    path_matches,
    pr_body_cites_id,
    load_locked_invariants,
    whole_tree_globs,
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
            inv_dir = Path(tmp) / "product" / "invariants"
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
            inv_dir = Path(tmp) / "product" / "invariants"
            inv_dir.mkdir(parents=True)
            (inv_dir / "chat.md").write_text(SAMPLE, encoding="utf-8")
            result = load_locked_invariants(Path(tmp))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["id"], "INV-CHAT-1")


class SquashCommitBodyTests(unittest.TestCase):
    """#11835: squash commit list is not a substitute for the PR body."""

    def test_about_user_voice_paths_require_inv_chat_1(self) -> None:
        root = Path(__file__).resolve().parents[1].parent
        invariants = load_locked_invariants(root)
        hits = matched_invariants(
            [
                "desktop/windows/src/renderer/src/lib/voice/aboutUser.ts",
                "desktop/windows/src/renderer/src/lib/voice/aboutUser.test.ts",
            ],
            invariants,
        )
        ids = {hit["id"] for hit in hits}
        self.assertIn("INV-CHAT-1", ids)

    def test_squash_commit_list_without_citation_fails(self) -> None:
        root = Path(__file__).resolve().parents[1].parent
        invariants = load_locked_invariants(root)
        hits = matched_invariants(
            ["desktop/windows/src/renderer/src/lib/voice/aboutUser.ts"],
            invariants,
        )
        squash_body = (
            "Cut the Windows app's idle and focus-driven backend request volume (#11835)\n\n"
            "* Stop rebuilding the about-user card on every voice hub warm\n"
        )
        missing = missing_invariant_hits(hits, squash_body)
        self.assertTrue(any(hit["id"] == "INV-CHAT-1" for hit in missing))

    def test_appended_pr_body_citation_passes(self) -> None:
        root = Path(__file__).resolve().parents[1].parent
        invariants = load_locked_invariants(root)
        hits = matched_invariants(
            ["desktop/windows/src/renderer/src/lib/voice/aboutUser.ts"],
            invariants,
        )
        combined = (
            "Cut the Windows app's idle and focus-driven backend request volume (#11835)\n\n"
            "* Stop rebuilding the about-user card\n\n"
            "## Product invariants affected\n\n- INV-CHAT-1\n"
        )
        self.assertEqual(missing_invariant_hits(hits, combined), [])




REPO_ROOT = Path(__file__).resolve().parents[2]


def _registry(tmp: Path, docs: dict[str, str], index_rows: str = "") -> Path:
    """Build a throwaway registry so the audit can be tested on real shapes."""
    directory = tmp / "product" / "invariants"
    directory.mkdir(parents=True)
    for name, body in docs.items():
        (directory / name).write_text(body, encoding="utf-8")
    (directory / "README.md").write_text(
        "# Product Invariant Registry\n\n| ID | Title | Status | Doc |\n|----|----|----|----|\n" + index_rows,
        encoding="utf-8",
    )
    (tmp / ".github").mkdir(exist_ok=True)
    return tmp


LOCKED_DOC = """# INV-TEST-1: Example

**Status:** locked
**Statement:** Example statement.

## MUST NOT

- Do the bad thing.

## Guard tests

- `guards/present.py`

## Path globs

- `backend/utils/example/**`

## PR rule

Name this invariant ID in the PR body if you touch the path globs above.
"""


class RegistryAuditTests(unittest.TestCase):
    """The registry must hold up its own claims, continuously."""

    def test_this_repository_registry_is_clean(self):
        self.assertEqual(audit_registry(REPO_ROOT), [])

    def test_locked_invariant_naming_a_missing_guard_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _registry(
                Path(tmp),
                {"example.md": LOCKED_DOC},
                "| INV-TEST-1 | Example | locked | [example.md](./example.md) |\n",
            )
            problems = audit_registry(root)
            self.assertTrue(any("does not exist: guards/present.py" in p for p in problems), problems)

    def test_guard_present_but_unwired_check_script_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = LOCKED_DOC.replace("`guards/present.py`", "`.github/scripts/check_example.py`")
            _registry(root, {"example.md": doc}, "| INV-TEST-1 | Example | locked | [example.md](./example.md) |\n")
            (root / ".github" / "scripts").mkdir(parents=True)
            (root / ".github" / "scripts" / "check_example.py").write_text("", encoding="utf-8")
            problems = audit_registry(root)
            self.assertTrue(any("no checks-manifest entry runs" in p for p in problems), problems)

            (root / ".github" / "checks-manifest.yaml").write_text(
                'checks:\n  - id: example\n    command: ["python3", ".github/scripts/check_example.py"]\n',
                encoding="utf-8",
            )
            self.assertEqual(audit_registry(root), [])

    def test_doc_missing_from_index_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _registry(Path(tmp), {"example.md": LOCKED_DOC.replace("`guards/present.py`", "`README.md`")}, "")
            self.assertTrue(any("missing from the README index" in p for p in audit_registry(root)), root)

    def test_index_row_without_a_doc_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _registry(
                Path(tmp),
                {},
                "| INV-GHOST-1 | Ghost | locked | [ghost.md](./ghost.md) |\n",
            )
            self.assertTrue(any("no matching doc" in p for p in audit_registry(root)), root)

    def test_unbackticked_glob_bullet_fails_instead_of_being_ignored(self):
        doc = LOCKED_DOC.replace("- `backend/utils/example/**`", "- backend/utils/example/**")
        with tempfile.TemporaryDirectory() as tmp:
            root = _registry(
                Path(tmp), {"example.md": doc.replace("`guards/present.py`", "`README.md`")},
                "| INV-TEST-1 | Example | locked | [example.md](./example.md) |\n",
            )
            self.assertTrue(any("silently ignored" in p for p in audit_registry(root)), root)

    def test_glob_may_carry_a_trailing_note(self):
        doc = LOCKED_DOC.replace(
            "- `backend/utils/example/**`", "- `backend/utils/example/**` (retired: must not return)"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.md"
            path.write_text(doc, encoding="utf-8")
            self.assertEqual(parse_invariant(path)["globs"], ["backend/utils/example/**"])
            self.assertEqual(parse_invariant(path)["unparsed_globs"], [])


class WholeTreeGlobTests(unittest.TestCase):
    def test_app_roots_are_whole_tree(self):
        self.assertEqual(
            whole_tree_globs(["backend/**", "desktop/macos/Desktop/Sources/**"]),
            ["backend/**", "desktop/macos/Desktop/Sources/**"],
        )

    def test_a_scoped_subtree_is_not_whole_tree(self):
        self.assertEqual(whole_tree_globs(["backend/utils/task_intelligence/**"]), [])

    def test_citation_on_a_whole_tree_glob_fails(self):
        doc = LOCKED_DOC.replace("- `backend/utils/example/**`", "- `backend/**`").replace(
            "`guards/present.py`", "`README.md`"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = _registry(
                Path(tmp), {"example.md": doc},
                "| INV-TEST-1 | Example | locked | [example.md](./example.md) |\n",
            )
            self.assertTrue(any("whole-tree glob" in p for p in audit_registry(root)), root)

    def test_opting_out_of_naming_clears_it(self):
        doc = (
            LOCKED_DOC.replace("- `backend/utils/example/**`", "- `backend/**`")
            .replace("`guards/present.py`", "`README.md`")
            .replace(
                "Name this invariant ID in the PR body if you touch the path globs above.",
                "Do **not** require naming; the guard enforces the floor.",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = _registry(
                Path(tmp), {"example.md": doc},
                "| INV-TEST-1 | Example | locked | [example.md](./example.md) |\n",
            )
            self.assertEqual(audit_registry(root), [])


class BriefingTests(unittest.TestCase):
    """A failure must carry the rule, not just the token."""

    def test_briefing_includes_statement_and_must_nots(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.md"
            path.write_text(LOCKED_DOC, encoding="utf-8")
            hit = {
                **parse_invariant(path),
                "matched_files": ["backend/utils/example/a.py"],
                "matched_by_glob": {"backend/utils/example/**": ["backend/utils/example/a.py"]},
            }
            text = format_invariant_briefing([hit])
            self.assertIn("Example statement.", text)
            self.assertIn("- Do the bad thing.", text)
            self.assertIn("backend/utils/example/a.py", text)

    def test_briefing_says_which_glob_made_it_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.md"
            path.write_text(LOCKED_DOC, encoding="utf-8")
            hit = {
                **parse_invariant(path),
                "matched_files": ["backend/utils/example/a.py"],
                "matched_by_glob": {"backend/utils/example/**": ["backend/utils/example/a.py"]},
            }
            text = format_invariant_briefing([hit])
            self.assertIn("Why it applies:", text)
            self.assertIn("`backend/utils/example/**` matched 1 changed file(s)", text)

    def test_briefing_lists_every_must_not_rather_than_a_sample(self):
        doc = LOCKED_DOC.replace(
            "- Do the bad thing.",
            "\n".join(f"- Rule number {i}." for i in range(1, 10)),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.md"
            path.write_text(doc, encoding="utf-8")
            hit = {**parse_invariant(path), "matched_files": [], "matched_by_glob": {}}
            text = format_invariant_briefing([hit])
            self.assertIn("MUST NOT (9):", text)
            self.assertIn("- Rule number 9.", text)


class GlobAttributionTests(unittest.TestCase):
    def test_a_file_is_attributed_to_every_glob_that_caught_it(self):
        inv = {
            "id": "INV-TEST-1",
            "globs": ["backend/**", "backend/utils/example/**"],
            "require_naming": True,
        }
        hit = matched_invariants(["backend/utils/example/a.py"], [inv])[0]
        self.assertEqual(
            hit["matched_by_glob"],
            {
                "backend/**": ["backend/utils/example/a.py"],
                "backend/utils/example/**": ["backend/utils/example/a.py"],
            },
        )

    def test_unmatched_globs_are_absent_from_the_attribution(self):
        inv = {"id": "INV-TEST-1", "globs": ["backend/**", "web/**"], "require_naming": True}
        hit = matched_invariants(["backend/a.py"], [inv])[0]
        self.assertEqual(list(hit["matched_by_glob"]), ["backend/**"])


if __name__ == "__main__":
    unittest.main()
