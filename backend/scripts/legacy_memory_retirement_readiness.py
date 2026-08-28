#!/usr/bin/env python3
# LIFECYCLE: one-time
# DELETE-AFTER: INV-MEM-6

"""Evaluate retirement readiness for the dedicated memory maintenance runtime.

The default path is offline-only: it consumes a sanitized JSON snapshot and
emits only fixed reason codes plus aggregate counts.  It does not prove that
other legacy memory surfaces are inactive or deleted.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

STATUS_ACTIVE = "ACTIVE"
STATUS_NO_LIVE_ACTIVITY = "NO_LIVE_ACTIVITY"
STATUS_DELETED = "DELETED"
STATUS_UNKNOWN = "UNKNOWN"

EXPECTED_CLOUD_RUN_JOB = "memory-maintenance-job"
EXPECTED_SCHEDULER_JOB = "memory-maintenance-hourly"
ACTIVE_EXECUTION_STATES = frozenset({"PENDING", "RUNNING"})
TERMINAL_EXECUTION_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})
KNOWN_SCHEDULER_STATES = frozenset({"ENABLED", "PAUSED", "DISABLED"})
MAINTENANCE_ENV_FLAGS = (
    "MEMORY_CANONICAL_MAINTENANCE_ENABLED",
    "MEMORY_CANONICAL_CONSOLIDATION_ENABLED",
    "MEMORY_CANONICAL_PROMOTION_CRON_ENABLED",
)

_ALLOWED_GCLOUD_COMMANDS: Mapping[tuple[str, ...], tuple[frozenset[str], int]] = {
    ("gcloud", "run", "jobs", "describe"): (
        frozenset({"--project", "--region", "--format"}),
        1,
    ),
    ("gcloud", "run", "jobs", "executions", "list"): (
        frozenset({"--job", "--project", "--region", "--format"}),
        0,
    ),
    ("gcloud", "scheduler", "jobs", "describe"): (
        frozenset({"--project", "--location", "--format"}),
        1,
    ),
    ("gcloud", "scheduler", "jobs", "list"): (
        frozenset({"--project", "--location", "--format"}),
        0,
    ),
}


@dataclass(frozen=True)
class Contract:
    project: str
    region: str
    cloud_run_job: str = EXPECTED_CLOUD_RUN_JOB
    scheduler_job: str = EXPECTED_SCHEDULER_JOB

    @property
    def scheduler_target_uri(self) -> str:
        return (
            f"https://run.googleapis.com/v2/projects/{self.project}"
            f"/locations/{self.region}/jobs/{self.cloud_run_job}:run"
        )


@dataclass(frozen=True)
class Evaluation:
    status: str
    counts: Mapping[str, int]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "counts": dict(self.counts), "reasons": list(self.reasons)}


def validate_read_only_gcloud_argv(argv: Sequence[str] | str) -> tuple[str, ...]:
    """Return a validated read-only argv tuple; reject shell strings and drift."""

    if isinstance(argv, str):
        raise ValueError("shell_strings_rejected")
    command = tuple(argv)
    matched: tuple[frozenset[str], int] | None = None
    prefix_length = 0
    for prefix, contract in _ALLOWED_GCLOUD_COMMANDS.items():
        if command[: len(prefix)] == prefix:
            matched = contract
            prefix_length = len(prefix)
            break
    if matched is None:
        raise ValueError("command_not_allowlisted")

    allowed_flags, positional_required = matched
    positional_count = 0
    for token in command[prefix_length:]:
        if not token or any(character in token for character in (";", "|", "&", "`", "\n", "\r")):
            raise ValueError("unsafe_argv_token")
        if token.startswith("-"):
            flag = token.split("=", 1)[0]
            if flag not in allowed_flags or "=" not in token:
                raise ValueError("command_flag_not_allowlisted")
        else:
            positional_count += 1
    if positional_count != positional_required:
        raise ValueError("unexpected_positional_argument_count")
    return command


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, dict) else None


def _resources(inventories: Mapping[str, object], key: str, reasons: list[str]) -> list[Mapping[str, object]]:
    inventory = _mapping(inventories.get(key))
    if inventory is None:
        reasons.append(f"{key}_inventory_missing")
        return []
    if inventory.get("complete") is not True:
        reasons.append(f"{key}_inventory_incomplete")
    raw_resources = inventory.get("resources")
    if not isinstance(raw_resources, list):
        reasons.append(f"{key}_resources_malformed")
        return []
    resources: list[Mapping[str, object]] = []
    for raw_resource in cast(list[object], raw_resources):
        resource = _mapping(raw_resource)
        if resource is None:
            reasons.append(f"{key}_resource_malformed")
        else:
            resources.append(resource)
    return resources


def _identity_matches(resource: Mapping[str, object], contract: Contract) -> bool:
    return resource.get("project") == contract.project and resource.get("region") == contract.region


def _is_enabled(value: object) -> bool | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "on", "1"}:
        return True
    if normalized in {"false", "off", "0", ""}:
        return False
    return None


def evaluate_snapshot(snapshot: object) -> Evaluation:
    reasons: list[str] = []
    root = _mapping(snapshot)
    if root is None or root.get("schema_version") != 1:
        return Evaluation(STATUS_UNKNOWN, _empty_counts(), ("snapshot_malformed",))
    identity = _mapping(root.get("identity"))
    inventories = _mapping(root.get("inventories"))
    if identity is None or inventories is None:
        return Evaluation(STATUS_UNKNOWN, _empty_counts(), ("snapshot_malformed",))

    project = identity.get("project")
    region = identity.get("region")
    cloud_run_job = identity.get("cloud_run_job")
    scheduler_job = identity.get("scheduler_job")
    if (
        not isinstance(project, str)
        or not project
        or not isinstance(region, str)
        or not region
        or not isinstance(cloud_run_job, str)
        or not cloud_run_job
        or not isinstance(scheduler_job, str)
        or not scheduler_job
    ):
        return Evaluation(STATUS_UNKNOWN, _empty_counts(), ("identity_malformed",))
    contract = Contract(
        project=project,
        region=region,
        cloud_run_job=cloud_run_job,
        scheduler_job=scheduler_job,
    )
    if contract.cloud_run_job != EXPECTED_CLOUD_RUN_JOB or contract.scheduler_job != EXPECTED_SCHEDULER_JOB:
        reasons.append("expected_resource_identity_mismatch")

    jobs = _resources(inventories, "cloud_run_jobs", reasons)
    executions = _resources(inventories, "executions", reasons)
    schedulers = _resources(inventories, "scheduler_jobs", reasons)

    matching_jobs = [resource for resource in jobs if resource.get("name") == contract.cloud_run_job]
    matching_executions = [resource for resource in executions if resource.get("job") == contract.cloud_run_job]
    matching_schedulers = [resource for resource in schedulers if resource.get("name") == contract.scheduler_job]

    if len(matching_jobs) > 1:
        reasons.append("duplicate_cloud_run_job")
    if len(matching_schedulers) > 1:
        reasons.append("duplicate_scheduler_job")
    execution_names = [resource.get("name") for resource in matching_executions]
    if any(not isinstance(name, str) or not name for name in execution_names):
        reasons.append("execution_identity_malformed")
    elif len(execution_names) != len(set(execution_names)):
        reasons.append("duplicate_execution")

    for resource in matching_jobs + matching_executions + matching_schedulers:
        if not _identity_matches(resource, contract):
            reasons.append("resource_project_or_region_mismatch")

    active_flags = 0
    if matching_jobs:
        env = _mapping(matching_jobs[0].get("env"))
        if env is None or "MEMORY_CANONICAL_MAINTENANCE_ENABLED" not in env:
            reasons.append("maintenance_env_evidence_missing")
        else:
            for flag in MAINTENANCE_ENV_FLAGS:
                if flag not in env:
                    continue
                enabled = _is_enabled(env.get(flag))
                if enabled is None:
                    reasons.append("maintenance_env_value_malformed")
                elif enabled:
                    active_flags += 1

    active_executions = 0
    for execution in matching_executions:
        state = execution.get("state")
        if state in ACTIVE_EXECUTION_STATES:
            active_executions += 1
        elif state not in TERMINAL_EXECUTION_STATES:
            reasons.append("execution_state_unknown")

    enabled_schedulers = 0
    paused_schedulers = 0
    if matching_schedulers:
        scheduler = matching_schedulers[0]
        state = scheduler.get("state")
        if state not in KNOWN_SCHEDULER_STATES:
            reasons.append("scheduler_state_unknown")
        elif state == "ENABLED":
            enabled_schedulers += 1
        else:
            paused_schedulers += 1
        if scheduler.get("target_uri") != contract.scheduler_target_uri:
            reasons.append("scheduler_target_mismatch")

    counts = {
        "cloud_run_jobs": len(matching_jobs),
        "scheduler_jobs": len(matching_schedulers),
        "executions": len(matching_executions),
        "active_executions": active_executions,
        "enabled_schedulers": enabled_schedulers,
        "paused_schedulers": paused_schedulers,
        "active_maintenance_flags": active_flags,
    }
    if reasons:
        return Evaluation(STATUS_UNKNOWN, counts, tuple(sorted(set(reasons))))
    if active_flags or active_executions or enabled_schedulers:
        return Evaluation(STATUS_ACTIVE, counts, ("maintenance_runtime_active",))
    if not matching_jobs and not matching_schedulers:
        return Evaluation(STATUS_DELETED, counts, ("maintenance_resources_proven_absent",))
    return Evaluation(STATUS_NO_LIVE_ACTIVITY, counts, ("maintenance_resources_present_without_live_activity",))


def _empty_counts() -> dict[str, int]:
    return {
        "cloud_run_jobs": 0,
        "scheduler_jobs": 0,
        "executions": 0,
        "active_executions": 0,
        "enabled_schedulers": 0,
        "paused_schedulers": 0,
        "active_maintenance_flags": 0,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline memory-maintenance runtime retirement readiness evaluator")
    parser.add_argument("--snapshot", type=Path, required=True, help="Sanitized JSON snapshot to evaluate")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        evaluation = evaluate_snapshot(snapshot)
    except (OSError, UnicodeError, json.JSONDecodeError):
        evaluation = Evaluation(STATUS_UNKNOWN, _empty_counts(), ("snapshot_unreadable",))
    print(json.dumps(evaluation.as_dict(), sort_keys=True))
    return 0 if evaluation.status != STATUS_UNKNOWN else 2


if __name__ == "__main__":
    raise SystemExit(main())
