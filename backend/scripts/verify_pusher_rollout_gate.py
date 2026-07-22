#!/usr/bin/env python3
"""Static + contract preflight that fails closed when a Pusher rollout cannot be
verified safe, plus a rollback CONTRACT (capture-and-print, never execute).

This gate is intentionally read-only: it scans the chart and metrics source to
confirm the rollout contract holds *before* any deploy.  It performs no deploy,
no rollback execution, and no cluster mutation.

**preflight** checks (fail closed):
  1. capacity headroom: PDB minAvailable, HPA minReplicas, RollingUpdate
     maxUnavailable<=1 / maxSurge>=1, terminationGracePeriodSeconds >=
     BackendConfig drainingTimeoutSec.
  2. image identity: tag mode delegates the tag to the deploy workflow; a digest
     pin (build-once promotion) must be exact ``sha256:<hex>`` with the mutable
     tag dropped and ``pullPolicy: IfNotPresent``.
  3. readiness/health split: readinessProbe → /ready, liveness/startup →
     /health, BackendConfig connectionDraining present.
  4. telemetry fail-closed: each rollout-blocking metric must be DEFINED in
     backend/utils/metrics.py (static scan, not live scrape).

**rollback** emits the rollback contract as structured JSON (read-only capture,
never execution).

Run as::

  python -m backend.scripts.verify_pusher_rollout_gate preflight
  python -m backend.scripts.verify_pusher_rollout_gate rollback --env prod
  python3  backend/scripts/verify_pusher_rollout_gate.py preflight

Stdlib-only: runs in the shared pre-push lane before backend dependencies are
installed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENTS = ("dev", "prod")

# ponytail: re-scan chart values locally rather than importing Lane B's
# verify_pusher_rollout_budget helpers.  Lane B's script is standalone and
# invoked via runpy in tests; importing it at module level breaks script-mode
# execution.  The YAML mapping helpers are ~40 lines and kept in sync by the
# regression tests below.  Re-deriving here is defense-in-depth: if Lane B's
# verifier drifts, this gate still catches the regression independently.

MAPPING_ENTRY_PATTERN = re.compile(r"^(?P<indent> *)(?P<key>[^\s#][^:]*):(?:\s*(?P<value>.*))?$")
DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


class ContractError(ValueError):
    """Raised when chart or telemetry inputs violate the rollout contract."""


@dataclass(frozen=True)
class MappingEntry:
    line_number: int
    indent: int
    key: str
    value: str


# Metrics whose DEFINITION in backend/utils/metrics.py is rollout-blocking.
# Missing any one of these means we cannot observe a drain or a stuck rollout.
ROLLOUT_BLOCKING_METRICS = (
    "pusher_active_ws_connections",
    "pusher_ready",
    "pusher_drain_in_progress",
    "omi_journey_terminal_total",
    "pusher_sessions_degraded",
)

# Kubernetes default when revisionHistoryLimit is unset in the Deployment spec.
DEFAULT_REVISION_HISTORY_LIMIT = 10


# ---------------------------------------------------------------------------
# YAML mapping helpers (mirrors the subset in verify_pusher_rollout_budget.py)
# ---------------------------------------------------------------------------


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
    """Read a scalar from the small mapping-only subset used by rollout values."""

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


def _try_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Preflight sub-checks
# ---------------------------------------------------------------------------


def _draining_timeout_seconds(entries: list[MappingEntry], source: Path) -> int | None:
    """Read BackendConfig drainingTimeoutSec from the chart values mapping.

    Lane B renders this from ``backendConfig.connectionDraining.drainingTimeoutSec``
    in both values files.  When absent (connectionDraining not yet added) return
    None — the connectionDraining-presence check handles that case separately.
    """

    try:
        raw = _mapping_value(entries, ("backendConfig", "connectionDraining", "drainingTimeoutSec"), source)
    except ContractError:
        return None
    return _try_int(raw)


def validate_capacity_headroom(root: Path) -> list[str]:
    """Capacity headroom: PDB, HPA floor, gradual RollingUpdate, grace >= drain."""

    errors: list[str] = []
    for env in ENVIRONMENTS:
        values = root / "backend" / "charts" / "pusher" / f"{env}_omi_pusher_values.yaml"
        try:
            entries = _mapping_entries(values)
        except ContractError as exc:
            errors.append(str(exc))
            continue

        # --- PDB minAvailable ---
        try:
            _mapping_value(entries, ("podDisruptionBudget", "minAvailable"), values)
        except ContractError:
            errors.append(
                f"{values}: podDisruptionBudget/minAvailable must be present for voluntary-disruption headroom"
            )

        # --- HPA minReplicas (when autoscaling enabled) ---
        try:
            autoscaling_enabled = _mapping_value(entries, ("autoscaling", "enabled"), values).lower()
            if autoscaling_enabled == "true":
                _mapping_value(entries, ("autoscaling", "minReplicas"), values)
        except ContractError:
            errors.append(f"{values}: autoscaling/minReplicas must be present when autoscaling is enabled")

        # --- RollingUpdate maxUnavailable <= 1, maxSurge >= 1 ---
        try:
            strategy_type = _mapping_value(entries, ("strategy", "type"), values)
            if strategy_type != "RollingUpdate":
                errors.append(f"{values}: strategy/type must be RollingUpdate, got {strategy_type!r}")
            max_unavailable_raw = _mapping_value(entries, ("strategy", "rollingUpdate", "maxUnavailable"), values)
            max_surge_raw = _mapping_value(entries, ("strategy", "rollingUpdate", "maxSurge"), values)
            # ponytail: integer-only check; percentage maxUnavailable/maxSurge
            # would need replica-count context (deferred — current chart uses ints).
            mu = _try_int(max_unavailable_raw)
            ms = _try_int(max_surge_raw)
            if mu is not None and mu > 1:
                errors.append(f"{values}: strategy/rollingUpdate/maxUnavailable={mu} must be <= 1 for gradual rollout")
            if ms is not None and ms < 1:
                errors.append(f"{values}: strategy/rollingUpdate/maxSurge={ms} must be >= 1 for surge capacity")
        except ContractError as exc:
            errors.append(str(exc))

        # --- terminationGracePeriodSeconds >= drainingTimeoutSec ---
        try:
            grace = _try_int(_mapping_value(entries, ("terminationGracePeriodSeconds",), values))
        except ContractError:
            grace = None
        draining = _draining_timeout_seconds(entries, values)
        if grace is not None and draining is not None and draining > grace:
            errors.append(
                f"{values}: BackendConfig drainingTimeoutSec={draining}s must not exceed "
                f"terminationGracePeriodSeconds={grace}s"
            )
    return errors


def _optional_scalar(entries: list[MappingEntry], path: tuple[str, ...], source: Path) -> str | None:
    """Return a scalar value, or None when the key is absent/empty."""
    try:
        return _mapping_value(entries, path, source)
    except ContractError:
        return None


def validate_image_identity(root: Path) -> list[str]:
    """Build-once promotion contract for image identity.

    Tag mode (default): ``repository:tag``; the chart delegates the tag to the
    deploy workflow (``tag: ""`` is INFO, not a failure).
    Digest mode (promotion): ``repository@sha256:<hex>`` — the immutable content
    address. A digest-pinned release must drop the mutable tag and pin
    ``pullPolicy: IfNotPresent`` (a digest is already the content address, so an
    ``Always`` round-trip is pointless). Malformed/ambiguous identity fails.
    """
    errors: list[str] = []
    for env in ENVIRONMENTS:
        values = root / "backend" / "charts" / "pusher" / f"{env}_omi_pusher_values.yaml"
        try:
            entries = _mapping_entries(values)
        except ContractError as exc:
            errors.append(str(exc))
            continue
        repository = _optional_scalar(entries, ("image", "repository"), values)
        if repository is None:
            errors.append(f"{values}: image/repository is required")
            continue
        digest = _optional_scalar(entries, ("image", "digest"), values)
        if digest is None:
            continue  # tag mode: the chart delegates the tag to the deploy workflow.
        if not DIGEST_RE.fullmatch(digest):
            errors.append(
                f"{values}: image/digest must be sha256:<64 lowercase hex>; "
                f"rejecting ambiguous/mutable identity {digest!r}"
            )
        if _optional_scalar(entries, ("image", "tag"), values) is not None:
            errors.append(f"{values}: image/tag must be empty when image/digest pins the release")
        if _optional_scalar(entries, ("image", "pullPolicy"), values) != "IfNotPresent":
            errors.append(
                f"{values}: image/pullPolicy must be IfNotPresent for a digest-pinned release "
                "(the digest is the content address; Always only adds a registry round-trip)"
            )
    return errors


def validate_probe_split(root: Path) -> list[str]:
    """readinessProbe → /ready, liveness/startup → /health, connectionDraining present."""

    errors: list[str] = []
    for env in ENVIRONMENTS:
        values = root / "backend" / "charts" / "pusher" / f"{env}_omi_pusher_values.yaml"
        try:
            entries = _mapping_entries(values)
        except ContractError as exc:
            errors.append(str(exc))
            continue

        try:
            readiness_path = _mapping_value(entries, ("readinessProbe", "httpGet", "path"), values)
            if readiness_path != "/ready":
                errors.append(
                    f"{values}: readinessProbe/httpGet/path must be '/ready' for graceful drain, got {readiness_path!r}"
                )
        except ContractError:
            errors.append(f"{values}: readinessProbe/httpGet/path must be '/ready'")

        try:
            liveness_path = _mapping_value(entries, ("livenessProbe", "httpGet", "path"), values)
            if liveness_path != "/health":
                errors.append(f"{values}: livenessProbe/httpGet/path must be '/health', got {liveness_path!r}")
        except ContractError:
            errors.append(f"{values}: livenessProbe/httpGet/path must be '/health'")

        try:
            startup_path = _mapping_value(entries, ("startupProbe", "httpGet", "path"), values)
            if startup_path != "/health":
                errors.append(f"{values}: startupProbe/httpGet/path must be '/health', got {startup_path!r}")
        except ContractError:
            errors.append(f"{values}: startupProbe/httpGet/path must be '/health'")

    # --- connectionDraining in the BackendConfig template ---
    template = root / "backend" / "charts" / "pusher" / "templates" / "backendconfig.yaml"
    try:
        template_text = template.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"could not read {template}: {exc}")
    else:
        if "connectionDraining" not in template_text:
            errors.append(
                f"{template}: BackendConfig must define connectionDraining for graceful WS drain "
                "(LB keeps in-flight connections alive during endpoint removal)"
            )
        # The healthCheck MUST stay on /health (liveness semantics). Routing it to
        # /ready flips the backend unhealthy during a drain and defeats connectionDraining.
        if not re.search(r"requestPath:\s*/health\b", template_text) or re.search(
            r"requestPath:\s*/ready\b", template_text
        ):
            errors.append(
                f"{template}: BackendConfig healthCheck.requestPath must render to /health "
                "(liveness semantics); routing it to /ready defeats connectionDraining"
            )
    return errors


def validate_telemetry(root: Path) -> list[str]:
    """Each rollout-blocking metric must be DEFINED in metrics.py (static scan).

    Missing telemetry = the rollout cannot be observed; fail closed rather than
    proceeding blind.
    """

    metrics_path = root / "backend" / "utils" / "metrics.py"
    try:
        text = metrics_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"could not read {metrics_path}: {exc}"]

    errors: list[str] = []
    for metric in ROLLOUT_BLOCKING_METRICS:
        # Search for the metric name as a quoted string literal.
        if not re.search(rf"['\"]({re.escape(metric)})['\"]", text):
            errors.append(
                f"{metrics_path}: rollout-blocking metric '{metric}' is not defined — "
                "missing telemetry blocks the rollout"
            )
    return errors


def validate_preflight(root: Path = ROOT) -> list[str]:
    """Return every static + contract violation that would block a safe rollout."""

    errors: list[str] = []
    errors.extend(validate_capacity_headroom(root))
    errors.extend(validate_image_identity(root))
    errors.extend(validate_probe_split(root))
    errors.extend(validate_telemetry(root))
    return errors


# ---------------------------------------------------------------------------
# Rollback contract (read-only capture, never execution)
# ---------------------------------------------------------------------------


def _chart_revision_history_limit(root: Path) -> int | None:
    """Return the chart's revisionHistoryLimit if set in the Deployment template."""

    template = root / "backend" / "charts" / "pusher" / "templates" / "deployment.yaml"
    try:
        text = template.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^\s*revisionHistoryLimit:\s*(\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class RollbackContract:
    """Read-only rollback contract emitted as structured JSON."""

    environment: str
    revision_history_limit: int
    revision_history_source: str
    prior_restore: str
    capture_command: str
    restore_command: str
    traffic_rollback: str
    data_rollback: str
    note: str

    def as_dict(self) -> dict:
        return {
            "environment": self.environment,
            "revision_history_limit": self.revision_history_limit,
            "revision_history_source": self.revision_history_source,
            "prior_restore": self.prior_restore,
            "capture_command": self.capture_command,
            "restore_command": self.restore_command,
            "traffic_rollback": self.traffic_rollback,
            "data_rollback": self.data_rollback,
            "note": self.note,
        }


def rollback_contract(root: Path = ROOT, environment: str = "prod") -> RollbackContract:
    """Build the read-only rollback contract for one environment.

    This NEVER mutates cluster, registry, or repo state.  It captures the
    procedure the operator must follow, including the prior-image-restore step
    captured at runtime (a future workflow may record it automatically).
    """

    chart_limit = _chart_revision_history_limit(root)
    if chart_limit is not None:
        revision_history_limit = chart_limit
        revision_history_source = f"chart sets revisionHistoryLimit={chart_limit} in deployment.yaml"
    else:
        revision_history_limit = DEFAULT_REVISION_HISTORY_LIMIT
        revision_history_source = (
            f"chart does not set revisionHistoryLimit; Kubernetes default ({DEFAULT_REVISION_HISTORY_LIMIT}) applies. "
            "Prior ReplicaSets are retained for rollback."
        )

    release = f"{environment}-omi-pusher"
    return RollbackContract(
        environment=environment,
        revision_history_limit=revision_history_limit,
        revision_history_source=revision_history_source,
        prior_restore=(
            "The prior image tag/digest to restore is the currently-deployed one. "
            "It must be captured at runtime by the operator BEFORE the rollout "
            "(not by this static script)."
        ),
        capture_command=(
            f"kubectl get deployment {release} " f"-o jsonpath='{{.spec.template.spec.containers[0].image}}'"
        ),
        restore_command=(
            f"helm upgrade --install {release} ./backend/charts/pusher "
            f"-f backend/charts/pusher/{environment}_omi_pusher_values.yaml "
            "--set image.tag=<prior-tag>   # tag mode\n"
            "      # OR, for a digest-pinned release (build-once promotion):\n"
            "      # --set image.digest=sha256:<prior-digest> --set image.tag= --set image.pullPolicy=IfNotPresent"
        ),
        traffic_rollback=(
            "Traffic/runtime rollback (Helm upgrade to the prior immutable tag) is SAFE and always available. "
            "The LB cuts existing WebSocket sessions on endpoint removal; backend-listen reconnects "
            "within a bounded ~1-60s gap per affected session. New connections are served immediately."
        ),
        data_rollback=(
            "Data changes (Firestore writes, Redis state, file-system mutations) are IRREVERSIBLE. "
            "They must NEVER be auto-rolled-back. Verify data integrity manually after a runtime rollback."
        ),
        note=(
            "This contract is read-only. It captures the procedure; it does not execute any rollback, "
            "deploy, digest copy, or cluster mutation."
        ),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", nargs="?", default="preflight", choices=("preflight", "rollback"))
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root (for hermetic fixture tests).")
    parser.add_argument("--env", choices=ENVIRONMENTS, default="prod", help="Environment for rollback contract.")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.mode == "rollback":
        contract = rollback_contract(root, args.env)
        print(json.dumps(contract.as_dict(), indent=2))
        return 0

    # preflight (default)
    errors = validate_preflight(root)
    if errors:
        print("FAIL: Pusher rollout quality gate", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("OK: Pusher rollout quality gate passed.")
    for env in ENVIRONMENTS:
        values = root / "backend" / "charts" / "pusher" / f"{env}_omi_pusher_values.yaml"
        try:
            entries = _mapping_entries(values)
        except ContractError:
            continue
        # tag: "" is valid — the chart delegates to the deploy workflow. Report as INFO.
        tag = ""
        try:
            tag = _mapping_value(entries, ("image", "tag"), values)
        except ContractError:
            pass
        if not tag:
            print(f"- {env}: image/tag is empty — INFO only (chart delegates to deploy workflow per .github/AGENTS.md)")
        else:
            print(f"- {env}: image/tag={tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
