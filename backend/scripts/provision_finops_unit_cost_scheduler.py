#!/usr/bin/env python3
"""Create or update the Cloud Scheduler trigger for the finops unit-cost Cloud Run Job.

Source-derived contract (same pattern as provision_daily_memory_sweep_scheduler.py):
the deployment workflow checks out an admitted SHA before running this, so the
scheduler target always matches the job revision being deployed.

  schedule  30 10 * * *  (America/New_York) — 10:30 ET, matching the retired laptop cron
  target    POST https://run.googleapis.com/v2/.../jobs/finops-unit-cost-job:run
  auth      OIDC with the dedicated scheduler SA (needs roles/run.invoker + the
            Cloud Run Job run invoker binding on the job's runtime SA project).
"""

from __future__ import annotations

import argparse
import subprocess

EXPECTED_SCHEDULER_JOB = "finops-unit-cost-daily"
EXPECTED_CLOUD_RUN_JOB = "finops-unit-cost-job"
EXPECTED_SCHEDULE = "30 10 * * *"
EXPECTED_TIME_ZONE = "America/New_York"


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
    schedule: str = EXPECTED_SCHEDULE,
    time_zone: str = EXPECTED_TIME_ZONE,
) -> list[str]:
    if action not in {"create", "update"}:
        raise ValueError("action must be create or update")
    project = _required_identity(project, field="project")
    region = _required_identity(region, field="region")
    scheduler_job = _required_identity(scheduler_job, field="scheduler_job")
    cloud_run_job = _required_identity(cloud_run_job, field="cloud_run_job")
    service_account = _required_identity(service_account, field="service_account")
    if scheduler_job != EXPECTED_SCHEDULER_JOB or cloud_run_job != EXPECTED_CLOUD_RUN_JOB:
        raise ValueError("scheduler identity does not match the finops unit-cost contract")
    return [
        "gcloud",
        "scheduler",
        "jobs",
        action,
        "http",
        scheduler_job,
        f"--location={region}",
        f"--project={project}",
        f"--schedule={schedule}",
        f"--time-zone={time_zone}",
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
) -> str:
    """Ensure the trigger exists, targets this job, and is enabled."""
    describe = subprocess.run(
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
    )
    action = "update" if describe.returncode == 0 else "create"
    result = subprocess.run(
        scheduler_http_args(
            action,
            project=project,
            region=region,
            scheduler_job=scheduler_job,
            cloud_run_job=cloud_run_job,
            service_account=service_account,
        ),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"scheduler {action} failed: {result.stderr[-1000:]}")
    verify = subprocess.run(
        [
            "gcloud",
            "scheduler",
            "jobs",
            "describe",
            scheduler_job,
            f"--location={region}",
            f"--project={project}",
            "--format=json",
        ],
        capture_output=True,
        text=True,
    )
    if verify.returncode != 0:
        raise SystemExit("scheduler describe after %s failed" % action)
    return verify.stdout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--region", required=True)
    ap.add_argument("--scheduler-job", default=EXPECTED_SCHEDULER_JOB)
    ap.add_argument("--cloud-run-job", default=EXPECTED_CLOUD_RUN_JOB)
    ap.add_argument("--scheduler-service-account", required=True)
    a = ap.parse_args()
    state = ensure_scheduler(
        project=a.project,
        region=a.region,
        scheduler_job=a.scheduler_job,
        cloud_run_job=a.cloud_run_job,
        service_account=a.scheduler_service_account,
    )
    import json

    parsed = json.loads(state)
    if parsed.get("schedule") != EXPECTED_SCHEDULE or parsed.get("timeZone") != EXPECTED_TIME_ZONE:
        raise SystemExit("scheduler state does not match the expected schedule/timezone")
    print(
        json.dumps(
            {
                "scheduler_job": a.scheduler_job,
                "cloud_run_job": a.cloud_run_job,
                "schedule": parsed.get("schedule"),
                "time_zone": parsed.get("timeZone"),
                "state": parsed.get("state"),
            }
        )
    )


if __name__ == "__main__":
    main()
