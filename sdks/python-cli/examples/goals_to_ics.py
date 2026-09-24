#!/usr/bin/env python3
"""
Convert Omi goal-list JSON exports to an iCalendar (.ics) file.

Exports personal goals, milestones, and OKRs into standard RFC 5545 iCalendar
format for Apple Reminders/Calendar, Google Calendar, Microsoft Outlook, and
Thunderbird.

Supports RFC 5545 VTODO components with PERCENT-COMPLETE (0-100%), target
milestone deadlines, and status mappings.

Usage:
    # From saved JSON exports
    python goals_to_ics.py goals.json goals.ics

    # From stdin pipeline
    omi --json goal list --limit 200 | python goals_to_ics.py - goals.ics

    # Export as milestone calendar events (VEVENT)
    python goals_to_ics.py goals.json goals.ics --format event
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def ics_text(value: Any) -> str:
    """Escape text for an iCalendar property value (RFC 5545 Section 3.3.11)."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    else:
        value = str(value)
    # RFC 5545 escaping: backslash, semicolon, comma, newlines
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def ics_datetime(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def stamp(dt: datetime) -> str:
    """Format UTC datetime as RFC 5545 date-time stamp (YYYYMMDDTHHMMSSZ)."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold(line: str) -> List[str]:
    """Fold a content line at 75 octets (RFC 5545 Section 3.1), never splitting UTF-8 characters."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    parts: List[str] = []
    chunk = b""
    limit = 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > limit:
            parts.append(chunk.decode("utf-8"))
            chunk = b" " + b
            limit = 75
        else:
            chunk += b
    if chunk:
        parts.append(chunk.decode("utf-8"))
    return parts


def compute_progress(item: Dict[str, Any], is_active: bool) -> Tuple[Optional[int], str]:
    """Compute progress percentage (0-100 integer) and metric description label."""
    if not is_active:
        return 100, "100% (Completed)"

    goal_type = str(item.get("goal_type") or item.get("type") or "qualitative").lower()
    unit = str(item.get("unit") or "").strip()
    unit_str = f" {unit}" if unit else ""

    if goal_type == "qualitative":
        return None, "Qualitative"

    if goal_type == "boolean":
        cur = float(item.get("current_value") or 0.0)
        target = float(item.get("target_value") or 1.0)
        return (100, "100%") if cur >= target else (0, "0%")

    target = item.get("target_value")
    if target is None:
        target = item.get("max_value")

    if target is not None:
        try:
            target_f = float(target)
            cur_f = float(item.get("current_value") or 0.0)
            min_f = float(item.get("min_value") or 0.0)
            if target_f == min_f:
                return 100, f"{cur_f:g}/{target_f:g}{unit_str}"
            pct = ((cur_f - min_f) / (target_f - min_f)) * 100.0
            pct_int = int(max(0, min(100, round(pct))))
            return pct_int, f"{pct_int}% ({cur_f:g}/{target_f:g}{unit_str})"
        except (ValueError, TypeError, ZeroDivisionError):
            return None, "Metric"

    return None, "Active"


def load(sources: List[str]) -> Dict[str, Dict[str, Any]]:
    """Load goal objects from one or more JSON files or stdin ('-'). Deduplicates by ID."""
    goals: Dict[str, Dict[str, Any]] = {}
    for src in sources:
        if src == "-":
            raw = sys.stdin.read()
            display_name = "<stdin>"
        else:
            p = Path(src)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {src}")
            raw = p.read_bytes().decode("utf-8-sig")
            display_name = src

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{display_name}: invalid JSON ({exc})") from exc

        if isinstance(parsed, dict):
            items = (
                parsed.get("goals")
                or parsed.get("items")
                or parsed.get("data")
                or [parsed]
            )
        else:
            items = parsed

        if not isinstance(items, list):
            raise ValueError(f"{display_name}: expected a JSON array of goals from 'omi --json goal list'")

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{display_name}[{idx}]: each goal must be a JSON object")
            item_id = item.get("id")
            if not item_id or not isinstance(item_id, str):
                raise ValueError(f"{display_name}[{idx}]: missing or invalid string 'id'")
            goals[str(item_id).strip()] = item

    return goals


def generate_ics(
    goals: Dict[str, Dict[str, Any]],
    component_format: str = "todo",
    calendar_name: str = "Omi Goals",
    now_dt: Optional[datetime] = None,
) -> str:
    """Compile goals dictionary into an RFC 5545 iCalendar string."""
    now = now_dt or datetime.now(timezone.utc)
    now_str = stamp(now)

    lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//omi-cli examples//goals_to_ics//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_text(calendar_name)}",
    ]

    for gid, item in goals.items():
        title = str(item.get("title") or item.get("text") or item.get("description") or "(untitled goal)").strip()
        status_raw = str(item.get("status") or "").strip().lower()
        is_active = item.get("is_active")
        if is_active is not None:
            active_flag = bool(is_active)
        else:
            active_flag = status_raw not in ("completed", "archived", "done")

        progress_pct, metric_label = compute_progress(item, active_flag)
        created_dt = ics_datetime(item.get("created_at")) or now
        updated_dt = ics_datetime(item.get("updated_at")) or created_dt

        # Check target date / deadline
        due_dt = (
            ics_datetime(item.get("target_date"))
            or ics_datetime(item.get("due_at"))
            or ics_datetime(item.get("deadline"))
        )

        goal_type = str(item.get("goal_type") or item.get("type") or "qualitative")
        desc_parts = [
            f"Type: {goal_type.capitalize()}",
            f"Progress: {metric_label}",
            f"Status: {'Active' if active_flag else 'Completed'}",
            f"Goal ID: {gid}",
        ]
        desc_text = "\\n".join(desc_parts)

        # 1. Output VTODO (standard Task / Goal item)
        if component_format in ("todo", "both"):
            lines.extend([
                "BEGIN:VTODO",
                f"UID:goal-{gid}@omi",
                f"DTSTAMP:{now_str}",
                f"CREATED:{stamp(created_dt)}",
                f"LAST-MODIFIED:{stamp(updated_dt)}",
                f"SUMMARY:{ics_text(title)}",
                f"DESCRIPTION:{desc_text}",
                f"STATUS:{'NEEDS-ACTION' if active_flag else 'COMPLETED'}",
            ])
            if progress_pct is not None:
                lines.append(f"PERCENT-COMPLETE:{progress_pct}")
            if not active_flag:
                lines.append(f"COMPLETED:{stamp(updated_dt)}")
            if due_dt:
                lines.append(f"DUE:{stamp(due_dt)}")
                # Alarm 1 day before due date
                lines.extend([
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:Goal milestone due: {ics_text(title)}",
                    "TRIGGER:-P1D",
                    "END:VALARM",
                ])
            lines.append("END:VTODO")

        # 2. Output VEVENT (Milestone calendar event)
        if component_format in ("event", "both"):
            event_dt = due_dt or created_dt
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:goal-event-{gid}@omi",
                f"DTSTAMP:{now_str}",
                f"CREATED:{stamp(created_dt)}",
                f"LAST-MODIFIED:{stamp(updated_dt)}",
                f"DTSTART:{stamp(event_dt)}",
                f"DTEND:{stamp(event_dt + timedelta(hours=1))}",
                f"SUMMARY:{ics_text(f'[Goal] {title} ({metric_label})')}",
                f"DESCRIPTION:{desc_text}",
                f"STATUS:{'CONFIRMED' if active_flag else 'CANCELLED'}",
                "END:VEVENT",
            ])

    lines.append("END:VCALENDAR")

    # Line folding at 75 octets
    folded_lines: List[str] = []
    for line in lines:
        folded_lines.extend(fold(line))

    return "\r\n".join(folded_lines) + "\r\n"


def convert(
    sources: List[str],
    destination: str,
    component_format: str = "todo",
    calendar_name: str = "Omi Goals",
    force: bool = False,
) -> None:
    """Load goal sources, convert to iCalendar, and write to destination file."""
    dest_path = Path(destination)
    if dest_path.exists() and not force:
        raise FileExistsError(f"Destination file already exists: {destination}. Use --force to overwrite.")

    goals = load(sources)
    ics_content = generate_ics(
        goals=goals,
        component_format=component_format,
        calendar_name=calendar_name,
    )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(ics_content.encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goal JSON exports to an iCalendar (.ics) file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  omi --json goal list | python goals_to_ics.py - goals.ics
  python goals_to_ics.py goals.json my_goals.ics --calendar-name "My OKRs"
  python goals_to_ics.py g1.json g2.json milestones.ics --format event --force
""",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        metavar="SOURCE",
        help="One or more JSON files exported from 'omi --json goal list', or '-' for stdin.",
    )
    parser.add_argument(
        "destination",
        metavar="DESTINATION",
        help="Path to output .ics file.",
    )
    parser.add_argument(
        "--format",
        choices=["todo", "event", "both"],
        default="todo",
        help="iCalendar component format: 'todo' (VTODO, default), 'event' (VEVENT milestones), or 'both'.",
    )
    parser.add_argument(
        "--calendar-name",
        default="Omi Goals",
        help="Custom calendar display name (X-WR-CALNAME).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists.",
    )

    args = parser.parse_args()

    try:
        convert(
            sources=args.sources,
            destination=args.destination,
            component_format=args.format,
            calendar_name=args.calendar_name,
            force=args.force,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
