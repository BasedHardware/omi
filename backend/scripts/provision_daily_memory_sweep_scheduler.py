#!/usr/bin/env python3
"""Create or update an allowed retained Cloud Run Job Scheduler trigger.

This is intentionally separate from the legacy read-only maintenance
validator.  The deployment workflow checks out an admitted main SHA before
running this script, so the scheduler target contract is source-derived from
the same revision as the Cloud Run job.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import subprocess
from typing import Any

EXPECTED_SCHEDULER_JOB = "daily-memory-sweep-hourly"
EXPECTED_CLOUD_RUN_JOB = "daily-memory-sweep-job"
EXPECTED_TARGETS = {
    EXPECTED_SCHEDULER_JOB: EXPECTED_CLOUD_RUN_JOB,
    "knowledge-ledger-drain-hourly": "knowledge-ledger-drain-job",
}
EXPECTED_SCHEDULE = "0 * * * *"
EXPECTED_TIME_ZONE = "Etc/UTC"


def scheduler_target_uri(project: str, region: str, cloud_run_job: str) -> str:
    return f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{cloud_run_job}:run"


def _required_identity(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized or any(character in normalized for character in "\n\r\t "):
        raise ValueError(f"{field} must be a nonempty single token")
    return normalized


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
    if EXPECTED_TARGETS.get(scheduler_job) != cloud_run_job:
        raise ValueError("scheduler identity does not match a retained contract for Cloud Run Jobs")
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


def ensure_scheduler(
    *,
    project: str,
    region: str,
    scheduler_job: str = EXPECTED_SCHEDULER_JOB,
    cloud_run_job: str = EXPECTED_CLOUD_RUN_JOB,
    service_account: str,
    runner: Callable[..., Any] = subprocess.run,
) -> str:
    """Ensure the trigger exists, targets this job, and is enabled.

    A describe failure is allowed to fall through to create; authentication or
    permission failures still make create fail and therefore fail the deploy.
    ``runner`` is injectable so command selection is testable without GCP.
    """

    describe = runner(
        [
            "gcloud",
            "scheduler",
            "jobs",
            "describe",
            scheduler_job,
            f"--location={region}",
            f"--project={project}",
            "--quiet",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    action = "update" if describe.returncode == 0 else "create"
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
    if action == "update":
        # update preserves PAUSED/DISABLED state; the retained replacement
        # contract is an enabled hourly trigger, so resume it explicitly.
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
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"retained job scheduler provisioning failed: {exc}")
        return 1
    print(f"retained job scheduler provisioning: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
