#!/usr/bin/env python3
"""Unit tests for desktop changelog tooling (stdlib unittest).

Regression coverage for #9717: read_json/write_json must always use UTF-8 so a
contributor on a non-UTF-8 host locale (e.g. GBK on native Windows Python) does
not crash with a UnicodeDecodeError. The CI host is UTF-8, so a plain round-trip
would not catch a missing encoding; these tests assert the encoding is forwarded
on every platform.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
import unittest.mock
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("desktop_changelog", Path(__file__).with_name("desktop-changelog.py"))
changelog = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(changelog)

_CHECK_SPEC = importlib.util.spec_from_file_location(
    "check_desktop_changelog", Path(__file__).with_name("check-desktop-changelog.py")
)
checker = importlib.util.module_from_spec(_CHECK_SPEC)
_CHECK_SPEC.loader.exec_module(checker)


class EncodingTests(unittest.TestCase):
    def test_read_json_forces_utf8(self) -> None:
        captured: dict[str, object] = {}
        real_read_text = Path.read_text

        def spy(self: Path, *args: object, **kwargs: object) -> str:
            captured["encoding"] = kwargs.get("encoding")
            return real_read_text(self, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changelog.json"
            path.write_text('{"note": "“curly”"}', encoding="utf-8")
            with unittest.mock.patch.object(Path, "read_text", spy):
                self.assertEqual(changelog.read_json(path), {"note": "“curly”"})
        self.assertEqual(captured["encoding"], "utf-8")

    def test_write_json_forces_utf8(self) -> None:
        captured: dict[str, object] = {}
        real_write_text = Path.write_text

        def spy(self: Path, *args: object, **kwargs: object) -> int:
            captured["encoding"] = kwargs.get("encoding")
            return real_write_text(self, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out" / "changelog.json"
            with unittest.mock.patch.object(Path, "write_text", spy):
                changelog.write_json(path, {"note": "“curly”"})
        self.assertEqual(captured["encoding"], "utf-8")

    def test_round_trip_preserves_non_ascii(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changelog.json"
            payload = {"note": "“curly” — café"}
            changelog.write_json(path, payload)
            self.assertEqual(changelog.read_json(path), payload)


class ChangelogRequirementTests(unittest.TestCase):
    def test_internal_release_controls_are_exempt_but_product_source_is_not(self) -> None:
        for path in (
            "desktop/macos/docs/release.md",
            # CI-only flow validation and its shared source inventory do not
            # alter the desktop application users receive.
            "desktop/macos/scripts/desktop-flow-lint.py",
            "desktop/macos/scripts/desktop_flow_contract.py",
            "desktop/macos/tests/some-other-desktop-test.sh",
            # Generated Swift is derived from the OpenAPI contract, never a
            # user-facing app note (EXEMPT_DESKTOP_PATH_PREFIXES).
            "desktop/macos/Desktop/Sources/Generated/OmiApi.generated.swift",
            # E2E flow definitions are harness test artifacts; #11039 only added a
            # `covers:` entry and the post-merge push run reddened main.
            "desktop/macos/e2e/flows/notifications-settings.yaml",
        ):
            with self.subTest(path=path):
                self.assertFalse(checker.is_desktop_change_requiring_changelog(path))

        # Product source still requires a changelog — the exemptions must not leak.
        # Note the hand-written Sources file is NOT under Sources/Generated/.
        for path in (
            "desktop/macos/Desktop/Sources/AppDelegate.swift",
            "desktop/macos/scripts/some-user-facing-script.sh",
        ):
            with self.subTest(path=path):
                self.assertTrue(checker.is_desktop_change_requiring_changelog(path))

    def test_release_lane_accepts_fragments_already_in_the_tree(self) -> None:
        # Release Eligibility runs on main pushes, where the merged PR's
        # no-changelog-needed label is invisible (#11373 wedged the release
        # train exactly this way). The release contract is that the NEXT
        # RELEASE has notes — fragments already in the tree satisfy it.
        def fake_git(args: list[str]) -> str:
            if args[0] == "ls-tree":
                return "desktop/macos/changelog/unreleased/20260810-fix.json"
            if args[0] == "show":
                return '{"change": "Fixed a thing"}'
            raise AssertionError(f"unexpected git invocation: {args}")

        with unittest.mock.patch.object(checker, "run_git", side_effect=fake_git):
            self.assertTrue(checker.tree_has_unreleased_fragment("HEAD"))

    def test_release_lane_rejects_an_empty_unreleased_directory(self) -> None:
        with unittest.mock.patch.object(checker, "run_git", return_value=""):
            self.assertFalse(checker.tree_has_unreleased_fragment("HEAD"))

    def test_release_lane_still_fails_on_an_invalid_tree_fragment(self) -> None:
        def fake_git(args: list[str]) -> str:
            if args[0] == "ls-tree":
                return "desktop/macos/changelog/unreleased/bad.json"
            if args[0] == "show":
                return "{}"
            raise AssertionError(f"unexpected git invocation: {args}")

        with unittest.mock.patch.object(checker, "run_git", side_effect=fake_git):
            with self.assertRaises(SystemExit):
                checker.tree_has_unreleased_fragment("HEAD")

    def test_kind_none_is_a_valid_exemption_but_not_release_notes(self) -> None:
        self.assertEqual(
            checker.classify_fragment({"kind": "none"}, "desktop/macos/changelog/unreleased/none.json"),
            "none",
        )
        self.assertEqual(
            checker.classify_fragment({"change": "Fixed a thing"}, "desktop/macos/changelog/unreleased/fix.json"),
            "user_facing",
        )
        with self.assertRaises(SystemExit):
            checker.classify_fragment({}, "desktop/macos/changelog/unreleased/empty.json")

    def test_release_lane_ignores_leftover_kind_none_fragments(self) -> None:
        # A spent internal-only marker must not satisfy "the next release has notes".
        def fake_git(args: list[str]) -> str:
            if args[0] == "ls-tree":
                return "desktop/macos/changelog/unreleased/20260818-dead-code.json"
            if args[0] == "show":
                return '{"kind": "none"}'
            raise AssertionError(f"unexpected git invocation: {args}")

        with unittest.mock.patch.object(checker, "run_git", side_effect=fake_git):
            self.assertFalse(checker.tree_has_unreleased_fragment("HEAD"))


PR_11778_SOURCES = (
    "desktop/macos/Desktop/Sources/FloatingControlBar/PTTContextVocabularyProvider.swift",
    "desktop/macos/Desktop/Sources/Rewind/Core/ProactiveModels.swift",
    "desktop/macos/Desktop/Sources/Rewind/Core/ProactiveStorage.swift",
    "desktop/macos/Desktop/Sources/Rewind/Services/RewindIndexer.swift",
)


class MergeBoundaryAgreementTests(unittest.TestCase):
    """#11778: a green PR-run must not be able to redden the post-merge push run."""

    def test_11778_production_sources_require_a_changelog(self) -> None:
        for path in PR_11778_SOURCES:
            with self.subTest(path=path):
                self.assertTrue(checker.is_desktop_change_requiring_changelog(path))

    def test_11778_label_without_fragment_pr_and_push_both_fail(self) -> None:
        requiring = list(PR_11778_SOURCES)
        pr_code, pr_message = checker.evaluate_changelog_requirement(
            requiring_changelog=requiring,
            skip=True,
            has_new_fragment=False,
            accept_tree_fragments=False,
            has_tree_user_facing_fragment=False,
        )
        push_code, push_message = checker.evaluate_changelog_requirement(
            requiring_changelog=requiring,
            skip=False,
            has_new_fragment=False,
            accept_tree_fragments=True,
            has_tree_user_facing_fragment=False,
        )
        self.assertEqual(pr_code, push_code)
        self.assertEqual(pr_code, 1)
        self.assertIn("kind", pr_message)
        self.assertIn("no-changelog-needed", pr_message)
        self.assertIn("kind", push_message)

    def test_11778_kind_none_fragment_pr_and_push_both_pass(self) -> None:
        requiring = list(PR_11778_SOURCES)
        pr_code, _ = checker.evaluate_changelog_requirement(
            requiring_changelog=requiring,
            skip=True,
            has_new_fragment=True,
            accept_tree_fragments=False,
            has_tree_user_facing_fragment=False,
        )
        push_code, _ = checker.evaluate_changelog_requirement(
            requiring_changelog=requiring,
            skip=False,
            has_new_fragment=True,
            accept_tree_fragments=True,
            has_tree_user_facing_fragment=False,
        )
        self.assertEqual(pr_code, push_code)
        self.assertEqual(pr_code, 0)

    def test_skip_still_passes_when_only_exempt_paths_changed(self) -> None:
        code, message = checker.evaluate_changelog_requirement(
            requiring_changelog=[],
            skip=True,
            has_new_fragment=False,
            accept_tree_fragments=False,
            has_tree_user_facing_fragment=False,
        )
        self.assertEqual(code, 0)
        self.assertIn("skipped", message)

    def test_leftover_kind_none_does_not_satisfy_a_later_production_push(self) -> None:
        code, _ = checker.evaluate_changelog_requirement(
            requiring_changelog=list(PR_11778_SOURCES),
            skip=False,
            has_new_fragment=False,
            accept_tree_fragments=True,
            has_tree_user_facing_fragment=False,
        )
        self.assertEqual(code, 1)


class NoneKindFragmentIOTests(unittest.TestCase):
    def test_none_kind_fragment_contributes_no_release_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260818-dead-code.json"
            changelog.write_json(path, {"kind": "none"})
            self.assertEqual(changelog.read_unreleased_fragment(path), [])

    def test_none_kind_is_valid_for_repository_wide_validate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260818-dead-code.json"
            changelog.write_json(path, {"kind": "none"})
            self.assertEqual(changelog.read_unreleased_fragment(path), [])


if __name__ == "__main__":
    unittest.main()
