#!/usr/bin/env python3
"""Ensure the backend-wide Firestore missing-index metric and alert exist."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

Runner = Callable[..., subprocess.CompletedProcess[str]]
METRIC = "firestore_missing_index_errors"
GKE_METRIC = "firestore_missing_index_errors_gke"
METRIC_TYPES = (
    f"logging.googleapis.com/user/{METRIC}",
    f"logging.googleapis.com/user/{GKE_METRIC}",
)
DISPLAY_NAME = "Firestore query requires a missing index"
CONDITION_FILTERS = {
    "Cloud Run": f'metric.type="{METRIC_TYPES[0]}" AND resource.type="cloud_run_revision"',
    "GKE": f'metric.type="{METRIC_TYPES[1]}" AND resource.type="k8s_container"',
}
ALIGNMENT = "300s"
ALIGNER = "ALIGN_SUM"
DOCUMENTATION_URL = "https://github.com/BasedHardware/omi/blob/main/backend/docs/runbooks/firestore-missing-index.md"
DOCUMENTATION = (
    "A Cloud Run service or GKE container in based-hardware logged a Firestore query that requires an index. "
    f"Follow the runbook: {DOCUMENTATION_URL}"
)
SCRIPT_DIR = Path(__file__).resolve().parent
METRIC_CONFIGS = {
    METRIC: SCRIPT_DIR.parent / "monitoring" / "firestore_missing_index_errors_metric.json",
    GKE_METRIC: SCRIPT_DIR.parent / "monitoring" / "firestore_missing_index_errors_gke_metric.json",
}


def _run(runner: Runner, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return runner(["gcloud", *args], text=True, capture_output=True, check=False)


def _notification_channels(value: str) -> list[str]:
    channels = [channel.strip() for channel in value.split(",")]
    if not channels or any(not channel for channel in channels):
        raise ValueError("notification channels must be a comma-separated list without empty entries")
    if len(channels) != len(set(channels)):
        raise ValueError("notification channels must not contain duplicates")
    return channels


def _ensure_metric(*, name: str, config: Path, project: str, runner: Runner) -> None:
    described = _run(runner, ["logging", "metrics", "describe", name, f"--project={project}"])
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
            name,
            f"--project={project}",
            f"--config-from-file={config}",
        ],
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"failed to {operation} Cloud Logging metric")


def _policy_config(channels: list[str]) -> dict[str, object]:
    conditions = []
    for name, condition_filter in CONDITION_FILTERS.items():
        conditions.append(
            {
                "displayName": f"{DISPLAY_NAME} ({name})",
                "conditionThreshold": {
                    "filter": condition_filter,
                    "comparison": "COMPARISON_GT",
                    "thresholdValue": 0,
                    "duration": "0s",
                    "aggregations": [{"alignmentPeriod": ALIGNMENT, "perSeriesAligner": ALIGNER}],
                    "trigger": {"count": 1},
                },
            }
        )
    return {
        "displayName": DISPLAY_NAME,
        "documentation": {"content": DOCUMENTATION, "mimeType": "text/markdown"},
        "enabled": True,
        "combiner": "OR",
        "notificationChannels": channels,
        "conditions": conditions,
    }


def _verify_policy(policy: dict[str, object], channels: list[str]) -> None:
    conditions = policy.get("conditions")
    if not isinstance(conditions, list) or len(conditions) != len(CONDITION_FILTERS):
        raise RuntimeError("Monitoring policy must have exactly two conditions")
    by_filter = {}
    for condition in conditions:
        if not isinstance(condition, dict):
            raise RuntimeError("Monitoring policy condition must be an object")
        threshold = condition.get("conditionThreshold")
        if not isinstance(threshold, dict):
            raise RuntimeError("Monitoring policy condition must be a threshold")
        by_filter[threshold.get("filter")] = (condition, threshold)

    errors: list[str] = []
    for name, expected_filter in CONDITION_FILTERS.items():
        entry = by_filter.get(expected_filter)
        if entry is None:
            errors.append(f"{name} condition filter")
            continue
        condition, threshold = entry
        actual_aggregation = threshold.get("aggregations") or []
        aggregation = actual_aggregation[0] if isinstance(actual_aggregation, list) and actual_aggregation else {}
        trigger = threshold.get("trigger") or {}
        # Proto3 omits zero-valued scalar defaults from describe output; these zero defaults are not drift.
        actual_threshold = threshold.get("thresholdValue", 0)
        actual_trigger_count = trigger.get("count") if isinstance(trigger, dict) else None
        checks = (
            (condition.get("displayName") == f"{DISPLAY_NAME} ({name})", f"{name} condition display name"),
            (threshold.get("duration", "0s") == "0s", f"{name} condition duration"),
            (threshold.get("comparison") == "COMPARISON_GT", f"{name} condition comparison"),
            (
                isinstance(actual_threshold, (int, float))
                and not isinstance(actual_threshold, bool)
                and actual_threshold == 0,
                f"{name} condition threshold",
            ),
            (isinstance(aggregation, dict) and aggregation.get("alignmentPeriod") == ALIGNMENT, f"{name} alignment"),
            (isinstance(aggregation, dict) and aggregation.get("perSeriesAligner") == ALIGNER, f"{name} aligner"),
            (
                isinstance(actual_trigger_count, int)
                and not isinstance(actual_trigger_count, bool)
                and actual_trigger_count == 1,
                f"{name} trigger count",
            ),
        )
        errors.extend(label for matches, label in checks if not matches)

    policy_checks = (
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
    errors.extend(label for matches, label in policy_checks if not matches)
    if errors:
        raise RuntimeError("Monitoring policy drift: " + ", ".join(errors))


def _is_metric_propagation_error(error: str) -> bool:
    """A policy that names a log metric created moments ago is rejected until the metric is visible."""
    return any(
        "Cannot find metric(s) that match type" in error and metric_type in error and "created recently" in error
        for metric_type in METRIC_TYPES
    )


def _ensure_policy(*, project: str, channels: list[str], runner: Runner) -> str:
    config = _policy_config(channels)
    config_json = json.dumps(config, separators=(",", ":"))
    for attempt in range(21):
        listed = _run(
            runner,
            [
                "monitoring",
                "policies",
                "list",
                f"--project={project}",
                f'--filter=displayName="{DISPLAY_NAME}"',
                "--format=value(name)",
            ],
        )
        if listed.returncode:
            raise RuntimeError(listed.stderr.strip() or "failed to list Monitoring policies")
        policies = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
        if len(policies) > 1:
            raise RuntimeError(f"Duplicate {DISPLAY_NAME} alert policies; reconcile manually")
        if policies:
            return policies[0]
        created = _run(
            runner,
            [
                "monitoring",
                "policies",
                "create",
                f"--project={project}",
                f"--policy={config_json}",
                "--format=value(name)",
            ],
        )
        if created.returncode == 0 and created.stdout.strip():
            return created.stdout.strip()
        error = (created.stderr or created.stdout).strip()
        if not _is_metric_propagation_error(error) or attempt == 20:
            raise RuntimeError(error or "failed to create Monitoring policy")
        print(f"Waiting for Cloud Monitoring metric visibility (attempt {attempt + 1}/21)", file=sys.stderr)
        time.sleep(30)
    raise RuntimeError("unreachable Monitoring policy creation state")


def ensure_alert(*, project: str, notification_channels: str, runner: Runner = subprocess.run) -> str:
    """Create or update the metric and policy, then verify the stored policy."""
    if not project.strip():
        raise ValueError("project must not be empty")
    channels = _notification_channels(notification_channels)
    for name, config in METRIC_CONFIGS.items():
        _ensure_metric(name=name, config=config, project=project, runner=runner)
    policy = _ensure_policy(project=project, channels=channels, runner=runner)
    # The update path needs the same wait as creation: an existing policy gains a condition on a metric
    # that this run may have created seconds ago.
    for attempt in range(21):
        updated = _run(
            runner,
            [
                "monitoring",
                "policies",
                "update",
                policy,
                f"--project={project}",
                "--quiet",
                f"--policy={json.dumps(_policy_config(channels), separators=(',', ':'))}",
            ],
        )
        if not updated.returncode:
            break
        error = (updated.stderr or updated.stdout).strip()
        if not _is_metric_propagation_error(error) or attempt == 20:
            raise RuntimeError(error or "failed to update Monitoring policy")
        print(f"Waiting for Cloud Monitoring metric visibility (attempt {attempt + 1}/21)", file=sys.stderr)
        time.sleep(30)

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
