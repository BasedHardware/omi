#!/usr/bin/env python3
"""Classifier and workflow-contract fixtures for the admin deploy scope gate."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

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
        rate = panels["Activation rate"]["targets"][0]
        self.assertEqual(rate["url"], "http://127.0.0.1:8899/api/omi/stats/activation?days=60")
        self.assertEqual([column["selector"] for column in rate["columns"]], ["rate"])
        self.assertNotIn("viral-metrics", rate["url"])

        series = next(
            panel["targets"][0]
            for title, panel in panels.items()
            if title.startswith("Activation (signup")
        )
        self.assertEqual(series["url"], "http://127.0.0.1:8899/api/omi/stats/activation?days=60")
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
