#!/usr/bin/env python3
"""Fail closed when Pusher rollout waits cannot cover the committed chart budget.

The Pusher deployment rolls several replicas in sequence. A healthy pod may
use its full startup, readiness, and minimum-ready allowance, so Kubernetes'
progress deadline and the ``kubectl rollout status`` wait must both cover every
wave at the HPA ceiling. This is intentionally stdlib-only because it runs in
the shared pre-push and repository-check lanes before backend dependencies are
installed.
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENTS = ("dev", "prod")
WORKFLOW_ENVIRONMENTS = {
    ".github/workflows/gcp_backend_pusher.yml": ("dev", "prod"),
    ".github/workflows/gcp_backend_pusher_auto_deploy.yml": ("dev",),
}
ROLLOUT_TIMEOUT_PATTERN = re.compile(
    r"rollout\s+status\s+deploy/\$\{\{\s*vars\.ENV\s*\}\}-omi-pusher\s+--timeout=(\d+)s"
)
PROGRESS_DEADLINE_TEMPLATE_PATTERN = re.compile(
    r"^  progressDeadlineSeconds:\s*\{\{[^}]*\.Values\.progressDeadlineSeconds\b[^}]*\}\}\s*$",
    re.MULTILINE,
)
MIN_READY_TEMPLATE_PATTERN = re.compile(
    r"^  minReadySeconds:\s*\{\{[^}]*\.Values\.minReadySeconds\b[^}]*\}\}\s*$", re.MULTILINE
)
MAPPING_ENTRY_PATTERN = re.compile(r"^(?P<indent> *)(?P<key>[^\s#][^:]*):(?:\s*(?P<value>.*))?$")


class ContractError(ValueError):
    """Raised when committed chart inputs cannot establish a safe budget."""


@dataclass(frozen=True)
class MappingEntry:
    line_number: int
    indent: int
    key: str
    value: str


@dataclass(frozen=True)
class RolloutBudget:
    environment: str
    replica_ceiling: int
    pods_in_flight: int
    waves: int
    startup_seconds_per_pod: int
    readiness_seconds_per_pod: int
    min_ready_seconds: int
    availability_seconds_per_pod: int
    required_seconds: int
    progress_deadline_seconds: int


def _strip_comment(value: str) -> str:
    """Return one simple scalar value without its trailing YAML comment."""

    return value.split("#", 1)[0].strip().strip("\"'")


def _mapping_entries(path: Path) -> list[MappingEntry]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ContractError(f"could not read {path}: {exc}") from exc

    entries: list[MappingEntry] = []
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        match = MAPPING_ENTRY_PATTERN.match(raw_line)
        if match is None:
            continue
        entries.append(
            MappingEntry(
                line_number=line_number,
                indent=len(match.group("indent")),
                key=match.group("key").strip(),
                value=_strip_comment(match.group("value") or ""),
            )
        )
    return entries


def _mapping_value(entries: list[MappingEntry], path: tuple[str, ...], source: Path) -> str:
    """Read a scalar from the small mapping-only subset used by rollout values.

    This deliberately does not become a general YAML parser.  The fields used
    here are scalar mappings, while using stdlib keeps this CI/pre-push guard
    available before PyYAML is installed.
    """

    start = 0
    end = len(entries)
    parent_indent = -1
    selected: MappingEntry | None = None

    for index, key in enumerate(path):
        children = [entry for entry in entries[start:end] if entry.indent > parent_indent]
        if not children:
            raise ContractError(f"{source}: missing mapping {'/'.join(path[:index])}")
        child_indent = min(entry.indent for entry in children)
        matches = [entry for entry in children if entry.indent == child_indent and entry.key == key]
        if len(matches) != 1:
            qualifier = "missing" if not matches else "ambiguous"
            raise ContractError(f"{source}: {qualifier} scalar {'/'.join(path[: index + 1])}")
        selected = matches[0]

        selected_index = entries.index(selected, start, end)
        start = selected_index + 1
        end = next(
            (
                candidate_index
                for candidate_index in range(start, end)
                if entries[candidate_index].indent <= selected.indent
            ),
            end,
        )
        parent_indent = selected.indent

    assert selected is not None
    if not selected.value:
        raise ContractError(f"{source}:{selected.line_number}: {'/'.join(path)} must be an explicit scalar")
    return selected.value


def _positive_int(value: str, *, field: str, source: Path) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ContractError(f"{source}: {field} must be an integer, got {value!r}") from exc
    if parsed <= 0:
        raise ContractError(f"{source}: {field} must be positive, got {parsed}")
    return parsed


def _nonnegative_int(value: str, *, field: str, source: Path) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ContractError(f"{source}: {field} must be an integer, got {value!r}") from exc
    if parsed < 0:
        raise ContractError(f"{source}: {field} must not be negative, got {parsed}")
    return parsed


def _int_or_percent(value: str, *, replicas: int, round_up: bool, field: str, source: Path) -> int:
    if value.endswith("%"):
        percent = _nonnegative_int(value[:-1], field=field, source=source)
        scaled = replicas * percent / 100
        return math.ceil(scaled) if round_up else math.floor(scaled)
    return _nonnegative_int(value, field=field, source=source)


def rollout_budget(root: Path, environment: str) -> RolloutBudget:
    """Derive a bounded healthy-rollout allowance from one values file.

    Readiness failures can continue indefinitely, so they cannot be converted
    into an honest finite rollout deadline. The bounded healthy envelope uses
    the committed readiness failure and success thresholds; an outage that
    exceeds that envelope remains a stalled rollout and should still fail.
    """

    values_path = root / "backend" / "charts" / "pusher" / f"{environment}_omi_pusher_values.yaml"
    entries = _mapping_entries(values_path)

    autoscaling_enabled = _mapping_value(entries, ("autoscaling", "enabled"), values_path).lower()
    if autoscaling_enabled not in {"true", "false"}:
        raise ContractError(f"{values_path}: autoscaling/enabled must be true or false")
    if autoscaling_enabled == "true":
        min_replicas = _positive_int(
            _mapping_value(entries, ("autoscaling", "minReplicas"), values_path),
            field="autoscaling/minReplicas",
            source=values_path,
        )
        replica_ceiling = _positive_int(
            _mapping_value(entries, ("autoscaling", "maxReplicas"), values_path),
            field="autoscaling/maxReplicas",
            source=values_path,
        )
        if replica_ceiling < min_replicas:
            raise ContractError(
                f"{values_path}: autoscaling/maxReplicas={replica_ceiling} must be at least minReplicas={min_replicas}"
            )
    else:
        replica_ceiling = _positive_int(
            _mapping_value(entries, ("replicaCount",), values_path),
            field="replicaCount",
            source=values_path,
        )

    strategy_type = _mapping_value(entries, ("strategy", "type"), values_path)
    if strategy_type != "RollingUpdate":
        raise ContractError(f"{values_path}: strategy/type must be RollingUpdate, got {strategy_type!r}")
    max_surge = _int_or_percent(
        _mapping_value(entries, ("strategy", "rollingUpdate", "maxSurge"), values_path),
        replicas=replica_ceiling,
        round_up=True,
        field="strategy/rollingUpdate/maxSurge",
        source=values_path,
    )
    max_unavailable = _int_or_percent(
        _mapping_value(entries, ("strategy", "rollingUpdate", "maxUnavailable"), values_path),
        replicas=replica_ceiling,
        round_up=False,
        field="strategy/rollingUpdate/maxUnavailable",
        source=values_path,
    )
    pods_in_flight = max_surge + max_unavailable
    if pods_in_flight <= 0:
        raise ContractError(f"{values_path}: RollingUpdate must allow at least one pod in flight")

    startup_failure_threshold = _positive_int(
        _mapping_value(entries, ("startupProbe", "failureThreshold"), values_path),
        field="startupProbe/failureThreshold",
        source=values_path,
    )
    startup_initial_delay_seconds = _nonnegative_int(
        _mapping_value(entries, ("startupProbe", "initialDelaySeconds"), values_path),
        field="startupProbe/initialDelaySeconds",
        source=values_path,
    )
    startup_period_seconds = _positive_int(
        _mapping_value(entries, ("startupProbe", "periodSeconds"), values_path),
        field="startupProbe/periodSeconds",
        source=values_path,
    )
    startup_timeout_seconds = _positive_int(
        _mapping_value(entries, ("startupProbe", "timeoutSeconds"), values_path),
        field="startupProbe/timeoutSeconds",
        source=values_path,
    )
    startup_seconds_per_pod = startup_initial_delay_seconds + startup_failure_threshold * max(
        startup_period_seconds, startup_timeout_seconds
    )

    readiness_failure_threshold = _positive_int(
        _mapping_value(entries, ("readinessProbe", "failureThreshold"), values_path),
        field="readinessProbe/failureThreshold",
        source=values_path,
    )
    readiness_initial_delay_seconds = _nonnegative_int(
        _mapping_value(entries, ("readinessProbe", "initialDelaySeconds"), values_path),
        field="readinessProbe/initialDelaySeconds",
        source=values_path,
    )
    readiness_period_seconds = _positive_int(
        _mapping_value(entries, ("readinessProbe", "periodSeconds"), values_path),
        field="readinessProbe/periodSeconds",
        source=values_path,
    )
    readiness_success_threshold = _positive_int(
        _mapping_value(entries, ("readinessProbe", "successThreshold"), values_path),
        field="readinessProbe/successThreshold",
        source=values_path,
    )
    readiness_timeout_seconds = _positive_int(
        _mapping_value(entries, ("readinessProbe", "timeoutSeconds"), values_path),
        field="readinessProbe/timeoutSeconds",
        source=values_path,
    )
    readiness_seconds_per_pod = readiness_initial_delay_seconds + (
        readiness_failure_threshold + readiness_success_threshold
    ) * max(readiness_period_seconds, readiness_timeout_seconds)
    min_ready_seconds = _nonnegative_int(
        _mapping_value(entries, ("minReadySeconds",), values_path),
        field="minReadySeconds",
        source=values_path,
    )
    availability_seconds_per_pod = startup_seconds_per_pod + readiness_seconds_per_pod + min_ready_seconds
    waves = math.ceil(replica_ceiling / pods_in_flight)
    required_seconds = waves * availability_seconds_per_pod
    progress_deadline_seconds = _positive_int(
        _mapping_value(entries, ("progressDeadlineSeconds",), values_path),
        field="progressDeadlineSeconds",
        source=values_path,
    )

    return RolloutBudget(
        environment=environment,
        replica_ceiling=replica_ceiling,
        pods_in_flight=pods_in_flight,
        waves=waves,
        startup_seconds_per_pod=startup_seconds_per_pod,
        readiness_seconds_per_pod=readiness_seconds_per_pod,
        min_ready_seconds=min_ready_seconds,
        availability_seconds_per_pod=availability_seconds_per_pod,
        required_seconds=required_seconds,
        progress_deadline_seconds=progress_deadline_seconds,
    )


def validate_template(root: Path) -> list[str]:
    template = root / "backend" / "charts" / "pusher" / "templates" / "deployment.yaml"
    try:
        text = template.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"could not read {template}: {exc}"]
    errors: list[str] = []
    if not MIN_READY_TEMPLATE_PATTERN.search(text):
        errors.append(f"{template}: Deployment spec must render minReadySeconds from .Values.minReadySeconds")
    if not PROGRESS_DEADLINE_TEMPLATE_PATTERN.search(text):
        errors.append(
            f"{template}: Deployment spec must render progressDeadlineSeconds from .Values.progressDeadlineSeconds"
        )
    return errors


def validate_probe_and_drain_contract(root: Path) -> list[str]:
    """Fail closed on probe routing and BackendConfig drain regressions.

    readinessProbe must point at /ready so a drain flips LB readiness without
    restarting the pod; liveness/startup stay on /health. The BackendConfig
    must render connectionDraining and its timeout must fit inside the pod
    termination grace window so the LB drains before SIGTERM.
    """

    errors: list[str] = []
    for environment in ENVIRONMENTS:
        values_path = root / "backend" / "charts" / "pusher" / f"{environment}_omi_pusher_values.yaml"
        try:
            entries = _mapping_entries(values_path)
        except ContractError as exc:
            errors.append(str(exc))
            continue

        for probe, expected in (
            ("readinessProbe", "/ready"),
            ("livenessProbe", "/health"),
            ("startupProbe", "/health"),
        ):
            try:
                actual = _mapping_value(entries, (probe, "httpGet", "path"), values_path)
            except ContractError as exc:
                errors.append(str(exc))
                continue
            if actual != expected:
                errors.append(f"{values_path}: {probe}/httpGet/path must be {expected!r}, got {actual!r}")

        try:
            grace = _nonnegative_int(
                _mapping_value(entries, ("terminationGracePeriodSeconds",), values_path),
                field="terminationGracePeriodSeconds",
                source=values_path,
            )
            drain = _positive_int(
                _mapping_value(entries, ("backendConfig", "connectionDraining", "drainingTimeoutSec"), values_path),
                field="backendConfig/connectionDraining/drainingTimeoutSec",
                source=values_path,
            )
        except ContractError as exc:
            errors.append(str(exc))
            continue
        if drain > grace:
            errors.append(
                f"{values_path}: connectionDraining.drainingTimeoutSec={drain}s must be <= "
                f"terminationGracePeriodSeconds={grace}s"
            )

    template = root / "backend" / "charts" / "pusher" / "templates" / "backendconfig.yaml"
    try:
        text = template.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"could not read {template}: {exc}")
        return errors
    if not re.search(r"connectionDraining:\s*\n\s*drainingTimeoutSec:\s*\{\{", text):
        errors.append(f"{template}: BackendConfig must render connectionDraining.drainingTimeoutSec from .Values")
    # The BackendConfig healthCheck MUST stay on /health (liveness semantics).
    # Routing it to /ready would flip the backend unhealthy during a readiness
    # drain, defeating connectionDraining so the LB cuts in-flight WS at once.
    if not re.search(r"requestPath:\s*/health\b", text) or re.search(r"requestPath:\s*/ready\b", text):
        errors.append(
            f"{template}: BackendConfig healthCheck.requestPath must render to /health "
            "(liveness semantics); routing it to /ready flips the backend unhealthy during "
            "drain and defeats connectionDraining"
        )
    return errors


def workflow_timeout_seconds(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"could not read {path}: {exc}") from exc
    found = [int(value) for value in ROLLOUT_TIMEOUT_PATTERN.findall(text)]
    if len(found) != 1:
        raise ContractError(f"{path}: expected exactly one numeric Pusher rollout status timeout, found {len(found)}")
    return found[0]


def validate(root: Path = ROOT) -> list[str]:
    """Return every static contract violation for chart and workflow changes."""

    errors = validate_template(root)
    errors.extend(validate_probe_and_drain_contract(root))
    budgets: dict[str, RolloutBudget] = {}
    for environment in ENVIRONMENTS:
        try:
            budget = rollout_budget(root, environment)
        except ContractError as exc:
            errors.append(str(exc))
            continue
        budgets[environment] = budget
        if budget.progress_deadline_seconds < budget.required_seconds:
            errors.append(
                f"{environment} Pusher progressDeadlineSeconds={budget.progress_deadline_seconds}s is below the "
                f"{budget.required_seconds}s healthy rollout budget ({budget.waves} waves x "
                f"{budget.availability_seconds_per_pod}s availability allowance)"
            )

    for relative_path, environments in WORKFLOW_ENVIRONMENTS.items():
        path = root / relative_path
        try:
            timeout_seconds = workflow_timeout_seconds(path)
        except ContractError as exc:
            errors.append(str(exc))
            continue
        required_seconds = max(
            (budgets[environment].required_seconds for environment in environments if environment in budgets), default=0
        )
        if not required_seconds:
            continue
        if timeout_seconds < required_seconds:
            environment_label = ", ".join(environments)
            errors.append(
                f"{relative_path}: Pusher rollout timeout={timeout_seconds}s is below the {required_seconds}s "
                f"healthy rollout budget for {environment_label}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root (for hermetic fixture tests).")
    args = parser.parse_args()
    root = args.root.resolve()

    errors = validate(root)
    if errors:
        print("FAIL: Pusher rollout readiness budget")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK: Pusher rollout readiness budget is covered.")
    for environment in ENVIRONMENTS:
        budget = rollout_budget(root, environment)
        print(
            f"- {environment}: {budget.waves} waves x {budget.availability_seconds_per_pod}s "
            f"({budget.startup_seconds_per_pod}s startup + {budget.readiness_seconds_per_pod}s readiness + "
            f"{budget.min_ready_seconds}s min-ready) = {budget.required_seconds}s; progress deadline "
            f"{budget.progress_deadline_seconds}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
