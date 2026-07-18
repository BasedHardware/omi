#!/usr/bin/env python3
"""Adversarial fixtures for backend deployment source admission."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
CHECKER_PATH = SCRIPT_DIR / "check_backend_deploy_source_admission.py"
VERIFIER_PATH = SCRIPT_DIR / "verify_backend_release_admission.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CHECKER = load_module("check_backend_deploy_source_admission", CHECKER_PATH)
VERIFIER = load_module("verify_backend_release_admission", VERIFIER_PATH)

SHA = "a" * 40
REPOSITORY = "BasedHardware/omi"


def admitted_run(**overrides: object) -> dict[str, object]:
    run: dict[str, object] = {
        "name": "Release Eligibility",
        "path": ".github/workflows/release-eligibility.yml",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": SHA,
        "head_repository": {"full_name": REPOSITORY},
    }
    run.update(overrides)
    return run


class ReleaseAdmissionVerifierTests(unittest.TestCase):
    def payload(self, **overrides: object) -> dict[str, object]:
        return {"workflow_runs": [admitted_run(**overrides)]}

    def test_accepts_exact_successful_main_proof(self) -> None:
        VERIFIER.validate_admission(self.payload(), sha=SHA, repository=REPOSITORY)

    def test_accepts_githubs_main_qualified_workflow_path(self) -> None:
        VERIFIER.validate_admission(
            self.payload(path=".github/workflows/release-eligibility.yml@main"),
            sha=SHA,
            repository=REPOSITORY,
        )

    def test_rejects_ambiguous_release_sha(self) -> None:
        for value in ("main", "a" * 7, "A" * 40, "0" * 40):
            with self.subTest(value=value), self.assertRaisesRegex(VERIFIER.ReleaseAdmissionError, "release SHA"):
                VERIFIER.validate_admission(self.payload(), sha=value, repository=REPOSITORY)

    def test_rejects_wrong_proof_identity_or_result(self) -> None:
        cases = (
            ("workflow", {"name": "Build"}),
            ("workflow path", {"path": ".github/workflows/build.yml"}),
            ("event", {"event": "pull_request"}),
            ("status", {"status": "in_progress"}),
            ("conclusion", {"conclusion": "failure"}),
            ("branch", {"head_branch": "release"}),
            ("sha", {"head_sha": "b" * 40}),
            ("repository", {"head_repository": {"full_name": "fork/omi"}}),
        )
        for name, overrides in cases:
            with self.subTest(name=name), self.assertRaisesRegex(VERIFIER.ReleaseAdmissionError, "no successful main"):
                VERIFIER.validate_admission(self.payload(**overrides), sha=SHA, repository=REPOSITORY)

    def test_rejects_missing_or_malformed_workflow_runs(self) -> None:
        for payload in ({}, {"workflow_runs": {}}, {"workflow_runs": ["not-a-run"]}):
            with self.subTest(payload=payload), self.assertRaises(VERIFIER.ReleaseAdmissionError):
                VERIFIER.validate_admission(payload, sha=SHA, repository=REPOSITORY)


class WorkflowContractTests(unittest.TestCase):
    def fixture_root(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        for relative in (
            CHECKER.AUTO_WORKFLOW_PATH,
            CHECKER.MANUAL_WORKFLOW_PATH,
            CHECKER.ADMISSION_VERIFIER_PATH,
        ):
            source = ROOT / relative
            destination = temp / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        self.addCleanup(shutil.rmtree, temp)
        return temp

    def mutate(self, root: Path, relative: Path, old: str, new: str) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_workflows_are_valid(self) -> None:
        self.assertEqual(CHECKER.validate(), [])

    def test_auto_workflow_rejects_wrong_trigger_or_proof_workflow(self) -> None:
        root = self.fixture_root()
        self.mutate(root, CHECKER.AUTO_WORKFLOW_PATH, "  workflow_run:\n", "  push:\n")
        self.assertIn("auto backend deploy must trigger only from workflow_run", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(root, CHECKER.AUTO_WORKFLOW_PATH, 'workflows: ["Release Eligibility"]', 'workflows: ["Build"]')
        self.assertIn("auto backend deploy must consume completed Release Eligibility runs on main", CHECKER.validate(root))

    def test_auto_workflow_rejects_wrong_event_conclusion_branch_or_repository(self) -> None:
        cases = (
            ("event", "workflow_run.event == 'push'", "workflow_run.event == 'pull_request'", "push-originated"),
            ("conclusion", "workflow_run.conclusion == 'success'", "workflow_run.conclusion == 'failure'", "successful Release Eligibility"),
            ("branch", "workflow_run.head_branch == 'main'", "workflow_run.head_branch == 'release'", "main Release Eligibility"),
            (
                "repository",
                "workflow_run.head_repository.full_name == github.repository",
                "workflow_run.repository.full_name == github.repository",
                "proof source repository",
            ),
        )
        for name, old, new, expected in cases:
            with self.subTest(name=name):
                root = self.fixture_root()
                self.mutate(root, CHECKER.AUTO_WORKFLOW_PATH, old, new)
                self.assertTrue(
                    any(
                        expected in error
                        or "exactly the fail-closed Release Eligibility predicate" in error
                        for error in CHECKER.validate(root)
                    )
                )

    def test_auto_workflow_rejects_fail_open_conditions_or_dependency_bypasses(self) -> None:
        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.AUTO_WORKFLOW_PATH,
            "github.event.workflow_run.head_repository.full_name == github.repository",
            "github.event.workflow_run.head_repository.full_name == github.repository || true",
        )
        self.assertIn(
            "auto source-admission job must use exactly the fail-closed Release Eligibility predicate",
            CHECKER.validate(root),
        )

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.AUTO_WORKFLOW_PATH,
            "    needs: firestore_readiness\n",
            "    needs: firestore_readiness\n    if: always()\n",
        )
        self.assertIn("auto backend deploy must not override source-admission dependency", CHECKER.validate(root))

    def test_manual_workflow_rejects_fail_open_ref_or_mode_conditions(self) -> None:
        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "    if: >-\n      github.ref == 'refs/heads/main' &&\n      github.event.inputs.mode == 'repair-traffic-only'\n",
            "    if: >-\n      github.ref == 'refs/heads/main' &&\n      github.event.inputs.mode == 'repair-traffic-only' || true\n",
        )
        self.assertIn("traffic-only repair must use exactly the main-ref recovery condition", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "    if: >-\n      github.ref == 'refs/heads/main' &&\n      github.event.inputs.mode == 'deploy'\n",
            "    if: >-\n      github.ref == 'refs/heads/main' &&\n      github.event.inputs.mode == 'deploy' || true\n",
        )
        self.assertIn("manual source admission must use exactly the main-ref deploy condition", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "  deploy:\n    needs: firestore_readiness\n    if: >-\n      github.ref == 'refs/heads/main' &&\n      github.event.inputs.mode == 'deploy'\n",
            "  deploy:\n    needs: firestore_readiness\n    if: >-\n      github.ref == 'refs/heads/main' &&\n      github.event.inputs.mode == 'deploy' || true\n",
        )
        self.assertIn("manual deployment must use exactly the main-ref deploy condition", CHECKER.validate(root))

    def test_auto_workflow_rejects_github_sha_or_incomplete_source_binding(self) -> None:
        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.AUTO_WORKFLOW_PATH,
            "ref: ${{ github.event.workflow_run.head_sha }}",
            "ref: ${{ github.sha }}",
        )
        errors = CHECKER.validate(root)
        self.assertIn("auto backend deploy must not use github.sha after workflow_run admission", errors)
        self.assertIn("auto backend deploy must check out workflow_run.head_sha in both source jobs", errors)

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.AUTO_WORKFLOW_PATH,
            '--commit-sha "${{ github.event.workflow_run.head_sha }}"',
            '--commit-sha "${{ github.sha }}"',
        )
        errors = CHECKER.validate(root)
        self.assertIn("auto backend deploy must not use github.sha after workflow_run admission", errors)
        self.assertIn("auto backend deploy must bind every release vector to workflow_run.head_sha", errors)

    def test_manual_workflow_rejects_arbitrary_branch_or_missing_proof_query(self) -> None:
        root = self.fixture_root()
        self.mutate(root, CHECKER.MANUAL_WORKFLOW_PATH, "      release_sha:\n", "      branch:\n")
        self.assertIn("manual backend deploy must keep release_sha optional for traffic-only repair", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(root, CHECKER.MANUAL_WORKFLOW_PATH, "        required: false", "        required: true")
        self.assertIn("manual backend deploy must keep release_sha optional for traffic-only repair", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "github.event.inputs.release_sha",
            "github.event.inputs.branch",
        )
        self.assertIn("manual backend deploy must not accept an arbitrary branch or ref", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "head_sha=${DEPLOY_SHA}",
            "head_sha=${GITHUB_SHA}",
        )
        self.assertIn(
            "manual source admission must query the canonical main Release Eligibility workflow for the exact SHA",
            CHECKER.validate(root),
        )

    def test_manual_workflow_rejects_unadmitted_checkout_or_release_vector(self) -> None:
        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "ref: ${{ needs.firestore_readiness.outputs.admitted_sha }}",
            "ref: ${{ github.event.inputs.release_sha }}",
        )
        self.assertIn("manual deployment must check out the admitted SHA", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            '--commit-sha "${{ needs.firestore_readiness.outputs.admitted_sha }}"',
            '--commit-sha "${{ github.event.inputs.release_sha }}"',
        )
        self.assertIn("manual deployment must bind every release vector to the admitted SHA", CHECKER.validate(root))

    def test_traffic_only_repair_remains_separate_from_source_admission(self) -> None:
        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "github.event.inputs.mode == 'repair-traffic-only'",
            "github.event.inputs.mode == 'deploy'",
        )
        self.assertIn("traffic-only repair must use exactly the main-ref recovery condition", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "github.ref == 'refs/heads/main'",
            "github.ref == 'refs/heads/release'",
        )
        self.assertIn("traffic-only repair must use exactly the main-ref recovery condition", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(root, CHECKER.MANUAL_WORKFLOW_PATH, "          ref: main", "          ref: ${{ github.event.inputs.release_sha }}")
        self.assertIn("traffic-only repair must not require a release-source admission", CHECKER.validate(root))


if __name__ == "__main__":
    unittest.main()
