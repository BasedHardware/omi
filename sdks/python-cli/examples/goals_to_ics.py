#!/usr/bin/env python3
"""Convert Omi goals JSON exports into an iCalendar (.ics) file.

Usage:
    python goals_to_ics.py goals.json -o goals.ics
    omi --json goal list | python goals_to_ics.py - -o goals.ics
    python goals_to_ics.py page1.json page2.json -o all_goals.ics

Generates an RFC 5545 compliant iCalendar (.ics) file placing goal target deadlines
and milestone checkpoints on Apple Calendar, Google Calendar, and Outlook.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

EVENT_LENGTH = timedelta(hours=1)
PRODID = "-//Omi//omi-cli goals_to_ics//EN"


def ics_text(value: Any) -> str:
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def ics_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime, or None if invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def stamp(dt: datetime) -> str:
    """Format a datetime into an iCalendar UTC timestamp 'YYYYMMDDTHHMMSSZ'."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold(line: str) -> List[str]:
    """Fold a content line at 75 octets (RFC 5545 §3.1), never splitting a UTF-8 character."""
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


def extract_goals(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of goal dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("goals", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped goals object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each goal must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: goal missing required 'id' field")
        results.append(item)

    return results


def goal_to_event(goal: Dict[str, Any], now_utc: datetime) -> Optional[List[str]]:
    """Convert a single goal item to an iCalendar VEVENT block."""
    target_dt = (
        ics_datetime(goal.get("target_date"))
        or ics_datetime(goal.get("due_at"))
        or ics_datetime(goal.get("target_at"))
        or ics_datetime(goal.get("created_at"))
    )
    if not target_dt:
        return None

    goal_id = str(goal.get("id"))
    uid = f"{goal_id}@omi-goal"

    title = goal.get("title") or goal.get("name") or goal.get("description") or "Goal Target"
    summary = ics_text(f"Target: {title}")

    goal_type = goal.get("goal_type") or "goal"
    curr = goal.get("current_value")
    target = goal.get("target_value")
    unit = goal.get("unit") or ""
    is_active = goal.get("is_active") in (True, 1, "true", "1", "yes", "active")

    status = "NEEDS-ACTION"
    if curr is not None and target is not None:
        try:
            if float(target) > 0 and float(curr) >= float(target):
                status = "COMPLETED"
        except (ValueError, TypeError):
            pass

    desc_parts = [
        f"Goal: {title}",
        f"Type: {goal_type}",
    ]
    if curr is not None or target is not None:
        u_disp = f" {unit}" if unit else ""
        desc_parts.append(f"Progress: {curr} / {target}{u_disp}")
    desc_parts.append(f"Status: {'Active' if is_active else 'Inactive'}")

    description = ics_text("\n".join(desc_parts))
    end_dt = target_dt + EVENT_LENGTH
    created_dt = ics_datetime(goal.get("created_at")) or target_dt

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp(now_utc)}",
        f"DTSTART:{stamp(target_dt)}",
        f"DTEND:{stamp(end_dt)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"CATEGORIES:GOAL,{ics_text(goal_type)}",
        f"STATUS:{status}",
        f"CREATED:{stamp(created_dt)}",
        "END:VEVENT",
    ]
    return lines


def generate_ics(goals: Sequence[Dict[str, Any]]) -> Tuple[str, int, int]:
    """Generate RFC 5545 iCalendar text from a sequence of goals."""
    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for g in goals:
        gid = str(g.get("id"))
        if gid not in seen_ids:
            seen_ids.add(gid)
            deduped.append(g)

    now_utc = datetime.now(timezone.utc)
    raw_lines: List[str] = [
        "BEGIN:VCALENDAR",
        f"PRODID:{PRODID}",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    event_count = 0
    skipped_count = 0

    for g in deduped:
        ev_lines = goal_to_event(g, now_utc)
        if ev_lines:
            raw_lines.extend(ev_lines)
            event_count += 1
        else:
            skipped_count += 1

    raw_lines.append("END:VCALENDAR")

    folded_lines: List[str] = []
    for line in raw_lines:
        folded_lines.extend(fold(line))

    ics_text_content = "\r\n".join(folded_lines) + "\r\n"
    return ics_text_content, event_count, skipped_count


def convert_paths_to_ics(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
) -> Tuple[int, int]:
    """Convert goal JSON exports into an iCalendar file."""
    all_goals: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_goals.extend(extract_goals(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_goals.extend(extract_goals(content, str(p)))

    ics_content, event_count, skipped_count = generate_ics(all_goals)

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(ics_content.encode("utf-8"))
    else:
        sys.stdout.write(ics_content)

    return event_count, skipped_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports into an iCalendar (.ics) file."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input JSON files or '-' for standard input",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination .ics file (defaults to stdout)",
    )
    args = parser.parse_args()

    try:
        events, skipped = convert_paths_to_ics(args.inputs, args.output)
        if args.output != "-":
            print(
                f"Exported {events} goal event(s) to {args.output} ({skipped} skipped without target date)",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
