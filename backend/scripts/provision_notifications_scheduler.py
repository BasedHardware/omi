#!/usr/bin/env python3
"""Enforce the retained hourly Scheduler contract for notifications-job."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import json
import subprocess
from typing import Any

EXPECTED_SCHEDULER_JOB = "notifications-job-scheduler-trigger"
EXPECTED_CLOUD_RUN_JOB = "notifications-job"
EXPECTED_SCHEDULE = "0 * * * *"
EXPECTED_TIME_ZONE = "Etc/UTC"


def _required_identity(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized or any(character in normalized for character in "\n\r\t "):
        raise ValueError(f"{field} must be a nonempty single token")
    return normalized


def scheduler_target_uri(project: str, region: str, cloud_run_job: str) -> str:
    return f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{cloud_run_job}:run"


def scheduler_http_args(
    action: str,
    *,
    project: str,
    region: str,
    scheduler_job: str,
    cloud_run_job: str,
    service_account: str,
) -> list[str]:
    if action not in {"create", "update"}:
        raise ValueError("action must be create or update")
    project = _required_identity(project, field="project")
    region = _required_identity(region, field="region")
    scheduler_job = _required_identity(scheduler_job, field="scheduler_job")
    cloud_run_job = _required_identity(cloud_run_job, field="cloud_run_job")
    service_account = _required_identity(service_account, field="service_account")
    if scheduler_job != EXPECTED_SCHEDULER_JOB or cloud_run_job != EXPECTED_CLOUD_RUN_JOB:
        raise ValueError("notifications scheduler identity does not match the retained contract")
    return [
        "gcloud",
        "scheduler",
        "jobs",
        action,
        "http",
        scheduler_job,
        f"--location={region}",
        f"--project={project}",
        f"--schedule={EXPECTED_SCHEDULE}",
        f"--time-zone={EXPECTED_TIME_ZONE}",
        "--http-method=POST",
        f"--uri={scheduler_target_uri(project, region, cloud_run_job)}",
        f"--oauth-service-account-email={service_account}",
        "--quiet",
    ]


def validate_scheduler_state(
    payload: Any,
    *,
    project: str,
    region: str,
    service_account: str,
) -> None:
    if not isinstance(payload, dict):
        raise ValueError("notifications scheduler state must be an object")
    expected_uri = scheduler_target_uri(project, region, EXPECTED_CLOUD_RUN_JOB)
    http_target = payload.get("httpTarget")
    oauth_token = http_target.get("oauthToken") if isinstance(http_target, dict) else None
    checks = {
        "schedule": payload.get("schedule") == EXPECTED_SCHEDULE,
        "timeZone": payload.get("timeZone") == EXPECTED_TIME_ZONE,
        "state": payload.get("state") == "ENABLED",
        "httpMethod": isinstance(http_target, dict) and http_target.get("httpMethod") == "POST",
        "uri": isinstance(http_target, dict) and http_target.get("uri") == expected_uri,
        "serviceAccountEmail": isinstance(oauth_token, dict)
        and oauth_token.get("serviceAccountEmail") == service_account,
    }
    failed = [field for field, valid in checks.items() if not valid]
    if failed:
        raise ValueError(f"notifications scheduler state violates: {','.join(failed)}")


def ensure_scheduler(
    *,
    project: str,
    region: str,
    service_account: str,
    scheduler_job: str = EXPECTED_SCHEDULER_JOB,
    cloud_run_job: str = EXPECTED_CLOUD_RUN_JOB,
    runner: Callable[..., Any] = subprocess.run,
) -> str:
    project = _required_identity(project, field="project")
    region = _required_identity(region, field="region")
    service_account = _required_identity(service_account, field="service_account")
    scheduler_job = _required_identity(scheduler_job, field="scheduler_job")
    cloud_run_job = _required_identity(cloud_run_job, field="cloud_run_job")
    if scheduler_job != EXPECTED_SCHEDULER_JOB or cloud_run_job != EXPECTED_CLOUD_RUN_JOB:
        raise ValueError("notifications scheduler identity does not match the retained contract")

    describe_args = [
        "gcloud",
        "scheduler",
        "jobs",
        "describe",
        scheduler_job,
        f"--location={region}",
        f"--project={project}",
        "--format=json",
        "--quiet",
    ]
    describe = runner(describe_args, capture_output=True, text=True, check=False)
    existing_state: str | None = None
    if describe.returncode == 0:
        existing_payload = json.loads(describe.stdout)
        if not isinstance(existing_payload, dict) or existing_payload.get("state") not in {"ENABLED", "PAUSED"}:
            raise ValueError("existing notifications scheduler state must be ENABLED or PAUSED")
        existing_state = existing_payload["state"]
        action = "update"
    elif "not found" in describe.stderr.lower() or "not_found" in describe.stderr.lower():
        action = "create"
    else:
        raise subprocess.CalledProcessError(
            describe.returncode,
            describe_args,
            output=describe.stdout,
            stderr=describe.stderr,
        )
    runner(
        scheduler_http_args(
            action,
            project=project,
            region=region,
            scheduler_job=scheduler_job,
            cloud_run_job=cloud_run_job,
            service_account=service_account,
        ),
        check=True,
    )
    if action == "update" and existing_state == "PAUSED":
        runner(
            [
                "gcloud",
                "scheduler",
                "jobs",
                "resume",
                scheduler_job,
                f"--location={region}",
                f"--project={project}",
                "--quiet",
            ],
            check=True,
        )
    final_state = runner(describe_args, capture_output=True, text=True, check=True)
    validate_scheduler_state(
        json.loads(final_state.stdout),
        project=project,
        region=region,
        service_account=service_account,
    )
    return action


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--scheduler-job", default=EXPECTED_SCHEDULER_JOB)
    parser.add_argument("--cloud-run-job", default=EXPECTED_CLOUD_RUN_JOB)
    parser.add_argument("--service-account", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        action = ensure_scheduler(
            project=args.project,
            region=args.region,
            scheduler_job=args.scheduler_job,
            cloud_run_job=args.cloud_run_job,
            service_account=args.service_account,
        )
    except (json.JSONDecodeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"notifications scheduler provisioning failed: {exc}")
        return 1
    print(f"notifications scheduler provisioning: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
