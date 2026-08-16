#!/usr/bin/env python3
"""Behavioral routing fixtures for macOS-only deterministic checks.

The desktop workflow asks ``run_checks.py`` for an exclusive macOS selection
before allocating a hosted runner. These fixtures exercise that resolver
directly instead of trying to infer routes from workflow regex strings.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

from run_checks import Check, Manifest, resolve_check_selections, trigger_matches

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
MANIFEST_PATH = REPO_ROOT / ".github/checks-manifest.yaml"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pre_push_ci_prediction import resolve_impact  # noqa: E402
from run_checks import load_manifest  # noqa: E402


def _materialize_trigger(pattern: str) -> list[str]:
    """Produce concrete paths accepted by a manifest trigger glob."""
    if pattern == "all":
        return ["desktop/macos/Desktop/Sources/Probe.swift"]
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        candidates = [f"{prefix}/probe", f"{prefix}/nested/probe"]
    else:
        candidates = [
            re.sub(r"\*+", "probe", re.sub(r"/\*\*/", "/", pattern)),
            re.sub(r"\*+", "probe", re.sub(r"/\*\*/", "/nested/", pattern)),
        ]
    return [candidate for candidate in candidates if trigger_matches(pattern, candidate)]


def resolve_macos_only(paths: list[str], manifest: Manifest) -> list[str]:
    """The exact exclusive-platform query used by the desktop workflow."""
    return [
        selection.check.id
        for selection in resolve_check_selections(
            manifest,
            paths,
            "ci",
            include_pr_body_checks=False,
            platform="macos",
            exclusive_platform=True,
        )
    ]


class DesktopManifestRoutesTests(unittest.TestCase):
    """Verify manifest selection behavior for the macOS static phase."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_manifest(MANIFEST_PATH)

    def test_every_macos_only_check_has_a_real_resolver_fixture(self) -> None:
        macos_checks = [check for check in self.manifest.checks if set(check.platforms) == {"macos"}]
        self.assertGreater(len(macos_checks), 0)
        for check in macos_checks:
            fixture_paths = [path for trigger in check.triggers for path in _materialize_trigger(trigger)]
            with self.subTest(check_id=check.id, paths=fixture_paths):
                self.assertTrue(fixture_paths, "macOS-only checks need at least one materializable trigger")
                self.assertIn(check.id, resolve_macos_only(fixture_paths, self.manifest))

    def test_portable_checks_do_not_move_to_the_exclusive_macos_phase(self) -> None:
        manifest = Manifest(
            checks=(
                Check(
                    id="portable",
                    command=("true",),
                    triggers=("desktop/macos/**",),
                    lanes=("ci",),
                    reason="portable fixture",
                ),
                Check(
                    id="mac-only",
                    command=("true",),
                    triggers=("desktop/macos/**",),
                    lanes=("ci",),
                    reason="macOS fixture",
                    platforms=("macos",),
                ),
            ),
            exempt=(),
        )
        self.assertEqual(resolve_macos_only(["desktop/macos/Desktop/Sources/App.swift"], manifest), ["mac-only"])

    def test_releasable_desktop_path_skips_verifier_only_without_macos_work(self) -> None:
        # Resource edits retain the stable exact-SHA aggregate but have no
        # manifest-owned macOS static phase. A verifier skip is therefore an
        # explicit resolver decision, not an unmaintained workflow regex.
        paths = ["desktop/macos/Resources/Info.plist"]
        plan = resolve_impact(paths)
        self.assertTrue(plan.includes("desktop-ci-only"))
        self.assertEqual(resolve_macos_only(paths, self.manifest), [])

    def test_swift_source_requires_a_macos_static_phase(self) -> None:
        paths = ["desktop/macos/Desktop/Sources/Probe.swift"]
        self.assertTrue(resolve_macos_only(paths, self.manifest))


if __name__ == "__main__":
    unittest.main()
