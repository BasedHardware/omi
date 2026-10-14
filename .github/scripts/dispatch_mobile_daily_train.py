#!/usr/bin/env python3
"""Start one Codemagic `mobile-daily-train` run on main.

Codemagic schedules exist only in its UI, so the GitHub cron in
.github/workflows/mobile_daily_train.yml dispatches the train through the builds API. The
train itself (app/scripts/mobile_daily_train.py) self-drives the release on store approval;
the operator release gate's audited candidates travel with the dispatch as optional
TRAIN_PIN_IOS / TRAIN_PIN_ANDROID pins (X.Y.Z/build) and the train fails closed if the
store no longer matches them.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from dispatch_mobile_internal_builds import BUILDS_API, DispatchError, _api_post

WORKFLOW_ID = "mobile-daily-train"


def build_payload(app_id: str, *, dry_run: bool, branch: str = "main", pin_ios: str = "", pin_android: str = "") -> dict[str, Any]:
    """Codemagic drops the whole variables object on an empty string, so every value is non-empty."""
    if not app_id:
        raise DispatchError("Codemagic app id is required")
    variables: dict[str, str] = {"TRAIN_DRY_RUN": "true" if dry_run else "false"}
    if pin_ios:
        variables["TRAIN_PIN_IOS"] = pin_ios
    if pin_android:
        variables["TRAIN_PIN_ANDROID"] = pin_android
    return {
        "appId": app_id,
        "workflowId": WORKFLOW_ID,
        "branch": branch,
        "environment": {"variables": variables},
    }


def dispatch(
    app_id: str, token: str, *, dry_run: bool, pin_ios: str = "", pin_android: str = ""
) -> str:
    response = _api_post(BUILDS_API, token, build_payload(app_id, dry_run=dry_run, pin_ios=pin_ios, pin_android=pin_android))
    build_id = response.get("buildId")
    if not isinstance(build_id, str) or not build_id:
        raise DispatchError(f"Codemagic did not return a buildId: {response}")
    return build_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--dry-run", choices=("true", "false"), default="false")
    parser.add_argument(
        "--pin-ios",
        default="",
        help="audited iOS candidate (X.Y.Z/build) from the operator release gate; fails the train closed on drift",
    )
    parser.add_argument(
        "--pin-android",
        default="",
        help="audited Android candidate (X.Y.Z/build) from the operator release gate; fails the train closed on drift",
    )
    args = parser.parse_args(argv)
    token = os.environ.get("CODEMAGIC_API_TOKEN", "")
    if not token:
        print("CODEMAGIC_API_TOKEN is required", file=sys.stderr)
        return 1
    try:
        build_id = dispatch(
            args.app_id,
            token,
            dry_run=args.dry_run == "true",
            pin_ios=args.pin_ios,
            pin_android=args.pin_android,
        )
    except DispatchError as error:
        print(f"dispatch failed: {error}", file=sys.stderr)
        return 1
    print(f"mobile-daily-train dry_run={args.dry_run} build={build_id}")
    print(f"https://codemagic.io/app/{args.app_id}/build/{build_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
