#!/usr/bin/env python3
"""
Generate an executive Markdown digest report from Omi goal exports.

Usage:
    python goals_digest.py goals.json -o goals_digest.md
    python goals_digest.py page1.json page2.json -o goals_digest.md
    omi --json goal list --limit 100 --include-inactive | python goals_digest.py - -o goals_digest.md

Aggregates exported goal records, deduplicates by ID, calculates executive KPIs
(total, active, inactive, achieved, average progress), generates category and type
breakdowns, and renders an executive status table with progress bars.

Pure standard library: zero external dependencies, 100% offline.
"""

import argparse
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

INACTIVE_STATUSES = {"inactive", "paused", "abandoned", "archived", "disabled"}
COMPLETED_STATUSES = {"achieved", "completed", "done", "finished"}


def parse_float(val: Any, default: float = 0.0) -> float:
    """Parse numeric float safely, guarding against NaN, Inf, and OverflowError."""
    if val is None or val == "":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError, OverflowError):
        return default


def sanitize_markdown_cell(text: Any) -> str:
    """Sanitize text for Markdown table cells: escape backslashes and pipes, collapse newlines."""
    if text is None:
        return ""
    s = str(text)
    # 1. Escape backslashes first, then pipes
    s = s.replace("\\", "\\\\").replace("|", "\\|")
    # 2. Collapse newlines and tabs to single spaces to prevent table tearing
    s = re.sub(r"[\r\n\t]+", " ", s)
    return s.strip()


def validate_path_safety(path: Path) -> None:
    """Refuse directory traversal ('..') in paths."""
    for part in path.parts:
        if part == "..":
            raise ValueError(f"Path traversal ('..') is not permitted: {path}")


def is_qualitative_goal(goal: Dict[str, Any]) -> bool:
    """Determine if a goal is qualitative (metric-less or subjective milestone)."""
    metric = goal.get("metric")
    if metric is None and "target_value" not in goal and "current_value" not in goal:
        return True
    if isinstance(metric, dict) and not metric:
        return True
    g_type = str(goal.get("goal_type") or "").lower()
    return g_type in {"qualitative", "habit", "milestone"} and not goal.get("target_value")


def resolve_goal_type(goal: Dict[str, Any]) -> str:
    """Extract canonical goal type label."""
    if is_qualitative_goal(goal):
        return "qualitative"
    metric = goal.get("metric")
    if isinstance(metric, dict) and metric.get("type"):
        return str(metric["type"]).lower()
    g_type = goal.get("goal_type")
    if g_type:
        return str(g_type).lower()
    return "numeric"


def calculate_progress(goal: Dict[str, Any]) -> float:
    """
    Calculate progress percentage (0.0 to 100.0+) for a goal.
    Handles qualitative, scale, and bounded numeric goals.
    """
    if is_qualitative_goal(goal):
        status = str(goal.get("status") or "").lower()
        return 100.0 if status in COMPLETED_STATUSES else 0.0

    target = parse_float(goal.get("target_value"), 0.0)
    current = parse_float(goal.get("current_value"), 0.0)
    min_val = parse_float(goal.get("min_value"), 0.0)
    max_val = parse_float(goal.get("max_value"), 0.0)

    # Scale / bounded goals
    if max_val > min_val and target <= max_val and target > min_val:
        if current >= target:
            return 100.0
        return max(0.0, min(100.0, ((current - min_val) / (target - min_val)) * 100.0))

    if math.isclose(target, min_val):
        return 100.0 if current >= target else 0.0

    if target > min_val:
        pct = ((current - min_val) / (target - min_val)) * 100.0
        return max(0.0, round(pct, 1))

    # Fallback for simple ratio
    if target > 0:
        return max(0.0, round((current / target) * 100.0, 1))

    return 0.0


def determine_status(goal: Dict[str, Any]) -> str:
    """
    Determine canonical status string with strict lifecycle precedence:
    Explicit inactive/archived/paused status takes precedence over >=100% progress.
    """
    raw_status = str(goal.get("status") or "").lower().strip()
    if raw_status in INACTIVE_STATUSES:
        return raw_status

    # Check is_active flag
    is_active = goal.get("is_active")
    if is_active is False:
        return "inactive"

    if raw_status in COMPLETED_STATUSES:
        return "achieved"

    progress = calculate_progress(goal)
    if progress >= 100.0:
        return "achieved"

    return "active"


def render_progress_bar(pct: float, width: int = 10) -> str:
    """Generate visual ASCII progress bar, e.g. [======    ] 60.0%."""
    clamped = max(0.0, min(100.0, pct))
    filled = int(round((clamped / 100.0) * width))
    empty = width - filled
    return f"`[{'=' * filled}{' ' * empty}]` {pct:.1f}%"


def extract_goals(data: Any) -> List[Dict[str, Any]]:
    """Unwrap goal records from bare list, envelope dictionary, or single dict."""
    if isinstance(data, list):
        return [g for g in data if isinstance(g, dict)]
    if isinstance(data, dict):
        for key in ("goals", "items", "data", "results"):
            if key in data and isinstance(data[key], list):
                return [g for g in data[key] if isinstance(g, dict)]
        if "id" in data or "title" in data:
            return [data]
    return []


def load_and_deduplicate(inputs: List[str]) -> List[Dict[str, Any]]:
    """Load goal records from multiple file paths or stdin (-), deduplicating by ID."""
    goals_by_id: Dict[str, Dict[str, Any]] = {}
    fallback_goals: List[Dict[str, Any]] = []

    for item in inputs:
        if item == "-":
            raw = sys.stdin.read()
            if not raw.strip():
                continue
            parsed = json.loads(raw)
            entries = extract_goals(parsed)
        else:
            p = Path(item)
            validate_path_safety(p)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {item}")
            raw = p.read_text(encoding="utf-8-sig")
            if not raw.strip():
                continue
            parsed = json.loads(raw)
            entries = extract_goals(parsed)

        for g in entries:
            gid = str(g.get("id") or "").strip()
            if not gid:
                fallback_goals.append(g)
                continue

            if gid not in goals_by_id:
                goals_by_id[gid] = g
            else:
                # Keep latest updated_at
                existing_time = str(goals_by_id[gid].get("updated_at") or goals_by_id[gid].get("created_at") or "")
                new_time = str(g.get("updated_at") or g.get("created_at") or "")
                if new_time >= existing_time:
                    goals_by_id[gid] = g

    combined = list(goals_by_id.values()) + fallback_goals
    return combined


def build_digest(goals: List[Dict[str, Any]], title: str = "Omi Goals Executive Digest") -> str:
    """Generate executive Markdown digest report."""
    total = len(goals)
    active_count = 0
    inactive_count = 0
    achieved_count = 0
    progress_sum = 0.0

    type_counts: Dict[str, int] = {}
    rows_data: List[Tuple[str, str, str, str, float, str]] = []

    for g in goals:
        status = determine_status(g)
        g_type = resolve_goal_type(g)
        progress = calculate_progress(g)

        type_counts[g_type] = type_counts.get(g_type, 0) + 1

        if status == "achieved":
            achieved_count += 1
            active_count += 1
        elif status in INACTIVE_STATUSES or status == "inactive":
            inactive_count += 1
        else:
            active_count += 1

        progress_sum += progress

        gid = sanitize_markdown_cell(g.get("id") or "")
        g_title = sanitize_markdown_cell(g.get("title") or "Untitled Goal")
        target_val = sanitize_markdown_cell(g.get("target_value") or "-")
        current_val = sanitize_markdown_cell(g.get("current_value") or "-")
        progress_bar = render_progress_bar(progress)

        rows_data.append((gid, g_title, g_type, status.upper(), progress, progress_bar))

    avg_progress = (progress_sum / total) if total > 0 else 0.0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"# {title}",
        "",
        f"> *Generated on {now_iso} | Source: Omi CLI*",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Total Goals** | {total} |",
        f"| **Active Goals** | {active_count} |",
        f"| **Achieved Goals** | {achieved_count} |",
        f"| **Inactive / Paused** | {inactive_count} |",
        f"| **Average Progress** | {avg_progress:.1f}% |",
        "",
        "## Type Breakdown",
        "",
        "| Goal Type | Count | Share |",
        "|---|---|---|",
    ]

    for g_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        share = (count / total * 100.0) if total > 0 else 0.0
        lines.append(f"| {g_type.capitalize()} | {count} | {share:.1f}% |")

    lines.extend([
        "",
        "## Detailed Goals Status",
        "",
        "| ID | Title | Type | Status | Progress |",
        "|---|---|---|---|---|",
    ])

    # Sort: active first, then achieved, then inactive; within group by progress desc
    def sort_key(row):
        st = row[3].lower()
        st_order = 0 if st == "active" else (1 if st == "achieved" else 2)
        return (st_order, -row[4])

    for row in sorted(rows_data, key=sort_key):
        gid, g_title, g_type, status_str, _, progress_bar = row
        lines.append(f"| `{gid}` | {g_title} | {g_type} | **{status_str}** | {progress_bar} |")

    lines.append("")
    return "\n".join(lines)


def write_digest(content: str, output_path: Path, force: bool = False) -> Path:
    """Atomic write of digest to destination path with no-clobber protection."""
    validate_path_safety(output_path)

    if output_path.exists() and not force:
        raise FileExistsError(
            f"Destination '{output_path}' already exists. Use -f/--force to overwrite."
        )

    out_dir = output_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    temp_fd, temp_path_str = tempfile.mkstemp(
        prefix=".tmp_digest_", suffix=".md", dir=str(out_dir)
    )
    os.close(temp_fd)
    temp_path = Path(temp_path_str)

    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    return output_path


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an executive Markdown digest report from Omi goal exports."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input JSON files or '-' for standard input streaming.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output Markdown destination file (e.g. goals_digest.md). Defaults to stdout if omitted.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output destination without error.",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="Omi Goals Executive Digest",
        help="Custom title header for the Markdown digest report.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        goals = load_and_deduplicate(args.inputs)
        digest_md = build_digest(goals, title=args.title)

        if args.output:
            out_p = Path(args.output)
            write_digest(digest_md, out_p, force=args.force)
            print(f"Goals digest written to: {out_p}")
        else:
            sys.stdout.write(digest_md)
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error generating goals digest: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
