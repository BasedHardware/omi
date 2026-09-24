#!/usr/bin/env python3
"""Convert Omi action items into RFC 5545 VTODO iCalendar task feeds.

Usage:
    python action_items_to_vtodo.py action_items.json -o tasks.ics
    omi --json action-item list | python action_items_to_vtodo.py - -o ~/Library/Reminders.ics
    python action_items_to_vtodo.py tasks.json -o pending.ics --status open

Outputs standard iCalendar files populated with VTODO components, natively
imported by Apple Reminders, Things 3, OmniFocus, Thunderbird Tasks, and CalDAV task managers.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def ical_escape(text: str) -> str:
    """Escape text according to RFC 5545 rules."""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return text


def parse_boolean(value: Any) -> bool:
    """Normalize completion status to a strict boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "completed", "done")
    return False


def format_ical_dt(iso_str: Optional[str]) -> Optional[str]:
    """Convert ISO-8601 string to UTC iCalendar format 'YYYYMMDDTHHMMSSZ'."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        clean = re.sub(r"[^\d]", "", iso_str)
        if len(clean) >= 8:
            return f"{clean[:8]}T000000Z"
        return None


def extract_action_items(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of action item dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("action_items", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped action_items object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each action item must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: action item missing required 'id' field")
        results.append(item)

    return results


def render_vtodo_calendar(
    items: List[Dict[str, Any]],
    status_filter: str = "all",
    cal_name: str = "Omi Action Items",
) -> str:
    """Generate RFC 5545 VCALENDAR containing VTODO task components."""
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Omi//Omi CLI VTODO Exporter//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{ical_escape(cal_name)}",
    ]

    seen_ids = set()
    for item in items:
        iid = str(item.get("id"))
        if iid in seen_ids:
            continue
        seen_ids.add(iid)

        completed = parse_boolean(item.get("completed"))
        if status_filter == "open" and completed:
            continue
        if status_filter == "completed" and not completed:
            continue

        desc = str(item.get("description") or item.get("title") or "Action Item").strip()
        due_dt = format_ical_dt(item.get("due_at"))
        created_dt = format_ical_dt(item.get("created_at")) or now_stamp
        updated_dt = format_ical_dt(item.get("updated_at")) or now_stamp

        lines.extend([
            "BEGIN:VTODO",
            f"UID:{iid}@omi.me",
            f"DTSTAMP:{now_stamp}",
            f"CREATED:{created_dt}",
            f"LAST-MODIFIED:{updated_dt}",
            f"SUMMARY:{ical_escape(desc)}",
        ])

        if due_dt:
            lines.append(f"DUE:{due_dt}")

        if completed:
            lines.extend([
                "STATUS:COMPLETED",
                "PERCENT-COMPLETE:100",
                f"COMPLETED:{updated_dt}",
            ])
        else:
            lines.extend([
                "STATUS:NEEDS-ACTION",
                "PERCENT-COMPLETE:0",
            ])

        if item.get("conversation_id"):
            lines.append(f"DESCRIPTION:Linked conversation: {ical_escape(str(item['conversation_id']))}")

        lines.append("END:VTODO")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def convert_to_vtodo(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    status_filter: str = "all",
    cal_name: str = "Omi Action Items",
) -> int:
    """Convert action items to VTODO iCalendar format."""
    all_items: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_items.extend(extract_action_items(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_items.extend(extract_action_items(content, str(p)))

    ical_text = render_vtodo_calendar(all_items, status_filter=status_filter, cal_name=cal_name)

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(ical_text.encode("utf-8"))
    else:
        sys.stdout.write(ical_text)

    return len(all_items)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items into RFC 5545 VTODO iCalendar task feeds."
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
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter action items by status (default: all)",
    )
    parser.add_argument(
        "--name",
        default="Omi Action Items",
        help="Calendar list name (default: Omi Action Items)",
    )
    args = parser.parse_args()

    try:
        count = convert_to_vtodo(args.inputs, args.output, status_filter=args.status, cal_name=args.name)
        if args.output != "-":
            print(f"Exported {count} action item(s) to VTODO calendar at {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
