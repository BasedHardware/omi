#!/usr/bin/env python3
"""Fixtures for the automatic main-SHA release eligibility proof."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
CHECKER_PATH = SCRIPT_DIR / "check_release_eligibility.py"
VERIFIER_PATH = SCRIPT_DIR / "verify_release_eligibility.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CHECKER = load_module("check_release_eligibility", CHECKER_PATH)
VERIFIER = load_module("verify_release_eligibility", VERIFIER_PATH)

SHA = "a" * 40
BASE_SHA = "b" * 40


class ReleaseIdentityTests(unittest.TestCase):
    def identity(self, **overrides: str):
        values = {
            "ref": "refs/heads/main",
            "sha": SHA,
            "before": BASE_SHA,
            "after": SHA,
            "checkout_sha": SHA,
        }
        values.update(overrides)
        return VERIFIER.ReleaseIdentity(**values)

    def test_accepts_exact_main_sha_identity(self) -> None:
        VERIFIER.validate(self.identity())

    def test_rejects_non_main_ref(self) -> None:
        with self.assertRaisesRegex(VERIFIER.ReleaseEligibilityError, "refs/heads/main"):
            VERIFIER.validate(self.identity(ref="refs/heads/release"))

    def test_rejects_ambiguous_or_non_sha_release_identity(self) -> None:
        for value in ("main", "a" * 7, "A" * 40, "0" * 40):
            with self.subTest(value=value), self.assertRaisesRegex(VERIFIER.ReleaseEligibilityError, "release SHA"):
                VERIFIER.validate(self.identity(sha=value))

    def test_rejects_event_or_checkout_sha_mismatch(self) -> None:
        with self.assertRaisesRegex(VERIFIER.ReleaseEligibilityError, "event after SHA"):
            VERIFIER.validate(self.identity(after="c" * 40))
        with self.assertRaisesRegex(VERIFIER.ReleaseEligibilityError, "checked-out SHA"):
            VERIFIER.validate(self.identity(checkout_sha="c" * 40))


class WorkflowContractTests(unittest.TestCase):
    def fixture_root(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        workflow = temp / ".github/workflows/release-eligibility.yml"
        action = temp / ".github/actions/release-eligibility/action.yml"
        workflow.parent.mkdir(parents=True)
        action.parent.mkdir(parents=True)
        shutil.copy2(ROOT / ".github/workflows/release-eligibility.yml", workflow)
        shutil.copy2(ROOT / ".github/actions/release-eligibility/action.yml", action)
        self.addCleanup(shutil.rmtree, temp)
        return temp

    def test_current_workflow_and_action_are_valid(self) -> None:
        self.assertEqual(CHECKER.validate(), [])

    def test_non_main_push_trigger_is_rejected(self) -> None:
        root = self.fixture_root()
        workflow = root / ".github/workflows/release-eligibility.yml"
        workflow.write_text(workflow.read_text(encoding="utf-8").replace("branches: [main]", "branches: [development]"), encoding="utf-8")
        self.assertIn("release eligibility must trigger only on pushes to main", CHECKER.validate(root))

    def test_path_filter_is_rejected(self) -> None:
        root = self.fixture_root()
        workflow = root / ".github/workflows/release-eligibility.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace("branches: [main]", "branches: [main]\n    paths: ['backend/**']"),
            encoding="utf-8",
        )
        self.assertIn("release eligibility must not path-filter or otherwise narrow main pushes", CHECKER.validate(root))

    def test_manual_dispatch_is_rejected(self) -> None:
        root = self.fixture_root()
        workflow = root / ".github/workflows/release-eligibility.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace("on:\n", "on:\n  workflow_dispatch:\n", 1),
            encoding="utf-8",
        )
        self.assertIn("release eligibility must declare only the automatic push trigger", CHECKER.validate(root))

    def test_quoted_extra_trigger_is_rejected(self) -> None:
        root = self.fixture_root()
        workflow = root / ".github/workflows/release-eligibility.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace("on:\n", "on:\n  'workflow_dispatch':\n", 1),
            encoding="utf-8",
        )
        self.assertIn("release eligibility must declare only the automatic push trigger", CHECKER.validate(root))

    def test_conditional_result_job_is_rejected(self) -> None:
        root = self.fixture_root()
        workflow = root / ".github/workflows/release-eligibility.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace("    runs-on: ubuntu-latest", "    if: github.ref == 'refs/heads/main'\n    runs-on: ubuntu-latest"),
            encoding="utf-8",
        )
        self.assertIn("release eligibility result job must not be conditionally skipped or tolerated", CHECKER.validate(root))

    def test_result_job_continue_on_error_is_rejected(self) -> None:
        root = self.fixture_root()
        workflow = root / ".github/workflows/release-eligibility.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace("    runs-on: ubuntu-latest", "    continue-on-error: true\n    runs-on: ubuntu-latest"),
            encoding="utf-8",
        )
        self.assertIn("release eligibility result job must not be conditionally skipped or tolerated", CHECKER.validate(root))

    def test_action_invocation_cannot_be_skipped_or_tolerated(self) -> None:
        for field in ("if: github.ref == 'refs/heads/main'", "continue-on-error: true"):
            with self.subTest(field=field):
                root = self.fixture_root()
                workflow = root / ".github/workflows/release-eligibility.yml"
                workflow.write_text(
                    workflow.read_text(encoding="utf-8").replace(
                        "      - name: Verify release eligibility\n        uses:",
                        f"      - name: Verify release eligibility\n        {field}\n        uses:",
                    ),
                    encoding="utf-8",
                )
                self.assertIn(
                    "release eligibility action invocation must not be conditionally skipped or tolerated",
                    CHECKER.validate(root),
                )

    def test_least_privilege_permissions_are_enforced(self) -> None:
        root = self.fixture_root()
        workflow = root / ".github/workflows/release-eligibility.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace("  contents: read", "  contents: read\n  actions: write"),
            encoding="utf-8",
        )
        self.assertIn("release eligibility must use only repository contents: read permissions", CHECKER.validate(root))

    def test_ambiguous_workflow_sha_is_rejected(self) -> None:
        root = self.fixture_root()
        workflow = root / ".github/workflows/release-eligibility.yml"
        workflow.write_text(workflow.read_text(encoding="utf-8").replace("sha: ${{ github.sha }}", "sha: main"), encoding="utf-8")
        self.assertIn("release eligibility must pass sha as ${{ github.sha }}", CHECKER.validate(root))

    def test_missing_checkout_sha_binding_is_rejected(self) -> None:
        root = self.fixture_root()
        action = root / ".github/actions/release-eligibility/action.yml"
        action.write_text(
            action.read_text(encoding="utf-8").replace("--checkout-sha \"$RELEASE_CHECKOUT_SHA\"", "--checkout-sha main"),
            encoding="utf-8",
        )
        self.assertIn("release identity validator must receive the checkout SHA", CHECKER.validate(root))

    def test_uv_setup_is_required_and_fail_closed_before_canonical_preflight(self) -> None:
        cases = (
            (
                "missing setup",
                "    - name: Set up uv for canonical checks\n      uses: astral-sh/setup-uv@ecd24dd710f2fb0dca1693a67af11fc4a5c5ec84\n      with:\n        enable-cache: true\n        cache-dependency-glob: backend/openapi-requirements.txt\n\n",
                "",
                "release eligibility is missing its uv setup step",
            ),
            (
                "unpinned-or-wrong setup",
                "uses: astral-sh/setup-uv@ecd24dd710f2fb0dca1693a67af11fc4a5c5ec84",
                "uses: astral-sh/setup-uv@v7",
                "release eligibility uv setup step must use the pinned setup action",
            ),
            (
                "conditional setup",
                "    - name: Set up uv for canonical checks\n      uses:",
                "    - name: Set up uv for canonical checks\n      if: github.ref == 'refs/heads/main'\n      uses:",
                "release eligibility uv setup step must not be conditionally skipped or tolerated",
            ),
            (
                "missing OpenAPI cache key",
                "cache-dependency-glob: backend/openapi-requirements.txt",
                "cache-dependency-glob: backend/pylock.toml",
                "release eligibility uv setup must key the OpenAPI dependency cache",
            ),
            (
                "setup after preflight",
                "    - name: Set up uv for canonical checks\n      uses: astral-sh/setup-uv@ecd24dd710f2fb0dca1693a67af11fc4a5c5ec84\n      with:\n        enable-cache: true\n        cache-dependency-glob: backend/openapi-requirements.txt\n\n",
                "",
                "release eligibility must set up uv before the canonical preflight",
            ),
        )
        for name, old, new, expected in cases:
            with self.subTest(name=name):
                root = self.fixture_root()
                action = root / ".github/actions/release-eligibility/action.yml"
                text = action.read_text(encoding="utf-8")
                if name == "setup after preflight":
                    self.assertIn(old, text)
                    uv_start = text.index(old)
                    preflight_start = text.index("    - name: Run canonical deterministic CI preflight")
                    text = (
                        text[:uv_start]
                        + text[uv_start + len(old) : preflight_start]
                        + text[preflight_start:]
                        + old
                    )
                else:
                    self.assertIn(old, text)
                    text = text.replace(old, new, 1)
                action.write_text(text, encoding="utf-8")
                self.assertIn(expected, CHECKER.validate(root))

    def test_critical_action_steps_cannot_be_skipped_or_fail_open(self) -> None:
        cases = (
            (
                "identity condition",
                "    - name: Verify exact main release identity\n      shell:",
                "    - name: Verify exact main release identity\n      if: github.ref == 'refs/heads/main'\n      shell:",
                "release eligibility identity validation step must not be conditionally skipped or tolerated",
            ),
            (
                "identity tolerance",
                "    - name: Verify exact main release identity\n      shell:",
                "    - name: Verify exact main release identity\n      continue-on-error: true\n      shell:",
                "release eligibility identity validation step must not be conditionally skipped or tolerated",
            ),
            (
                "identity fail open",
                "git cat-file -e \"${RELEASE_SHA}^{commit}\"",
                "git cat-file -e \"${RELEASE_SHA}^{commit}\" || true",
                "release eligibility identity validation step must not contain a shell fail-open path",
            ),
            (
                "identity alternate fail open",
                "git cat-file -e \"${RELEASE_SHA}^{commit}\"",
                "git cat-file -e \"${RELEASE_SHA}^{commit}\" || :",
                "release eligibility identity validation step must not contain a shell fail-open path",
            ),
            (
                "preflight condition",
                "    - name: Run canonical deterministic CI preflight\n      shell:",
                "    - name: Run canonical deterministic CI preflight\n      if: github.ref == 'refs/heads/main'\n      shell:",
                "release eligibility canonical preflight step must not be conditionally skipped or tolerated",
            ),
            (
                "preflight tolerance",
                "    - name: Run canonical deterministic CI preflight\n      shell:",
                "    - name: Run canonical deterministic CI preflight\n      continue-on-error: true\n      shell:",
                "release eligibility canonical preflight step must not be conditionally skipped or tolerated",
            ),
            (
                "preflight fail open",
                "--skip-pr-body-checks",
                "--skip-pr-body-checks || true",
                "release eligibility canonical preflight step must not contain a shell fail-open path",
            ),
            (
                "preflight disables strict errors",
                "        set -euo pipefail\n        python3 .github/scripts/run_checks.py",
                "        set -euo pipefail\n        set +e\n        python3 .github/scripts/run_checks.py",
                "release eligibility canonical preflight step must not contain a shell fail-open path",
            ),
            (
                "missing ancestry",
                "        git merge-base --is-ancestor \"$RELEASE_BEFORE\" \"$RELEASE_SHA\"\n",
                "",
                "release eligibility must require the base SHA to be an ancestor",
            ),
        )
        for name, old, new, expected in cases:
            with self.subTest(name=name):
                root = self.fixture_root()
                action = root / ".github/actions/release-eligibility/action.yml"
                action.write_text(action.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
                self.assertIn(expected, CHECKER.validate(root))


if __name__ == "__main__":
    unittest.main()
