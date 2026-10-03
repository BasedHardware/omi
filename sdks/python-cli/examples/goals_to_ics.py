#!/usr/bin/env python3
"""Convert Omi goal JSON exports into standard RFC 5545 iCalendar (.ics) files.

Features:
- Dual RFC 5545 mode support:
  * VEVENT (default): calendar events for deadlines and target milestones.
  * VTODO: actionable tasks with native PERCENT-COMPLETE and task status.
- Rich event descriptions with progress bars and metric targets.
- Multi-file ingestion with automatic ID deduplication (latest updated_at wins).
- Resilient envelope extraction (raw lists, or wrapped in "goals", "items", "data", "results").
- Strict RFC 5545 text escaping and 75-octet line folding.
- Path traversal protection and atomic non-destructive writes (-f/--force).
- Zero third-party dependencies: strictly Python standard library.

Usage:
    # Export to iCalendar events (Google Calendar, Outlook, Apple Calendar)
    omi --json goal list | python goals_to_ics.py - -o goals.ics

    # Export to VTODO tasks (Apple Reminders, Thunderbird Tasks, OmniFocus)
    python goals_to_ics.py goals.json --mode vtodo -o goals_tasks.ics --force

    # Filter active goals and specify custom calendar title
    python goals_to_ics.py goals.json --status active --name "My Personal Milestones"
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple


PRODID = "-//Omi Community//Omi Goals Exporter 1.0//EN"
DEFAULT_EVENT_DURATION = timedelta(minutes=30)
ACHIEVED_STATUSES = {"completed", "achieved", "done"}
INACTIVE_STATUSES = {"inactive", "archived", "cancelled", "canceled", "abandoned"}


def ics_escape(value: Any) -> str:
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11).

    Coerces arbitrary types and escapes backslashes, semicolons, commas, and line breaks.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        else:
            value = str(value)

    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def ics_datetime(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string into an aware UTC datetime, or None if invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    clean_val = value.strip().replace("Z", "+00:00")
    if len(clean_val) == 10 and clean_val.count("-") == 2:
        clean_val += "T00:00:00+00:00"
    try:
        dt = datetime.fromisoformat(clean_val)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def stamp_utc(dt: datetime) -> str:
    """Format an aware datetime as an RFC 5545 UTC timestamp (YYYYMMDDTHHMMSSZ)."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold_line(line: str, max_octets: int = 75) -> List[str]:
    """Fold an iCalendar content line at max_octets according to RFC 5545 §3.1.

    Continuation lines are prefixed by a single ASCII space.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= max_octets:
        return [line]

    result: List[str] = []
    chunk: List[bytes] = []
    current_len = 0
    is_first_line = True

    for char in line:
        char_bytes = char.encode("utf-8")
        limit = max_octets if is_first_line else (max_octets - 1)

        if current_len + len(char_bytes) > limit and chunk:
            folded_str = b"".join(chunk).decode("utf-8")
            if not is_first_line:
                folded_str = " " + folded_str
            result.append(folded_str)
            chunk = [char_bytes]
            current_len = len(char_bytes)
            is_first_line = False
        else:
            chunk.append(char_bytes)
            current_len += len(char_bytes)

    if chunk:
        folded_str = b"".join(chunk).decode("utf-8")
        if not is_first_line:
            folded_str = " " + folded_str
        result.append(folded_str)

    return result


def calculate_progress(goal: Dict[str, Any]) -> float:
    """Calculate progress percentage (0.0 to 100.0+) for a goal."""
    gtype = str(goal.get("goal_type") or "scale").strip().lower()

    if gtype == "boolean":
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

    if target > min_val:
        span = target - min_val
        return max(0.0, (curr - min_val) / span * 100.0)

    if target > 0:
        return max(0.0, (curr / target) * 100.0)

    if curr > 0 and target == 0:
        return 100.0

    return 0.0


def determine_status(goal: Dict[str, Any], progress: float) -> Tuple[str, str]:
    """Determine category ('achieved', 'active', 'inactive') and display status."""
    raw_status = str(goal.get("status") or "").strip().lower()
    is_active = goal.get("is_active")

    if raw_status in ACHIEVED_STATUSES or progress >= 100.0:
        return "achieved", "Completed"

    if is_active is False or raw_status in INACTIVE_STATUSES:
        return "inactive", "Inactive"

    return "active", "In-Process"


def render_progress_bar(progress: float, width: int = 10) -> str:
    """Render a compact ASCII progress bar."""
    if not math.isfinite(progress):
        progress = 0.0
    clamped = max(0.0, min(100.0, progress))
    filled_len = int(round((clamped / 100.0) * width))
    empty_len = width - filled_len
    bar = "=" * filled_len + "." * empty_len
    return f"[{bar}] {progress:.1f}%"


def build_description(goal: Dict[str, Any], progress: float, status_label: str) -> str:
    """Construct a clean, multi-line progress description for the calendar entry."""
    gtype = str(goal.get("goal_type") or "scale")
    unit = str(goal.get("unit") or "").strip()
    curr = goal.get("current_value", 0)
    target = goal.get("target_value", 0)

    lines: List[str] = [
        f"Goal: {goal.get('title') or 'Untitled Goal'}",
        f"Type: {gtype}",
        f"Status: {status_label}",
        f"Target: {curr} / {target}{(' ' + unit) if unit else ''}",
        f"Progress: {render_progress_bar(progress, 10)}",
    ]

    created = ics_datetime(goal.get("created_at"))
    if created:
        lines.append(f"Created: {created.strftime('%Y-%m-%d %H:%M UTC')}")

    updated = ics_datetime(goal.get("updated_at"))
    if updated:
        lines.append(f"Last Updated: {updated.strftime('%Y-%m-%d %H:%M UTC')}")

    return "\n".join(lines)


def goal_to_vevent(goal: Dict[str, Any], now_utc: datetime) -> Optional[List[str]]:
    """Convert a goal record into RFC 5545 VEVENT property lines."""
    gid = str(goal.get("id") or "").strip()
    title = str(goal.get("title") or "Untitled Goal").strip()
    gtype = str(goal.get("goal_type") or "scale").strip()

    if not gid:
        gid = hashlib.sha256(f"{title}:{goal.get('created_at')}".encode("utf-8")).hexdigest()[:12]

    prog = calculate_progress(goal)
    cat, status_label = determine_status(goal, prog)

    # Determine event time: target_date / deadline, or fallback to updated_at/created_at
    target_dt = ics_datetime(goal.get("target_date")) or ics_datetime(goal.get("deadline"))
    created_dt = ics_datetime(goal.get("created_at")) or now_utc

    if not target_dt:
        target_dt = ics_datetime(goal.get("updated_at")) or created_dt

    end_dt = target_dt + DEFAULT_EVENT_DURATION

    # RFC 5545 VEVENT status: NEEDS-ACTION, COMPLETED, CANCELLED, or CONFIRMED
    if cat == "achieved":
        vevent_status = "COMPLETED"
    elif cat == "inactive":
        vevent_status = "CANCELLED"
    else:
        vevent_status = "CONFIRMED"

    uid = f"omi-goal-{gid}@basedhardware.com"
    summary_text = f"Goal: {title}"
    if cat == "achieved":
        summary_text = f"✅ [Done] {title}"

    desc = build_description(goal, prog, status_label)

    return [
        "BEGIN:VEVENT",
        f"UID:{ics_escape(uid)}",
        f"DTSTAMP:{stamp_utc(now_utc)}",
        f"DTSTART:{stamp_utc(target_dt)}",
        f"DTEND:{stamp_utc(end_dt)}",
        f"SUMMARY:{ics_escape(summary_text)}",
        f"DESCRIPTION:{ics_escape(desc)}",
        f"CATEGORIES:GOAL,{ics_escape(gtype).upper()}",
        f"STATUS:{vevent_status}",
        f"CREATED:{stamp_utc(created_dt)}",
        "END:VEVENT",
    ]


def goal_to_vtodo(goal: Dict[str, Any], now_utc: datetime) -> List[str]:
    """Convert a goal record into RFC 5545 VTODO property lines."""
    gid = str(goal.get("id") or "").strip()
    title = str(goal.get("title") or "Untitled Goal").strip()
    gtype = str(goal.get("goal_type") or "scale").strip()

    if not gid:
        gid = hashlib.sha256(f"{title}:{goal.get('created_at')}".encode("utf-8")).hexdigest()[:12]

    prog = calculate_progress(goal)
    cat, status_label = determine_status(goal, prog)

    created_dt = ics_datetime(goal.get("created_at")) or now_utc
    target_dt = ics_datetime(goal.get("target_date")) or ics_datetime(goal.get("deadline"))

    uid = f"omi-goal-{gid}@basedhardware.com"
    desc = build_description(goal, prog, status_label)

    prog_safe = prog if math.isfinite(prog) else 0.0
    pct_int = max(0, min(100, int(round(prog_safe))))

    lines = [
        "BEGIN:VTODO",
        f"UID:{ics_escape(uid)}",
        f"DTSTAMP:{stamp_utc(now_utc)}",
        f"SUMMARY:{ics_escape(title)}",
        f"DESCRIPTION:{ics_escape(desc)}",
        f"CATEGORIES:GOAL,{ics_escape(gtype).upper()}",
        f"PERCENT-COMPLETE:{pct_int}",
        f"CREATED:{stamp_utc(created_dt)}",
    ]

    if target_dt:
        lines.append(f"DUE:{stamp_utc(target_dt)}")

    if cat == "achieved":
        lines.append("STATUS:COMPLETED")
        completed_dt = ics_datetime(goal.get("updated_at")) or now_utc
        lines.append(f"COMPLETED:{stamp_utc(completed_dt)}")
    elif cat == "inactive":
        lines.append("STATUS:CANCELLED")
    else:
        lines.append("STATUS:IN-PROCESS")

    lines.append("END:VTODO")
    return lines


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
            title_part = str(goal.get("title") or f"unnamed_{idx}")
            created_part = str(goal.get("created_at") or "")
            digest_src = f"{title_part}:{created_part}:{idx}".encode("utf-8")
            goal["id"] = f"goal_{hashlib.sha256(digest_src).hexdigest()[:12]}"

        valid_goals.append(goal)

    return valid_goals


def load_and_deduplicate(sources: Sequence[str | Path]) -> List[Dict[str, Any]]:
    """Load goals from one or more file paths or '-' (stdin) and deduplicate by ID."""
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
            ts = ics_datetime(goal.get("updated_at")) or ics_datetime(goal.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)

            if gid not in goals_by_id:
                goals_by_id[gid] = goal
                timestamps[gid] = ts
            else:
                if ts >= timestamps[gid]:
                    goals_by_id[gid] = goal
                    timestamps[gid] = ts

    return list(goals_by_id.values())


def generate_ics_content(
    goals: Sequence[Dict[str, Any]],
    mode: str = "vevent",
    calendar_name: str = "Omi Goals",
    filter_status: str = "all",
    filter_type: str = "all",
) -> Tuple[str, int]:
    """Generate complete RFC 5545 iCalendar stream from goal records."""
    now_utc = datetime.now(timezone.utc)

    raw_lines: List[str] = [
        "BEGIN:VCALENDAR",
        f"PRODID:{PRODID}",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calendar_name)}",
    ]

    item_count = 0

    for goal in goals:
        gtype = str(goal.get("goal_type") or "scale").strip().lower()
        prog = calculate_progress(goal)
        cat, _ = determine_status(goal, prog)

        if filter_type != "all" and gtype != filter_type.lower():
            continue
        if filter_status != "all" and cat != filter_status.lower():
            continue

        if mode.lower() == "vtodo":
            comp_lines = goal_to_vtodo(goal, now_utc)
        else:
            comp_lines = goal_to_vevent(goal, now_utc)

        if comp_lines:
            raw_lines.extend(comp_lines)
            item_count += 1

    raw_lines.append("END:VCALENDAR")

    folded_lines: List[str] = []
    for line in raw_lines:
        folded_lines.extend(fold_line(line))

    # Strict RFC 5545 CRLF output
    ics_text = "\r\n".join(folded_lines) + "\r\n"
    return ics_text, item_count


def write_ics(content: str, dest_path: str | Path, force: bool = False) -> None:
    """Safely write iCalendar content with atomic replacement and security checks."""
    dest = Path(dest_path).resolve()

    orig_str = str(dest_path)
    norm_str = orig_str.replace("\\", "/")
    if ".." in Path(dest_path).parts or ".." in norm_str.split("/"):
        raise ValueError(f"Path traversal sequence '..' is forbidden: {dest_path}")

    if dest.exists() and not force:
        raise FileExistsError(
            f"Destination file '{dest}' already exists. Use -f / --force to overwrite."
        )

    dest.parent.mkdir(parents=True, exist_ok=True)

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
        description="Convert Omi goal JSON exports into standard RFC 5545 iCalendar (.ics) files."
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
        help="Destination .ics file path (defaults to stdout '-')",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force overwrite existing destination file",
    )
    parser.add_argument(
        "--mode",
        choices=["vevent", "vtodo"],
        default="vevent",
        help="iCalendar component mode: 'vevent' (calendar events) or 'vtodo' (actionable tasks)",
    )
    parser.add_argument(
        "--name",
        default="Omi Goals",
        help="Custom calendar display name (X-WR-CALNAME)",
    )
    parser.add_argument(
        "--status",
        choices=["all", "active", "achieved", "inactive"],
        default="all",
        help="Filter goals by status category (default: all)",
    )
    parser.add_argument(
        "--type",
        default="all",
        help="Filter goals by goal_type (e.g. scale, numeric, boolean, or 'all')",
    )

    args = parser.parse_args()

    try:
        goals = load_and_deduplicate(args.sources)
        ics_text, count = generate_ics_content(
            goals,
            mode=args.mode,
            calendar_name=args.name,
            filter_status=args.status,
            filter_type=args.type,
        )

        if args.output == "-":
            sys.stdout.write(ics_text)
        else:
            write_ics(ics_text, args.output, force=args.force)
            mode_desc = "event(s)" if args.mode == "vevent" else "task(s)"
            print(f"Exported {count} goal {mode_desc} to {args.output}", file=sys.stderr)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
