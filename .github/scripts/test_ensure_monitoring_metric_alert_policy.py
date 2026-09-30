from __future__ import annotations

import subprocess
import unittest

from ensure_monitoring_metric_alert_policy import ensure_policy


PROJECT = "based-hardware"
DISPLAY_NAME = "Sync backfill UID sequencer Scheduler execution failed"
METRIC_TYPE = "logging.googleapis.com/user/sync_backfill_uid_sequencer_scheduler_failure"
POLICY_NAME = "projects/based-hardware/alertPolicies/123"


class EnsureMonitoringMetricAlertPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[list[str]] = []
        self.create_attempts = 0

    def runner(self, args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if args[1:3] == ["monitoring", "policies"] and "list" in args:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["monitoring", "policies"] and "create" in args:
            self.create_attempts += 1
            if self.create_attempts == 1:
                message = (
                    f'ERROR: Cannot find metric(s) that match type = "{METRIC_TYPE}". '
                    "If a metric was created recently, it could take up to 10 minutes to become available."
                )
                return subprocess.CompletedProcess(args, 1, "", message)
            return subprocess.CompletedProcess(args, 0, POLICY_NAME + "\n", "")
        self.fail(f"unexpected gcloud command: {args}")
        raise AssertionError("unreachable")

    def test_retries_only_metric_propagation_then_creates_policy(self) -> None:
        sleeps: list[float] = []
        policy = ensure_policy(
            project=PROJECT,
            display_name=DISPLAY_NAME,
            metric_type=METRIC_TYPE,
            condition_display_name=DISPLAY_NAME,
            condition_filter=f'metric.type="{METRIC_TYPE}" AND resource.type="cloud_scheduler_job"',
            duration="0s",
            comparison="> 0",
            combiner="OR",
            notification_channels="projects/based-hardware/notificationChannels/1",
            documentation="Scheduler execution failures",
            runner=self.runner,
            sleep=sleeps.append,
            retry_interval_seconds=30,
            max_attempts=3,
        )

        self.assertEqual(policy, POLICY_NAME)
        self.assertEqual(self.create_attempts, 2)
        self.assertEqual(sleeps, [30])

    def test_existing_policy_is_returned_without_recreation(self) -> None:
        def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.calls.append(args)
            if "list" in args:
                return subprocess.CompletedProcess(args, 0, POLICY_NAME + "\n", "")
            self.fail("existing policy must not be overwritten")
            raise AssertionError("unreachable")

        policy = ensure_policy(
            project=PROJECT,
            display_name=DISPLAY_NAME,
            metric_type=METRIC_TYPE,
            condition_display_name=DISPLAY_NAME,
            condition_filter="filter",
            duration="0s",
            comparison="> 0",
            combiner="OR",
            notification_channels="channel",
            documentation="docs",
            runner=runner,
        )
        self.assertEqual(policy, POLICY_NAME)
        self.assertEqual(len(self.calls), 1)

    def test_non_propagation_create_error_fails_without_retry(self) -> None:
        def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.calls.append(args)
            if "list" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            return subprocess.CompletedProcess(args, 1, "", "PERMISSION_DENIED")

        with self.assertRaisesRegex(RuntimeError, "PERMISSION_DENIED"):
            ensure_policy(
                project=PROJECT,
                display_name=DISPLAY_NAME,
                metric_type=METRIC_TYPE,
                condition_display_name=DISPLAY_NAME,
                condition_filter="filter",
                duration="0s",
                comparison="> 0",
                combiner="OR",
                notification_channels="channel",
                documentation="docs",
                runner=runner,
                sleep=lambda _: self.fail("permanent errors must not sleep"),
                max_attempts=3,
            )
        self.assertEqual(sum("create" in call for call in self.calls), 1)


if __name__ == "__main__":
    unittest.main()
