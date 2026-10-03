#!/usr/bin/env python3
"""
Convert Omi goals JSON exports to structured Markdown checklists for Obsidian & Notion.

Features:
    - Pure Python standard library implementation (zero external pip packages).
    - Unix pipeline stdin streaming (`omi --json goal list | python goals_to_markdown.py - -o goals.md`).
    - Multi-file deduplication (latest `updated_at` / `created_at` timestamp wins).
    - Strict path traversal defense (rejecting `..` with ValueError).
    - Atomic file replacement via temporary files and os.replace.
    - Obsidian & Notion compatible CommonMark task trees with progress bars.

Usage:
    # Direct stdin pipeline:
    omi --json goal list --include-inactive --limit 100 | python goals_to_markdown.py - -o goals.md

    # Merge multiple export snapshots with deduplication:
    python goals_to_markdown.py page1.json page2.json -o vault/goals.md --force

    # Filter by status category (active, achieved, inactive):
    python goals_to_markdown.py goals.json --status active -o active_goals.md

    # Group by goal type (numeric, scale, boolean):
    python goals_to_markdown.py goals.json --group-by type -o grouped_goals.md

    # Split into separate notes in an output directory:
    python goals_to_markdown.py goals.json -d ./vault/goals/
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple


COMPLETED_STATUSES = {"achieved", "completed", "done"}
INACTIVE_STATUSES = {"paused", "abandoned", "archived", "inactive"}
BOOLEAN_TRUE_VALUES = {"true", "yes", "1", "done", "completed"}


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert any value to a finite float, falling back to default."""
    if val is None:
        return default
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    if isinstance(val, (int, float)):
        try:
            f_val = float(val)
            if math.isfinite(f_val):
                return f_val
        except OverflowError:
            return default
        return default
    if isinstance(val, str):
        cleaned = val.strip()
        try:
            num = float(cleaned)
            if math.isfinite(num):
                return num
        except (ValueError, TypeError, OverflowError):
            pass
    return default


def is_truthy(flag: Any) -> bool:
    """Determine boolean truthiness with defensive handling of string flags."""
    if flag is None:
        return False
    if isinstance(flag, bool):
        return flag
    if isinstance(flag, (int, float)):
        return safe_float(flag) > 0
    if isinstance(flag, str):
        return flag.strip().lower() in BOOLEAN_TRUE_VALUES
    return False



def parse_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Safely parse an ISO-8601 datetime string and normalize to UTC."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    cleaned = iso_str.strip()
    if not cleaned:
        return None
    try:
        # Standardize Z to +00:00 for python 3.11+ fromisoformat
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def validate_safe_path(path: Path | str) -> Path:
    """Validate that path does not contain path traversal sequences ('..').

    Raises:
        ValueError: If '..' is detected in path components or normalized string.
    """
    p_str = str(path)
    norm_str = p_str.replace("\\", "/")
    p = Path(path)
    if ".." in p.parts or ".." in norm_str.split("/") or any(part == ".." for part in norm_str.split("/")):
        raise ValueError(f"Path traversal sequence '..' is forbidden: {path}")
    return p


def atomic_write_file(dest_path: Path | str, content: str, force: bool = True) -> None:
    """Safely write content to destination path using atomic file replacement.

    Creates a temporary file in the destination's parent directory and renames
    it via os.replace to prevent partial writes and race conditions.

    Raises:
        ValueError: If path traversal is detected.
        FileExistsError: If destination exists and force is False.
    """
    dest = validate_safe_path(dest_path)
    if not dest.is_absolute():
        dest = dest.resolve()

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        raise FileExistsError(f"Destination file already exists: {dest} (use --force to overwrite)")

    prefix = f".{dest.name}.tmp_"
    with tempfile.NamedTemporaryFile(
        dir=dest.parent,
        prefix=prefix,
        delete=False,
        mode="w",
        encoding="utf-8",
        newline="\n",
    ) as tf:
        tf.write(content)
        temp_path = Path(tf.name)

    try:
        os.replace(temp_path, dest)
    except Exception:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


def calculate_progress(goal: Dict[str, Any]) -> float:
    """Calculate progress percentage (0.0 to 100.0) for a goal record."""
    status = str(goal.get("status") or "").strip().lower()
    if status in COMPLETED_STATUSES:
        return 100.0

    raw_current = goal.get("current_value")
    # If no progress has been recorded yet, progress is 0.0 unless completed
    if raw_current is None:
        return 0.0

    goal_type = str(goal.get("goal_type") or "numeric").strip().lower()
    if goal_type == "boolean":
        val = raw_current
        if isinstance(val, bool):
            return 100.0 if val else 0.0
        if isinstance(val, (int, float)):
            return 100.0 if safe_float(val) > 0 else 0.0
        if isinstance(val, str):
            return 100.0 if val.strip().lower() in BOOLEAN_TRUE_VALUES else 0.0
        return 0.0

    current = safe_float(raw_current, default=0.0)
    target = safe_float(goal.get("target_value"), default=10.0)
    min_val = safe_float(goal.get("min_value"), default=0.0)

    # Ascending goal (typical: reach target)
    if target > min_val:
        if current <= min_val:
            return 0.0
        pct = ((current - min_val) / (target - min_val)) * 100.0
        return min(max(pct, 0.0), 100.0)

    # Descending goal (e.g. reduce screen time, lower budget)
    if target < min_val:
        if current >= min_val:
            return 0.0
        pct = ((min_val - current) / (min_val - target)) * 100.0
        return min(max(pct, 0.0), 100.0)

    # Target equals min_val (qualitative goal or exact numeric boundary)
    if target == min_val:
        is_qualitative = goal.get("metric") is None and (target == 0.0 or raw_current == 0.0)
        if is_qualitative:
            return 100.0 if status in COMPLETED_STATUSES else 0.0
        return 100.0 if current >= target else 0.0

    return 0.0


def render_progress_bar(percentage: float, width: int = 10) -> str:
    """Render an ASCII progress bar compatible with CommonMark.

    Example: `[======....] 60.0%`
    """
    clamped_pct = min(max(percentage, 0.0), 100.0)
    filled_len = int(round((clamped_pct / 100.0) * width))
    bar_str = "=" * filled_len + "." * (width - filled_len)
    return f"`[{bar_str}] {clamped_pct:.1f}%`"


def is_goal_completed(goal: Dict[str, Any]) -> bool:
    """Determine whether a goal has been accomplished."""
    status = str(goal.get("status") or "").strip().lower()
    if status in COMPLETED_STATUSES:
        return True

    raw_current = goal.get("current_value")
    if raw_current is None:
        return False

    goal_type = str(goal.get("goal_type") or "numeric").strip().lower()
    if goal_type == "boolean":
        val = raw_current
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return safe_float(val) > 0
        if isinstance(val, str):
            return val.strip().lower() in BOOLEAN_TRUE_VALUES
        return False

    current = safe_float(raw_current, default=0.0)
    target = safe_float(goal.get("target_value"), default=10.0)
    min_val = safe_float(goal.get("min_value"), default=0.0)

    if target > min_val:
        return current >= target
    elif target < min_val:
        return current <= target

    # target == min_val
    is_qualitative = goal.get("metric") is None and (target == 0.0 or raw_current == 0.0)
    if is_qualitative:
        return status in COMPLETED_STATUSES
    return current >= target




def determine_status_category(goal: Dict[str, Any]) -> str:
    """Categorize goal status into one of: 'achieved', 'inactive', 'active'."""
    if is_goal_completed(goal):
        return "achieved"

    status = str(goal.get("status") or "").strip().lower()
    if status in INACTIVE_STATUSES:
        return "inactive"

    is_active = goal.get("is_active")
    if is_active is False:
        return "inactive"

    return "active"


def extract_goals(raw_data: Any) -> List[Dict[str, Any]]:
    """Extract and normalize a list of goal dictionaries from arbitrary parsed JSON."""
    goals_list: List[Dict[str, Any]] = []

    if isinstance(raw_data, list):
        goals_list = [it for it in raw_data if isinstance(it, dict)]
    elif isinstance(raw_data, dict):
        for candidate_key in ("goals", "items", "data", "results", "goal"):
            candidate = raw_data.get(candidate_key)
            if isinstance(candidate, list):
                goals_list = [it for it in candidate if isinstance(it, dict)]
                break
            elif isinstance(candidate, dict) and candidate:
                goals_list = [candidate]
                break
        else:
            # Single goal object
            if raw_data:
                goals_list = [raw_data]


    # Ensure stable goal id for each record
    normalized_goals: List[Dict[str, Any]] = []
    for g in goals_list:
        goal_copy = dict(g)
        gid = goal_copy.get("id")
        if not gid or not str(gid).strip():
            # Derive deterministic SHA-256 fallback id
            hash_src = json.dumps(goal_copy, sort_keys=True, default=str).encode("utf-8")
            goal_copy["id"] = f"goal_{hashlib.sha256(hash_src).hexdigest()[:12]}"
        else:
            goal_copy["id"] = str(gid).strip()
        normalized_goals.append(goal_copy)

    return normalized_goals


def load_and_deduplicate(sources: Sequence[str]) -> List[Dict[str, Any]]:
    """Load goals from multiple files or stdin and deduplicate by goal ID.

    For duplicate goal IDs, the record with the most recent `updated_at` (or
    `created_at`) timestamp takes precedence.
    """
    id_map: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}

    for src in sources:
        if src == "-":
            raw_text = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        else:
            p = validate_safe_path(src)
            if not p.is_file():
                print(f"Error: file not found: {p}", file=sys.stderr)
                sys.exit(1)
            raw_text = p.read_text(encoding="utf-8-sig", errors="replace")

        raw_text = raw_text.strip().lstrip("\ufeff")
        if not raw_text:
            continue

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            print(f"Error: Invalid JSON in {src}: {exc}", file=sys.stderr)
            sys.exit(1)

        goals = extract_goals(parsed)
        for goal in goals:
            gid = goal["id"]
            dt = parse_datetime(goal.get("updated_at")) or parse_datetime(goal.get("created_at"))
            # Fallback to minimum UTC datetime if timestamps are missing
            record_dt = dt or datetime.min.replace(tzinfo=timezone.utc)

            if gid not in id_map:
                id_map[gid] = (record_dt, goal)
            else:
                existing_dt, _ = id_map[gid]
                # Later timestamp wins; if equal, newer input overwrites
                if record_dt >= existing_dt:
                    id_map[gid] = (record_dt, goal)

    return [item[1] for item in id_map.values()]


def format_goal_tree(goal: Dict[str, Any]) -> str:
    """Format a single goal into a hierarchical Markdown checklist tree.

    Renders top-level checkbox with progress bar, followed by indented
    subtasks and success criteria checkboxes.
    """
    completed = is_goal_completed(goal)
    progress_pct = calculate_progress(goal)
    progress_bar = render_progress_bar(progress_pct)

    raw_title = str(goal.get("title") or "").strip()
    clean_title = re.sub(r"\s+", " ", raw_title).strip()
    title = clean_title if clean_title else "Untitled Goal"

    box = "[x]" if completed else "[ ]"
    gid = re.sub(r"[^\w-]", "", str(goal.get("id") or ""))

    # Metric detail string
    goal_type = str(goal.get("goal_type") or "numeric").strip().lower()
    unit = str(goal.get("unit") or "").strip()

    if goal_type == "boolean":
        metric_str = "Boolean"
    else:
        current = safe_float(goal.get("current_value"), 0.0)
        target = safe_float(goal.get("target_value"), 10.0)
        cur_fmt = f"{current:g}"
        tgt_fmt = f"{target:g}"
        if unit:
            metric_str = f"{cur_fmt} / {tgt_fmt} {unit}"
        else:
            metric_str = f"{cur_fmt} / {tgt_fmt}"

    meta_tag = f"`#{gid}`" if gid else ""
    details = f" *({metric_str} · {meta_tag})*" if meta_tag else f" *({metric_str})*"

    lines = [f"- {box} **{title}** {progress_bar}{details}"]

    # Desired outcome blockquote if present
    desired_outcome = goal.get("desired_outcome")
    if desired_outcome and str(desired_outcome).strip():
        clean_outcome = re.sub(r"\s+", " ", str(desired_outcome)).strip()
        lines.append(f"  > **Outcome:** {clean_outcome}")

    why = goal.get("why_it_matters")
    if why and str(why).strip():
        clean_why = re.sub(r"\s+", " ", str(why)).strip()
        lines.append(f"  > **Why:** {clean_why}")

    # Subtasks
    subtasks = goal.get("subtasks") or goal.get("tasks")
    if isinstance(subtasks, list):
        for sub in subtasks:
            if isinstance(sub, dict):
                raw_st = str(sub.get("title") or sub.get("name") or "Subtask")
                sub_title = re.sub(r"\s+", " ", raw_st).strip()
                raw_done = sub.get("completed") if "completed" in sub else sub.get("done")
                sub_box = "[x]" if is_truthy(raw_done) else "[ ]"
                lines.append(f"  - {sub_box} {sub_title}")


            elif isinstance(sub, str) and sub.strip():
                clean_sub = re.sub(r"\s+", " ", str(sub)).strip()
                sub_box = "[x]" if completed else "[ ]"
                lines.append(f"  - {sub_box} {clean_sub}")

    # Success criteria
    criteria = goal.get("success_criteria")
    if isinstance(criteria, list):
        for crit in criteria:
            if isinstance(crit, str) and crit.strip():
                clean_crit = re.sub(r"\s+", " ", str(crit)).strip()
                crit_box = "[x]" if completed else "[ ]"
                lines.append(f"  - {crit_box} {clean_crit}")

    return "\n".join(lines)


def goals_to_markdown(
    goals: List[Dict[str, Any]],
    title: str = "Omi Goals Checklist",
    group_by: str = "status",
) -> str:
    """Render a list of goals into a structured CommonMark document with YAML frontmatter."""
    total = len(goals)
    active_count = sum(1 for g in goals if determine_status_category(g) == "active")
    achieved_count = sum(1 for g in goals if determine_status_category(g) == "achieved")
    inactive_count = sum(1 for g in goals if determine_status_category(g) == "inactive")

    overall_progress = (
        sum(calculate_progress(g) for g in goals) / total if total > 0 else 0.0
    )

    now_iso = datetime.now(timezone.utc).isoformat()

    lines: List[str] = [
        "---",
        "type: goals",
        f"total: {total}",
        f"active: {active_count}",
        f"achieved: {achieved_count}",
        f"inactive: {inactive_count}",
        f"overall_progress: {overall_progress:.1f}%",
        f"exported_at: {json.dumps(now_iso)}",
        "tags:",
        "  - omi",
        "  - goals",
        "  - obsidian",
        "  - checklist",
        "---",
        "",
        f"# {title}",
        "",
        f"> **Summary:** {active_count} active, {achieved_count} achieved, {inactive_count} inactive ({total} total). Overall Progress: {overall_progress:.1f}%. Exported from Omi CLI.",
        "",
    ]

    if not goals:
        lines.append("_No goals found._")
        return "\n".join(lines).strip() + "\n"

    if group_by == "status":
        active_goals = [g for g in goals if determine_status_category(g) == "active"]
        achieved_goals = [g for g in goals if determine_status_category(g) == "achieved"]
        inactive_goals = [g for g in goals if determine_status_category(g) == "inactive"]

        lines.append("## 🟢 Active Goals")
        lines.append("")
        if active_goals:
            for g in active_goals:
                lines.append(format_goal_tree(g))
        else:
            lines.append("_No active goals._")
        lines.append("")

        lines.append("## ✅ Achieved Goals")
        lines.append("")
        if achieved_goals:
            for g in achieved_goals:
                lines.append(format_goal_tree(g))
        else:
            lines.append("_No achieved goals._")
        lines.append("")

        lines.append("## ⚪ Inactive Goals")
        lines.append("")
        if inactive_goals:
            for g in inactive_goals:
                lines.append(format_goal_tree(g))
        else:
            lines.append("_No inactive goals._")
        lines.append("")

    elif group_by == "type":
        type_groups: Dict[str, List[Dict[str, Any]]] = {
            "numeric": [],
            "scale": [],
            "boolean": [],
        }
        for g in goals:
            gtype = str(g.get("goal_type") or "numeric").strip().lower()
            if gtype in type_groups:
                type_groups[gtype].append(g)
            else:
                type_groups.setdefault("numeric", []).append(g)

        labels = [
            ("numeric", "🎯 Numeric Goals"),
            ("scale", "📊 Scale Goals"),
            ("boolean", "🔘 Boolean Goals"),
        ]
        for key, section_title in labels:
            section_items = type_groups.get(key, [])
            lines.append(f"## {section_title}")
            lines.append("")
            if section_items:
                for g in section_items:
                    lines.append(format_goal_tree(g))
            else:
                lines.append(f"_No {key} goals._")
            lines.append("")

    else:
        # Flat list
        for g in goals:
            lines.append(format_goal_tree(g))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports to structured Markdown checklists for Obsidian & Notion."
    )
    parser.add_argument(
        "sources",
        nargs="+",
        help="One or more JSON files, or '-' to read from stdin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Path to output Markdown file. Defaults to stdout if omitted.",
    )
    parser.add_argument(
        "-d",
        "--output-dir",
        default=None,
        help="Output directory to write individual or grouped Markdown files.",
    )
    parser.add_argument(
        "--status",
        choices=["all", "active", "achieved", "inactive"],
        default="all",
        help="Filter goals by status category (default: all).",
    )
    parser.add_argument(
        "--type",
        dest="goal_type",
        choices=["all", "numeric", "scale", "boolean"],
        default="all",
        help="Filter goals by goal type (default: all).",
    )
    parser.add_argument(
        "--group-by",
        choices=["status", "type", "none"],
        default="status",
        help="Grouping strategy for Markdown task sections (default: status).",
    )
    parser.add_argument(
        "--title",
        default="Omi Goals Checklist",
        help="Document header title.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file(s) if they already exist.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI execution entrypoint."""
    args = parse_args(argv)

    # Validate output paths early against traversal attacks
    try:
        if args.output:
            validate_safe_path(args.output)
        if args.output_dir:
            validate_safe_path(args.output_dir)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    # Load and deduplicate
    try:
        goals = load_and_deduplicate(args.sources)
    except Exception as exc:
        print(f"Error loading inputs: {exc}", file=sys.stderr)
        return 1

    # Filter by status category if requested
    if args.status != "all":
        goals = [g for g in goals if determine_status_category(g) == args.status]

    # Filter by goal type if requested
    if args.goal_type != "all":
        goals = [
            g
            for g in goals
            if str(g.get("goal_type") or "numeric").strip().lower() == args.goal_type
        ]

    # Handle output-dir mode (e.g. writing separate notes per category or vault file)
    if args.output_dir:
        out_dir = Path(args.output_dir)
        try:
            validate_safe_path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

            if args.group_by == "type":
                # Write separate notes for each goal type
                type_groups: Dict[str, List[Dict[str, Any]]] = {
                    "numeric": [],
                    "scale": [],
                    "boolean": [],
                }
                for g in goals:
                    gt = str(g.get("goal_type") or "numeric").strip().lower()
                    if gt in type_groups:
                        type_groups[gt].append(g)
                    else:
                        type_groups["numeric"].append(g)

                for gtype, grp_goals in type_groups.items():
                    target_file = out_dir / f"{gtype}_goals.md"
                    content = goals_to_markdown(
                        grp_goals,
                        title=f"{args.title} — {gtype.capitalize()}",
                        group_by="status",
                    )
                    atomic_write_file(target_file, content, force=args.force)
                print(f"Exported goals into type-specific notes in {out_dir}", file=sys.stderr)
                return 0
            else:
                target_file = out_dir / "goals.md"
                content = goals_to_markdown(goals, title=args.title, group_by=args.group_by)
                atomic_write_file(target_file, content, force=args.force)
                print(f"Exported {len(goals)} goals to {target_file}", file=sys.stderr)
                return 0
        except Exception as exc:
            print(f"Error writing to output directory: {exc}", file=sys.stderr)
            return 1

    # Single output or stdout
    content = goals_to_markdown(goals, title=args.title, group_by=args.group_by)

    if args.output:
        try:
            atomic_write_file(args.output, content, force=args.force)
            print(f"Exported {len(goals)} goals to {args.output}", file=sys.stderr)
        except Exception as exc:
            print(f"Error writing output file: {exc}", file=sys.stderr)
            return 1
    else:
        sys.stdout.buffer.write(content.encode("utf-8"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
