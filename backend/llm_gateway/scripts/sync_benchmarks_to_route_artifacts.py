"""Sync benchmarks.json -> route_artifacts.proposed.yaml.

R1 of the auto-router-on-LLM-gateway feature (see PLAN.md). Reads benchmarks
(either via the cherry-picked BenchmarksFetcher or from a local file via
--benchmarks), scores every R0 lane's candidate models against the lane's
declared objective, and emits top-3 picks per lane to a `proposed` YAML
file next to `route_artifacts.yaml`. NEVER edits `route_artifacts.yaml`
directly -- a human (or the R4 cron) lands the diff via PR.

This script is part of the artifact-emission path (offline, scheduled),
NOT the request path. The gateway's executor never imports from here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml

# Private scoring -- emitted artifacts depend on these formulas, but the
# gateway's request path does NOT. This is intentional (see PLAN.md §R5a).
from llm_gateway.gateway._private.scoring import ModelSpec, TaskSpec, score
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.schemas import (
    BenchmarkSource,
    Evidence,
    FailureClass,
    FallbackPolicy,
    ProviderRef,
    RetryPolicy,
    RolloutPolicy,
    RolloutStage,
    RouteArtifact,
    TimeoutPolicy,
)

logger = logging.getLogger(__name__)


# Lane -> v3 task mapping (see .aidlc/spec.md lane-table).
# R0 added 15 new lanes; v3 covers 5 of them. The other 11 are skipped
# with a warning -- the emitter does NOT synthesize fake models.
LANE_TO_V3_TASK: dict[str, str] = {
    "omi:auto:realtime-ptt": "ptt_response",
    "omi:auto:screenshot-understanding": "screenshot_understanding",
    "omi:auto:screenshot-embedding": "screenshot_embedding",
    "omi:auto:general-assistant": "general_assistant",
    "omi:auto:transcription": "transcription",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _objective_to_taskspec(objective, task_name: str) -> TaskSpec:
    """Build a TaskSpec from a LaneConfig.objective (Omi-owned weights)."""
    return TaskSpec(
        name=task_name,
        quality_weight=objective.quality,
        latency_weight=objective.latency,
        cost_weight=objective.cost,
        description=f"Lane objective for {task_name}",
    )


def _modelspec_from_dict(d: dict) -> ModelSpec:
    """Build a ModelSpec from a v3-format candidate dict.

    Defensive validation per the sibling scoring module's posture (v3's
    TaskSpec rejects bool weights with TypeError). Without this guard,
    isinstance(True, int) is True and a bool quality_score would silently
    become 1.0 / 0.0, distorting the score. We also reject non-numeric
    scores (strings, lists, None already handled by ModelSpec's Optional).

    Raises:
        ValueError: if the candidate is missing required fields, has a bool
            score, or has a non-numeric score.
    """
    if "id" not in d or not isinstance(d["id"], str) or not d["id"]:
        raise ValueError(f"benchmark candidate missing non-empty 'id': {d!r}")
    if "provider" not in d or not isinstance(d["provider"], str) or not d["provider"]:
        raise ValueError(f"benchmark candidate {d.get('id')!r} missing non-empty 'provider': {d!r}")

    model_id = d["id"]
    for key in ("quality_score", "latency_score", "cost_score"):
        v = d.get(key)
        if v is None:
            continue
        # bool check MUST come first (bool is a subclass of int in Python)
        if isinstance(v, bool):
            raise ValueError(f"benchmark candidate {model_id!r} has bool {key}={v}; expected float")
        if not isinstance(v, (int, float)):
            raise ValueError(f"benchmark candidate {model_id!r} has non-numeric {key}={v!r}; expected float")

    return ModelSpec(
        id=d["id"],
        quality_score=d.get("quality_score"),
        latency_score=d.get("latency_score"),
        cost_score=d.get("cost_score"),
        provider=d.get("provider", ""),
    )


def _route_id_for(lane_id: str, today: date) -> str:
    """route.<capability>.<YYYY_MM_DD>.001 — matches R0's id pattern."""
    capability = lane_id[len("omi:auto:") :].replace("-", "_")
    return f"route.{capability}.{today.strftime('%Y_%m_%d')}.001"


def _benchmark_snapshot_hash(benchmarks: dict) -> str:
    """sha256 of the canonical JSON of the benchmarks payload."""
    canonical = json.dumps(benchmarks, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


# ---------------------------------------------------------------------------
# Core emission (T-003)
# ---------------------------------------------------------------------------


def load_benchmarks(path: Path) -> dict:
    """Load benchmarks JSON from a local file. The R1 emitter uses this for
    tests + CI; the R4 cron can call this OR the cherry-picked BenchmarksFetcher.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def emit_for_lane(
    lane,
    candidates: Iterable[dict],
    *,
    today: date | None = None,
    benchmark_snapshot: str,
    eval_report_id: str,
) -> RouteArtifact:
    """Score `candidates` against `lane.objective`, return a RouteArtifact.

    Top scorer becomes `primary`; next 2 become `fallbacks`.
    Tie-break by model.id ascending for determinism.

    Raises:
        ValueError: if `candidates` is empty (caller's responsibility to skip).
    """
    candidates_list = list(candidates)
    if not candidates_list:
        raise ValueError(f"no candidates for lane {lane.lane_id}")

    task_name = LANE_TO_V3_TASK.get(str(lane.lane_id), str(lane.lane_id))
    task = _objective_to_taskspec(lane.objective, task_name)

    scored: list[tuple[float, str, dict]] = []
    for c in candidates_list:
        m = _modelspec_from_dict(c)
        s = score(m, task)
        scored.append((s, c["id"], c))
    # Sort: score DESC, then id ASC (deterministic tie-break)
    scored.sort(key=lambda t: (-t[0], t[1]))

    winner = scored[0][2]
    fallbacks = [s[2] for s in scored[1:3]]

    return RouteArtifact(
        route_artifact_id=_route_id_for(lane.lane_id, today or _today_utc()),
        lane_id=lane.lane_id,
        surface=lane.surface,
        primary=ProviderRef(provider=winner["provider"], model=winner["id"]),
        fallbacks=[ProviderRef(provider=f["provider"], model=f["id"]) for f in fallbacks],
        timeouts=TimeoutPolicy(request_ms=8000),
        retry=RetryPolicy(max_attempts=1),
        capabilities=lane.capabilities,
        evidence=Evidence(
            benchmark_snapshot=benchmark_snapshot,
            eval_report=eval_report_id,
            benchmark_source=BenchmarkSource.EXTERNAL_BENCHMARK,
            dev_only=False,
        ),
        rollout=RolloutPolicy(stage=RolloutStage.SHADOW, percent=0),
        credential_policy=lane.credential_policy,
        fallback_policy=FallbackPolicy(
            fallback_on=[
                FailureClass.TIMEOUT_BEFORE_OUTPUT,
                FailureClass.PROVIDER_429_OMI_PAID,
                FailureClass.PROVIDER_5XX_OMI_PAID,
            ],
            never_fallback_on=[
                FailureClass.BYOK_AUTH,
                FailureClass.BYOK_QUOTA,
                FailureClass.BYOK_RATE_LIMIT,
                FailureClass.BYOK_UNSUPPORTED_PROVIDER,
                FailureClass.MISSING_BYOK_KEY,
                FailureClass.CAPABILITY_MISMATCH,
                FailureClass.INVALID_CONFIG,
            ],
        ),
    )


def emit_all(
    benchmarks: dict,
    *,
    today: date | None = None,
) -> tuple[list[RouteArtifact], list[str]]:
    """Emit one RouteArtifact per lane that has v3 coverage.

    Returns (artifacts, warnings) -- warnings list the lanes that were skipped.
    Lanes without v3 coverage keep their R0 hand-curated (model, provider)
    until a future emitter iteration (or v3 itself) covers them.
    """
    cfg = load_gateway_config()
    snapshot = _benchmark_snapshot_hash(benchmarks)
    artifacts: list[RouteArtifact] = []
    warnings: list[str] = []
    for lane_id, lane in sorted(cfg.lanes.items()):
        task_name = LANE_TO_V3_TASK.get(lane_id)
        if task_name is None:
            warnings.append(f"{lane_id}: no v3 task mapping, skipping")
            continue
        candidates = benchmarks.get("models", {}).get(task_name, [])
        if not candidates:
            warnings.append(f"{lane_id}: v3 task {task_name!r} has no candidates, skipping")
            continue
        try:
            art = emit_for_lane(
                lane,
                candidates,
                today=today,
                benchmark_snapshot=snapshot,
                eval_report_id=f"eval.{task_name}.v1",
            )
            artifacts.append(art)
        except ValueError as e:
            warnings.append(f"{lane_id}: {e}")
    return artifacts, warnings


def write_proposed_yaml(artifacts: list[RouteArtifact], path: Path) -> None:
    """Write the proposed YAML. NEVER writes to `route_artifacts.yaml`.

    The path is rejected via if/raise (NOT assert) because `assert` is stripped
    under Python's -O optimization flag. The emitter's safety contract (the PR
    is the decision, per PLAN.md §R4 gate) must hold regardless of optimization.

    Each artifact is dumped with its computed `content_digest` baked into the
    `artifact_digest` field (matches the R0 hand-curated format). The loader
    validates that `artifact_digest` matches the sha256 of the body on load,
    so this is required for the proposed YAML to be loadable as-is.
    """
    if path.name == "route_artifacts.yaml":
        raise ValueError(f"emitter must not edit route_artifacts.yaml directly (got {path})")
    payload = {"route_artifacts": []}
    for a in artifacts:
        body = a.model_dump(mode="json", exclude={"content_digest", "artifact_digest"})
        body["artifact_digest"] = a.content_digest
        payload["route_artifacts"].append(body)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False, width=120),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI (T-004)
# ---------------------------------------------------------------------------


def _emit_for_lane_id(
    lane_id: str,
    benchmarks: dict,
    *,
    today: date | None = None,
) -> RouteArtifact | None:
    """Emit one artifact for a single lane. Returns None if the lane has no
    v3 coverage or no candidates (caller surfaces a warning to stderr).
    """
    cfg = load_gateway_config()
    if lane_id not in cfg.lanes:
        raise ValueError(f"unknown lane {lane_id}")
    lane = cfg.lanes[lane_id]
    task_name = LANE_TO_V3_TASK.get(lane_id)
    if task_name is None:
        return None
    candidates = benchmarks.get("models", {}).get(task_name, [])
    if not candidates:
        return None
    return emit_for_lane(
        lane,
        candidates,
        today=today,
        benchmark_snapshot=_benchmark_snapshot_hash(benchmarks),
        eval_report_id=f"eval.{task_name}.v1",
    )


# ---------------------------------------------------------------------------
# Path resolution — package-relative, NOT CWD-relative
# ---------------------------------------------------------------------------
#
# Default paths are computed relative to the package location (this file's
# directory), NOT the current working directory. The previous design hardcoded
# `backend/llm_gateway/config/...` which broke when run as
# `cd backend && python -m llm_gateway.scripts.sync_benchmarks_to_route_artifacts`
# (CWD = backend/, the prefix would double).
#
# The CLI accepts --benchmarks and --out to override. Defaults resolve to
# the gateway config dir under the repo root regardless of CWD.
_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_GATEWAY_CONFIG_DIR = (_PACKAGE_DIR.parent / "config").resolve()
_DEFAULT_BENCHMARKS_PATH = _DEFAULT_GATEWAY_CONFIG_DIR / "benchmarks.json"
_DEFAULT_PROPOSED_PATH = _DEFAULT_GATEWAY_CONFIG_DIR / "route_artifacts.proposed.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync benchmarks.json -> route_artifacts.proposed.yaml (R1 emitter).",
    )
    parser.add_argument(
        "--lane",
        help="Emit one lane only (e.g. omi:auto:realtime-ptt). Default: emit all v3-covered lanes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print JSON summary to stdout, do NOT write route_artifacts.proposed.yaml.",
    )
    parser.add_argument(
        "--benchmarks",
        type=Path,
        default=_DEFAULT_BENCHMARKS_PATH,
        help=(
            "Path to benchmarks.json. "
            f"Default: {_DEFAULT_BENCHMARKS_PATH} (resolved relative to the package, not CWD)."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_PROPOSED_PATH,
        help=(
            "Path to the proposed YAML output. "
            f"Default: {_DEFAULT_PROPOSED_PATH} (resolved relative to the package, not CWD). "
            "Must NOT equal `route_artifacts.yaml`."
        ),
    )
    args = parser.parse_args(argv)

    if not args.benchmarks.exists():
        print(f"ERROR: benchmarks file not found: {args.benchmarks}", file=sys.stderr)
        return 2

    benchmarks = load_benchmarks(args.benchmarks)

    if args.lane:
        try:
            art = _emit_for_lane_id(args.lane, benchmarks)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        if art is None:
            print(
                f"WARNING: {args.lane} has no v3 task mapping or no candidates",
                file=sys.stderr,
            )
            return 1
        artifacts, warnings = [art], []
    else:
        artifacts, warnings = emit_all(benchmarks)

    summary = {
        "emitted": [a.lane_id for a in artifacts],
        "skipped": warnings,
        "count": len(artifacts),
    }
    print(json.dumps(summary, indent=2))

    if args.dry_run:
        return 0

    if not artifacts:
        return 1

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_proposed_yaml(artifacts, out_path)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
