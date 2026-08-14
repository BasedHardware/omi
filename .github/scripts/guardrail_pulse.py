#!/usr/bin/env python3
"""Guardrail baseline health pulse (#9454 Part 2).

Invokes each existing check script's counter (never reimplements counting).
Emits one line per baseline, optional JSON, optional JSONL history append, and
staleness detection when a nonzero count has not decreased for 30 days.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_brand_ui  # noqa: E402
import check_isinstance_return_ratchet  # noqa: E402
import check_lifecycle_headers  # noqa: E402
import check_package_architecture_maps  # noqa: E402
import check_version_prefixed_filenames  # noqa: E402

DEFAULT_HISTORY = Path(".github/guardrail-pulse-history.jsonl")
STALENESS_DAYS = 30


@dataclass(frozen=True)
class Metric:
    name: str
    count: int
    baseline: int


def _load_hyphen_module(filename: str, module_name: str):
    path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _union_return_metric(repo_root: Path) -> Metric:
    baseline_path = repo_root / check_isinstance_return_ratchet.DEFAULT_BASELINE
    baseline = check_isinstance_return_ratchet.load_baseline(baseline_path)
    counts = check_isinstance_return_ratchet.collect_counts(
        repo_root, check_isinstance_return_ratchet.DEFAULT_SCAN_ROOT
    )
    return Metric(
        "union_return_isinstance",
        sum(counts.values()),
        sum(baseline.values()),
    )


def _lifecycle_metric(repo_root: Path) -> Metric:
    baseline_path = repo_root / check_lifecycle_headers.BASELINE_PATH
    baseline_entries, _errors = check_lifecycle_headers.load_baseline(baseline_path)
    headerless = 0
    for _relative_path, path in check_lifecycle_headers.iter_designated_files(repo_root):
        lifecycle, header_error = check_lifecycle_headers.parse_lifecycle_header(path)
        if header_error is None and lifecycle is None:
            headerless += 1
    return Metric("lifecycle_unlabeled_scripts", headerless, len(baseline_entries))


def _mapless_metric(repo_root: Path) -> Metric:
    baseline_path = repo_root / ".github" / "scripts" / "package_architecture_baseline.json"
    baseline = check_package_architecture_maps.load_baseline(baseline_path)
    findings = check_package_architecture_maps.evaluate_packages(
        repo_root, baseline, check_package_architecture_maps.DEFAULT_THRESHOLD
    )
    # Live mapless packages (warnings + errors); baseline is the committed grandfather map.
    return Metric("mapless_packages", len(findings), len(baseline))


def _version_prefixed_metric() -> Metric:
    # Grandfathered paths are the frozen debt the pulse tracks for burn-down.
    # New violations outside the set fail CI separately (live_new should stay 0).
    grandfathered = len(check_version_prefixed_filenames.GRANDFATHERED_VIOLATIONS)
    live_new = len(check_version_prefixed_filenames.violations(check_version_prefixed_filenames.tracked_paths()))
    return Metric("version_prefixed_files", grandfathered + live_new, grandfathered)


def _deferred_metric(repo_root: Path) -> Metric:
    deferred = _load_hyphen_module("deferred-work-marker-count.py", "deferred_work_marker_count")
    marker_counts, _file_counts = deferred.count_markers(repo_root, raw=False)
    total = sum(marker_counts.values())
    # No committed ceiling — baseline tracks the live normalized total for display.
    return Metric("deferred_work_markers", total, total)


def _brand_ui_metric(repo_root: Path) -> Metric:
    total = 0
    for prefix in check_brand_ui.UI_ROOTS:
        root = repo_root / prefix
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(repo_root).as_posix()
            if not check_brand_ui.is_ui_source(relative):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            total += check_brand_ui.count_purple(text)
    return Metric("brand_ui_purple", total, total)


def collect_metrics(repo_root: Path) -> list[Metric]:
    return [
        _union_return_metric(repo_root),
        _lifecycle_metric(repo_root),
        _mapless_metric(repo_root),
        _version_prefixed_metric(),
        _deferred_metric(repo_root),
        _brand_ui_metric(repo_root),
    ]


def format_text(metrics: list[Metric]) -> str:
    width = max(len(metric.name) for metric in metrics)
    lines = [f"{metric.name:<{width}}  {metric.count:<5} (baseline {metric.baseline})" for metric in metrics]
    return "\n".join(lines)


def metrics_payload(metrics: list[Metric], *, recorded_at: str) -> dict[str, Any]:
    return {
        "date": recorded_at,
        "metrics": {metric.name: {"count": metric.count, "baseline": metric.baseline} for metric in metrics},
    }


def append_history(history_path: Path, payload: dict[str, Any]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def load_history(history_path: Path) -> list[dict[str, Any]]:
    if not history_path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(history_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{history_path}:{line_number}: invalid JSONL: {exc}") from exc
        if not isinstance(row, dict) or "date" not in row or "metrics" not in row:
            raise ValueError(f"{history_path}:{line_number}: expected object with date and metrics")
        rows.append(row)
    return rows


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def find_stale_metrics(
    history: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    window_days: int = STALENESS_DAYS,
) -> list[str]:
    """Return metric names whose nonzero count has not decreased for ``window_days``.

    Requires history spanning at least ``window_days``. A metric that only appeared
    recently is not stale yet.
    """
    as_of = as_of or datetime.now(timezone.utc).date()
    series_by_name: dict[str, list[tuple[date, int]]] = {}
    for row in history:
        day = _parse_iso_date(str(row["date"]))
        metrics = row.get("metrics") or {}
        if not isinstance(metrics, dict):
            continue
        for name, payload in metrics.items():
            if not isinstance(payload, dict):
                continue
            count = payload.get("count")
            if not isinstance(count, int):
                continue
            series_by_name.setdefault(name, []).append((day, count))

    stale: list[str] = []
    for name, series in sorted(series_by_name.items()):
        series.sort(key=lambda item: item[0])
        current_count = series[-1][1]
        if current_count <= 0:
            continue
        last_decrease: date | None = None
        for previous, current in zip(series, series[1:]):
            if current[1] < previous[1]:
                last_decrease = current[0]
        reference = last_decrease or series[0][0]
        if (as_of - reference).days >= window_days:
            stale.append(name)
    return stale


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--record",
        action="store_true",
        help=f"Append today's snapshot to {DEFAULT_HISTORY.as_posix()}.",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=None,
        help="JSONL history path (default: repo-relative guardrail-pulse-history.jsonl).",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="ISO date for the snapshot / staleness as-of (default: today UTC).",
    )
    parser.add_argument(
        "--check-staleness",
        action="store_true",
        help="Print stale metrics (nonzero, no decrease for 30 days) and exit 1 if any.",
    )
    parser.add_argument(
        "--staleness-days",
        type=int,
        default=STALENESS_DAYS,
        help="Staleness window in days (default: 30).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.root.resolve()
    history_path = args.history or (repo_root / DEFAULT_HISTORY)
    if not history_path.is_absolute():
        history_path = repo_root / history_path

    recorded_at = args.date or datetime.now(timezone.utc).date().isoformat()
    metrics = collect_metrics(repo_root)
    payload = metrics_payload(metrics, recorded_at=recorded_at)

    if args.record:
        append_history(history_path, payload)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_text(metrics))

    if args.check_staleness:
        history = load_history(history_path)
        # Include the just-computed snapshot even when --record was not used.
        if not args.record:
            history = [*history, payload]
        as_of = _parse_iso_date(recorded_at)
        stale = find_stale_metrics(history, as_of=as_of, window_days=args.staleness_days)
        if stale:
            print("STALE: nonzero baselines with no decrease for " f"{args.staleness_days} days: {', '.join(stale)}")
            return 1
        print(f"OK: no stale nonzero baselines (window={args.staleness_days}d).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
