#!/usr/bin/env python3
"""Ensure the per-route backend 5xx metric and alert policy exist.

The log-based metric counts Cloud Run platform request-log entries with
httpRequest.status in [500, 600) for the `backend` service and labels each
series with a bounded (method, route, route_resource, route_action,
status_class) tuple. Route identity is method + route for static paths, or
method + route_resource + /{id}/ + route_action for the parameterised
reprocess route; unknown paths extract empty route labels and are excluded
by the alert condition. The initial catalogue covers the supplied
incident/chronic routes only.

Metric and policy bodies are immutable configuration under
.github/monitoring/; this script only loads, provisions, and verifies them.
Policy creation reuses ensure_monitoring_metric_alert_policy.ensure_policy
so the documented metric-propagation retry stays in one place; the stored
policy is then updated with the complete configured body and verified.
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
    "metric.label.route_resource",
    "metric.label.route_action",
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


def _verify_policy(policy: dict[str, object], body: dict[str, object], channels: list[str]) -> None:
    """Compare core fields; describe output may add names and output-only fields."""
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
    documentation = policy.get("documentation")
    actual_doc_content = documentation.get("content") if isinstance(documentation, dict) else ""
    actual_channels = policy.get("notificationChannels")

    checks = (
        (policy.get("displayName") == body["displayName"], "policy display name"),
        (policy.get("combiner") == body["combiner"], "combiner"),
        (policy.get("enabled") is True, "enabled state"),
        (
            isinstance(actual_channels, list) and sorted(actual_channels) == sorted(channels),
            "notification channels",
        ),
        (
            isinstance(actual_doc_content, str) and str(body["documentation"]["content"]) in actual_doc_content,
            "documentation",
        ),
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
    if not isinstance(actual_aggregations, list) or len(actual_aggregations) != 1:
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

    if errors:
        raise RuntimeError("Monitoring policy drift: " + ", ".join(errors))


def ensure_alert(
    *,
    project: str,
    notification_channels: str,
    runner: Runner = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Create or update the metric and policy, then verify the stored policy."""
    if not project.strip():
        raise ValueError("project must not be empty")
    channels = _notification_channels(notification_channels)
    body = _load_json(POLICY_CONFIG)
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

    body["notificationChannels"] = channels
    _update_policy(project=project, policy=policy, body=body, runner=runner, sleep=sleep)

    described = _run(runner, ["monitoring", "policies", "describe", policy, f"--project={project}", "--format=json"])
    if described.returncode:
        raise RuntimeError((described.stderr or described.stdout).strip() or "failed to describe Monitoring policy")
    try:
        payload = json.loads(described.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Monitoring policy describe returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Monitoring policy describe returned a non-object")
    _verify_policy(payload, body, channels)
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
