#!/usr/bin/env python3
"""Delete aged idle/abandoned `omi-agent-*` GCE VMs so boot disks stop billing.

Root cause: idle auto-stop leaves the instance in TERMINATED. `autoDelete: true`
only fires on instance *delete*, so ~50 GB pd-balanced disks keep charging
(~$0.10/GB-mo) until the instance is deleted.

Defaults are refuse-to-delete (dry-run). Live deletes require an explicit
`--live` flag *and* `AGENT_VM_REAPER_LIVE=1`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_PROJECT = "based-hardware"
DEFAULT_RUNNING_AGE_DAYS = 2
DEFAULT_TERMINATED_MIN_AGE_HOURS = 12
NAME_PREFIX = "omi-agent-"


def parse_rfc3339(value: str) -> datetime:
    """Parse GCE timestamps such as 2026-07-22T12:08:49.845-07:00."""
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def terminated_age_timestamp(instance: dict[str, Any]) -> str | None:
    """Prefer lastStopTimestamp; fall back to creationTimestamp."""
    return instance.get("lastStopTimestamp") or instance.get("creationTimestamp")


def is_reapable(
    instance: dict[str, Any],
    *,
    now: datetime,
    running_age_days: int,
    terminated_min_age_hours: int,
) -> bool:
    name = str(instance.get("name") or "")
    if not name.startswith(NAME_PREFIX):
        return False

    status = str(instance.get("status") or "")
    if status == "TERMINATED":
        raw = terminated_age_timestamp(instance)
        if not raw:
            return False
        age = now - parse_rfc3339(raw)
        return age >= timedelta(hours=terminated_min_age_hours)

    if status == "RUNNING":
        raw = instance.get("creationTimestamp")
        if not raw:
            return False
        age = now - parse_rfc3339(str(raw))
        return age >= timedelta(days=running_age_days)

    return False


def select_reapable(
    instances: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    running_age_days: int = DEFAULT_RUNNING_AGE_DAYS,
    terminated_min_age_hours: int = DEFAULT_TERMINATED_MIN_AGE_HOURS,
) -> list[dict[str, Any]]:
    clock = now or datetime.now(timezone.utc)
    return [
        inst
        for inst in instances
        if is_reapable(
            inst,
            now=clock,
            running_age_days=running_age_days,
            terminated_min_age_hours=terminated_min_age_hours,
        )
    ]


def list_agent_vms(project: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [
            "gcloud",
            "compute",
            "instances",
            "list",
            f"--project={project}",
            f"--filter=name~^{NAME_PREFIX}",
            "--format=json(name,zone,status,creationTimestamp,lastStopTimestamp,disks)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(proc.stdout or "[]")
    if not isinstance(data, list):
        raise RuntimeError("unexpected gcloud JSON for instance list")
    return data


def zone_name(instance: dict[str, Any]) -> str:
    zone = str(instance.get("zone") or "")
    return zone.rsplit("/", 1)[-1]


def delete_instance(project: str, name: str, zone: str) -> None:
    subprocess.run(
        [
            "gcloud",
            "compute",
            "instances",
            "delete",
            name,
            f"--zone={zone}",
            f"--project={project}",
            "--quiet",
        ],
        check=True,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.environ.get("GCE_PROJECT", DEFAULT_PROJECT))
    parser.add_argument(
        "--running-age-days",
        type=int,
        default=int(os.environ.get("REAP_RUNNING_AGE_DAYS", DEFAULT_RUNNING_AGE_DAYS)),
    )
    parser.add_argument(
        "--terminated-min-age-hours",
        type=int,
        default=int(os.environ.get("REAP_TERMINATED_MIN_AGE_HOURS", DEFAULT_TERMINATED_MIN_AGE_HOURS)),
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("DRY_RUN", "true").lower() in {"1", "true", "yes"},
        help="Log targets without deleting (default: true unless DRY_RUN=false)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Local CLI opt-in for deletes. Also requires AGENT_VM_REAPER_LIVE=1 and "
            "--no-dry-run / DRY_RUN=false. In-cluster CronJob skips --live when "
            "KUBERNETES_SERVICE_HOST is set."
        ),
    )
    parser.add_argument(
        "--instances-json",
        help="Optional path to a gcloud instances JSON list (skips live list; for tests/fixtures).",
    )
    return parser.parse_args(argv)


def live_deletes_allowed(*, dry_run: bool, live_flag: bool) -> bool:
    """Live deletes need DRY_RUN off + AGENT_VM_REAPER_LIVE=1; local CLI also needs --live."""
    if dry_run:
        return False
    if os.environ.get("AGENT_VM_REAPER_LIVE") != "1":
        return False
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        return True
    return live_flag


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dry_run = bool(args.dry_run)

    print(
        "agent-vm-reaper start "
        f"project={args.project} "
        f"running_age_days={args.running_age_days} "
        f"terminated_min_age_hours={args.terminated_min_age_hours} "
        f"dry_run={dry_run}"
    )

    if args.instances_json:
        with open(args.instances_json, encoding="utf-8") as handle:
            instances = json.load(handle)
    else:
        instances = list_agent_vms(args.project)

    targets = select_reapable(
        instances,
        running_age_days=args.running_age_days,
        terminated_min_age_hours=args.terminated_min_age_hours,
    )
    print(f"found {len(targets)} reapable omi-agent VMs (of {len(instances)} listed)")
    if not targets:
        print("nothing to reap")
        return 0

    if not dry_run and not live_deletes_allowed(dry_run=dry_run, live_flag=args.live):
        print(
            "REFUSED: live deletes require AGENT_VM_REAPER_LIVE=1 and "
            "(--live for local CLI, or in-cluster CronJob).",
            file=sys.stderr,
        )
        return 2

    for inst in targets:
        name = str(inst["name"])
        zone = zone_name(inst)
        status = inst.get("status")
        if dry_run:
            print(f"DRY_RUN would delete {name} ({zone}) status={status}")
            continue
        try:
            delete_instance(args.project, name, zone)
            print(f"deleted {name} ({zone})")
        except subprocess.CalledProcessError as exc:
            print(f"FAILED to delete {name} ({zone}): {exc}", file=sys.stderr)

    print("agent-vm-reaper done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
