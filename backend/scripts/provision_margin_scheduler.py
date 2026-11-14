#!/usr/bin/env python3
"""Provision the approved cloud margin schedule after the active job is accepted.

This operation uses the existing FinOps CI identity. It never deploys an image,
changes IAM, or mutates the settled-ledger job or its daily schedule.
"""

import json
import re
import subprocess

PROJECT = "based-hardware"
REGION = "us-central1"
JOB = "omi-margin-hourly"
SCHEDULER_SA = "finops-unit-cost-scheduler@based-hardware.iam.gserviceaccount.com"
RUNTIME_SA = "finops-writer@based-hardware.iam.gserviceaccount.com"
SCHEDULE = "12 * * * *"
URI = f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{JOB}:run"


def command(*args):
    return subprocess.run(
        ["gcloud", *args, f"--project={PROJECT}", "--format=json", "--quiet"],
        capture_output=True,
        text=True,
        timeout=180,
    )


def verify_active_job(job):
    task = job["spec"]["template"]["spec"]["template"]["spec"]
    container = task["containers"][0]
    image = container["image"]
    args = container.get("args", [])
    if (
        task.get("serviceAccountName") != RUNTIME_SA
        or len(task["containers"]) != 1
        or not re.fullmatch(r"us-central1-docker\.pkg\.dev/based-hardware/omi-margin/producer:[a-f0-9]{40}", image)
        or len(args) != 5
        or args[:4] != ["run", "--mode", "active", "--inputs"]
        or not re.fullmatch(r"margin/inputs/[a-f0-9]{64}\.json", args[4])
    ):
        raise ValueError("margin job is not the expected source-pinned active producer")


def verify_schedule(state):
    target = state.get("httpTarget", {})
    if (
        state.get("schedule") != SCHEDULE
        or state.get("timeZone") != "UTC"
        or state.get("state") != "ENABLED"
        or target.get("uri") != URI
        or target.get("httpMethod") != "POST"
        or target.get("oauthToken", {}).get("serviceAccountEmail") != SCHEDULER_SA
        or target.get("oauthToken", {}).get("scope") != "https://www.googleapis.com/auth/cloud-platform"
    ):
        raise ValueError("margin schedule readback differs from its approved contract")


def main():
    job = command("run", "jobs", "describe", JOB, f"--region={REGION}")
    if job.returncode:
        raise SystemExit("cannot verify the active margin job: " + job.stderr[-1000:])
    verify_active_job(json.loads(job.stdout))
    before = command("scheduler", "jobs", "describe", JOB, f"--location={REGION}")
    if before.returncode and "NOT_FOUND" not in before.stderr:
        raise SystemExit("scheduler inspection failed: " + before.stderr[-1000:])
    action = "update" if before.returncode == 0 else "create"
    result = command(
        "scheduler",
        "jobs",
        action,
        "http",
        JOB,
        f"--location={REGION}",
        f"--schedule={SCHEDULE}",
        "--time-zone=UTC",
        "--http-method=POST",
        f"--uri={URI}",
        f"--oauth-service-account-email={SCHEDULER_SA}",
        "--oauth-token-scope=https://www.googleapis.com/auth/cloud-platform",
        "--max-retry-attempts=0",
        "--attempt-deadline=180s",
    )
    if result.returncode:
        raise SystemExit("margin schedule mutation failed: " + result.stderr[-1000:])
    after = command("scheduler", "jobs", "describe", JOB, f"--location={REGION}")
    if after.returncode:
        raise SystemExit("margin schedule readback failed")
    state = json.loads(after.stdout)
    verify_schedule(state)
    print(json.dumps({"job": JOB, "schedule": SCHEDULE, "time_zone": "UTC", "state": state["state"]}))


if __name__ == "__main__":
    main()
