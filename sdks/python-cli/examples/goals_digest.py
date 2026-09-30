#!/usr/bin/env python3
"""Build an executive Markdown digest report from Omi goals exports.

Converts one or more Omi goal JSON exports into a structured Markdown digest
containing high-level KPIs, goal-type breakdowns, and a detailed progress table.

Features:
- Multi-file ingestion with automatic ID deduplication (latest updated_at wins).
- Resilient envelope extraction (raw lists, or wrapped in "goals", "items", "data", "results").
- Unified KPI analytics (total, active, achieved, inactive, average progress).
- Strict Markdown table hygiene: sanitizes pipes ('|') and line breaks to prevent table tearing.
- ASCII progress indicators for quick visual scanning.
- Safe output handling: atomic writing, path-traversal guard, and overwrite protection.
- Zero third-party dependencies: strictly Python standard library.

Usage:
    # Pipe directly from omi CLI
    omi --json goal list | python goals_digest.py - -o digest.md

    # Summarize multiple export pages
    python goals_digest.py goals_p1.json goals_p2.json -o weekly_digest.md --force

    # Filter by status or goal type
    python goals_digest.py goals.json --status active --type scale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple


ACHIEVED_STATUSES = {"completed", "achieved", "done"}
INACTIVE_STATUSES = {"inactive", "archived", "cancelled", "canceled", "abandoned"}


def sanitize_text(value: Any) -> str:
    """Normalize and escape arbitrary input into a safe single-line string for Markdown tables.

    Pipes ('|') are escaped to prevent Markdown table column breakage.
    Newlines and carriage returns are collapsed into single spaces.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        else:
            value = str(value)

    # Collapse any inner whitespace/newlines
    collapsed = " ".join(value.split())
    # Escape backslashes first, then escape pipe characters so Markdown tables don't tear
    return collapsed.replace("\\", "\\\\").replace("|", "\\|")


def parse_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Safely parse an ISO-8601 datetime string and normalize to UTC."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    clean_val = iso_str.strip().replace("Z", "+00:00")
    if len(clean_val) == 10 and clean_val.count("-") == 2:
        clean_val += "T00:00:00+00:00"
    try:
        dt = datetime.fromisoformat(clean_val)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def calculate_progress(goal: Dict[str, Any]) -> float:
    """Calculate progress percentage (0.0 to 100.0+) for a goal."""
    goal_type = str(goal.get("goal_type") or "scale").strip().lower()

    if goal_type == "boolean":
        val = goal.get("current_value")
        if isinstance(val, bool):
            return 100.0 if val else 0.0
        if isinstance(val, (int, float)):
            return 100.0 if val >= 1.0 else 0.0
        if isinstance(val, str) and val.strip().lower() in ("true", "1", "yes", "done", "completed"):
            return 100.0
        return 0.0

    try:
        curr = float(goal.get("current_value") or 0.0)
        if not math.isfinite(curr):
            curr = 0.0
    except (ValueError, TypeError):
        curr = 0.0

    try:
        target = float(goal.get("target_value") or 0.0)
        if not math.isfinite(target):
            target = 0.0
    except (ValueError, TypeError):
        target = 0.0

    try:
        min_val = float(goal.get("min_value") or 0.0)
        if not math.isfinite(min_val):
            min_val = 0.0
    except (ValueError, TypeError):
        min_val = 0.0

    if min_val > target:
        span = min_val - target
        return max(0.0, (min_val - curr) / span * 100.0)

    # If min_val is defined and target != min_val
    if target > min_val:
        span = target - min_val
        achieved = (curr - min_val) / span * 100.0
        return max(0.0, achieved)

    if target > 0:
        return max(0.0, (curr / target) * 100.0)

    if curr > 0 and target == 0:
        return 100.0

    return 0.0


def determine_status(goal: Dict[str, Any], progress: float) -> Tuple[str, str]:
    """Determine the normalized status category and display label for a goal.

    Returns:
        (category, display_label) where category is one of 'achieved', 'active', 'inactive'.
    """
    raw_status = str(goal.get("status") or "").strip().lower()
    is_active = goal.get("is_active")

    # Explicit boolean False means inactive unless explicitly achieved
    if raw_status in ACHIEVED_STATUSES or progress >= 100.0:
        return "achieved", "✅ Achieved"

    if is_active is False or raw_status in INACTIVE_STATUSES:
        return "inactive", "⚪ Inactive"

    return "active", "🟢 Active"


def render_progress_bar(progress: float, width: int = 10) -> str:
    """Render a compact ASCII progress bar."""
    if not math.isfinite(progress):
        progress = 0.0
    clamped = max(0.0, min(100.0, progress))
    filled_len = int(round((clamped / 100.0) * width))
    empty_len = width - filled_len
    bar = "=" * filled_len + "." * empty_len
    return f"[{bar}] {progress:.1f}%"


def extract_goals(raw_content: str, source_label: str) -> List[Dict[str, Any]]:
    """Resiliently parse JSON content into a list of goal dictionaries."""
    stripped = raw_content.strip()
    if not stripped:
        return []

    try:
        data = json.loads(stripped)
    except Exception as exc:
        raise ValueError(f"Malformed JSON in {source_label}: {exc}") from exc

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("goals", "items", "data", "results"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        else:
            # Single object export
            items = [data] if "title" in data or "id" in data else []
    else:
        items = []

    valid_goals: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        goal = dict(item)
        if not goal.get("id"):
            # Synthesize stable deterministic ID if missing
            title_part = str(goal.get("title") or f"unnamed_{idx}")
            created_part = str(goal.get("created_at") or "")
            digest_src = f"{title_part}:{created_part}:{idx}".encode("utf-8")
            goal["id"] = f"goal_{hashlib.sha256(digest_src).hexdigest()[:12]}"

        valid_goals.append(goal)

    return valid_goals


def load_and_deduplicate(sources: Sequence[str | Path]) -> List[Dict[str, Any]]:
    """Load goals from one or more file paths or '-' (stdin) and deduplicate by ID.

    When duplicate IDs are encountered across files/pages, the record with the
    newest updated_at (or created_at) is retained.
    """
    goals_by_id: Dict[str, Dict[str, Any]] = {}
    timestamps: Dict[str, datetime] = {}

    for src in sources:
        src_str = str(src)
        if src_str == "-":
            raw = sys.stdin.read()
            extracted = extract_goals(raw, "<stdin>")
        else:
            p = Path(src)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {p}")
            raw = p.read_text(encoding="utf-8")
            extracted = extract_goals(raw, str(p))

        for goal in extracted:
            gid = str(goal["id"])
            ts = parse_datetime(goal.get("updated_at")) or parse_datetime(goal.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)

            if gid not in goals_by_id:
                goals_by_id[gid] = goal
                timestamps[gid] = ts
            else:
                if ts >= timestamps[gid]:
                    goals_by_id[gid] = goal
                    timestamps[gid] = ts

    return list(goals_by_id.values())


@dataclass
class DigestKPIs:
    total_goals: int
    active_goals: int
    achieved_goals: int
    inactive_goals: int
    overall_progress: float
    type_counts: Dict[str, int]
    type_achieved: Dict[str, int]
    type_progress_sum: Dict[str, float]


def calculate_kpis(goals: Sequence[Dict[str, Any]]) -> DigestKPIs:
    """Compute aggregate KPI metrics across goals."""
    total = len(goals)
    if total == 0:
        return DigestKPIs(
            total_goals=0,
            active_goals=0,
            achieved_goals=0,
            inactive_goals=0,
            overall_progress=0.0,
            type_counts={},
            type_achieved={},
            type_progress_sum={},
        )

    active_cnt = 0
    achieved_cnt = 0
    inactive_cnt = 0
    progress_sum = 0.0

    type_counts: Dict[str, int] = {}
    type_achieved: Dict[str, int] = {}
    type_progress_sum: Dict[str, float] = {}

    for goal in goals:
        gtype = str(goal.get("goal_type") or "scale").strip().lower()
        prog = calculate_progress(goal)
        cat, _ = determine_status(goal, prog)

        progress_sum += prog

        if cat == "achieved":
            achieved_cnt += 1
        elif cat == "inactive":
            inactive_cnt += 1
        else:
            active_cnt += 1

        type_counts[gtype] = type_counts.get(gtype, 0) + 1
        type_progress_sum[gtype] = type_progress_sum.get(gtype, 0.0) + prog
        if cat == "achieved":
            type_achieved[gtype] = type_achieved.get(gtype, 0) + 1
        else:
            type_achieved.setdefault(gtype, 0)

    avg_prog = progress_sum / total if total > 0 else 0.0

    return DigestKPIs(
        total_goals=total,
        active_goals=active_cnt,
        achieved_goals=achieved_cnt,
        inactive_goals=inactive_cnt,
        overall_progress=avg_prog,
        type_counts=type_counts,
        type_achieved=type_achieved,
        type_progress_sum=type_progress_sum,
    )


def generate_markdown_digest(
    goals: Sequence[Dict[str, Any]],
    title: str = "Omi Goals Executive Digest",
    filter_status: str = "all",
    filter_type: str = "all",
) -> str:
    """Format goal records into a comprehensive GitHub-flavored Markdown digest."""
    # Apply filtering
    filtered: List[Dict[str, Any]] = []
    for g in goals:
        gtype = str(g.get("goal_type") or "scale").strip().lower()
        prog = calculate_progress(g)
        cat, _ = determine_status(g, prog)

        if filter_type != "all" and gtype != filter_type.lower():
            continue
        if filter_status != "all" and cat != filter_status.lower():
            continue

        filtered.append(g)

    # Sort goals: Achieved first, then active by progress descending, then title
    def sort_key(item: Dict[str, Any]):
        p = calculate_progress(item)
        c, _ = determine_status(item, p)
        # category order: active(0), achieved(1), inactive(2)
        cat_rank = 0 if c == "active" else (1 if c == "achieved" else 2)
        return (cat_rank, -p, str(item.get("title") or "").lower())

    filtered.sort(key=sort_key)
    kpis = calculate_kpis(filtered)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines: List[str] = [
        f"# {sanitize_text(title)}",
        "",
        f"> Generated on **{generated_at}** • Total Records Evaluated: **{kpis.total_goals}**",
        "",
        "## Executive Summary",
        "",
        "| Metric | Count | Percentage |",
        "| :--- | :--- | :--- |",
        f"| 🎯 **Total Goals** | `{kpis.total_goals}` | `100.0%` |",
        f"| 🟢 **Active Goals** | `{kpis.active_goals}` | `{kpis.active_goals / kpis.total_goals * 100:.1f}%` |" if kpis.total_goals > 0 else "| 🟢 **Active Goals** | `0` | `0.0%` |",
        f"| ✅ **Achieved Goals** | `{kpis.achieved_goals}` | `{kpis.achieved_goals / kpis.total_goals * 100:.1f}%` |" if kpis.total_goals > 0 else "| ✅ **Achieved Goals** | `0` | `0.0%` |",
        f"| ⚪ **Inactive Goals** | `{kpis.inactive_goals}` | `{kpis.inactive_goals / kpis.total_goals * 100:.1f}%` |" if kpis.total_goals > 0 else "| ⚪ **Inactive Goals** | `0` | `0.0%` |",
        f"| 📊 **Average Progress** | `{render_progress_bar(kpis.overall_progress, 12)}` | `{kpis.overall_progress:.1f}%` |",
        "",
    ]

    # Category / Type Breakdown
    if kpis.type_counts:
        lines.extend([
            "## Breakdown by Goal Type",
            "",
            "| Goal Type | Total | Achieved | Avg Progress |",
            "| :--- | :--- | :--- | :--- |",
        ])
        for tname in sorted(kpis.type_counts.keys()):
            cnt = kpis.type_counts[tname]
            ach = kpis.type_achieved.get(tname, 0)
            avg_p = kpis.type_progress_sum.get(tname, 0.0) / cnt if cnt > 0 else 0.0
            lines.append(
                f"| `{sanitize_text(tname)}` | {cnt} | {ach} ({ach / cnt * 100:.1f}%) | {render_progress_bar(avg_p, 8)} |"
            )
        lines.append("")

    # Detailed Goals Table
    lines.extend([
        "## Goal Details",
        "",
        "| Status | Title | Type | Progress | Target | Last Updated |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    if not filtered:
        lines.append("| _No goals found matching criteria_ | - | - | - | - | - |")
    else:
        for goal in filtered:
            prog = calculate_progress(goal)
            _, status_label = determine_status(goal, prog)
            title_text = sanitize_text(goal.get("title") or "Untitled Goal")
            gtype = sanitize_text(goal.get("goal_type") or "scale")
            unit = sanitize_text(goal.get("unit") or "")

            curr = goal.get("current_value")
            tval = goal.get("target_value")

            if curr is None:
                curr_disp = "0"
            elif isinstance(curr, float) and math.isfinite(curr) and curr.is_integer():
                curr_disp = str(int(curr))
            else:
                curr_disp = str(curr)

            if tval is None:
                tval_disp = "0"
            elif isinstance(tval, float) and math.isfinite(tval) and tval.is_integer():
                tval_disp = str(int(tval))
            else:
                tval_disp = str(tval)

            target_repr = f"{curr_disp} / {tval_disp} {unit}".strip()

            updated_dt = parse_datetime(goal.get("updated_at")) or parse_datetime(goal.get("created_at"))
            updated_str = updated_dt.strftime("%Y-%m-%d") if updated_dt else "-"

            prog_cell = render_progress_bar(prog, 8)

            lines.append(
                f"| {status_label} | {title_text} | `{gtype}` | {prog_cell} | {target_repr} | {updated_str} |"
            )

    lines.append("")
    return "\n".join(lines)


def write_digest(content: str, dest_path: str | Path, force: bool = False) -> None:
    """Safely write markdown content to destination file with atomic replacement and security checks."""
    dest = Path(dest_path).resolve()

    # Guard against path traversal patterns in user-specified relative path
    orig_str = str(dest_path)
    norm_str = orig_str.replace("\\", "/")
    if ".." in Path(dest_path).parts or ".." in norm_str.split("/"):
        raise ValueError(f"Path traversal sequence '..' is forbidden: {dest_path}")

    if dest.exists() and not force:
        raise FileExistsError(
            f"Destination file '{dest}' already exists. Use -f / --force to overwrite."
        )

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write via temporary file
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=dest.parent, prefix=f".{dest.name}.tmp_", delete=False
        ) as tf:
            tf.write(content.encode("utf-8"))
            temp_path = Path(tf.name)
        os.replace(temp_path, dest)
        temp_path = None
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an executive Markdown digest report from Omi goals exports."
    )
    parser.add_argument(
        "sources",
        nargs="+",
        help="Input JSON file paths or '-' for stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination markdown file path (defaults to stdout '-')",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force overwrite existing destination file",
    )
    parser.add_argument(
        "--title",
        default="Omi Goals Executive Digest",
        help="Title header for the generated digest report",
    )
    parser.add_argument(
        "--status",
        choices=["all", "active", "achieved", "inactive"],
        default="all",
        help="Filter goals by status (default: all)",
    )
    parser.add_argument(
        "--type",
        default="all",
        help="Filter goals by goal_type (e.g. scale, numeric, boolean, or 'all')",
    )

    args = parser.parse_args()

    try:
        goals = load_and_deduplicate(args.sources)
        digest_md = generate_markdown_digest(
            goals,
            title=args.title,
            filter_status=args.status,
            filter_type=args.type,
        )

        if args.output == "-":
            sys.stdout.write(digest_md)
        else:
            write_digest(digest_md, args.output, force=args.force)
            total = len(goals)
            print(f"Exported digest for {total} goal(s) to {args.output}", file=sys.stderr)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
