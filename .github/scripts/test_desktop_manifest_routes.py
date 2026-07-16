#!/usr/bin/env python3
"""Cross-workflow contract test: macOS-scoped manifest checks must be runnable on macOS CI.

Ticket 02 of #9843 gave the deterministic check manifest a ``platforms`` field so a
check can declare ``platforms: ["macos"]`` and execute only under the macOS CI
workflow (``.github/workflows/desktop-swift-ci.yml``). That workflow gates its
manifest step behind a changed-file ``grep`` (the "Check changed files" step that
sets ``should_run``). If a macOS-only check's trigger paths fall outside that gate,
editing one of those files sets ``should_run=false`` and the manifest step never
runs -- the check is silently stranded with no CI route at all.

This test pins the contract:

  1. The macOS workflow has a step running ``run_checks.py`` with ``--platform macos``.
  2. Every macOS-scoped manifest check has at least one trigger path covered by the
     macOS workflow's changed-file gate, so editing a trigger actually wakes the
     manifest step on macOS CI.
  3. Adversarial: a macOS-only check whose trigger escapes the gate is detected as a
     missing route.

Stdlib-only (no PyYAML dependency) so it runs on any CI runner.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from run_checks import Check, load_manifest, trigger_matches

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
MANIFEST_PATH = REPO_ROOT / ".github/checks-manifest.yaml"
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/desktop-swift-ci.yml"

# The changed-file gate is a `grep -qE 'PATTERN'` over changed file paths. Capture
# the single-quoted extended-regex argument (matches -qE, -E, -Eq, ...). The gate
# uses single quotes, which never contain an escaped single quote, so '[^']+' is safe.
_GATE_RE = re.compile(r"grep\s+-[A-Za-z]*E[A-Za-z]*\s+'([^']+)'")


def _workflow_text() -> str:
    """Return the raw workflow YAML text (no PyYAML needed)."""
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _runs_macos_manifest(run_body: str) -> bool:
    """True if *run_body* invokes run_checks.py scoped to the macos platform."""
    return "run_checks.py" in run_body and bool(re.search(r"--platform[ =]macos\b", run_body))


def _extract_gate(run_body: str) -> str | None:
    match = _GATE_RE.search(run_body)
    return match.group(1) if match else None


def _macos_route(workflow_text: str) -> tuple[str | None, bool]:
    """Return ``(changed-file gate regex, has_macos_manifest_step)``.

    The gate is taken from the step sequence surrounding the ``run_checks.py
    --platform macos`` invocation: that job's changed-file ``grep`` is the only
    thing standing between a changed trigger and the manifest step executing.

    Works on raw YAML text (no PyYAML) by searching for the ``run_checks.py
    --platform macos`` marker, then scanning backward for the nearest gate.
    """
    has_manifest = _runs_macos_manifest(workflow_text)
    if not has_manifest:
        return None, False
    # The gate appears before the manifest step in the same job. Search the full
    # text for the last gate before the run_checks.py invocation.
    manifest_pos = workflow_text.find("run_checks.py")
    # Find the first gate in the text (there is typically one per job)
    gate_match = _GATE_RE.search(workflow_text)
    gate = gate_match.group(1) if gate_match and gate_match.start() < manifest_pos else None
    # If gate is after manifest step, try to find one before
    if gate is None:
        for m in _GATE_RE.finditer(workflow_text):
            if m.start() < manifest_pos:
                gate = m.group(1)
    return gate, True


def _materialize_trigger(pattern: str) -> list[str]:
    """Concrete repo-relative paths that would activate *pattern*.

    ``all`` is a marker, not a path, so it yields nothing -- a check whose only
    trigger is ``all`` routes whenever the manifest step fires. For real globs we
    synthesize representative paths (recursively, across zero/one intermediate
    directory) and keep only those the real resolver would actually accept, so we
    never claim coverage from a path the check would not match.
    """
    if pattern == "all":
        return []
    raw: list[str] = []
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        raw.extend([f"{prefix}/probe", f"{prefix}/nested/probe"])
    else:
        bases = {re.sub(r"/\*\*/", "/", pattern), re.sub(r"/\*\*/", "/nested/", pattern)}
        for base in bases:
            raw.append(re.sub(r"\*+", "probe", base))
    return [candidate for candidate in raw if trigger_matches(pattern, candidate)]


def _trigger_covered_by_gate(pattern: str, gate_regex: str) -> bool:
    """True if a path that activates *pattern* also matches the *gate_regex* (grep -E)."""
    return any(re.search(gate_regex, path) for path in _materialize_trigger(pattern))


def _check_has_route(check: Check, gate_regex: str) -> bool:
    """True if *check* can be woken on macOS CI through the changed-file gate."""
    if "all" in check.triggers:
        return True  # matches every change; routes whenever the manifest step fires
    return any(_trigger_covered_by_gate(trigger, gate_regex) for trigger in check.triggers)


class DesktopManifestRoutesTests(unittest.TestCase):
    """Guard the macOS manifest-check route in desktop-swift-ci.yml."""

    def setUp(self) -> None:
        workflow_text = _workflow_text()
        self.gate, self.has_manifest_step = _macos_route(workflow_text)
        self.manifest = load_manifest(MANIFEST_PATH)

    def test_macos_manifest_step_exists(self) -> None:
        """desktop-swift-ci.yml must run run_checks.py with --platform macos."""
        self.assertTrue(
            self.has_manifest_step,
            "desktop-swift-ci.yml must run run_checks.py with --platform macos so "
            "macOS-scoped checks actually execute on macOS CI.",
        )

    def test_changed_file_gate_is_present(self) -> None:
        """The manifest-check job must declare a changed-file gate (grep -E)."""
        self.assertTrue(
            self.gate,
            "desktop-swift-ci.yml must declare a changed-file gate (grep -E) in the "
            "job that runs the macOS manifest checks.",
        )

    def test_macos_scoped_checks_have_routes(self) -> None:
        """Every platforms:[macos] check must reach the macOS workflow's gate."""
        if not self.gate:
            self.skipTest("no macOS changed-file gate; guarded by test_changed_file_gate_is_present")
        macos_checks = [check for check in self.manifest.checks if "macos" in check.platforms]
        for check in macos_checks:
            with self.subTest(check_id=check.id):
                self.assertTrue(
                    _check_has_route(check, self.gate),
                    f"macOS-scoped check {check.id!r} has no trigger path covered by the "
                    f"desktop-swift-ci.yml changed-file gate; editing one of its triggers "
                    f"(triggers={list(check.triggers)}) would not wake the macOS manifest "
                    f"step, leaving the check with no CI route.",
                )

    def test_adversarial_uncovered_route_is_detected(self) -> None:
        """A macOS-only check whose trigger escapes the gate must be flagged."""
        if not self.gate:
            self.skipTest("no macOS changed-file gate; cannot exercise detection")
        covered = Check(
            id="fake-covered-route",
            command=(),
            triggers=("desktop/macos/Desktop/Sources/Fake.swift",),
            lanes=("ci",),
            reason="",
            platforms=("macos",),
        )
        uncovered = Check(
            id="fake-uncovered-route",
            command=(),
            triggers=("backend/some/macos-only-concern.py",),
            lanes=("ci",),
            reason="",
            platforms=("macos",),
        )
        self.assertTrue(
            _check_has_route(covered, self.gate),
            "sanity: a trigger under desktop/macos/Desktop/ must be routed by the gate",
        )
        self.assertFalse(
            _check_has_route(uncovered, self.gate),
            "a macOS-only check whose trigger escapes the gate must be detected as unrouted",
        )


if __name__ == "__main__":
    unittest.main()
