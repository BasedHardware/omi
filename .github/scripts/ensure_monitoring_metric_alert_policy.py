#!/usr/bin/env python3
"""Create a Monitoring alert policy after its log-based metric is queryable.

Cloud Logging metrics can take several minutes to appear in Cloud Monitoring.
Retry only that documented propagation error; all other policy errors fail
immediately. Rechecking the display name before each retry avoids creating a
duplicate if a prior create succeeded but its response was lost.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run_gcloud(runner: Runner, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return runner(["gcloud", *args], text=True, capture_output=True, check=False)


def ensure_policy(
    *,
    project: str,
    display_name: str,
    metric_type: str,
    condition_display_name: str,
    condition_filter: str,
    duration: str,
    comparison: str,
    combiner: str,
    notification_channels: str,
    documentation: str,
    aggregation: str | None = None,
    trigger_count: int | None = None,
    runner: Runner = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    retry_interval_seconds: int = 30,
    max_attempts: int = 21,
) -> str:
    """Return the unique matching policy name, creating it when absent."""
    create_args = [
        "monitoring",
        "policies",
        "create",
        f"--project={project}",
        f"--display-name={display_name}",
        f"--condition-display-name={condition_display_name}",
        f"--condition-filter={condition_filter}",
        f"--duration={duration}",
        f"--if={comparison}",
        f"--combiner={combiner}",
        f"--notification-channels={notification_channels}",
        f"--documentation={documentation}",
        "--format=value(name)",
    ]
    if aggregation is not None:
        create_args.append(f"--aggregation={aggregation}")
    if trigger_count is not None:
        create_args.append(f"--trigger-count={trigger_count}")

    for attempt in range(1, max_attempts + 1):
        listed = _run_gcloud(
            runner,
            [
                "monitoring",
                "policies",
                "list",
                f"--project={project}",
                f'--filter=displayName="{display_name}"',
                "--format=value(name)",
            ],
        )
        if listed.returncode:
            raise RuntimeError(listed.stderr.strip() or "failed to list Monitoring policies")
        policies = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
        if len(policies) > 1:
            raise RuntimeError(f"Duplicate {display_name} alert policies; reconcile manually")
        if policies:
            return policies[0]

        created = _run_gcloud(runner, create_args)
        if created.returncode == 0:
            policy = created.stdout.strip()
            if policy:
                return policy
            # A successful create without a returned name is unusual. Re-list
            # on the next iteration so we never issue a blind duplicate create.
            if attempt < max_attempts:
                sleep(retry_interval_seconds)
                continue
            raise RuntimeError("Monitoring policy create succeeded without returning its name")

        error = created.stderr.strip() or created.stdout.strip()
        propagation_error = (
            "Cannot find metric(s) that match type" in error and metric_type in error and "created recently" in error
        )
        if not propagation_error or attempt == max_attempts:
            raise RuntimeError(error or "failed to create Monitoring policy")
        print(
            f"Waiting for Cloud Monitoring to expose {metric_type} " f"(attempt {attempt}/{max_attempts})",
            file=sys.stderr,
        )
        sleep(retry_interval_seconds)

    raise RuntimeError("unreachable policy creation state")



def ensure_json_policy(
    *,
    project: str,
    body: dict,
    runner: Runner = subprocess.run,
) -> str:
    """Reconcile a JSON policy, including ratio conditions, without resetting dwell.

    Built-in metrics need no log-metric propagation retry. Read-before-write and
    preserve existing condition resource names on updates. Ignore output-only and
    default fields returned by Monitoring, but verify every declared field.
    """
    desired = copy.deepcopy(body)
    display_name = desired["displayName"]
    desired_conditions = desired.get("conditions", [])
    if not (len(desired_conditions) == 1 or (len(desired_conditions) == 2 and desired.get("combiner") == "AND")):
        raise ValueError("JSON policy requires one condition or two conditions combined with AND")
    if any(not isinstance(c.get("conditionThreshold"), dict) for c in desired_conditions):
        raise ValueError("JSON policy conditions must be metric thresholds")
    if len({c["displayName"] for c in desired_conditions}) != len(desired_conditions):
        raise ValueError("JSON policy condition display names must be unique")

    def run(args):
        result = _run_gcloud(runner, ["monitoring", "policies", *args, f"--project={project}"])
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Monitoring policy operation failed")
        return result.stdout

    def managed(actual, expected):
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(managed(actual.get(k), v) for k, v in expected.items())
        if isinstance(expected, list):
            return isinstance(actual, list) and len(actual) == len(expected) and all(
                managed(a, e) for a, e in zip(actual, expected)
            )
        return actual == expected

    def matches(actual):
        candidate = copy.deepcopy(actual)
        candidate["notificationChannels"] = sorted(candidate.get("notificationChannels", []))
        conditions = candidate.get("conditions", [])
        if len(conditions) != len(desired_conditions):
            return False
        conditions.sort(key=lambda c: c.get("displayName", ""))
        expected = copy.deepcopy(desired)
        expected["conditions"].sort(key=lambda c: c["displayName"])
        for condition, expected_condition in zip(conditions, expected["conditions"]):
            threshold = condition.get("conditionThreshold")
            expected_threshold = expected_condition["conditionThreshold"]
            if not isinstance(threshold, dict):
                return False
            # A stale denominator or forecast changes semantics. Ignore only
            # absent/default optional API fields, for every condition.
            for key in ("denominatorFilter", "denominatorAggregations", "forecastOptions", "disableMetricValidation"):
                if key not in expected_threshold and threshold.get(key) in (None, "", [], {}, False):
                    threshold.pop(key, None)
            if threshold != expected_threshold:
                return False
        return managed(candidate, expected)

    desired["notificationChannels"] = sorted(desired["notificationChannels"])
    names = run(["list", f'--filter=displayName="{display_name}"', "--format=value(name)"]).split()
    if len(names) > 1:
        raise RuntimeError(f"Duplicate {display_name} alert policies; reconcile manually")
    preserved_names = {}
    if names:
        name = names[0]
        existing = json.loads(run(["describe", name, "--format=json"]))
        if matches(existing):
            return name
        conditions = existing.get("conditions", [])
        if not conditions or len(conditions) > len(desired_conditions) or any(not c.get("name") for c in conditions):
            raise RuntimeError("Existing JSON policy has an unexpected condition shape or unnamed conditions")
        by_display = {c["displayName"]: c["name"] for c in conditions}
        if len(by_display) != len(conditions) or len(set(by_display.values())) != len(conditions):
            raise RuntimeError("Existing JSON policy conditions must have unique names")
        used = set()
        for index, condition in enumerate(desired_conditions):
            # Display names identify conditions even if Monitoring reorders them.
            # For a display-name-only rename with unchanged cardinality, retain
            # the corresponding position rather than replace the condition.
            old_name = by_display.get(condition["displayName"])
            if old_name is None and len(conditions) == len(desired_conditions):
                old_name = conditions[index]["name"]
            if old_name is not None:
                if old_name in used:
                    raise RuntimeError("Ambiguous existing condition identity")
                condition["name"] = old_name
                used.add(old_name)
                preserved_names[condition["displayName"]] = old_name
        if len(used) != len(conditions):
            raise RuntimeError("Cannot preserve all existing condition identities")
        run(["update", name, "--quiet", f"--policy={json.dumps(desired)}"])
    else:
        # A lost create response fails this run; the next deploy re-lists before
        # attempting creation rather than issuing a blind retry.
        name = run(["create", f"--policy={json.dumps(desired)}", "--format=value(name)"]).strip()
        if not name:
            raise RuntimeError("Monitoring policy create returned no name")
    verified = json.loads(run(["describe", name, "--format=json"]))
    if not matches(verified):
        raise RuntimeError(f"Monitoring policy drift after reconciliation: {display_name}")
    verified_names = {c["displayName"]: c.get("name") for c in verified["conditions"]}
    if any(verified_names.get(display) != name for display, name in preserved_names.items()):
        raise RuntimeError("Monitoring condition name changed across update")
    return name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--metric-type", required=True)
    parser.add_argument("--condition-display-name", required=True)
    parser.add_argument("--condition-filter", required=True)
    parser.add_argument("--duration", required=True)
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--combiner", default="OR")
    parser.add_argument("--notification-channels", required=True)
    parser.add_argument("--documentation", required=True)
    parser.add_argument("--aggregation")
    parser.add_argument("--trigger-count", type=int)
    args = parser.parse_args()
    try:
        policy = ensure_policy(
            project=args.project,
            display_name=args.display_name,
            metric_type=args.metric_type,
            condition_display_name=args.condition_display_name,
            condition_filter=args.condition_filter,
            duration=args.duration,
            comparison=args.comparison,
            combiner=args.combiner,
            notification_channels=args.notification_channels,
            documentation=args.documentation,
            aggregation=args.aggregation,
            trigger_count=args.trigger_count,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(policy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
