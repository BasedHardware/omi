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
import os
import sys

from dispatch_mobile_daily_train import BUILDS_API, DispatchError, _api_post

WORKFLOW_ID = "mobile-rollout-advance"


def build_payload(app_id: str, *, dry_run: bool, branch: str = "main") -> dict:
    """Codemagic drops the whole variables object on an empty string, so every value is non-empty."""
    if not app_id:
        raise DispatchError("Codemagic app id is required")
    return {
        "appId": app_id,
        "workflowId": WORKFLOW_ID,
        "branch": branch,
        "environment": {"variables": {"TRAIN_ADVANCE_ROLLOUTS": "true", "TRAIN_DRY_RUN": "true" if dry_run else "false"}},
    }


def dispatch(app_id: str, token: str, *, dry_run: bool) -> str:
    response = _api_post(BUILDS_API, token, build_payload(app_id, dry_run=dry_run))
    build_id = response.get("buildId")
    if not isinstance(build_id, str) or not build_id:
        raise DispatchError(f"Codemagic did not return a buildId: {response}")
    return build_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--dry-run", choices=("true", "false"), default="false")
    args = parser.parse_args(argv)
    token = os.environ.get("CODEMAGIC_API_TOKEN", "")
    if not token:
        print("CODEMAGIC_API_TOKEN is required", file=sys.stderr)
        return 1
    try:
        build_id = dispatch(args.app_id, token, dry_run=args.dry_run == "true")
    except DispatchError as error:
        print(f"dispatch failed: {error}", file=sys.stderr)
        return 1
    print(f"mobile-rollout-advance dry_run={args.dry_run} build={build_id}")
    print(f"https://codemagic.io/app/{args.app_id}/build/{build_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
