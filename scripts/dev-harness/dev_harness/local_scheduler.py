"""Cloud Scheduler stand-in for a prod-parity stack.

Several production safety nets are not triggered by a request: Cloud Scheduler
calls a sweep route every few minutes (queued backfill jobs, enrichment that
was enrolled but never woken, held audio, stock census). Without those calls a
local stack strands work that production would pick up.

This process reads production's own job list (``backend/deploy/scheduler/jobs.yaml``),
keeps the enabled jobs that call a backend service, rewrites each target to the
local process standing in for that service, and calls it on the job's cron
schedule with the identity token the route expects.

Only jobs on the recording path run by default; ``OMI_HARNESS_SCHEDULER_JOBS=all``
runs every backend-service job (that includes agent sweeps that call LLMs).
"""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

JOBS_ENV = "OMI_HARNESS_SCHEDULER_JOBS"
PLAN_ENV = "OMI_HARNESS_SCHEDULER_PLAN"
RECORDING_JOBS = (
    "sync-backfill-uid-sequencer",
    "enrichment-maintenance",
    "cap-hold-durable-redrive",
    "batch-stock-census",
)


@dataclass(frozen=True)
class Job:
    name: str
    schedule: str
    url: str
    method: str
    audience: str
    identity: str
    body: str | None = None
    timeout: float = 600.0


def plan(
    repo_root: Path,
    *,
    localize: Callable[[str], str | None],
    identity_for: Callable[[str], str],
    names: tuple[str, ...] | None = RECORDING_JOBS,
) -> list[Job]:
    """Production's enabled HTTP jobs that target a service this stack runs.

    ``localize`` maps a production address to the local one (None when the
    target has no local stand-in). ``identity_for`` gives the invoker identity
    the local target accepts for a local URL.
    """
    import yaml

    document = yaml.safe_load((repo_root / "backend" / "deploy" / "scheduler" / "jobs.yaml").read_text())
    jobs: list[Job] = []
    for raw in document["environments"]["prod"]["jobs"]:
        target = raw.get("target") or {}
        oidc = target.get("oidc") or {}
        if raw.get("state") != "ENABLED" or target.get("type") != "http" or not oidc.get("audience"):
            continue
        if names is not None and raw["name"] not in names:
            continue
        url, audience = localize(str(target["uri"])), localize(str(oidc["audience"]))
        if url is None or audience is None:
            continue
        body = target.get("body")
        jobs.append(
            Job(
                name=raw["name"],
                schedule=str(raw["schedule"]),
                url=url,
                method=str(target.get("method", "POST")),
                audience=audience,
                identity=identity_for(url),
                body=body if isinstance(body, str) or body is None else json.dumps(body),
                timeout=float(str(raw.get("attempt_deadline", "600s")).rstrip("s")),
            )
        )
    return jobs


def plan_live(
    live_jobs: list[Mapping[str, Any]],
    *,
    localize: Callable[[str], str | None],
    identity_for: Callable[[str], str],
    names: tuple[str, ...] | None = RECORDING_JOBS,
) -> list[Job]:
    """The same plan from the running Cloud Scheduler jobs (a production snapshot)."""
    jobs: list[Job] = []
    for raw in live_jobs:
        if raw.get("state") != "ENABLED" or not raw.get("uri") or not raw.get("audience"):
            continue
        if names is not None and raw["name"] not in names:
            continue
        url, audience = localize(str(raw["uri"])), localize(str(raw["audience"]))
        if url is None or audience is None:
            continue
        jobs.append(
            Job(
                name=raw["name"],
                schedule=str(raw["schedule"]),
                url=url,
                method=str(raw.get("method") or "POST"),
                audience=audience,
                identity=identity_for(url),
                body=raw.get("body"),
                timeout=float(str(raw.get("attempt_deadline") or "600s").rstrip("s")),
            )
        )
    return jobs


def encode(jobs: list[Job]) -> str:
    return json.dumps([job.__dict__ for job in jobs])


def run(jobs: list[Job], token_for: Callable[[str, str], str], stop: threading.Event) -> None:
    import httpx
    from croniter import croniter

    from dev_harness import log_timestamps

    verify: object = os.environ.get("OMI_HARNESS_CA_BUNDLE", "").strip() or True
    due = {job.name: croniter(job.schedule, time.time()).get_next(float) for job in jobs}
    running: set[str] = set()
    lock = threading.Lock()
    print(f"harness_scheduler event=started jobs={','.join(job.name for job in jobs)}", flush=True)

    def fire(job: Job) -> None:
        started = time.monotonic()
        try:
            with httpx.Client(trust_env=False, verify=verify) as client:
                response = client.request(
                    job.method,
                    job.url,
                    content=job.body,
                    headers={
                        "Authorization": f"Bearer {token_for(job.audience, job.identity)}",
                        "User-Agent": "Google-Cloud-Scheduler",
                        "X-CloudScheduler-JobName": job.name,
                        **({"Content-Type": "application/json"} if job.body else {}),
                    },
                    timeout=job.timeout,
                )
            outcome = str(response.status_code)
        except Exception as error:  # noqa: BLE001 - a failed run is reported and the schedule goes on
            outcome = f"exception:{type(error).__name__}"
        finally:
            with lock:
                running.discard(job.name)
        print(
            log_timestamps.line(
                f"harness_scheduler event=ran job={job.name} status={outcome} "
                f"ms={int((time.monotonic() - started) * 1000)}"
            ),
            flush=True,
        )

    while not stop.wait(1.0):
        now = time.time()
        for job in jobs:
            if now < due[job.name]:
                continue
            due[job.name] = croniter(job.schedule, now).get_next(float)
            with lock:
                if job.name in running:
                    continue  # the previous run is still in flight; Cloud Scheduler would skip this tick too
                running.add(job.name)
            # Each run has its own thread: a sweep with a half-hour deadline must not
            # hold back the other jobs or the process's shutdown.
            threading.Thread(target=fire, args=(job,), name=f"scheduler-{job.name}", daemon=True).start()


def main(env: Mapping[str, str] | None = None) -> int:
    from dev_harness import local_task_queue

    source = os.environ if env is None else env
    raw = source.get(PLAN_ENV, "").strip()
    secret = source.get(local_task_queue.SECRET_ENV, "").strip()
    if not raw or not secret:
        raise RuntimeError(f"the scheduler needs {PLAN_ENV} and {local_task_queue.SECRET_ENV} (set by the dev harness)")
    jobs = [Job(**entry) for entry in json.loads(raw)]
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_args: stop.set())

    def token_for(audience: str, identity: str) -> str:
        return f"{local_task_queue.TOKEN_PREFIX}:{secret}:{audience}:{identity}"

    run(jobs, token_for, stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
