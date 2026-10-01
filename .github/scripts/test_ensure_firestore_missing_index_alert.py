from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from ensure_firestore_missing_index_alert import (
    CONDITION_FILTERS,
    DOCUMENTATION_URL,
    DISPLAY_NAME,
    GKE_METRIC,
    METRIC,
    METRIC_CONFIGS,
    _policy_config,
    ensure_alert,
    main,
)

PROJECT = "based-hardware"
CHANNELS = "projects/based-hardware/notificationChannels/123"
POLICY = "projects/based-hardware/alertPolicies/456"


def policy_documentation(*, omit_proto_defaults: bool = False) -> str:
    policy = {"name": POLICY, **_policy_config([CHANNELS])}
    if omit_proto_defaults:
        for condition in policy["conditions"]:
            threshold = condition["conditionThreshold"]
            del threshold["thresholdValue"]
            del threshold["duration"]
    return json.dumps(policy)


class EnsureFirestoreMissingIndexAlertTests(unittest.TestCase):
    def test_readback_without_proto_default_fields_is_not_drift(self) -> None:
        def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[1:3] == ["logging", "metrics"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, "{}", "")
            if args[1:3] == ["monitoring", "policies"] and "list" in args:
                return subprocess.CompletedProcess(args, 0, POLICY + "\n", "")
            if args[1:3] == ["monitoring", "policies"] and "update" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, policy_documentation(omit_proto_defaults=True), "")
            if args[1:3] == ["logging", "metrics"] and "update" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            raise AssertionError(f"unexpected command: {args}")

        self.assertEqual(ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=runner), POLICY)

    def test_existing_policy_update_waits_for_a_newly_created_metric(self) -> None:
        # Prod already has the policy; the GKE metric is created by this run. Monitoring rejects a policy
        # naming a metric created seconds ago, so the update must retry like creation does.
        import ensure_firestore_missing_index_alert as module

        updates: list[list[str]] = []
        sleeps: list[float] = []
        original_sleep = module.time.sleep
        module.time.sleep = sleeps.append
        self.addCleanup(setattr, module.time, "sleep", original_sleep)

        def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[1:3] == ["logging", "metrics"] and "describe" in args:
                if GKE_METRIC in args:
                    return subprocess.CompletedProcess(args, 1, "", "NOT_FOUND: metric not found")
                return subprocess.CompletedProcess(args, 0, "{}", "")
            if args[1:3] == ["logging", "metrics"] and ("create" in args or "update" in args):
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "list" in args:
                return subprocess.CompletedProcess(args, 0, POLICY + "\n", "")
            if args[1:3] == ["monitoring", "policies"] and "update" in args:
                updates.append(args)
                if len(updates) == 1:
                    error = (
                        "Cannot find metric(s) that match type = "
                        f'"logging.googleapis.com/user/{GKE_METRIC}". If a metric was created recently, '
                        "it could take up to 10 minutes to become available."
                    )
                    return subprocess.CompletedProcess(args, 1, "", error)
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, policy_documentation(), "")
            raise AssertionError(f"unexpected command: {args}")

        self.assertEqual(ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=runner), POLICY)
        self.assertEqual(len(updates), 2)
        self.assertEqual(sleeps, [30])

    def test_existing_policy_update_does_not_retry_other_errors(self) -> None:
        def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[1:3] == ["logging", "metrics"]:
                return subprocess.CompletedProcess(args, 0, "{}", "")
            if args[1:3] == ["monitoring", "policies"] and "list" in args:
                return subprocess.CompletedProcess(args, 0, POLICY + "\n", "")
            if args[1:3] == ["monitoring", "policies"] and "update" in args:
                return subprocess.CompletedProcess(args, 1, "", "PERMISSION_DENIED: monitoring.alertPolicies.update")
            raise AssertionError(f"unexpected command: {args}")

        with self.assertRaisesRegex(RuntimeError, "PERMISSION_DENIED"):
            ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=runner)

    def test_existing_metrics_and_policy_update_without_duplicate_creation(self) -> None:
        calls: list[list[str]] = []

        def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[1:3] == ["logging", "metrics"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, "{}", "")
            if args[1:3] == ["monitoring", "policies"] and "list" in args:
                return subprocess.CompletedProcess(args, 0, POLICY + "\n", "")
            if args[1:3] == ["monitoring", "policies"] and "update" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, policy_documentation(), "")
            if args[1:3] == ["logging", "metrics"] and "update" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            raise AssertionError(f"unexpected command: {args}")

        self.assertEqual(ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=runner), POLICY)
        self.assertEqual(ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=runner), POLICY)
        self.assertEqual(sum("create" in call for call in calls), 0)
        self.assertEqual(sum("update" in call for call in calls), 6)
        for metric, config in METRIC_CONFIGS.items():
            self.assertTrue(any(f"--config-from-file={config}" in call for call in calls), metric)
        policy_update = next(call for call in calls if call[1:3] == ["monitoring", "policies"] and "update" in call)
        policy = json.loads(next(value.removeprefix("--policy=") for value in policy_update if value.startswith("--policy=")))
        self.assertEqual(policy["combiner"], "OR")
        self.assertEqual(len(policy["conditions"]), 2)

    def test_missing_metrics_and_policy_are_created(self) -> None:
        calls: list[list[str]] = []

        def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[1:3] == ["logging", "metrics"] and "describe" in args:
                return subprocess.CompletedProcess(args, 1, "", "NOT_FOUND: metric not found")
            if args[1:3] == ["logging", "metrics"] and "create" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "list" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "create" in args:
                return subprocess.CompletedProcess(args, 0, POLICY, "")
            if args[1:3] == ["monitoring", "policies"] and "update" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, policy_documentation(), "")
            raise AssertionError(f"unexpected command: {args}")

        ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=runner)
        self.assertEqual(sum(call[1:3] == ["logging", "metrics"] and "create" in call for call in calls), 2)
        created_policy = next(call for call in calls if call[1:3] == ["monitoring", "policies"] and "create" in call)
        policy = json.loads(next(value.removeprefix("--policy=") for value in created_policy if value.startswith("--policy=")))
        self.assertEqual(len(policy["conditions"]), 2)

    def test_arguments_reject_empty_or_duplicate_channels(self) -> None:
        with self.assertRaisesRegex(ValueError, "project must not be empty"):
            ensure_alert(project=" ", notification_channels=CHANNELS, runner=lambda *a, **k: self.fail("gcloud called"))
        with self.assertRaisesRegex(ValueError, "without empty entries"):
            ensure_alert(project=PROJECT, notification_channels=f"{CHANNELS},", runner=lambda *a, **k: self.fail("gcloud called"))
        with self.assertRaisesRegex(ValueError, "must not contain duplicates"):
            ensure_alert(
                project=PROJECT,
                notification_channels=f"{CHANNELS},{CHANNELS}",
                runner=lambda *a, **k: self.fail("gcloud called"),
            )
        with self.assertRaises(SystemExit):
            main(["--project", PROJECT])

    def test_workflow_calls_script_after_successful_backend_deploy(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/gcp_backend.yml").read_text(encoding="utf-8")
        deploy = workflow.index("- name: Deploy backend stack")
        alert = workflow.index("- name: Provision Firestore missing-index alert")
        step = workflow[alert:]
        self.assertLess(deploy, alert)
        self.assertIn("if: github.event.inputs.environment == 'prod'", step)
        self.assertIn("ALERT_CHANNELS: ${{ vars.SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS }}", step)
        self.assertIn('test -n "${DEPLOY_WORKFLOW_ROOT:-}"', step)
        self.assertIn('test -f "$DEPLOY_WORKFLOW_ROOT/.github/scripts/ensure_firestore_missing_index_alert.py"', step)
        self.assertIn('python3 "$DEPLOY_WORKFLOW_ROOT/.github/scripts/ensure_firestore_missing_index_alert.py"', step)
        self.assertIn('--notification-channels "$ALERT_CHANNELS"', step)
        self.assertTrue((root / "backend/docs/runbooks/firestore-missing-index.md").is_file())

    def test_metric_configs_split_resource_types_and_extract_platform_labels(self) -> None:
        root = Path(__file__).resolve().parents[2]
        cloud_run = json.loads((root / ".github/monitoring/firestore_missing_index_errors_metric.json").read_text())
        gke = json.loads(METRIC_CONFIGS[GKE_METRIC].read_text())
        self.assertIn('resource.type="cloud_run_revision"', cloud_run["filter"])
        self.assertIn('resource.type="k8s_container"', gke["filter"])
        self.assertEqual(cloud_run["labelExtractors"], {"service_name": "EXTRACT(resource.labels.service_name)"})
        self.assertEqual(
            gke["labelExtractors"],
            {
                "namespace_name": "EXTRACT(resource.labels.namespace_name)",
                "container_name": "EXTRACT(resource.labels.container_name)",
            },
        )
        self.assertEqual(set(CONDITION_FILTERS), {"Cloud Run", "GKE"})
        self.assertEqual(set(METRIC_CONFIGS), {METRIC, GKE_METRIC})
        self.assertIn(DOCUMENTATION_URL, (root / ".github/scripts/ensure_firestore_missing_index_alert.py").read_text())


if __name__ == "__main__":
    unittest.main()
