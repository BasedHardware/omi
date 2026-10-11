#!/usr/bin/env python3
"""Build an executive Markdown digest report from Omi goals exports.

Converts one or more Omi goal JSON exports into a structured Markdown digest
containing high-level KPIs, goal-type breakdowns, and a detailed progress table.

Features:
- Multi-file ingestion with automatic ID deduplication (latest updated_at wins).
- Resilient envelope extraction (raw lists, or wrapped in "goals", "items", "data", "results").
- Unified KPI analytics (total, active, achieved, inactive, average progress).
- Strict Markdown table hygiene: sanitizes pipes ('|') and line breaks to prevent column tearing.
- ASCII progress indicators for instant visual scanning.
- Safe output handling: atomic writing, symlink guard, path-traversal guard, and overwrite protection.
- Zero third-party dependencies: strictly Python standard library.

Usage:
    # Pipe directly from omi CLI
    omi --json goal list --limit 100 --include-inactive | python goals_digest.py - -o digest.md

    # Summarize multiple export pages
    python goals_digest.py goals_active.json goals_all.json -o weekly_digest.md --force

    # Filter by status or goal type
    python goals_digest.py goals.json --status active --type scale
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple


ACHIEVED_STATUSES = {"completed", "achieved", "done"}
INACTIVE_STATUSES = {"inactive", "archived", "cancelled", "canceled", "abandoned", "paused"}



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
    """Safely parse an ISO-8601 datetime or date string and normalize to UTC."""
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


def normalize_bool_flag(value: Any) -> Optional[bool]:
    """Normalize boolean-like representations (bool, int, or string) to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "1", "yes", "y", "t"):
            return True
        if s in ("false", "0", "no", "n", "f"):
            return False
    return None


def parse_float(value: Any) -> Optional[float]:
    """Parse numeric values defensively against OverflowError, TypeError, and NaN/Inf."""
    if value is None:
        return None
    try:
        f = float(value)
        if not math.isfinite(f):
            return None
        return f
    except (ValueError, TypeError, OverflowError):
        return None


def is_qualitative_goal(goal: Dict[str, Any]) -> bool:
    """Return True if the goal is qualitative (metricless).

    The Omi backend sets canonical `metric: None` for qualitative goals while injecting
    inert compatibility aliases (goal_type='scale', current=0, target=0) for older clients.
    A goal is qualitative if:
    1. The canonical 'metric' field is explicitly present and None, OR
    2. 'goal_type' is explicitly 'qualitative', OR
    3. No metric dictionary and no target_value/min_value/max_value are present.
    """
    if "metric" in goal:
        return goal.get("metric") is None
    gtype = str(goal.get("goal_type") or "").strip().lower()
    if gtype == "qualitative":
        return True
    if gtype in ("scale", "numeric", "boolean"):
        return False
    has_metrics = any(
        goal.get(k) is not None
        for k in ("target_value", "current_value", "min_value", "max_value")
    )
    return not has_metrics


def resolve_goal_type(goal: Dict[str, Any]) -> str:
    """Resolve the canonical goal type ('boolean', 'numeric', 'scale', or 'qualitative')."""
    if is_qualitative_goal(goal):
        return "qualitative"
    metric = goal.get("metric")
    if isinstance(metric, dict) and metric.get("type"):
        return str(metric["type"]).strip().lower()
    raw_type = goal.get("goal_type")
    if raw_type:
        return str(raw_type).strip().lower()
    return "scale"


def calculate_progress(goal: Dict[str, Any]) -> float:
    """Calculate progress percentage (0.0 to 100.0+) for a goal."""
    gtype = resolve_goal_type(goal)
    if gtype == "qualitative":
        raw_status = str(goal.get("status") or "").strip().lower()
        if raw_status in ACHIEVED_STATUSES:
            return 100.0
        return 0.0

    if gtype == "boolean":
        val = goal.get("current_value")
        b_norm = normalize_bool_flag(val)
        if b_norm is True:
            return 100.0
        parsed_f = parse_float(val)
        if parsed_f is not None and parsed_f >= 1.0:
            return 100.0
        if isinstance(val, str) and val.strip().lower() in ("done", "completed", "achieved"):
            return 100.0
        return 0.0

    metric = goal.get("metric")
    if isinstance(metric, dict):
        curr = parse_float(metric.get("current") if "current" in metric else goal.get("current_value")) or 0.0
        target = parse_float(metric.get("target") if "target" in metric else goal.get("target_value")) or 0.0
        min_val = parse_float(metric.get("min") if "min" in metric else goal.get("min_value")) or 0.0
        max_val = parse_float(metric.get("max") if "max" in metric else goal.get("max_value"))
    else:
        curr = parse_float(goal.get("current_value")) or 0.0
        target = parse_float(goal.get("target_value")) or 0.0
        min_val = parse_float(goal.get("min_value")) or 0.0
        max_val = parse_float(goal.get("max_value"))

    if min_val > target:
        span = min_val - target
        prog = (min_val - curr) / span * 100.0
    elif target > min_val:
        span = target - min_val
        prog = (curr - min_val) / span * 100.0
    elif target > 0:
        prog = (curr / target) * 100.0
    elif curr > 0 and target == 0:
        prog = 100.0
    else:
        prog = 0.0

    prog = max(0.0, prog)
    # Only cap if max_val represents a true bound higher than or equal to target.
    # Default CLI aliases set max_value=10 even when target=100; don't cap in that case.
    if max_val is not None and max_val > 0 and curr > max_val and target <= max_val:
        prog = min(prog, (max_val / target) * 100.0 if target > 0 else prog)

    return prog


def determine_status(goal: Dict[str, Any], progress: float) -> Tuple[str, str]:
    """Determine the normalized status category and display label for a goal.

    Inactive status takes strict precedence over numerical progress completion:
    an inactive, paused, or archived goal remains inactive unless explicitly completed.

    Returns:
        (category, display_label) where category is one of 'active', 'achieved', 'inactive'.
    """
    raw_status = str(goal.get("status") or "").strip().lower()
    is_active = normalize_bool_flag(goal.get("is_active"))

    # Explicit completion status
    if raw_status in ACHIEVED_STATUSES:
        return "achieved", "✅ Achieved"

    # Inactive precedence (including paused)
    if is_active is False or raw_status in INACTIVE_STATUSES:
        return "inactive", "⚪ Inactive"

    # Progress completion for active metric-backed goals
    if not is_qualitative_goal(goal) and progress >= 100.0:
        return "achieved", "✅ Achieved"

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
            ts = (
                parse_datetime(goal.get("updated_at"))
                or parse_datetime(goal.get("created_at"))
                or datetime.min.replace(tzinfo=timezone.utc)
            )

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
        gtype = resolve_goal_type(goal)
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
    filtered: List[Dict[str, Any]] = []
    for g in goals:
        gtype = resolve_goal_type(g)
        prog = calculate_progress(g)
        cat, _ = determine_status(g, prog)

        if filter_type != "all" and gtype != filter_type.lower():
            continue
        if filter_status != "all" and cat != filter_status.lower():
            continue

        filtered.append(g)

    # Sort goals: Active first, then achieved, then inactive, then progress descending, then title
    def sort_key(item: Dict[str, Any]) -> Tuple[int, float, str]:
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
        f"| 🟢 **Active Goals** | `{kpis.active_goals}` | "
        f"`{kpis.active_goals / kpis.total_goals * 100:.1f}%` |"
        if kpis.total_goals > 0
        else "| 🟢 **Active Goals** | `0` | `0.0%` |",
        f"| ✅ **Achieved Goals** | `{kpis.achieved_goals}` | "
        f"`{kpis.achieved_goals / kpis.total_goals * 100:.1f}%` |"
        if kpis.total_goals > 0
        else "| ✅ **Achieved Goals** | `0` | `0.0%` |",
        f"| ⚪ **Inactive Goals** | `{kpis.inactive_goals}` | "
        f"`{kpis.inactive_goals / kpis.total_goals * 100:.1f}%` |"
        if kpis.total_goals > 0
        else "| ⚪ **Inactive Goals** | `0` | `0.0%` |",
        f"| 📊 **Average Progress** | `{render_progress_bar(kpis.overall_progress, 12)}` | "
        f"`{kpis.overall_progress:.1f}%` |",
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
                f"| `{sanitize_text(tname)}` | {cnt} | {ach} ({ach / cnt * 100:.1f}%) | "
                f"{render_progress_bar(avg_p, 8)} |"
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
            gtype = sanitize_text(resolve_goal_type(goal))
            unit = sanitize_text(goal.get("unit") or "")

            if resolve_goal_type(goal) == "qualitative":
                target_repr = "-"
            else:
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

                curr_disp_safe = sanitize_text(curr_disp)
                tval_disp_safe = sanitize_text(tval_disp)
                target_parts = [f"{curr_disp_safe} / {tval_disp_safe}"]
                if unit:
                    target_parts.append(unit)
                target_repr = " ".join(target_parts)

            updated_dt = parse_datetime(goal.get("updated_at")) or parse_datetime(goal.get("created_at"))
            updated_str = updated_dt.strftime("%Y-%m-%d") if updated_dt else "-"

            prog_cell = render_progress_bar(prog, 8)

            lines.append(
                f"| {status_label} | {title_text} | `{gtype}` | {prog_cell} | {target_repr} | {updated_str} |"
            )

    lines.append("")
    return "\n".join(lines)


def _restore_umask_permissions(path: Path) -> None:
    """Restore standard non-restrictive umask file permissions after tempfile creation."""
    try:
        current_umask = os.umask(0)
        os.umask(current_umask)
        expected_mode = 0o666 & ~current_umask
        os.chmod(path, expected_mode)
    except Exception:
        pass


def write_digest(content: str, dest_path: str | Path, force: bool = False) -> None:
    """Safely write markdown content to destination file with atomic replacement and security checks."""
    raw_p = Path(dest_path)
    if raw_p.is_symlink():
        raise ValueError(f"Destination path is a symlink: {dest_path}")

    dest = raw_p.resolve()
    if dest.is_symlink():
        raise ValueError(f"Destination path is a symlink: {dest_path}")

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

        _restore_umask_permissions(temp_path)

        if force:
            os.replace(temp_path, dest)
            temp_path = None
        else:
            try:
                os.link(temp_path, dest)
                temp_path.unlink()
                temp_path = None
            except FileExistsError:
                raise FileExistsError(
                    f"Destination file '{dest}' already exists. Use -f / --force to overwrite."
                )
            except (AttributeError, NotImplementedError, OSError):
                # Fallback for environments or filesystems that do not support hard links
                if dest.exists():
                    raise FileExistsError(
                        f"Destination file '{dest}' already exists. Use -f / --force to overwrite."
                    )
                os.replace(temp_path, dest)
                temp_path = None

        _restore_umask_permissions(dest)
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
