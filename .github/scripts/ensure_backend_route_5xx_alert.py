#!/usr/bin/env python3
"""Ensure the backend route-family 5xx metric and alert policy exist.

The log-based metric counts Cloud Run platform request-log entries with
httpRequest.status in [500, 600) for the `backend` service and labels each
series with (method, route). Route is a generic path family: an optional
version plus up to three complete lowercase path segments, stopping at the
first segment that does not match. Any matching non-empty family can page;
there is no fixed route list.

Metric and policy bodies are immutable configuration under
.github/monitoring/; this script only loads, provisions, and verifies them.
Both resources reconcile read-before-write: an existing metric is updated
only when its filter or label extractors differ, and an existing policy is
updated only when its managed fields drift — carrying over the existing
condition's resource name so unchanged deploys do not restart the dwell.
Policy creation reuses ensure_monitoring_metric_alert_policy.ensure_policy
so the documented metric-propagation retry stays in one place.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from ensure_firestore_missing_index_alert import _notification_channels
from ensure_monitoring_metric_alert_policy import ensure_policy

Runner = Callable[..., subprocess.CompletedProcess[str]]
METRIC = "backend_route_5xx"
METRIC_TYPE = f"logging.googleapis.com/user/{METRIC}"
SCRIPT_DIR = Path(__file__).resolve().parent
METRIC_CONFIG = SCRIPT_DIR.parent / "monitoring" / "backend_route_5xx_metric.json"
POLICY_CONFIG = SCRIPT_DIR.parent / "monitoring" / "backend_route_5xx_policy.json"
COMPARISON_OPERATORS = {"COMPARISON_GT": ">"}
GROUP_BY_FIELDS = (
    "metric.label.method",
    "metric.label.route",
)


def _run(runner: Runner, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return runner(["gcloud", *args], text=True, capture_output=True, check=False)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _condition(policy_body: dict[str, object]) -> dict[str, object]:
    conditions = policy_body.get("conditions")
    if not isinstance(conditions, list) or len(conditions) != 1:
        raise ValueError(f"{POLICY_CONFIG.name} must declare exactly one condition")
    condition = conditions[0]
    if not isinstance(condition, dict) or not isinstance(condition.get("conditionThreshold"), dict):
        raise ValueError(f"{POLICY_CONFIG.name} condition must be a threshold")
    return condition


def _comparison(threshold: dict[str, object]) -> str:
    operator = COMPARISON_OPERATORS.get(str(threshold.get("comparison")))
    if operator is None:
        raise ValueError(f"unsupported comparison {threshold.get('comparison')!r} in {POLICY_CONFIG.name}")
    return f"{operator} {threshold['thresholdValue']}"


def _aggregation(threshold: dict[str, object]) -> str:
    aggregations = threshold.get("aggregations")
    if not isinstance(aggregations, list) or len(aggregations) != 1:
        raise ValueError(f"{POLICY_CONFIG.name} must declare exactly one aggregation")
    return json.dumps(aggregations[0], separators=(",", ":"))


def _parse_described(described: subprocess.CompletedProcess[str], resource: str) -> dict[str, object]:
    try:
        payload = json.loads(described.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{resource} describe returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{resource} describe returned a non-object")
    return payload


def _ensure_metric(*, name: str, config: Path, project: str, runner: Runner) -> None:
    desired = _load_json(config)
    described = _run(runner, ["logging", "metrics", "describe", name, f"--project={project}", "--format=json"])
    if described.returncode:
        error = (described.stderr or described.stdout).strip()
        if "not found" not in error.lower() and "not_found" not in error.lower():
            raise RuntimeError(error or "failed to describe Cloud Logging metric")
        operation = "create"
    else:
        existing = _parse_described(described, "Cloud Logging metric")
        if existing.get("filter") == desired.get("filter") and (existing.get("labelExtractors") or {}) == (
            desired.get("labelExtractors") or {}
        ):
            return
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


def _is_metric_propagation_error(error: str) -> bool:
    """A policy naming a log metric created moments ago is rejected until it is visible."""
    return "Cannot find metric(s) that match type" in error and METRIC_TYPE in error and "created recently" in error


def _update_policy(
    *,
    project: str,
    policy: str,
    body: dict[str, object],
    runner: Runner,
    sleep: Callable[[float], None],
) -> None:
    policy_json = json.dumps(body, separators=(",", ":"))
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
                f"--policy={policy_json}",
            ],
        )
        if not updated.returncode:
            return
        error = (updated.stderr or updated.stdout).strip()
        if not _is_metric_propagation_error(error) or attempt == 20:
            raise RuntimeError(error or "failed to update Monitoring policy")
        print(f"Waiting for Cloud Monitoring metric visibility (attempt {attempt + 1}/21)", file=sys.stderr)
        sleep(30)
    raise RuntimeError("unreachable Monitoring policy update state")


def _describe_policy(*, policy: str, project: str, runner: Runner) -> dict[str, object]:
    described = _run(runner, ["monitoring", "policies", "describe", policy, f"--project={project}", "--format=json"])
    if described.returncode:
        raise RuntimeError((described.stderr or described.stdout).strip() or "failed to describe Monitoring policy")
    return _parse_described(described, "Monitoring policy")


def _sole_condition_name(policy: dict[str, object]) -> str:
    conditions = policy.get("conditions")
    if not isinstance(conditions, list) or len(conditions) != 1 or not isinstance(conditions[0], dict):
        raise RuntimeError("existing Monitoring policy must have exactly one condition to update")
    name = conditions[0].get("name")
    if not isinstance(name, str) or not name:
        raise RuntimeError("existing Monitoring policy condition has no resource name to preserve")
    return name


def _policy_drift(policy: dict[str, object], body: dict[str, object], channels: list[str]) -> list[str]:
    condition = _condition(body)
    expected_threshold = condition["conditionThreshold"]
    errors: list[str] = []

    conditions = policy.get("conditions")
    if not isinstance(conditions, list) or len(conditions) != 1 or not isinstance(conditions[0], dict):
        errors.append("exactly one condition")
        actual_condition: dict[str, object] = {}
        actual_threshold: dict[str, object] = {}
    else:
        actual_condition = conditions[0]
        threshold = actual_condition.get("conditionThreshold")
        actual_threshold = threshold if isinstance(threshold, dict) else {}

    trigger = actual_threshold.get("trigger")
    actual_trigger_count = trigger.get("count") if isinstance(trigger, dict) else None
    expected_documentation = body["documentation"]
    documentation = policy.get("documentation")
    actual_doc_content = documentation.get("content") if isinstance(documentation, dict) else None
    actual_doc_mime = documentation.get("mimeType") if isinstance(documentation, dict) else None
    actual_channels = policy.get("notificationChannels")

    checks = (
        (policy.get("displayName") == body["displayName"], "policy display name"),
        (policy.get("combiner") == body["combiner"], "combiner"),
        (policy.get("enabled") == body["enabled"], "enabled state"),
        (
            isinstance(actual_channels, list) and sorted(actual_channels) == sorted(channels),
            "notification channels",
        ),
        (actual_doc_content == expected_documentation["content"], "documentation content"),
        (actual_doc_mime == expected_documentation.get("mimeType"), "documentation MIME type"),
        (actual_condition.get("displayName") == condition["displayName"], "condition display name"),
        (actual_threshold.get("filter") == expected_threshold["filter"], "condition filter"),
        (actual_threshold.get("comparison") == expected_threshold["comparison"], "comparison"),
        (actual_threshold.get("thresholdValue") == expected_threshold["thresholdValue"], "threshold value"),
        (actual_threshold.get("duration") == expected_threshold["duration"], "duration"),
        (actual_trigger_count == expected_threshold["trigger"]["count"], "trigger count"),
    )
    errors.extend(label for matches, label in checks if not matches)

    expected_aggregation = expected_threshold["aggregations"][0]
    actual_aggregations = actual_threshold.get("aggregations")
    if (
        not isinstance(actual_aggregations, list)
        or len(actual_aggregations) != 1
        or not isinstance(actual_aggregations[0], dict)
    ):
        errors.append("exactly one aggregation")
    else:
        actual_aggregation = actual_aggregations[0]
        for key, expected_value in expected_aggregation.items():
            actual_value = actual_aggregation.get(key)
            if key == "groupByFields":
                if not isinstance(actual_value, list) or sorted(actual_value) != sorted(expected_value):
                    errors.append("group-by fields")
            elif actual_value != expected_value:
                errors.append(f"aggregation {key}")

    return errors


def _verify_policy(policy: dict[str, object], body: dict[str, object], channels: list[str]) -> None:
    """Compare managed fields; describe output may add names and output-only fields."""
    errors = _policy_drift(policy, body, channels)
    if errors:
        raise RuntimeError("Monitoring policy drift: " + ", ".join(errors))


def ensure_alert(
    *,
    project: str,
    notification_channels: str,
    runner: Runner = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Reconcile the metric and policy read-before-write, preserving the condition name."""
    if not project.strip():
        raise ValueError("project must not be empty")
    channels = _notification_channels(notification_channels)
    body = _load_json(POLICY_CONFIG)
    body["notificationChannels"] = channels
    condition = _condition(body)
    threshold = condition["conditionThreshold"]

    _ensure_metric(name=METRIC, config=METRIC_CONFIG, project=project, runner=runner)
    policy = ensure_policy(
        project=project,
        display_name=str(body["displayName"]),
        metric_type=METRIC_TYPE,
        condition_display_name=str(condition["displayName"]),
        condition_filter=str(threshold["filter"]),
        duration=str(threshold["duration"]),
        comparison=_comparison(threshold),
        combiner=str(body["combiner"]),
        notification_channels=",".join(channels),
        documentation=str(body["documentation"]["content"]),
        aggregation=_aggregation(threshold),
        trigger_count=int(threshold["trigger"]["count"]),
        runner=runner,
        sleep=sleep,
    )

    existing = _describe_policy(policy=policy, project=project, runner=runner)
    if not _policy_drift(existing, body, channels):
        return policy

    condition_name = _sole_condition_name(existing)
    condition["name"] = condition_name
    _update_policy(project=project, policy=policy, body=body, runner=runner, sleep=sleep)

    updated = _describe_policy(policy=policy, project=project, runner=runner)
    _verify_policy(updated, body, channels)
    updated_conditions = updated.get("conditions")
    surviving_name = (
        updated_conditions[0].get("name")
        if isinstance(updated_conditions, list) and len(updated_conditions) == 1
        else None
    )
    if surviving_name != condition_name:
        raise RuntimeError("Monitoring policy condition resource name changed across update")
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
