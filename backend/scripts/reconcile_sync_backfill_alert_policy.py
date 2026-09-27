#!/usr/bin/env python3
"""Repair only notification-channel drift on a managed sync-backfill alert."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Any

try:
    from scripts.verify_sync_backfill_alert_policy import check_policy
except ModuleNotFoundError:  # Direct execution from the backend/scripts directory.
    from verify_sync_backfill_alert_policy import check_policy


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run(runner: Runner, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return runner(["gcloud", *args], text=True, capture_output=True, check=False)


def reconcile_policy_channels(
    *,
    project: str,
    policy_name: str,
    display_name: str,
    condition: str,
    filter_text: str,
    duration_seconds: int,
    channels: list[str],
    runner: Runner = subprocess.run,
) -> bool:
    """Align channels when all other policy contract fields already match.

    Returns True if an update was required. It refuses to repair policies with
    condition, duration, enabled-state, or identity drift, preserving the
    strict release gate for any change outside the declared routing config.
    """
    if not channels or len(channels) != len(set(channels)):
        raise ValueError("expected distinct nonempty notification channels")

    def describe() -> dict[str, Any]:
        result = _run(
            runner,
            ["monitoring", "policies", "describe", policy_name, f"--project={project}", "--format=json"],
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "failed to describe Monitoring policy")
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Monitoring policy describe returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise RuntimeError("Monitoring policy describe returned a non-object")
        return value

    policy = describe()
    if policy.get("displayName") != display_name:
        raise RuntimeError("Monitoring policy identity differs")
    errors = check_policy(
        policy,
        condition=condition,
        filter_text=filter_text,
        duration_seconds=duration_seconds,
        channels=channels,
    )
    non_channel_errors = [error for error in errors if error != "notification channels differ"]
    if non_channel_errors:
        raise RuntimeError("Monitoring policy contract drift: " + "; ".join(non_channel_errors))
    if not errors:
        return False

    updated = _run(
        runner,
        [
            "monitoring",
            "policies",
            "update",
            policy_name,
            f"--project={project}",
            "--set-notification-channels=" + ",".join(channels),
            "--quiet",
        ],
    )
    if updated.returncode:
        raise RuntimeError(updated.stderr.strip() or "failed to update Monitoring policy channels")

    verified = describe()
    if verified.get("displayName") != display_name:
        raise RuntimeError("Monitoring policy identity changed during channel reconciliation")
    remaining = check_policy(
        verified,
        condition=condition,
        filter_text=filter_text,
        duration_seconds=duration_seconds,
        channels=channels,
    )
    if remaining:
        raise RuntimeError("Monitoring policy remains out of contract: " + "; ".join(remaining))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--condition", choices=("threshold", "absent"), required=True)
    parser.add_argument("--filter", required=True)
    parser.add_argument("--duration-seconds", type=int, required=True)
    parser.add_argument("--channels", required=True)
    args = parser.parse_args()
    channels = [item.strip() for item in args.channels.split(",") if item.strip()]
    if not channels or len(channels) != len(set(channels)):
        parser.error("expected distinct nonempty notification channels")
    try:
        changed = reconcile_policy_channels(
            project=args.project,
            policy_name=args.policy,
            display_name=args.display_name,
            condition=args.condition,
            filter_text=args.filter,
            duration_seconds=args.duration_seconds,
            channels=channels,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("Reconciled notification channels" if changed else "Notification channels already match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
