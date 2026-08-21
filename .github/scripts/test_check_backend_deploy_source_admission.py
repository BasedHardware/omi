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
AUTO_VERIFIER_PATH = SCRIPT_DIR / "verify_auto_backend_release_admission.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CHECKER = load_module("check_backend_deploy_source_admission", CHECKER_PATH)
VERIFIER = load_module("verify_backend_release_admission", VERIFIER_PATH)
AUTO_VERIFIER = load_module("verify_auto_backend_release_admission", AUTO_VERIFIER_PATH)

SHA = "a" * 40
REPOSITORY = "BasedHardware/omi"


def admitted_run(**overrides: object) -> dict[str, object]:
    run: dict[str, object] = {
        "name": "Release Eligibility",
        "path": ".github/workflows/release-eligibility.yml",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
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

    def test_backend_default_accepts_successful_rerun(self) -> None:
        VERIFIER.validate_admission(self.payload(run_attempt=2), sha=SHA, repository=REPOSITORY)

    def test_gateway_first_attempt_mode_rejects_rerun(self) -> None:
        with self.assertRaisesRegex(VERIFIER.ReleaseAdmissionError, "no successful main"):
            VERIFIER.validate_admission(
                self.payload(run_attempt=2),
                sha=SHA,
                repository=REPOSITORY,
                require_first_attempt=True,
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


class AutomaticReleaseAdmissionVerifierTests(unittest.TestCase):
    def identity(self, **overrides):
        values = {
            "sha": SHA,
            "trigger_sha": SHA,
            "main_sha": SHA,
            "run_attempt": "1",
            "sha_is_ancestor_of_main": True,
            "trigger_is_ancestor_of_sha": True,
        }
        values.update(overrides)
        return AUTO_VERIFIER.AutomaticReleaseIdentity(**values)

    def test_accepts_first_attempt_for_exact_current_main(self) -> None:
        AUTO_VERIFIER.validate(self.identity())

    def test_accepts_a_merged_sha_that_main_has_moved_past(self) -> None:
        """Tip-equality rejected merged commits whenever main moved mid-proof."""
        AUTO_VERIFIER.validate(self.identity(main_sha="b" * 40))

    def test_rejects_reruns_or_stale_current_main(self) -> None:
        for name, overrides, expected in (
            ("rerun", {"run_attempt": "2"}, "first run attempt"),
            ("noncanonical attempt", {"run_attempt": "01"}, "first run attempt"),
            ("unmerged release sha", {"sha_is_ancestor_of_main": False}, "merged into current main"),
            (
                "target older than its trigger",
                {"trigger_is_ancestor_of_sha": False},
                "older than the triggering release SHA",
            ),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(
                AUTO_VERIFIER.AutomaticReleaseAdmissionError, expected
            ):
                AUTO_VERIFIER.validate(self.identity(**overrides))

    def test_rejects_ambiguous_automatic_release_identity(self) -> None:
        for field in ("sha", "trigger_sha", "main_sha"):
            with self.subTest(field=field), self.assertRaisesRegex(
                AUTO_VERIFIER.AutomaticReleaseAdmissionError, "full 40-character"
            ):
                AUTO_VERIFIER.validate(self.identity(**{field: "main"}))


class WorkflowContractTests(unittest.TestCase):
    def fixture_root(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        for relative in (
            CHECKER.AUTO_WORKFLOW_PATH,
            CHECKER.MANUAL_WORKFLOW_PATH,
            CHECKER.ADMISSION_VERIFIER_PATH,
            CHECKER.AUTO_ADMISSION_VERIFIER_PATH,
            CHECKER.DEPLOY_BACKEND_STACK_ACTION,
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
        if old in text:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            return
        composite = root / CHECKER.DEPLOY_BACKEND_STACK_ACTION
        composite_text = composite.read_text(encoding="utf-8")
        self.assertIn(old, composite_text)
        composite.write_text(composite_text.replace(old, new, 1), encoding="utf-8")

    def move_step_before(self, root: Path, relative: Path, name: str, before_name: str) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        marker = f"      - name: {name}"
        before_marker = f"      - name: {before_name}"
        start = text.index(marker)
        end = text.find("\n      - ", start + 1)
        self.assertNotEqual(end, -1)
        step = text[start : end + 1]
        text = text[:start] + text[end + 1 :]
        before = text.index(before_marker)
        path.write_text(text[:before] + step + text[before:], encoding="utf-8")

    def test_current_workflows_are_valid(self) -> None:
        self.assertEqual(CHECKER.validate(), [])

    def test_auto_workflow_rejects_wrong_trigger_or_proof_workflow(self) -> None:
        root = self.fixture_root()
        self.mutate(root, CHECKER.AUTO_WORKFLOW_PATH, "  workflow_run:\n", "  push:\n")
        self.assertIn("auto backend deploy must trigger only from workflow_run", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(root, CHECKER.AUTO_WORKFLOW_PATH, 'workflows: ["Release Eligibility"]', 'workflows: ["Build"]')
        self.assertIn(
            "auto backend deploy must consume completed Release Eligibility runs on main", CHECKER.validate(root)
        )

    def test_auto_workflow_rejects_wrong_event_conclusion_branch_or_repository(self) -> None:
        cases = (
            ("event", "workflow_run.event == 'push'", "workflow_run.event == 'pull_request'", "push-originated"),
            (
                "conclusion",
                "workflow_run.conclusion == 'success'",
                "workflow_run.conclusion == 'failure'",
                "successful Release Eligibility",
            ),
            ("rerun", "workflow_run.run_attempt == 1", "workflow_run.run_attempt == 2", "first run attempt"),
            (
                "branch",
                "workflow_run.head_branch == 'main'",
                "workflow_run.head_branch == 'release'",
                "main Release Eligibility",
            ),
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
                        expected in error or "exactly the fail-closed Release Eligibility predicate" in error
                        for error in CHECKER.validate(root)
                    )
                )

    def test_auto_workflow_rejects_scope_bypasses_or_cloud_access(self) -> None:
        cases = (
            (
                "readiness scope dependency",
                "    needs: scope\n",
                "",
                "auto source-admission job must depend on the scope decision",
            ),
            (
                "scope output predicate",
                "needs.scope.outputs.applies == 'true' &&",
                "needs.scope.outputs.applies == 'false' &&",
                "auto source-admission job must use exactly the fail-closed Release Eligibility predicate",
            ),
            (
                "triggering SHA checkout",
                "ref: ${{ github.event.workflow_run.head_sha }}\n          # The parent diff is the only local scope proof required here. Current\n          # main/supersession proof below is bounded to read-only GitHub API calls.\n          fetch-depth: 2",
                "ref: main\n          # The parent diff is the only local scope proof required here. Current\n          # main/supersession proof below is bounded to read-only GitHub API calls.\n          fetch-depth: 2",
                "auto backend scope decision must inspect the triggering SHA",
            ),
            (
                "full-history checkout",
                "fetch-depth: 2",
                "fetch-depth: 0",
                "auto backend scope decision must shallow-fetch only the triggering parent diff",
            ),
            (
                "parent diff",
                'git diff --name-only "$parent_sha" "$RELEASE_SHA"',
                'git diff --name-only "$parent_sha" HEAD',
                "auto backend scope decision must diff the triggering SHA against its parent",
            ),
            (
                "cloud authentication",
                "    runs-on: ubuntu-latest\n    outputs:",
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: google-github-actions/auth@v3\n    outputs:",
                "auto backend scope decision must not authenticate to cloud services",
            ),
        )
        for name, old, new, expected in cases:
            with self.subTest(name=name):
                root = self.fixture_root()
                self.mutate(root, CHECKER.AUTO_WORKFLOW_PATH, old, new)
                self.assertIn(expected, CHECKER.validate(root))

    def test_auto_workflow_rejects_reintroduced_scope_supersession(self) -> None:
        """Scope must never strand a behind triggering SHA.

        Deciding supersession here loses backend changes: the behind commit
        no-ops for being behind, and the newer commit no-ops because its own
        diff is unrelated, so nothing deploys. Admission resolves the newest
        proven commit instead, which subsumes supersession without that hole.
        """
        anchor = 'git diff --name-only "$parent_sha" "$RELEASE_SHA"'
        cases = (
            (
                "compare-based supersession",
                'compare_url="$api_base/repos/$GITHUB_REPOSITORY/compare/$RELEASE_SHA...$main_sha"\n          ' + anchor,
                "auto backend scope decision must not decide supersession",
            ),
            (
                "behind status no-op",
                'if [[ "$comparison" == "behind" ]]; then :; fi\n          ' + anchor,
                "auto backend scope decision must not strand a behind triggering SHA",
            ),
            (
                "superseded summary",
                'echo "Backend development deploy superseded no-op"\n          ' + anchor,
                "auto backend scope decision must not publish a superseded no-op",
            ),
            (
                "local ancestry proof",
                'git merge-base --is-ancestor "$RELEASE_SHA" "$main_sha"\n          ' + anchor,
                "auto backend scope decision must not compute local ancestry",
            ),
            (
                "local main history fetch",
                "git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main\n          " + anchor,
                "auto backend scope decision must not fetch local main history",
            ),
        )
        for name, replacement, expected in cases:
            with self.subTest(name=name):
                root = self.fixture_root()
                self.mutate(root, CHECKER.AUTO_WORKFLOW_PATH, anchor, replacement)
                self.assertIn(expected, CHECKER.validate(root))

    def test_auto_workflow_rejects_stale_or_unverified_source_admission(self) -> None:
        cases = (
            (
                "unbound run attempt",
                "RELEASE_RUN_ATTEMPT: ${{ github.event.workflow_run.run_attempt }}",
                "RELEASE_RUN_ATTEMPT: 2",
                "automatic source admission must bind the proof run attempt",
            ),
            (
                "untrusted initial checkout",
                "      - name: Checkout current main for automatic source admission\n        uses: actions/checkout@v7\n        with:\n          ref: main",
                "      - name: Checkout current main for automatic source admission\n        uses: actions/checkout@v7\n        with:\n          ref: ${{ github.event.workflow_run.head_sha }}",
                "automatic source admission must check out current main",
            ),
            (
                "stale main fetch",
                "RELEASE_RUN_ATTEMPT: ${{ github.event.workflow_run.run_attempt }}\n        run: |\n          set -euo pipefail\n          git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main",
                "RELEASE_RUN_ATTEMPT: ${{ github.event.workflow_run.run_attempt }}\n        run: |\n          set -euo pipefail\n          git fetch --no-tags origin +refs/heads/release:refs/remotes/origin/main",
                "automatic source admission must refresh current main",
            ),
            (
                "stale main comparison",
                "--main-sha \"$main_sha\"",
                "--main-sha \"$RELEASE_SHA\"",
                "automatic source admission must verify current main",
            ),
            (
                "target resolved from an unproven listing",
                "actions/workflows/release-eligibility.yml/runs?event=push&branch=main&status=success",
                "actions/workflows/release-eligibility.yml/runs?event=push&branch=main&status=completed",
                "automatic source admission must resolve the newest successful main Release Eligibility proof",
            ),
            (
                "candidate not required to be merged",
                'git merge-base --is-ancestor "$candidate_sha" "$main_sha"',
                'git merge-base --is-ancestor "$candidate_sha" "$candidate_sha"',
                "automatic source admission must only admit a candidate reachable from current main",
            ),
            (
                "target allowed to be older than its trigger",
                '--trigger-is-ancestor-of-sha "$trigger_is_ancestor_of_sha"',
                '--trigger-is-ancestor-of-sha true',
                "automatic source admission must refuse a target older than its trigger",
            ),
            (
                "unreadable proof listing tolerated",
                "curl --silent --show-error --fail",
                "curl --silent --show-error",
                "automatic source admission must refuse to deploy on an unreadable proof listing",
            ),
            (
                "guard tolerance",
                "        id: admitted_source\n        env:",
                "        id: admitted_source\n        continue-on-error: true\n        env:",
                "automatic release-proof freshness validation must not be conditionally skipped or tolerated",
            ),
            (
                "guard fail open",
                "--run-attempt \"$RELEASE_RUN_ATTEMPT\"",
                "--run-attempt \"$RELEASE_RUN_ATTEMPT\" || true",
                "automatic release-proof freshness validation must not contain a shell fail-open path",
            ),
            (
                "old SHA checked out for deployment",
                "ref: ${{ inputs.admitted_sha }}",
                "ref: ${{ github.event.workflow_run.head_sha }}",
                "auto backend deploy must check out the verified SHA before deployment",
            ),
        )
        for name, old, new, expected in cases:
            with self.subTest(name=name):
                root = self.fixture_root()
                self.mutate(root, CHECKER.AUTO_WORKFLOW_PATH, old, new)
                self.assertIn(expected, CHECKER.validate(root))

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

    def test_auto_workflow_rejects_steps_outside_the_source_admission_sequence(self) -> None:
        cases = (
            (
                "read-only credentials",
                "Require read-only Firestore credentials",
                "Resolve and verify the newest proven main source",
                "automatic release-proof freshness validation must run before read-only credential use",
            ),
            (
                "admitted source checkout",
                "Checkout admitted Firestore source",
                "Resolve and verify the newest proven main source",
                "automatic release-proof freshness validation must run before admitted-source checkout or execution",
            ),
            (
                "read-only Firestore auth",
                "Google Auth for read-only Firestore inventory",
                "Resolve and verify the newest proven main source",
                "automatic release-proof freshness validation must run before read-only Firestore authentication",
            ),
            (
                "admitted source checkout before credentials",
                "Checkout admitted Firestore source",
                "Require read-only Firestore credentials",
                "read-only credential use must run before admitted-source checkout",
            ),
            (
                "read-only Firestore auth before admitted source checkout",
                "Google Auth for read-only Firestore inventory",
                "Checkout admitted Firestore source",
                "admitted-source checkout must run before read-only Firestore authentication",
            ),
        )
        for name, moved_step, before_step, expected in cases:
            with self.subTest(name=name):
                root = self.fixture_root()
                self.move_step_before(
                    root,
                    CHECKER.AUTO_WORKFLOW_PATH,
                    moved_step,
                    before_step,
                )
                self.assertIn(expected, CHECKER.validate(root))

    def test_auto_workflow_scopes_admission_steps_to_readiness_and_rejects_duplicates(self) -> None:
        root = self.fixture_root()
        self.move_step_before(
            root,
            CHECKER.AUTO_WORKFLOW_PATH,
            "Require read-only Firestore credentials",
            "Resolve and verify the newest proven main source",
        )
        self.mutate(
            root,
            CHECKER.AUTO_WORKFLOW_PATH,
            "  firestore_readiness:\n",
            "  dummy:\n    runs-on: ubuntu-latest\n    steps:\n      - name: Resolve and verify the newest proven main source\n        run: true\n\n  firestore_readiness:\n",
        )
        self.assertIn(
            "automatic release-proof freshness validation must run before read-only credential use",
            CHECKER.validate(root),
        )

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.AUTO_WORKFLOW_PATH,
            "      - name: Resolve and verify the newest proven main source\n        id: admitted_source\n",
            "      - name: Resolve and verify the newest proven main source\n        run: true\n\n      - name: Resolve and verify the newest proven main source\n        id: admitted_source\n",
        )
        self.assertIn(
            "backend source admission must contain exactly one automatic release-proof freshness validation step",
            CHECKER.validate(root),
        )

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
            "  deploy:\n    needs: [validate-production-boundary, firestore_readiness, record_break_glass]\n    if: >-\n      always() &&\n      github.ref == 'refs/heads/main' &&\n      github.event.inputs.mode == 'deploy' &&\n      needs.validate-production-boundary.result == 'success' &&\n      needs.firestore_readiness.result == 'success' &&\n      (needs.record_break_glass.result == 'success' || needs.record_break_glass.result == 'skipped')\n",
            "  deploy:\n    needs: [validate-production-boundary, firestore_readiness, record_break_glass]\n    if: >-\n      always() &&\n      github.ref == 'refs/heads/main' &&\n      github.event.inputs.mode == 'deploy' &&\n      needs.validate-production-boundary.result == 'success' &&\n      needs.firestore_readiness.result == 'success' &&\n      true\n",
        )
        self.assertIn("manual deployment must gate break-glass deploys on a successful audit record", CHECKER.validate(root))

    def test_manual_workflow_rejects_boundary_dependency_bypasses(self) -> None:
        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "    needs: validate-production-boundary\n",
            "",
        )
        self.assertIn(
            "manual source admission must wait for production-boundary validation",
            CHECKER.validate(root),
        )

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "needs: [validate-production-boundary, firestore_readiness, record_break_glass]",
            "needs: firestore_readiness",
        )
        self.assertIn(
            "manual deployment must depend on production-boundary validation, source admission, and break-glass audit",
            CHECKER.validate(root),
        )

    def test_auto_workflow_rejects_github_sha_or_incomplete_source_binding(self) -> None:
        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.DEPLOY_BACKEND_STACK_ACTION,
            "ref: ${{ inputs.admitted_sha }}",
            "ref: ${{ github.sha }}",
        )
        errors = CHECKER.validate(root)
        self.assertIn("auto backend deploy must not use github.sha after workflow_run admission", errors)
        self.assertIn("auto backend deploy must check out the verified SHA before deployment", errors)

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.DEPLOY_BACKEND_STACK_ACTION,
            '--commit-sha "${{ inputs.admitted_sha }}"',
            '--commit-sha "${{ github.sha }}"',
        )
        errors = CHECKER.validate(root)
        self.assertIn("auto backend deploy must not use github.sha after workflow_run admission", errors)
        self.assertIn("auto backend deploy must bind every release vector to the verified SHA", errors)

    def test_manual_workflow_rejects_arbitrary_branch_or_missing_proof_query(self) -> None:
        root = self.fixture_root()
        self.mutate(root, CHECKER.MANUAL_WORKFLOW_PATH, "      release_sha:\n", "      branch:\n")
        self.assertIn(
            "manual backend deploy must keep release_sha optional for traffic-only repair", CHECKER.validate(root)
        )

        root = self.fixture_root()
        self.mutate(root, CHECKER.MANUAL_WORKFLOW_PATH, "        required: false", "        required: true")
        self.assertIn(
            "manual backend deploy must keep release_sha optional for traffic-only repair", CHECKER.validate(root)
        )

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
            "admitted_sha: ${{ needs.firestore_readiness.outputs.admitted_sha }}",
            "admitted_sha: ${{ github.event.inputs.release_sha }}",
        )
        self.assertIn("manual deployment must pass the admitted SHA to the deploy composite action", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.DEPLOY_BACKEND_STACK_ACTION,
            '--commit-sha "${{ inputs.admitted_sha }}"',
            '--commit-sha "${{ github.event.inputs.release_sha }}"',
        )
        self.assertIn("manual deployment must bind every release vector to the admitted SHA", CHECKER.validate(root))

        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.DEPLOY_BACKEND_STACK_ACTION,
            "ref: ${{ github.sha }}",
            "ref: ${{ github.event.inputs.release_sha }}",
        )
        self.assertIn(
            "manual backend deploy must stage workflow-owned control scripts from github.sha",
            CHECKER.validate(root),
        )

    def test_commented_composite_reference_does_not_expand_contract(self) -> None:
        root = self.fixture_root()
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "        uses: ./.github/actions/deploy-backend-stack",
            "        # uses: ./.github/actions/deploy-backend-stack",
        )
        self.mutate(
            root,
            CHECKER.DEPLOY_BACKEND_STACK_ACTION,
            '--commit-sha "${{ inputs.admitted_sha }}"',
            '--commit-sha "${{ github.sha }}"',
        )
        errors = CHECKER.validate(root)
        self.assertIn("manual deployment must bind every release vector to the admitted SHA", errors)

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
        self.mutate(
            root,
            CHECKER.MANUAL_WORKFLOW_PATH,
            "          ref: main",
            "          ref: ${{ github.event.inputs.release_sha }}",
        )
        self.assertIn("traffic-only repair must not require a release-source admission", CHECKER.validate(root))


class BreakGlassContractTests(unittest.TestCase):
    """Static contract for the eligibility-proof break-glass hatch.

    These read the workflow source rather than executing it -- GitHub Actions
    cannot be driven from a unit test -- so they are tripwires, not behavioral
    coverage. They pin the properties the hatch must never lose.
    """

    def workflow(self) -> str:
        return (ROOT / CHECKER.MANUAL_WORKFLOW_PATH).read_text(encoding="utf-8")

    def test_break_glass_requires_an_explicit_confirm_string_and_reason(self) -> None:
        text = self.workflow()
        self.assertIn('!= "deploy-without-proof"', text)
        self.assertIn("requires a non-empty break_glass_reason", text)

    def test_merged_main_ancestry_is_enforced_outside_the_break_glass_branch(self) -> None:
        # The hatch may skip the eligibility proof, never the ancestry check:
        # unreviewed code must not reach production by any path.
        text = self.workflow()
        ancestor = text.index("git merge-base --is-ancestor")
        skip_branch = text.index('if [[ "${SKIP_PROOF:-false}" == "true" ]]')
        self.assertLess(
            ancestor,
            skip_branch,
            "ancestry check must run before (and outside) the break-glass branch",
        )

    def test_break_glass_use_is_recorded_as_an_issue(self) -> None:
        text = self.workflow()
        self.assertIn("release-gate-failure", text)
        self.assertIn("Record that the eligibility proof was bypassed", text)


if __name__ == "__main__":
    unittest.main()
