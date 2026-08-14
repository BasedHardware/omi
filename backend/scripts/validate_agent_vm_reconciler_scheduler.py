#!/usr/bin/env python3
"""Validate the read-only Cloud Scheduler contract for Agent VM reconciliation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

EXPECTED_SCHEDULE = "*/5 * * * *"
EXPECTED_TIME_ZONE = "Etc/UTC"
EXPECTED_HTTP_METHOD = "POST"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def target_uri(project: str, region: str, job: str) -> str:
    return f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run"


def validate_scheduler_state(
    state: Mapping[str, Any],
    *,
    project: str,
    region: str,
    scheduler_job: str,
    cloud_run_job: str,
    scheduler_service_account: str | None = None,
    expected_state: str = "ENABLED",
) -> list[str]:
    http_target = _mapping(state.get("httpTarget"))
    oauth_token = _mapping(http_target.get("oauthToken"))
    expected = {
        "name": f"projects/{project}/locations/{region}/jobs/{scheduler_job}",
        "state": expected_state,
        "schedule": EXPECTED_SCHEDULE,
        "timeZone": EXPECTED_TIME_ZONE,
        "httpTarget.httpMethod": EXPECTED_HTTP_METHOD,
        "httpTarget.uri": target_uri(project, region, cloud_run_job),
    }
    actual = {
        "name": state.get("name"),
        "state": state.get("state"),
        "schedule": state.get("schedule"),
        "timeZone": state.get("timeZone"),
        "httpTarget.httpMethod": http_target.get("httpMethod"),
        "httpTarget.uri": http_target.get("uri"),
    }
    errors = [
        f"{key} must equal {expected[key]!r}; got {actual[key]!r}" for key in expected if actual[key] != expected[key]
    ]
    if not isinstance(oauth_token.get("serviceAccountEmail"), str) or not oauth_token["serviceAccountEmail"].strip():
        errors.append("httpTarget.oauthToken.serviceAccountEmail must be a nonempty string")
    elif scheduler_service_account and oauth_token["serviceAccountEmail"] != scheduler_service_account:
        errors.append(
            "httpTarget.oauthToken.serviceAccountEmail must equal "
            f"{scheduler_service_account!r}; got {oauth_token['serviceAccountEmail']!r}"
        )
    return errors


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--state-file", type=Path, required=True)
    command.add_argument("--project", required=True)
    command.add_argument("--region", required=True)
    command.add_argument("--scheduler-job", required=True)
    command.add_argument("--cloud-run-job", required=True)
    command.add_argument("--scheduler-service-account")
    command.add_argument("--expected-state", choices=("ENABLED", "PAUSED"), default="ENABLED")
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        state = json.loads(args.state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"agent VM reconciler scheduler contract: invalid state file: {exc}", file=sys.stderr)
        return 2
    if not isinstance(state, Mapping):
        print("agent VM reconciler scheduler contract: state JSON must be an object", file=sys.stderr)
        return 2
    errors = validate_scheduler_state(
        state,
        project=args.project,
        region=args.region,
        scheduler_job=args.scheduler_job,
        cloud_run_job=args.cloud_run_job,
        scheduler_service_account=args.scheduler_service_account,
        expected_state=args.expected_state,
    )
    if errors:
        print("agent VM reconciler scheduler contract: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("agent VM reconciler scheduler contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
