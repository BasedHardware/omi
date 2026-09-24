#!/usr/bin/env python3
"""Convert Omi goals JSON export into an RFC 5545 VTODO task feed (.ics).

Usage:
    python goals_to_vtodo.py goals.json -o goals_tasks.ics
    omi --json goal list | python goals_to_vtodo.py - -o milestones.ics

Converts goals into standard VTODO components for CalDAV task managers,
Apple Reminders, OmniFocus, and Things 3. Tracks progress percentages,
completion statuses, and target due dates.
Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


def extract_goals(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON and extract list of goal items."""
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

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        gid = str(item.get("id") or "").strip()
        if title and gid:
            results.append(item)

    return results


def escape_ics(text: str) -> str:
    """Escape text for RFC 5545 text value grammar."""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return text


def format_dt(iso_str: str | None) -> str | None:
    """Format ISO timestamp into RFC 5545 UTC timestamp (YYYYMMDDTHHMMSSZ)."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return None


def generate_vcalendar(goals: List[Dict[str, Any]], cal_name: str = "Omi Goals & Milestones") -> str:
    """Generate VCALENDAR string with VTODO components."""
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Omi//Goal VTODO Exporter//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{escape_ics(cal_name)}",
    ]

    for goal in goals:
        gid = str(goal.get("id"))
        title = str(goal.get("title") or goal.get("name") or f"Goal {gid}").strip()
        desc = str(goal.get("description") or "").strip()

        # Progress & Status
        progress = int(goal.get("progress") or 0)
        progress = max(0, min(100, progress))
        completed = goal.get("completed") is True or progress >= 100

        if completed:
            status = "COMPLETED"
            progress = 100
        elif progress > 0:
            status = "IN-PROCESS"
        else:
            status = "NEEDS-ACTION"

        due_stamp = format_dt(goal.get("target_date") or goal.get("due_date"))

        lines.append("BEGIN:VTODO")
        lines.append(f"UID:goal-{gid}@omi.me")
        lines.append(f"DTSTAMP:{now_stamp}")
        lines.append(f"SUMMARY:{escape_ics(title)}")
        if desc:
            lines.append(f"DESCRIPTION:{escape_ics(desc)}")
        lines.append(f"PERCENT-COMPLETE:{progress}")
        lines.append(f"STATUS:{status}")
        if due_stamp:
            lines.append(f"DUE:{due_stamp}")
        if completed:
            lines.append(f"COMPLETED:{now_stamp}")
        lines.append("END:VTODO")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON export into an RFC 5545 VTODO task feed (.ics)."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination .ics file (defaults to stdout)",
    )
    parser.add_argument(
        "--cal-name",
        default="Omi Goals & Milestones",
        help="Custom calendar name header",
    )
    args = parser.parse_args()

    if not args.inputs:
        parser.print_help()
        sys.exit(1)

    all_goals: List[Dict[str, Any]] = []
    for src in args.inputs:
        if str(src) == "-":
            content = sys.stdin.read()
            all_goals.extend(extract_goals(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_goals.extend(extract_goals(content, str(p)))

    ics_output = generate_vcalendar(all_goals, args.cal_name)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(ics_output, encoding="utf-8")
        print(f"Generated VTODO task feed with {len(all_goals)} goal(s) at {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(ics_output)


if __name__ == "__main__":
    main()
