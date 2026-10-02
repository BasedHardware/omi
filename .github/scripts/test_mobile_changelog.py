#!/usr/bin/env python3
"""Unit tests for mobile changelog tooling and its PR/push gate (stdlib unittest)."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("mobile_changelog", Path(__file__).with_name("mobile-changelog.py"))
changelog = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(changelog)

_CHECK_SPEC = importlib.util.spec_from_file_location(
    "check_mobile_changelog", Path(__file__).with_name("check-mobile-changelog.py")
)
checker = importlib.util.module_from_spec(_CHECK_SPEC)
_CHECK_SPEC.loader.exec_module(checker)


@contextlib.contextmanager
def patched_changelog_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        unreleased = Path(tmp) / "unreleased"
        releases = Path(tmp) / "releases"
        unreleased.mkdir()
        releases.mkdir()
        with (
            unittest.mock.patch.object(changelog, "UNRELEASED_DIR", unreleased),
            unittest.mock.patch.object(changelog, "RELEASES_DIR", releases),
        ):
            yield unreleased, releases


def write_fragment(unreleased: Path, name: str, data: object) -> Path:
    path = unreleased / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class FragmentValidationTests(unittest.TestCase):
    def test_change_fragment_returns_verbatim_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260924-chat.json"
            changelog.write_json(path, {"change": "Calls now show live transcription"})
            self.assertEqual(changelog.read_unreleased_fragment(path), ["Calls now show live transcription"])

    def test_change_whitespace_is_preserved_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260924-padded.json"
            changelog.write_json(path, {"change": "  padded  entry  "})
            self.assertEqual(changelog.read_unreleased_fragment(path), ["  padded  entry  "])

    def test_none_kind_contributes_no_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260924-internal.json"
            changelog.write_json(path, {"kind": "none"})
            self.assertEqual(changelog.read_unreleased_fragment(path), [])

    def test_invalid_fragments_fail(self) -> None:
        cases = (
            {},
            {"change": ""},
            {"change": "   "},
            {"change": 5},
            {"changes": ["a list is not the mobile fragment shape"]},
            ["not an object"],
            {"kind": "other"},
        )
        for index, data in enumerate(cases):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"bad-{index}.json"
                changelog.write_json(path, data)
                with self.assertRaises(changelog.ChangelogError):
                    changelog.read_unreleased_fragment(path)


class CollectTests(unittest.TestCase):
    def test_collect_writes_release_and_consumes_fragments(self) -> None:
        with patched_changelog_dirs() as (unreleased, releases):
            write_fragment(unreleased, "20260924-a-search.json", {"change": "Search across all your memories"})
            write_fragment(unreleased, "20260925-b-tasks.json", {"change": "Export or delete multiple tasks at once"})
            release = changelog.collect("1.2.3", "2026-09-24")
            self.assertEqual(
                release,
                {
                    "version": "1.2.3",
                    "date": "2026-09-24",
                    "changes": ["Search across all your memories", "Export or delete multiple tasks at once"],
                },
            )
            self.assertEqual(changelog.read_json(releases / "1.2.3.json"), release)
            self.assertEqual(list(unreleased.glob("*.json")), [])

    def test_collect_merges_after_existing_lines_in_order(self) -> None:
        with patched_changelog_dirs() as (unreleased, releases):
            changelog.write_json(
                releases / "1.2.3.json",
                {"version": "1.2.3", "date": "2026-09-20", "changes": ["  kept verbatim  "]},
            )
            write_fragment(unreleased, "20260924-new.json", {"change": "New authored line"})
            release = changelog.collect("1.2.3", "2026-09-24")
            self.assertEqual(release["changes"], ["  kept verbatim  ", "New authored line"])
            self.assertEqual(release["date"], "2026-09-20")
            self.assertEqual(list(unreleased.glob("*.json")), [])

    def test_collect_with_existing_release_and_no_fragments_is_idempotent(self) -> None:
        with patched_changelog_dirs() as (unreleased, releases):
            release_path = releases / "1.2.3.json"
            changelog.write_json(
                release_path, {"version": "1.2.3", "date": "2026-09-20", "changes": ["Existing line"]}
            )
            before = release_path.read_text(encoding="utf-8")
            release = changelog.collect("1.2.3", "2026-09-24")
            self.assertEqual(release["changes"], ["Existing line"])
            self.assertEqual(release_path.read_text(encoding="utf-8"), before)

    def test_collect_fails_closed_without_fragments_or_release(self) -> None:
        with patched_changelog_dirs() as (unreleased, releases):
            with self.assertRaises(changelog.ChangelogError):
                changelog.collect("1.2.3", "2026-09-24")
            self.assertFalse((releases / "1.2.3.json").exists())

    def test_collect_none_only_fragments_persist_empty_changes(self) -> None:
        with patched_changelog_dirs() as (unreleased, releases):
            write_fragment(unreleased, "20260924-internal.json", {"kind": "none"})
            release = changelog.collect("1.2.3", "2026-09-24")
            self.assertEqual(release["changes"], [])
            self.assertEqual(list(unreleased.glob("*.json")), [])

    def test_collect_validates_every_fragment_before_mutating(self) -> None:
        with patched_changelog_dirs() as (unreleased, releases):
            write_fragment(unreleased, "20260924-good.json", {"change": "Good line"})
            write_fragment(unreleased, "20260925-bad.json", {"change": ""})
            with self.assertRaises(changelog.ChangelogError):
                changelog.collect("1.2.3", "2026-09-24")
            self.assertFalse((releases / "1.2.3.json").exists())
            self.assertTrue((unreleased / "20260924-good.json").is_file())
            self.assertTrue((unreleased / "20260925-bad.json").is_file())

    def test_collect_rejects_non_strict_version_and_date(self) -> None:
        with patched_changelog_dirs() as (unreleased, _releases):
            write_fragment(unreleased, "20260924-a.json", {"change": "A line"})
            for bad in ("v1.2.3", "1.2", "1.2.3.4", "1.02.3"):
                with self.subTest(version=bad):
                    with self.assertRaises(changelog.ChangelogError):
                        changelog.collect(bad, "2026-09-24")
            with self.assertRaises(changelog.ChangelogError):
                changelog.collect("1.2.3", "2026-13-45")
            with self.assertRaises(changelog.ChangelogError):
                changelog.collect("1.2.3", "24-09-2026")


class StoreNotesTests(unittest.TestCase):
    def test_missing_release_file_fails_closed(self) -> None:
        with patched_changelog_dirs():
            with self.assertRaises(changelog.ChangelogError):
                changelog.store_notes("9.9.9", "ios")

    def test_none_only_release_yields_exact_fallback(self) -> None:
        with patched_changelog_dirs() as (_unreleased, releases):
            changelog.write_json(releases / "1.2.3.json", {"version": "1.2.3", "date": "2026-09-24", "changes": []})
            self.assertEqual(changelog.store_notes("1.2.3", "ios"), "Bug fixes and improvements")
            self.assertEqual(changelog.store_notes("1.2.3", "android"), "Bug fixes and improvements")

    def test_ios_notes_are_newline_bullets_within_budget(self) -> None:
        with patched_changelog_dirs() as (_unreleased, releases):
            changelog.write_json(
                releases / "1.2.3.json",
                {"version": "1.2.3", "date": "2026-09-24", "changes": ["First", "Second"]},
            )
            self.assertEqual(changelog.store_notes("1.2.3", "ios"), "- First\n- Second")

    def test_ios_notes_drop_trailing_whole_lines(self) -> None:
        with patched_changelog_dirs() as (_unreleased, releases):
            changes = ["x" * 3997, "dropped one", "dropped two"]
            changelog.write_json(
                releases / "1.2.3.json", {"version": "1.2.3", "date": "2026-09-24", "changes": changes}
            )
            notes = changelog.store_notes("1.2.3", "ios")
            self.assertEqual(notes, "- " + "x" * 3997)
            self.assertLessEqual(len(notes), changelog.IOS_NOTES_LIMIT)

    def test_ios_notes_reject_oversized_first_line(self) -> None:
        with patched_changelog_dirs() as (_unreleased, releases):
            changelog.write_json(
                releases / "1.2.3.json",
                {"version": "1.2.3", "date": "2026-09-24", "changes": ["x" * 4000]},
            )
            with self.assertRaises(changelog.ChangelogError):
                changelog.store_notes("1.2.3", "ios")

    def test_android_notes_join_authored_lines_within_budget(self) -> None:
        with patched_changelog_dirs() as (_unreleased, releases):
            changelog.write_json(
                releases / "1.2.3.json",
                {"version": "1.2.3", "date": "2026-09-24", "changes": ["First", "Second", "Third"]},
            )
            self.assertEqual(changelog.store_notes("1.2.3", "android"), "First; Second; Third")

    def test_android_notes_drop_trailing_lines_over_budget(self) -> None:
        with patched_changelog_dirs() as (_unreleased, releases):
            changes = ["a" * 498, "will not fit"]
            changelog.write_json(
                releases / "1.2.3.json", {"version": "1.2.3", "date": "2026-09-24", "changes": changes}
            )
            self.assertEqual(changelog.store_notes("1.2.3", "android"), "a" * 498)

    def test_android_notes_truncate_first_line_at_whole_word(self) -> None:
        with patched_changelog_dirs() as (_unreleased, releases):
            first = "word " * 120 + "tailword"
            changelog.write_json(
                releases / "1.2.3.json", {"version": "1.2.3", "date": "2026-09-24", "changes": [first]}
            )
            notes = changelog.store_notes("1.2.3", "android")
            self.assertLessEqual(len(notes), changelog.ANDROID_NOTES_LIMIT)
            self.assertTrue(first.startswith(notes))
            self.assertEqual(first[len(notes)], " ")

    def test_android_notes_reject_first_line_without_whole_word(self) -> None:
        with patched_changelog_dirs() as (_unreleased, releases):
            changelog.write_json(
                releases / "1.2.3.json",
                {"version": "1.2.3", "date": "2026-09-24", "changes": ["x" * 600]},
            )
            with self.assertRaises(changelog.ChangelogError):
                changelog.store_notes("1.2.3", "android")

    def test_store_notes_never_rewrite_the_release_file(self) -> None:
        with patched_changelog_dirs() as (_unreleased, releases):
            release_path = releases / "1.2.3.json"
            changelog.write_json(
                release_path,
                {"version": "1.2.3", "date": "2026-09-24", "changes": ["word " * 120 + "tailword"]},
            )
            before = release_path.read_text(encoding="utf-8")
            changelog.store_notes("1.2.3", "android")
            self.assertEqual(release_path.read_text(encoding="utf-8"), before)

    def test_store_notes_rejects_bad_platform_and_version(self) -> None:
        with patched_changelog_dirs():
            with self.assertRaises(changelog.ChangelogError):
                changelog.store_notes("1.2.3", "web")
            with self.assertRaises(changelog.ChangelogError):
                changelog.store_notes("v1.2.3", "ios")


class GatePathClassificationTests(unittest.TestCase):
    def test_internal_allowlist_paths_do_not_require_a_fragment(self) -> None:
        for path in sorted(checker.EXEMPT_APP_PATHS):
            with self.subTest(path=path):
                self.assertTrue(path.startswith("app/"))
                self.assertFalse(checker.is_app_change_requiring_changelog(path))

    def test_changelog_tree_is_exempt(self) -> None:
        for path in (
            "app/changelog/README.md",
            "app/changelog/unreleased/20260924-anything.json",
            "app/changelog/releases/1.2.3.json",
        ):
            with self.subTest(path=path):
                self.assertFalse(checker.is_app_change_requiring_changelog(path))

    def test_production_and_nonallowlisted_app_paths_require_a_fragment(self) -> None:
        for path in (
            "app/lib/main.dart",
            "app/test/widgets/chat_scroll_layout_test.dart",
            "app/scripts/l10n.py",
            "app/scripts/mobile_distribution.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(checker.is_app_change_requiring_changelog(path))

    def test_non_app_paths_never_require_a_fragment(self) -> None:
        for path in (
            ".github/scripts/mobile-changelog.py",
            "backend/main.py",
            "desktop/macos/Desktop/Sources/AppDelegate.swift",
        ):
            with self.subTest(path=path):
                self.assertFalse(checker.is_app_change_requiring_changelog(path))


GIT = shutil.which("git")


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "user.email=mobile-changelog-test@example.invalid", "-c", "user.name=mobile-changelog-test", *args],
        text=True,
        cwd=repo,
    ).strip()


def commit_all(repo: Path, files: dict[str, str]) -> str:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fixture")
    return git(repo, "rev-parse", "HEAD")


@unittest.skipUnless(GIT, "git binary required for the diff gate fixtures")
class GateFixtureTests(unittest.TestCase):
    def run_gate(self, files: dict[str, str]) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init", "-q")
            base = commit_all(repo, {"README.md": "fixture repo\n"})
            head = commit_all(repo, files)
            with unittest.mock.patch.object(checker, "REPO_ROOT", repo):
                return checker.check_changelog(base, head)

    def test_app_change_without_fragment_fails(self) -> None:
        code, message = self.run_gate({"app/lib/main.dart": "void main() {}\n"})
        self.assertEqual(code, 1)
        self.assertIn("app/lib/main.dart", message)

    def test_app_change_with_none_fragment_passes(self) -> None:
        code, _ = self.run_gate(
            {
                "app/lib/main.dart": "void main() {}\n",
                "app/changelog/unreleased/20260924-internal.json": '{"kind": "none"}\n',
            }
        )
        self.assertEqual(code, 0)

    def test_app_change_with_user_facing_fragment_passes(self) -> None:
        code, _ = self.run_gate(
            {
                "app/lib/main.dart": "void main() {}\n",
                "app/changelog/unreleased/20260924-calls.json": '{"change": "Calls now show live transcription"}\n',
            }
        )
        self.assertEqual(code, 0)

    def test_all_allowlisted_internal_paths_pass_without_fragment(self) -> None:
        files = {path: "fixture\n" for path in checker.EXEMPT_APP_PATHS}
        code, _ = self.run_gate(files)
        self.assertEqual(code, 0)

    def test_nonallowlisted_app_path_still_requires_a_fragment(self) -> None:
        allowlisted = {path: "fixture\n" for path in checker.EXEMPT_APP_PATHS}
        code, message = self.run_gate({**allowlisted, "app/scripts/l10n.py": "fixture\n"})
        self.assertEqual(code, 1)
        self.assertIn("app/scripts/l10n.py", message)

    def test_invalid_fragment_fails_even_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init", "-q")
            base = commit_all(repo, {"README.md": "fixture repo\n"})
            head = commit_all(
                repo,
                {
                    "app/lib/main.dart": "void main() {}\n",
                    "app/changelog/unreleased/20260924-bad.json": "{}\n",
                },
            )
            with unittest.mock.patch.object(checker, "REPO_ROOT", repo):
                with self.assertRaises(SystemExit):
                    checker.check_changelog(base, head)

    def test_main_push_without_metadata_matches_pr_verdict(self) -> None:
        files = {
            "app/lib/main.dart": "void main() {}\n",
            "app/changelog/unreleased/20260924-calls.json": '{"change": "Calls now show live transcription"}\n',
        }
        first = self.run_gate(files)
        second = self.run_gate(files)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 0)

        failing = {
            "app/lib/main.dart": "void main() {}\n",
        }
        first = self.run_gate(failing)
        second = self.run_gate(failing)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 1)


if __name__ == "__main__":
    unittest.main()
