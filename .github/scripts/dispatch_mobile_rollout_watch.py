#!/usr/bin/env python3
"""Start one Codemagic `mobile-rollout-advance` run on main.

Codemagic schedules exist only in its UI, so the intraday exposure ladder is
advanced through the GitHub cron in .github/workflows/mobile_rollout_watch.yml,
which dispatches this every ~4 hours between the operator gate's daily train
runs. The advance mode of app/scripts/mobile_daily_train.py (TRAIN_ADVANCE_
ROLLOUTS=true) never submits or stages a candidate: it only moves the already-
released rollouts along the ladder — the iOS phased rollout jumps to 100% after
its 12-hour observation window (never while PAUSED in App Store Connect), the
Android staged rollout takes its next hop (1% -> 10% -> 50% -> 100%) after its
4-hour window.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from dispatch_mobile_daily_train import BUILDS_API, DispatchError, _api_post

WORKFLOW_ID = "mobile-rollout-advance"
# Clock-driven advancement must stop when the daily health gate goes RED or dies;
# allow the daily GREEN gate receipt two hours of scheduling slack.
GATE_RECEIPT_MAX_AGE = timedelta(hours=26)


def latest_gate_receipt() -> datetime | None:
    repository = os.environ.get("GITHUB_REPOSITORY", "BasedHardware/omi")
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                "--method",
                "GET",
                f"repos/{repository}/actions/workflows/mobile_daily_train.yml/runs",
                "-f",
                "branch=main",
                "-f",
                "status=success",
                "-f",
                "per_page=1",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise DispatchError("GitHub daily gate receipt lookup failed") from error
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise DispatchError("GitHub daily gate receipt response is malformed")
    if not runs:
        return None
    run = runs[0]
    if not isinstance(run, dict) or run.get("head_branch") != "main" or run.get("conclusion") != "success":
        raise DispatchError("GitHub daily gate receipt is not a successful main run")
    try:
        created_at = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, TypeError, ValueError) as error:
        raise DispatchError("GitHub daily gate receipt created_at is malformed") from error
    if created_at.tzinfo is None:
        raise DispatchError("GitHub daily gate receipt created_at has no timezone")
    return created_at


def build_payload(app_id: str, *, dry_run: bool, branch: str = "main", capture_health_override: str = "") -> dict:
    """Codemagic drops the whole variables object on an empty string, so every value is non-empty."""
    if not app_id:
        raise DispatchError("Codemagic app id is required")
    variables = {"TRAIN_ADVANCE_ROLLOUTS": "true", "TRAIN_DRY_RUN": "true" if dry_run else "false"}
    if capture_health_override.strip():
        # One-shot: lets this run's hops past a capture-health HOLD, with the reason in the log.
        variables["TRAIN_CAPTURE_HEALTH_OVERRIDE"] = capture_health_override.strip()
    return {
        "appId": app_id,
        "workflowId": WORKFLOW_ID,
        "branch": branch,
        "environment": {"variables": variables},
    }


def dispatch(app_id: str, token: str, *, dry_run: bool, capture_health_override: str = "") -> str:
    response = _api_post(
        BUILDS_API, token, build_payload(app_id, dry_run=dry_run, capture_health_override=capture_health_override)
    )
    build_id = response.get("buildId")
    if not isinstance(build_id, str) or not build_id:
        raise DispatchError(f"Codemagic did not return a buildId: {response}")
    return build_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--dry-run", choices=("true", "false"), default="false")
    parser.add_argument(
        "--capture-health-override",
        default="",
        help="reason to advance past a capture-health HOLD for this run only (empty = no override)",
    )
    args = parser.parse_args(argv)
    try:
        receipt = latest_gate_receipt()
        if receipt is None or not timedelta(0) <= datetime.now(timezone.utc) - receipt <= GATE_RECEIPT_MAX_AGE:
            last = receipt.isoformat() if receipt is not None else "never"
            reason = f"LADDER FROZEN: no successful mobile_daily_train run in the last 26h (last: {last})"
            print(reason)
            if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
                with open(summary, "a", encoding="utf-8") as output:
                    output.write(reason + "\n")
            return 0
        token = os.environ.get("CODEMAGIC_API_TOKEN", "")
        if not token:
            print("CODEMAGIC_API_TOKEN is required", file=sys.stderr)
            return 1
        build_id = dispatch(
            args.app_id, token, dry_run=args.dry_run == "true", capture_health_override=args.capture_health_override
        )
    except DispatchError as error:
        print(f"dispatch failed: {error}", file=sys.stderr)
        return 1
    print(f"mobile-rollout-advance dry_run={args.dry_run} build={build_id}")
    print(f"https://codemagic.io/app/{args.app_id}/build/{build_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
