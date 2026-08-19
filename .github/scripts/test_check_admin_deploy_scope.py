#!/usr/bin/env python3
"""Classifier and workflow-contract fixtures for the admin deploy scope gate."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Disposable repos must not inherit a pre-push hook's GIT_DIR or hooksPath.
GIT_ISOLATION = ("-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false")

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
CLASSIFIER_PATH = SCRIPT_DIR / "check_admin_deploy_scope.py"
ADMISSION_PATH = SCRIPT_DIR / "check_admin_deploy_scope_admission.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CLASSIFIER = load_module("check_admin_deploy_scope", CLASSIFIER_PATH)
ADMISSION = load_module("check_admin_deploy_scope_admission", ADMISSION_PATH)


class AdminDeployScopeClassifierTests(unittest.TestCase):
    def test_workflow_dispatch_always_applies(self) -> None:
        self.assertTrue(
            CLASSIFIER.admin_deploy_applies(
                ["web/admin/lib/services/omi-api/omiApi.generated.ts"],
                event_name="workflow_dispatch",
            )
        )

    def test_generated_client_only_skips(self) -> None:
        self.assertFalse(
            CLASSIFIER.admin_deploy_applies(
                ["web/admin/lib/services/omi-api/omiApi.generated.ts"],
                event_name="push",
            )
        )
        self.assertFalse(
            CLASSIFIER.admin_deploy_applies(
                [
                    "backend/routers/foo.py",
                    "web/admin/lib/services/omi-api/omiApi.generated.ts",
                    "desktop/macos/Desktop/Sources/Foo.swift",
                ],
                event_name="push",
            )
        )

    def test_real_admin_runtime_still_deploys(self) -> None:
        self.assertTrue(
            CLASSIFIER.admin_deploy_applies(
                ["web/admin/app/api/omi/stats/activation/route.ts"],
                event_name="push",
            )
        )
        self.assertTrue(
            CLASSIFIER.admin_deploy_applies(
                [
                    "web/admin/lib/services/omi-api/omiApi.generated.ts",
                    "web/admin/app/(protected)/dashboard/page.tsx",
                ],
                event_name="push",
            )
        )

    def test_workflow_and_public_build_inputs_still_deploy(self) -> None:
        for path in (
            ".github/workflows/gcp_admin.yml",
            ".github/scripts/check_admin_deploy_scope.py",
            ".github/actions/deploy-public-build/action.yml",
            ".github/actions/prepare-public-build/action.yml",
            ".github/actions/public-build-candidate-promotion/action.yml",
            ".github/scripts/preflight_public_build_config.py",
            ".github/scripts/preflight_public_build_runtime.py",
            ".github/scripts/smoke_public_build_browser.py",
            "config/public-build-values.json",
            "config/public-build-contract.json",
        ):
            with self.subTest(path=path):
                self.assertTrue(CLASSIFIER.admin_deploy_applies([path], event_name="push"))

    def test_unrelated_backend_or_desktop_paths_skip(self) -> None:
        self.assertFalse(
            CLASSIFIER.admin_deploy_applies(
                ["backend/models/memory.py", "desktop/macos/AGENTS.md"],
                event_name="push",
            )
        )

    def test_uncertain_parent_or_missing_diff_deploys(self) -> None:
        self.assertTrue(
            CLASSIFIER.admin_deploy_applies(
                ["web/admin/lib/services/omi-api/omiApi.generated.ts"],
                event_name="push",
                parent_available=False,
            )
        )
        self.assertTrue(CLASSIFIER.admin_deploy_applies(None, event_name="push"))

    def test_generated_client_plus_public_build_helper_still_deploys(self) -> None:
        self.assertTrue(
            CLASSIFIER.admin_deploy_applies(
                [
                    "web/admin/lib/services/omi-api/omiApi.generated.ts",
                    ".github/actions/deploy-public-build/action.yml",
                ],
                event_name="push",
            )
        )


class AdminDeployPushRangeTests(unittest.TestCase):
    def git(self, repo: Path, *args: str) -> str:
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        completed = subprocess.run(
            [
                "git",
                "-c",
                "user.name=admin-scope-fixture",
                "-c",
                "user.email=admin-scope-fixture@example.com",
                *GIT_ISOLATION,
                *args,
            ],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return completed.stdout.strip()

    def write(self, repo: Path, relative: str, contents: str) -> None:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def commit(self, repo: Path, message: str) -> str:
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-m", message)
        return self.git(repo, "rev-parse", "HEAD")

    def repo_with_push_range(self) -> tuple[Path, str, str, str]:
        temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp)
        self.git(temp, "init", "-b", "main")
        self.write(temp, "README.md", "base\n")
        before = self.commit(temp, "base")
        self.write(temp, "web/admin/app/api/omi/stats/activation/route.ts", "export const runtime = true;\n")
        runtime = self.commit(temp, "admin runtime")
        self.write(
            temp,
            "web/admin/lib/services/omi-api/omiApi.generated.ts",
            "export const generated = true;\n",
        )
        tip = self.commit(temp, "generated client only")
        return temp, before, runtime, tip

    def test_multi_commit_push_with_earlier_runtime_change_deploys(self) -> None:
        repo, before, _runtime, tip = self.repo_with_push_range()
        applies, reason = CLASSIFIER.decide_from_git(
            event_name="push",
            sha=tip,
            before=before,
            repo=repo,
        )
        self.assertTrue(applies)
        self.assertIn("push range", reason)

    def test_generated_only_tip_skips_when_range_is_also_generated_only(self) -> None:
        repo, before, runtime, tip = self.repo_with_push_range()
        applies, _reason = CLASSIFIER.decide_from_git(
            event_name="push",
            sha=tip,
            before=runtime,
            repo=repo,
        )
        self.assertFalse(applies)
        self.assertNotEqual(before, runtime)

    def test_missing_or_zero_before_deploys_fail_closed(self) -> None:
        repo, _before, _runtime, tip = self.repo_with_push_range()
        for before in (None, "", "0" * 40):
            with self.subTest(before=before):
                applies, reason = CLASSIFIER.decide_from_git(
                    event_name="push",
                    sha=tip,
                    before=before,
                    repo=repo,
                )
                self.assertTrue(applies)
                self.assertIn("fail-closed", reason)

    def test_workflow_dispatch_ignores_push_range(self) -> None:
        repo, before, _runtime, tip = self.repo_with_push_range()
        applies, reason = CLASSIFIER.decide_from_git(
            event_name="workflow_dispatch",
            sha=tip,
            before=before,
            repo=repo,
        )
        self.assertTrue(applies)
        self.assertIn("workflow_dispatch", reason)


class AdminDeployScopeAdmissionTests(unittest.TestCase):
    def fixture_root(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        for relative in (ADMISSION.WORKFLOW_PATH, ADMISSION.CLASSIFIER_PATH):
            destination = temp / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        self.addCleanup(shutil.rmtree, temp)
        return temp

    def mutate(self, root: Path, old: str, new: str) -> None:
        path = root / ADMISSION.WORKFLOW_PATH
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_workflow_is_valid(self) -> None:
        self.assertEqual(ADMISSION.validate(), [])

    def test_rejects_scope_bypasses_or_cloud_access(self) -> None:
        cases = (
            (
                "scope dependency",
                "    needs: scope\n",
                "",
                "admin deploy job must depend on the scope decision",
            ),
            (
                "scope output predicate",
                "if: needs.scope.outputs.applies == 'true'",
                "if: needs.scope.outputs.applies == 'false'",
                "admin deploy job must take the environment slot only when scope applies",
            ),
            (
                "environment on scope",
                "    permissions:\n      contents: read\n",
                "    environment: prod\n    permissions:\n      contents: read\n",
                "admin scope decision must not receive a deployment environment",
            ),
            (
                "cloud authentication",
                "    runs-on: ubuntu-latest\n    outputs:",
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: google-github-actions/auth@v3\n    outputs:",
                "admin scope decision must not authenticate to cloud services",
            ),
            (
                "cancel in progress",
                "cancel-in-progress: false",
                "cancel-in-progress: true",
                "admin deploy must keep cancel-in-progress: false",
            ),
            (
                "lock group",
                "group: deploy-cloud-run-omi-admin-dashboard-",
                "group: deploy-cloud-run-omi-admin-dashboard-other-",
                "admin deploy must keep the existing lock group",
            ),
            (
                "classifier",
                ".github/scripts/check_admin_deploy_scope.py --github-output",
                "echo applies=true >> \"$GITHUB_OUTPUT\"",
                "admin scope decision must use the shared admin deploy classifier",
            ),
            (
                "commented needs",
                "    needs: scope\n",
                "    # needs: scope\n",
                "admin deploy job must depend on the scope decision",
            ),
            (
                "commented if",
                "    if: needs.scope.outputs.applies == 'true'\n",
                "    # if: needs.scope.outputs.applies == 'true'\n",
                "admin deploy job must take the environment slot only when scope applies",
            ),
            (
                "commented environment",
                "    environment: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || (github.ref == 'refs/heads/development' && 'development') || 'prod' }}\n",
                "    # environment: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || (github.ref == 'refs/heads/development' && 'development') || 'prod' }}\n",
                "admin deploy job must keep the existing environment: prod expression",
            ),
            (
                "scope step id",
                "        id: scope\n",
                "        id: classify\n",
                "admin scope classifier step must keep id: scope",
            ),
            (
                "scope job output",
                "      applies: ${{ steps.scope.outputs.applies }}\n",
                "      applies: 'true'\n",
                "admin scope job must export applies from steps.scope.outputs.applies",
            ),
            (
                "workflow_dispatch",
                "  workflow_dispatch:\n    inputs:\n      environment:\n        description: 'Environment to deploy to'\n        required: false\n        default: 'prod'\n        type: choice\n        options: [development, prod]\n",
                "",
                "admin deploy must keep workflow_dispatch so manual recovery stays available",
            ),
            (
                "dispatch environment input",
                "      environment:\n        description: 'Environment to deploy to'\n        required: false\n        default: 'prod'\n        type: choice\n        options: [development, prod]\n",
                "      branch:\n        description: 'Branch to deploy'\n        required: false\n        default: 'main'\n        type: string\n",
                "admin deploy workflow_dispatch must expose the environment input",
            ),
        )
        for name, old, new, expected in cases:
            with self.subTest(name=name):
                root = self.fixture_root()
                self.mutate(root, old, new)
                self.assertIn(expected, ADMISSION.validate(root))


class OmiTvDashboardContractTests(unittest.TestCase):
    def dashboard(self) -> dict:
        path = ROOT / "web/admin/grafana/dashboards/omi-tv.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_keeps_uid_and_strips_instance_ids(self) -> None:
        dashboard = self.dashboard()
        self.assertEqual(dashboard["uid"], "omi-tv")
        self.assertNotIn("id", dashboard)
        self.assertNotIn("version", dashboard)

    def test_activation_panels_use_firestore_activation_selectors(self) -> None:
        panels = {panel["title"]: panel for panel in self.dashboard()["panels"]}
        # The base (all-platform) board labels the Firestore-backed activation
        # panels "(macOS)" because that route only covers macOS signups.
        rate = panels["Activation rate (macOS)"]["targets"][0]
        self.assertEqual(rate["url"], "http://127.0.0.1:8899/api/omi/stats/activation?days=60")
        self.assertEqual([column["selector"] for column in rate["columns"]], ["rate"])
        self.assertNotIn("viral-metrics", rate["url"])

        series = next(
            panel["targets"][0]
            for title, panel in panels.items()
            if title.startswith("Activation (signup")
        )
        # `_tzdates=week` is a proxy-side display rewrite (stripped before the
        # upstream request); the Firestore activation route contract is the
        # base URL.
        self.assertEqual(
            series["url"].split("&_tzdates=")[0],
            "http://127.0.0.1:8899/api/omi/stats/activation?days=60",
        )
        self.assertEqual(series["root_selector"], "weeks")
        self.assertEqual(
            [column["selector"] for column in series["columns"]],
            ["week", "signups", "activated", "rate"],
        )


class ApplyOmiTvDashboardTests(unittest.TestCase):
    def test_skips_when_token_is_absent(self) -> None:
        import subprocess

        env = {key: value for key, value in __import__("os").environ.items() if key != "GRAFANA_TOKEN"}
        completed = subprocess.run(
            [sys.executable, str(ROOT / "web/admin/grafana/apply_omi_tv_dashboard.py")],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("skipping omi-tv apply", completed.stdout)


if __name__ == "__main__":
    unittest.main()
