#!/usr/bin/env python3
"""Ensure the backend-wide Firestore missing-index metric and alert exist."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from ensure_monitoring_metric_alert_policy import ensure_policy

Runner = Callable[..., subprocess.CompletedProcess[str]]
METRIC = "firestore_missing_index_errors"
METRIC_TYPE = f"logging.googleapis.com/user/{METRIC}"
DISPLAY_NAME = "Firestore query requires a missing index"
CONDITION_FILTER = f'metric.type="{METRIC_TYPE}" AND resource.type="cloud_run_revision"'
ALIGNMENT = "300s"
ALIGNER = "ALIGN_SUM"
DOCUMENTATION_URL = "https://github.com/BasedHardware/omi/blob/main/backend/docs/runbooks/firestore-missing-index.md"
DOCUMENTATION = (
    "A Cloud Run service in based-hardware logged a Firestore query that requires an index. "
    f"Follow the runbook: {DOCUMENTATION_URL}"
)
METRIC_CONFIG = Path(__file__).resolve().parents[1] / "monitoring" / "firestore_missing_index_errors_metric.json"


def _run(runner: Runner, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return runner(["gcloud", *args], text=True, capture_output=True, check=False)


def _notification_channels(value: str) -> list[str]:
    channels = [channel.strip() for channel in value.split(",")]
    if not channels or any(not channel for channel in channels):
        raise ValueError("notification channels must be a comma-separated list without empty entries")
    if len(channels) != len(set(channels)):
        raise ValueError("notification channels must not contain duplicates")
    return channels


def _ensure_metric(*, project: str, runner: Runner) -> None:
    described = _run(runner, ["logging", "metrics", "describe", METRIC, f"--project={project}"])
    if described.returncode:
        error = (described.stderr or described.stdout).strip()
        if "not found" not in error.lower() and "not_found" not in error.lower():
            raise RuntimeError(error or "failed to describe Cloud Logging metric")
        operation = "create"
    else:
        operation = "update"

    result = _run(
        runner,
        [
            "logging",
            "metrics",
            operation,
            METRIC,
            f"--project={project}",
            f"--config-from-file={METRIC_CONFIG}",
        ],
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"failed to {operation} Cloud Logging metric")


def _verify_policy(policy: dict[str, object], channels: list[str]) -> None:
    conditions = policy.get("conditions")
    if not isinstance(conditions, list) or len(conditions) != 1 or not isinstance(conditions[0], dict):
        raise RuntimeError("Monitoring policy must have exactly one condition")
    condition = conditions[0]
    threshold = condition.get("conditionThreshold")
    if not isinstance(threshold, dict):
        raise RuntimeError("Monitoring policy condition must be a threshold")

    actual_aggregation = threshold.get("aggregations") or []
    aggregation = actual_aggregation[0] if isinstance(actual_aggregation, list) and actual_aggregation else {}
    trigger = threshold.get("trigger") or {}
    actual_threshold = threshold.get("thresholdValue")
    actual_trigger_count = trigger.get("count") if isinstance(trigger, dict) else None
    checks = (
        (condition.get("displayName") == DISPLAY_NAME, "condition display name"),
        (threshold.get("filter") == CONDITION_FILTER, "condition filter"),
        (threshold.get("duration", "0s") == "0s", "condition duration"),
        (threshold.get("comparison") == "COMPARISON_GT", "condition comparison"),
        (
            isinstance(actual_threshold, (int, float))
            and not isinstance(actual_threshold, bool)
            and actual_threshold == 0,
            "condition threshold",
        ),
        (isinstance(aggregation, dict) and aggregation.get("alignmentPeriod") == ALIGNMENT, "alignment period"),
        (isinstance(aggregation, dict) and aggregation.get("perSeriesAligner") == ALIGNER, "per-series aligner"),
        (
            isinstance(actual_trigger_count, int)
            and not isinstance(actual_trigger_count, bool)
            and actual_trigger_count == 1,
            "trigger count",
        ),
        (policy.get("displayName") == DISPLAY_NAME, "policy display name"),
        (policy.get("combiner") == "OR", "policy combiner"),
        (policy.get("enabled") is True, "enabled state"),
        (
            isinstance(policy.get("notificationChannels"), list)
            and sorted(policy["notificationChannels"]) == sorted(channels),
            "notification channels",
        ),
        (DOCUMENTATION_URL in str(policy.get("documentation", "")), "runbook documentation"),
    )
    errors = [label for matches, label in checks if not matches]
    if errors:
        raise RuntimeError("Monitoring policy drift: " + ", ".join(errors))


def ensure_alert(*, project: str, notification_channels: str, runner: Runner = subprocess.run) -> str:
    """Create or update the metric and policy, then verify the stored policy."""
    if not project.strip():
        raise ValueError("project must not be empty")
    channels = _notification_channels(notification_channels)
    _ensure_metric(project=project, runner=runner)
    policy = ensure_policy(
        project=project,
        display_name=DISPLAY_NAME,
        metric_type=METRIC_TYPE,
        condition_display_name=DISPLAY_NAME,
        condition_filter=CONDITION_FILTER,
        duration="0s",
        comparison="> 0",
        combiner="OR",
        notification_channels=",".join(channels),
        documentation=DOCUMENTATION,
        aggregation=json.dumps({"alignmentPeriod": ALIGNMENT, "perSeriesAligner": ALIGNER}, separators=(",", ":")),
        trigger_count=1,
        runner=runner,
        sleep=lambda _: None,
    )
    updated = _run(
        runner,
        [
            "monitoring",
            "policies",
            "update",
            policy,
            f"--project={project}",
            "--quiet",
            "--enabled",
            f"--set-notification-channels={','.join(channels)}",
            f"--documentation={DOCUMENTATION}",
        ],
    )
    if updated.returncode:
        raise RuntimeError((updated.stderr or updated.stdout).strip() or "failed to update Monitoring policy")

    described = _run(runner, ["monitoring", "policies", "describe", policy, f"--project={project}", "--format=json"])
    if described.returncode:
        raise RuntimeError((described.stderr or described.stdout).strip() or "failed to describe Monitoring policy")
    try:
        payload = json.loads(described.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Monitoring policy describe returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Monitoring policy describe returned a non-object")
    _verify_policy(payload, channels)
    return policy


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--notification-channels", required=True)
    args = parser.parse_args(argv)
    try:
        print(ensure_alert(project=args.project, notification_channels=args.notification_channels))
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
