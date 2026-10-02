#!/usr/bin/env python3
"""Convert an Omi goal export into a standard todo.txt file.

See goals_todotxt.md for the full recipe and integration guide.

Usage:
    omi --json goal list --limit 100 --include-inactive > goals.json
    python goals_to_todotxt.py goals.json todo.txt --utc-offset +00:00
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

ACHIEVED_STATUSES = {"completed", "achieved", "done"}
INACTIVE_STATUSES = {"inactive", "archived", "cancelled", "canceled", "abandoned"}
RESERVED_KEYS = {"due", "t", "rec", "h", "pri", "omi", "cur", "target", "pct", "unit"}
ZWSP = "\u200b"  # zero-width space: breaks todo.txt syntax without altering rendered text


def one_line(value: Any) -> str:
    """Render one exported field as clean single-line text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        else:
            value = str(value)
    return " ".join(value.split())


def task_text(value: Any) -> str:
    """Sanitize goal title so it is not misinterpreted as todo.txt projects, contexts, or metadata."""
    words = []
    for word in one_line(value).split(" "):
        if len(word) > 1 and word[0] in "+@":
            word = ZWSP + word
        elif ":" in word and word.split(":", 1)[0].lower() in RESERVED_KEYS:
            key, rest = word.split(":", 1)
            word = f"{key}{ZWSP}:{rest}"
        words.append(word)
    text = " ".join(words) or "(untitled goal)"
    if re.match(r"(?:x|\([A-Z]\)|\d{4}-\d{2}-\d{2})(?: |$)", text):
        text = ZWSP + text
    return text


def parse_offset(text: Optional[str]) -> timezone:
    """Parse a UTC offset string (+HH:MM or -HH:MM) into a timezone object."""
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", text or "")
    if not match or int(match.group(2)) > 14 or int(match.group(3)) > 59:
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    if delta > timedelta(hours=14):
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    return timezone(delta if match.group(1) == "+" else -delta)


def local_date(value: Any, zone: timezone) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp and normalize to local calendar date."""
    if not isinstance(value, str) or not value.strip():
        return None
    clean = value.strip().replace("Z", "+00:00")
    if len(clean) == 10 and clean.count("-") == 2:
        clean += "T00:00:00+00:00"
    try:
        parsed = datetime.fromisoformat(clean)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone)


def normalize_bool_flag(value: Any) -> Optional[bool]:
    """Normalize boolean representation from bool, int, or string."""
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
    """Safely parse a floating-point number, guarding against OverflowError, NaN, and Inf."""
    if value is None:
        return None
    try:
        f = float(value)
        if not math.isfinite(f):
            return None
        return f
    except (ValueError, TypeError, OverflowError):
        return None


def format_metric_num(value: Optional[float]) -> str:
    """Format numeric values cleanly without trailing zero decimals if integer."""
    if value is None:
        return "0"
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def calculate_progress(goal: Dict[str, Any]) -> float:
    """Calculate progress percentage (0.0 to 100.0+) for a goal."""
    gtype = str(goal.get("goal_type") or "scale").strip().lower()

    if gtype == "boolean":
        val = goal.get("current_value")
        b = normalize_bool_flag(val)
        if b is True:
            return 100.0
        parsed_f = parse_float(val)
        if parsed_f is not None and parsed_f >= 1.0:
            return 100.0
        if isinstance(val, str) and val.strip().lower() in ("done", "completed", "achieved"):
            return 100.0
        return 0.0

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
    if max_val is not None and max_val > 0 and curr > max_val:
        prog = min(prog, (max_val / target) * 100.0 if target > 0 else prog)

    return prog


def is_goal_completed_or_inactive(goal: Dict[str, Any], progress: float) -> Tuple[bool, bool]:
    """Determine whether a goal is considered finished (completed or inactive).

    Returns:
        (is_finished, is_achieved)
    """
    raw_status = str(goal.get("status") or "").strip().lower()
    is_active = normalize_bool_flag(goal.get("is_active"))

    if raw_status in ACHIEVED_STATUSES:
        return True, True

    if is_active is False or raw_status in INACTIVE_STATUSES:
        return True, False

    if progress >= 100.0:
        return True, True

    return False, False


def goal_to_task_line(goal: Dict[str, Any], zone: timezone, default_priority: str = "B") -> str:
    """Format an individual goal dictionary into a valid todo.txt line."""
    progress = calculate_progress(goal)
    is_finished, is_achieved = is_goal_completed_or_inactive(goal, progress)

    parts: List[str] = []
    created_dt = local_date(goal.get("created_at"), zone)
    created_str = created_dt.strftime("%Y-%m-%d") if created_dt else None

    if is_finished:
        parts.append("x")
        updated_dt = (
            local_date(goal.get("completed_at"), zone)
            or local_date(goal.get("updated_at"), zone)
            or created_dt
        )
        completed_str = updated_dt.strftime("%Y-%m-%d") if updated_dt else None
        if completed_str:
            parts.append(completed_str)
            if created_str:
                parts.append(created_str)
    else:
        pri = default_priority.strip().upper()
        if re.fullmatch(r"[A-Z]", pri):
            parts.append(f"({pri})")
        if created_str:
            parts.append(created_str)

    # Goal title
    parts.append(task_text(goal.get("title")))

    # Project category (+scale, +numeric, +boolean)
    gtype = one_line(goal.get("goal_type") or "scale").lower()
    clean_type = re.sub(r"[^a-zA-Z0-9_-]", "", gtype)
    if clean_type:
        parts.append(f"+{clean_type}")

    # Metrics tags
    curr = parse_float(goal.get("current_value"))
    target = parse_float(goal.get("target_value"))
    parts.append(f"cur:{format_metric_num(curr)}")
    parts.append(f"target:{format_metric_num(target)}")
    parts.append(f"pct:{progress:.0f}%")

    unit = one_line(goal.get("unit"))
    if unit:
        clean_unit = re.sub(r"[^a-zA-Z0-9_-]", "", unit)
        if clean_unit:
            parts.append(f"unit:{clean_unit}")

    gid = one_line(goal.get("id"))
    if gid and " " not in gid:
        parts.append(f"omi:{gid}")

    return " ".join(parts)


def extract_goals(data: Any, source_label: str = "input") -> List[Dict[str, Any]]:
    """Unwrap goal items from bare lists or envelope dictionaries."""
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("goals", "items", "data", "results"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
        else:
            items = [data] if "title" in data or "id" in data else []
    else:
        raise ValueError(f"Expected JSON array or envelope object in {source_label}")

    valid: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        g = dict(item)
        if not g.get("id"):
            title_p = str(g.get("title") or f"unnamed_{idx}")
            created_p = str(g.get("created_at") or "")
            src_bytes = f"{title_p}:{created_p}:{idx}".encode("utf-8")
            g["id"] = f"goal_{hashlib.sha256(src_bytes).hexdigest()[:12]}"
        valid.append(g)

    return valid


def convert(
    source: str | Path,
    destination: str | Path,
    zone: timezone,
    default_priority: str = "B",
    force: bool = False,
) -> Tuple[int, int]:
    """Convert an Omi goal export into a todo.txt file."""
    src_str = str(source)
    if src_str == "-":
        raw_text = sys.stdin.read()
        raw_data = json.loads(raw_text)
        goals = extract_goals(raw_data, "<stdin>")
    else:
        src_path = Path(source)
        if not src_path.is_file():
            raise FileNotFoundError(f"Source file not found: {src_path}")
        raw_data = json.loads(src_path.read_bytes().decode("utf-8-sig"))
        goals = extract_goals(raw_data, str(src_path))

    # Sort: active first (by progress descending), then inactive/completed
    def sort_key(g: Dict[str, Any]) -> Tuple[int, float, str]:
        p = calculate_progress(g)
        is_fin, _ = is_goal_completed_or_inactive(g, p)
        return (1 if is_fin else 0, -p, str(g.get("title") or "").lower())

    goals.sort(key=sort_key)
    lines = [goal_to_task_line(g, zone, default_priority) for g in goals]
    active_count = sum(1 for g in goals if not is_goal_completed_or_inactive(g, calculate_progress(g))[0])

    payload = "".join(line + "\n" for line in lines).encode("utf-8")

    dest_str = str(destination)
    if dest_str == "-":
        sys.stdout.write("".join(line + "\n" for line in lines))
        sys.stdout.flush()
        return len(lines), active_count

    dest_path = Path(destination)
    if dest_path.is_symlink():
        raise ValueError(f"Destination path is a symlink: {dest_path}")

    norm_str = dest_str.replace("\\", "/")
    if ".." in dest_path.parts or ".." in norm_str.split("/"):
        raise ValueError(f"Path traversal sequence '..' is forbidden: {dest_path}")

    resolved_dest = dest_path.resolve()
    if resolved_dest.is_symlink():
        raise ValueError(f"Destination path resolves to a symlink: {dest_path}")

    if resolved_dest.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing {dest_path}. Use -f / --force.")

    resolved_dest.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=resolved_dest.parent, prefix=f".{resolved_dest.name}.tmp_", delete=False
        ) as tf:
            tf.write(payload)
            temp_path = Path(tf.name)
        os.replace(temp_path, resolved_dest)
        temp_path = None
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

    return len(lines), active_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an Omi goal JSON export to standard todo.txt format."
    )
    parser.add_argument(
        "source",
        help="JSON file from 'omi --json goal list' or '-' for stdin",
    )
    parser.add_argument(
        "destination",
        help="Destination todo.txt file or '-' for stdout",
    )
    parser.add_argument(
        "--utc-offset",
        type=parse_offset,
        default=None,
        help="Calendar date timezone offset (e.g. +00:00 or -05:00); default: local time zone",
    )
    parser.add_argument(
        "--priority",
        default="B",
        help="Priority letter for active goals (A-Z, default: B)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists",
    )

    args = parser.parse_args()
    zone = args.utc_offset or datetime.now().astimezone().tzinfo or timezone.utc

    try:
        total, active = convert(
            args.source,
            args.destination,
            zone,
            default_priority=args.priority,
            force=args.force,
        )
        if args.destination != "-":
            print(f"{total} goal(s) written ({active} active)", file=sys.stderr)
    except Exception as exc:
        print(f"todo.txt export failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
