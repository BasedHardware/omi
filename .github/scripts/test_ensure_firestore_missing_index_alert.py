from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from ensure_firestore_missing_index_alert import (
    ALIGNER,
    ALIGNMENT,
    CONDITION_FILTER,
    DOCUMENTATION,
    DOCUMENTATION_URL,
    DISPLAY_NAME,
    METRIC,
    METRIC_TYPE,
    ensure_alert,
    main,
)

PROJECT = "based-hardware"
CHANNELS = "projects/based-hardware/notificationChannels/123"
POLICY = "projects/based-hardware/alertPolicies/456"


def policy_documentation(*, omit_zero_threshold: bool = False) -> str:
    policy = json.loads(_policy_json())
    if omit_zero_threshold:
        del policy["conditions"][0]["conditionThreshold"]["thresholdValue"]
    return json.dumps(policy)


def _policy_json() -> str:
    return json.dumps(
        {
            "name": POLICY,
            "displayName": DISPLAY_NAME,
            "enabled": True,
            "combiner": "OR",
            "notificationChannels": [CHANNELS],
            "documentation": {"content": DOCUMENTATION},
            "conditions": [
                {
                    "displayName": DISPLAY_NAME,
                    "conditionThreshold": {
                        "filter": CONDITION_FILTER,
                        "duration": "0s",
                        "comparison": "COMPARISON_GT",
                        "thresholdValue": 0,
                        "aggregations": [{"alignmentPeriod": ALIGNMENT, "perSeriesAligner": ALIGNER}],
                        "trigger": {"count": 1},
                    },
                }
            ],
        }
    )


class EnsureFirestoreMissingIndexAlertTests(unittest.TestCase):
    def test_live_policy_without_zero_threshold_field_is_not_drift(self) -> None:
        # The Monitoring API omits thresholdValue when it is 0; prod deploy runs 36819288039 and
        # 36824113474 failed with "Monitoring policy drift: condition threshold" on exactly that shape.
        def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[1:5] == ["logging", "metrics", "describe", METRIC]:
                return subprocess.CompletedProcess(args, 0, "{}", "")
            if args[1:3] == ["monitoring", "policies"] and "list" in args:
                return subprocess.CompletedProcess(args, 0, POLICY + "\n", "")
            if args[1:3] == ["monitoring", "policies"] and "update" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, policy_documentation(omit_zero_threshold=True), "")
            if args[1:5] == ["logging", "metrics", "update", METRIC]:
                return subprocess.CompletedProcess(args, 0, "", "")
            raise AssertionError(f"unexpected command: {args}")

        self.assertEqual(ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=runner), POLICY)

    def test_existing_metric_and_policy_are_updated_without_duplicate_creation(self) -> None:
        calls: list[list[str]] = []

        def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[1:5] == ["logging", "metrics", "describe", METRIC]:
                return subprocess.CompletedProcess(args, 0, "{}", "")
            if args[1:3] == ["monitoring", "policies"] and "list" in args:
                return subprocess.CompletedProcess(args, 0, POLICY + "\n", "")
            if args[1:3] == ["monitoring", "policies"] and "update" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, policy_documentation(), "")
            if args[1:5] == ["logging", "metrics", "update", METRIC]:
                return subprocess.CompletedProcess(args, 0, "", "")
            raise AssertionError(f"unexpected command: {args}")

        self.assertEqual(ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=runner), POLICY)
        self.assertEqual(ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=runner), POLICY)
        self.assertEqual(sum("create" in call for call in calls), 0)
        self.assertEqual(sum("update" in call for call in calls), 4)
        self.assertTrue(
            any(
                f"--config-from-file={Path(__file__).resolve().parents[1] / 'monitoring' / 'firestore_missing_index_errors_metric.json'}"
                in call
                for call in calls
            )
        )

    def test_missing_metric_is_created(self) -> None:
        calls: list[list[str]] = []

        def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[1:5] == ["logging", "metrics", "describe", METRIC]:
                return subprocess.CompletedProcess(args, 1, "", "NOT_FOUND: metric not found")
            if args[1:5] == ["logging", "metrics", "create", METRIC]:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "list" in args:
                return subprocess.CompletedProcess(args, 0, POLICY + "\n", "")
            if args[1:3] == ["monitoring", "policies"] and "update" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[1:3] == ["monitoring", "policies"] and "describe" in args:
                return subprocess.CompletedProcess(args, 0, policy_documentation(), "")
            raise AssertionError(f"unexpected command: {args}")

        ensure_alert(project=PROJECT, notification_channels=CHANNELS, runner=runner)
        self.assertTrue(any(call[1:5] == ["logging", "metrics", "create", METRIC] for call in calls))

    def test_arguments_reject_empty_or_duplicate_channels(self) -> None:
        with self.assertRaisesRegex(ValueError, "project must not be empty"):
            ensure_alert(project=" ", notification_channels=CHANNELS, runner=lambda *a, **k: self.fail("gcloud called"))
        with self.assertRaisesRegex(ValueError, "without empty entries"):
            ensure_alert(
                project=PROJECT, notification_channels=f"{CHANNELS},", runner=lambda *a, **k: self.fail("gcloud called")
            )
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
        self.assertIn("python3 .github/scripts/ensure_firestore_missing_index_alert.py", step)
        self.assertIn("--notification-channels \"$ALERT_CHANNELS\"", step)
        self.assertIn(DOCUMENTATION_URL, (root / ".github/scripts/ensure_firestore_missing_index_alert.py").read_text())
        self.assertTrue((root / "backend/docs/runbooks/firestore-missing-index.md").is_file())


if __name__ == "__main__":
    unittest.main()
