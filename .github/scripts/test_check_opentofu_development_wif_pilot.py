#!/usr/bin/env python3
"""Fixture tests for the development WIF plan pilot guard."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = ROOT / ".github" / "scripts" / "check_opentofu_development_wif_pilot.py"
SPEC = importlib.util.spec_from_file_location("opentofu_development_wif_pilot", CHECKER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {CHECKER_PATH}")
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


class DevelopmentWifPilotFixture(unittest.TestCase):
    def partial_recovery_plan(self) -> dict[str, object]:
        def resource(address: str, values: dict[str, str] | None = None) -> dict[str, object]:
            return {"address": address, "values": values or {}}

        prior_resources = [
            resource(
                "google_service_account.plan",
                {"account_id": "omi-tofu-plan-dev-9842"},
            ),
            resource(
                "google_project_iam_member.plan_project_browser",
                {
                    "project": "based-hardware-dev",
                    "role": "roles/browser",
                    "member": "serviceAccount:omi-tofu-plan-dev-9842@based-hardware-dev.iam.gserviceaccount.com",
                },
            ),
        ]
        return {
            "prior_state": {"values": {"root_module": {"resources": prior_resources}}},
            "planned_values": {
                "values": {
                    "root_module": {
                        "resources": [resource(address) for address in sorted(CHECKER.EXPECTED_BOOTSTRAP_RESOURCES)]
                    }
                }
            },
            "resource_changes": [
                {"address": address, "change": {"actions": actions}}
                for address, actions in sorted(CHECKER.EXPECTED_PARTIAL_RECOVERY_ACTIONS.items())
            ],
        }

    def test_checked_in_pilot_contract_passes(self) -> None:
        self.assertEqual(CHECKER.main(), 0)

    def test_bootstrap_rejects_broad_or_secret_access(self) -> None:
        source = CHECKER.read(CHECKER.BOOTSTRAP)
        self.assertIn("roles/owner", "\n".join(CHECKER.check_bootstrap(source + '\nrole = "roles/owner"\n')))
        self.assertIn(
            "roles/secretmanager.secretAccessor",
            "\n".join(CHECKER.check_bootstrap(source + '\nrole = "roles/secretmanager.secretAccessor"\n')),
        )

    def test_bootstrap_rejects_a_broadened_browser_binding(self) -> None:
        source = CHECKER.read(CHECKER.BOOTSTRAP)
        errors = CHECKER.check_bootstrap(source.replace('role    = "roles/browser"', 'role    = "roles/viewer"'))
        self.assertIn("roles/viewer", "\n".join(errors))
        self.assertIn("plan_project_browser", "\n".join(errors))

    def test_bootstrap_variables_reject_production_project(self) -> None:
        source = CHECKER.read(CHECKER.BOOTSTRAP_VARIABLES)
        errors = CHECKER.check_bootstrap_variables(
            source.replace('default     = "based-hardware-dev"', 'default     = "based-hardware"')
        )
        self.assertIn("based-hardware-dev", "\n".join(errors))

    def test_bootstrap_rejects_non_immutable_github_identity(self) -> None:
        source = CHECKER.read(CHECKER.BOOTSTRAP)
        errors = CHECKER.check_bootstrap(source.replace("assertion.repository_id", "assertion.repository", 1))
        self.assertIn("repository_id", "\n".join(errors))

    def test_bootstrap_rejects_overlong_wif_display_names(self) -> None:
        source = CHECKER.read(CHECKER.BOOTSTRAP)
        errors = CHECKER.check_bootstrap(
            source.replace(
                'display_name              = "Omi OpenTofu dev GitHub pool"',
                'display_name              = "' + "x" * 33 + '"',
            )
        )
        self.assertIn("google_iam_workload_identity_pool.github display_name", "\n".join(errors))
        errors = CHECKER.check_bootstrap(
            source.replace(
                'display_name                       = "Omi GitHub dev plan OIDC"',
                'display_name                       = "' + "x" * 33 + '"',
            )
        )
        self.assertIn("google_iam_workload_identity_pool_provider.github display_name", "\n".join(errors))

    def test_bootstrap_rejects_extra_open_tofu_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="omi-opentofu-pilot-") as temp_dir:
            module_dir = Path(temp_dir)
            for name in ("main.tf", "variables.tf", "elevated.tf", "hidden.tf.json"):
                (module_dir / name).touch()
            errors = CHECKER.check_module_files(module_dir, CHECKER.EXPECTED_PILOT_FILES, "bootstrap")
        self.assertIn("elevated.tf", "\n".join(errors))
        self.assertIn("hidden.tf.json", "\n".join(errors))

    def test_bootstrap_plan_requires_exact_creates(self) -> None:
        plan = {
            "resource_changes": [
                {"address": address, "change": {"actions": ["create"]}}
                for address in sorted(CHECKER.EXPECTED_BOOTSTRAP_RESOURCES)
            ]
        }
        self.assertEqual(CHECKER.check_plan(plan), [])

        plan["resource_changes"].append(
            {"address": "google_project_iam_member.escalation", "change": {"actions": ["create"]}}
        )
        errors = CHECKER.check_plan(plan)
        self.assertIn("must be exactly", "\n".join(errors))

    def test_partial_recovery_plan_requires_exact_known_state_and_actions(self) -> None:
        plan = self.partial_recovery_plan()
        self.assertEqual(CHECKER.check_partial_recovery_plan(plan), [])

        unexpected_state = deepcopy(plan)
        unexpected_state["prior_state"]["values"]["root_module"]["resources"].append(
            {"address": "google_iam_workload_identity_pool.github", "values": {}}
        )
        errors = CHECKER.check_partial_recovery_plan(unexpected_state)
        self.assertIn("prior state must contain exactly", "\n".join(errors))

        destructive_change = deepcopy(plan)
        destructive_change["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
        errors = CHECKER.check_partial_recovery_plan(destructive_change)
        self.assertIn("actions must be exactly", "\n".join(errors))

    def test_probe_rejects_resources_and_remote_state(self) -> None:
        source = CHECKER.read(CHECKER.PROBE)
        errors = CHECKER.check_probe(
            source + '\nresource "google_cloud_run_v2_service" "forbidden" {}\nbackend "gcs" {}\n'
        )
        self.assertIn("must not declare resources", "\n".join(errors))
        self.assertIn("must not use a remote backend", "\n".join(errors))

    def test_workflow_rejects_apply_and_key_credentials(self) -> None:
        source = CHECKER.read(CHECKER.WORKFLOW)
        errors = CHECKER.check_workflow(source + "\ntofu apply\ncredentials_json: ${{ secrets.GCP_CREDENTIALS }}\n")
        self.assertIn("tofu apply", "\n".join(errors))
        self.assertIn("credentials_json", "\n".join(errors))

    def test_validation_workflow_rejects_real_or_extra_credentials(self) -> None:
        source = CHECKER.read(CHECKER.VALIDATION_WORKFLOW)
        errors = CHECKER.check_validation_workflow(source.replace("offline-validation-only", "not-a-sentinel"))
        self.assertIn("offline-validation-only", "\n".join(errors))
        errors = CHECKER.check_validation_workflow(
            source + "\nGOOGLE_APPLICATION_CREDENTIALS: ${{ secrets.GCP_CREDENTIALS }}\n"
        )
        self.assertIn("GOOGLE_APPLICATION_CREDENTIALS", "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
