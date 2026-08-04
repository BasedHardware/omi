#!/usr/bin/env python3
"""Validate the read-only Cloud Scheduler contract for memory maintenance.

The caller supplies JSON from ``gcloud scheduler jobs describe --format=json``.
This module performs no network calls and never creates, updates, resumes, or
pauses Scheduler or Cloud Run resources.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

EXPECTED_SCHEDULE = "0 * * * *"
EXPECTED_STATE = "ENABLED"
EXPECTED_TIME_ZONE = "Etc/UTC"
EXPECTED_HTTP_METHOD = "POST"


class SchedulerContract(NamedTuple):
    project: str
    region: str
    scheduler_job: str
    cloud_run_job: str

    @property
    def resource_name(self) -> str:
        return f"projects/{self.project}/locations/{self.region}/jobs/{self.scheduler_job}"

    @property
    def target_uri(self) -> str:
        return (
            f"https://run.googleapis.com/v2/projects/{self.project}"
            f"/locations/{self.region}/jobs/{self.cloud_run_job}:run"
        )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_scheduler_state(state: Mapping[str, Any], contract: SchedulerContract) -> list[str]:
    """Return deterministic validation errors for a described Scheduler job."""

    http_target = _mapping(state.get("httpTarget"))
    oauth_token = _mapping(http_target.get("oauthToken"))
    service_account = oauth_token.get("serviceAccountEmail")

    expected_values = (
        ("name", state.get("name"), contract.resource_name),
        ("state", state.get("state"), EXPECTED_STATE),
        ("schedule", state.get("schedule"), EXPECTED_SCHEDULE),
        ("timeZone", state.get("timeZone"), EXPECTED_TIME_ZONE),
        ("httpTarget.httpMethod", http_target.get("httpMethod"), EXPECTED_HTTP_METHOD),
        ("httpTarget.uri", http_target.get("uri"), contract.target_uri),
    )
    errors = [
        f"{field} must equal {expected!r}; got {actual!r}"
        for field, actual, expected in expected_values
        if actual != expected
    ]
    if not isinstance(service_account, str) or not service_account.strip():
        errors.append("httpTarget.oauthToken.serviceAccountEmail must be a nonempty string")
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--scheduler-job", required=True)
    parser.add_argument("--cloud-run-job", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        raw_state = json.loads(args.state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"memory maintenance scheduler contract: invalid state file: {exc}", file=sys.stderr)
        return 2
    if not isinstance(raw_state, Mapping):
        print("memory maintenance scheduler contract: state JSON must be an object", file=sys.stderr)
        return 2

    contract = SchedulerContract(
        project=args.project,
        region=args.region,
        scheduler_job=args.scheduler_job,
        cloud_run_job=args.cloud_run_job,
    )
    errors = validate_scheduler_state(raw_state, contract)
    if errors:
        print("memory maintenance scheduler contract: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("memory maintenance scheduler contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
