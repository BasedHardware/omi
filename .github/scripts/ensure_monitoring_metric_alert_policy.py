#!/usr/bin/env python3
"""Create a Monitoring alert policy after its log-based metric is queryable.

Cloud Logging metrics can take several minutes to appear in Cloud Monitoring.
Retry only that documented propagation error; all other policy errors fail
immediately. Rechecking the display name before each retry avoids creating a
duplicate if a prior create succeeded but its response was lost.
"""

from __future__ import annotations

import argparse
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
            "Cannot find metric(s) that match type" in error
            and metric_type in error
            and "created recently" in error
        )
        if not propagation_error or attempt == max_attempts:
            raise RuntimeError(error or "failed to create Monitoring policy")
        print(
            f"Waiting for Cloud Monitoring to expose {metric_type} "
            f"(attempt {attempt}/{max_attempts})",
            file=sys.stderr,
        )
        sleep(retry_interval_seconds)

    raise RuntimeError("unreachable policy creation state")


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
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(policy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
