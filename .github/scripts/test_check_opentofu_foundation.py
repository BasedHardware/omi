#!/usr/bin/env python3
"""Fixture tests for the OpenTofu foundation boundary checker."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / ".github" / "scripts" / "check_opentofu_foundation.py"
SPEC = importlib.util.spec_from_file_location("opentofu_foundation", CHECKER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {CHECKER_PATH}")
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


MODULE_HEADER = '''terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }

  backend "gcs" {}
}
'''


class OpenTofuFoundationFixture(unittest.TestCase):
    def module_errors(self, contents: str) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="omi-opentofu-foundation-") as temp_dir:
            module_dir = Path(temp_dir)
            (module_dir / "main.tf").write_text(contents, encoding="utf-8")
            return CHECKER.check_module(module_dir)

    def test_allows_empty_foundation_module(self) -> None:
        self.assertEqual(self.module_errors(MODULE_HEADER), [])

    def test_allows_future_foundation_service_account(self) -> None:
        contents = MODULE_HEADER + '''
resource "google_service_account" "ci_plan" {
  account_id = "omi-tofu-plan"
}
'''
        self.assertEqual(self.module_errors(contents), [])

    def test_rejects_cloud_run_resources(self) -> None:
        contents = MODULE_HEADER + '''
resource "google_cloud_run_v2_service" "backend" {}
'''
        errors = self.module_errors(contents)
        self.assertIn("outside the foundation boundary", "\n".join(errors))
        self.assertIn("forbidden release or secret-value reference", "\n".join(errors))

    def test_rejects_secret_versions_and_payloads(self) -> None:
        contents = MODULE_HEADER + '''
resource "google_secret_manager_secret_version" "api_key" {
  secret_data = "not-allowed"
}
'''
        errors = self.module_errors(contents)
        self.assertIn("google_secret_manager_secret_version", "\n".join(errors))
        self.assertIn("secret_data", "\n".join(errors))

    def test_rejects_non_foundation_resources_and_all_data_sources(self) -> None:
        contents = MODULE_HEADER + '''
resource "google_compute_network" "network" {}
data "google_secret_manager_secret_version" "api_key" {}
'''
        errors = self.module_errors(contents)
        self.assertIn("google_compute_network", "\n".join(errors))
        self.assertIn("data source google_secret_manager_secret_version", "\n".join(errors))

    def test_prepares_an_offline_plan_copy_without_mutating_the_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="omi-opentofu-foundation-") as temp_dir:
            source_dir = Path(temp_dir) / "source"
            plan_dir = Path(temp_dir) / "plan"
            source_dir.mkdir()
            source_file = source_dir / "main.tf"
            source_file.write_text(MODULE_HEADER, encoding="utf-8")

            CHECKER.prepare_offline_plan_module(source_dir, plan_dir)

            self.assertIn('backend "gcs" {}', source_file.read_text(encoding="utf-8"))
            self.assertNotIn('backend "gcs" {}', (plan_dir / "main.tf").read_text(encoding="utf-8"))

    def test_validation_workflow_remains_credentials_free_and_apply_free(self) -> None:
        self.assertEqual(CHECKER.check_workflow(CHECKER.DEFAULT_WORKFLOW_PATH), [])

    def test_validation_workflow_rejects_cloud_auth_and_apply(self) -> None:
        errors = CHECKER.check_workflow_text(
            """permissions:
  contents: read
  id-token: write
tofu apply
"""
        )
        self.assertIn("forbidden cloud mutation or credential reference", "\n".join(errors))
        self.assertIn("missing required no-mutation reference", "\n".join(errors))

    def test_plan_accepts_only_foundation_resource_types(self) -> None:
        plan = {"resource_changes": [{"address": "google_service_account.ci", "type": "google_service_account"}]}
        self.assertEqual(CHECKER.check_plan(plan, require_empty=False), [])

    def test_initial_plan_must_remain_empty_and_rejects_cloud_run(self) -> None:
        plan = {
            "resource_changes": [
                {"address": "google_cloud_run_v2_service.backend", "type": "google_cloud_run_v2_service"}
            ]
        }
        errors = CHECKER.check_plan(plan, require_empty=True)
        self.assertIn("outside the foundation boundary", "\n".join(errors))
        self.assertIn("initial no-mutation slice must have an empty plan", "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
